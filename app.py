"""Pharmacy Support Agent — Chainlit Application.

An AI-powered customer support chatbot for an online pharmacy,
built with pydantic-ai and Chainlit. Features multi-agent routing,
streaming responses, interactive starters, admin SQL analyst mode,
and voice input/output (STT + TTS).
"""

import base64
import io
import json
import os
import re
import sqlite3

import chainlit as cl
from chainlit.input_widget import Select
from dotenv import load_dotenv
from google import genai
from gtts import gTTS

# Import Logfire
import logfire

from tools import PharmacyDeps
from agents import triage_agent, sql_agent

# ─── Environment ────────────────────────────────────────────────────
load_dotenv()

# ─── Observability ──────────────────────────────────────────────────
logfire.configure(send_to_logfire='if-token-present')
logfire.instrument_pydantic_ai()
logfire.instrument_sqlite3()

# ─── Gemini client for STT ──────────────────────────────────────────
gemini_client = genai.Client()


# ─── Database Connection ───────────────────────────────────────────
def get_db_connection() -> sqlite3.Connection:
    """Get or create a SQLite connection for the current session."""
    return sqlite3.connect("pharmacy.db", check_same_thread=False)


# MIME types accepted as prescription uploads
PRESCRIPTION_MIME_TYPES = {
    "image/png", "image/jpeg", "image/webp",
    "image/gif", "application/pdf",
}


# ─── TTS Helper ────────────────────────────────────────────────────
def text_to_speech(text: str) -> bytes:
    """Convert text to MP3 audio bytes using gTTS."""
    # Limit TTS to first 500 chars to keep audio short
    tts_text = text[:500] if len(text) > 500 else text
    tts = gTTS(text=tts_text, lang="en")
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()


async def extract_prescription(file_path: str, mime_type: str) -> list[dict]:
    """Read a prescription image/PDF with Gemini Vision and extract medications.

    Args:
        file_path: Absolute path to the uploaded file (written by Chainlit).
        mime_type: MIME type of the file, e.g. "image/jpeg".

    Returns:
        List of dicts: [{"name": "ibuprofen", "dosage": "400mg", "quantity": 30}, ...]
        Returns an empty list if no prescription is detected.
    """
    with open(file_path, "rb") as f:
        file_b64 = base64.b64encode(f.read()).decode("utf-8")

    response = await gemini_client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            {"inline_data": {"mime_type": mime_type, "data": file_b64}},
            (
                "This is a pharmacy prescription. Extract every medication listed. "
                "Return ONLY valid JSON — no explanation, no markdown fences:\n"
                '{"medications": [{"name": "lowercase_drug_name", '
                '"dosage": "Xmg", "quantity": N}]}\n'
                "If no prescription is visible, return: {\"medications\": []}"
            ),
        ],
    )

    raw = (response.text or "").strip()
    # Strip markdown code fences Gemini sometimes adds
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw).get("medications", [])
    except (json.JSONDecodeError, AttributeError):
        return []


# ─── Persona-Aware Starters ───────────────────────────────────────
CUSTOMER_STARTERS = [
    cl.Starter(
        label="📦 Track my order",
        message="What's the status of order ORD-101?",
    ),
    cl.Starter(
        label="💊 Check stock",
        message="Is ibuprofen available?",
    ),
    cl.Starter(
        label="⚠️ Drug interactions",
        message="Can I take ibuprofen and aspirin together?",
    ),
    cl.Starter(
        label="📋 FDA warnings",
        message="What are the FDA warnings for ibuprofen?",
    ),
    cl.Starter(
        label="💊 Upload prescription",
        message="I'd like to order the medications from my prescription.",
    ),
]

ADMIN_STARTERS = [
    cl.Starter(
        label="📊 Order summary",
        message="How many orders are there for each status?",
    ),
    cl.Starter(
        label="🚫 Out of stock",
        message="Which products are currently out of stock?",
    ),
    cl.Starter(
        label="📦 Shipped orders",
        message="Show me all shipped orders with their items and delivery dates.",
    ),
    cl.Starter(
        label="📈 Inventory overview",
        message="What is the total stock count across all products?",
    ),
]


@cl.set_starters
async def set_starters():
    try:
        persona = cl.user_session.get("persona", "customer")
    except Exception:
        persona = "customer"
    if persona == "admin":
        return ADMIN_STARTERS
    return CUSTOMER_STARTERS


# ─── Core Agent Processing ────────────────────────────────────────
async def process_query(text: str, generate_audio: bool = False) -> str:
    """Run a query through the appropriate agent and return the response.

    This is the shared processing pipeline used by both text and voice input.

    Args:
        text: The user's query text.
        generate_audio: If True, attach TTS audio to the response message.

    Returns:
        The agent's text response.
    """
    message_history = cl.user_session.get("agent_message_history", [])
    db_conn = cl.user_session.get("db_conn")
    deps = PharmacyDeps(db_conn=db_conn)
    persona = cl.user_session.get("persona", "customer")

    # Pick the right agent
    active_agent = sql_agent if persona == "admin" else triage_agent

    # Create an empty message for streaming
    msg = cl.Message(content="")
    await msg.send()

    # Stream the agent response
    async with active_agent.run_stream(
        text,
        deps=deps,
        message_history=message_history or None,
    ) as result:
        async for chunk in result.stream_text(delta=True):
            await msg.stream_token(chunk)

        # Persist updated message history
        cl.user_session.set("agent_message_history", result.all_messages())

    # Check for pending cancellation in the response
    pending_order_id = _extract_cancellation_order_id(msg.content)
    if pending_order_id:
        actions = [
            cl.Action(
                name="confirm_cancel",
                label="✅ Confirm Cancellation",
                payload={"order_id": pending_order_id},
            ),
            cl.Action(
                name="abort_cancel",
                label="❌ Keep Order",
                payload={"order_id": pending_order_id},
            ),
        ]
        msg.actions = actions

    # Attach TTS audio if requested
    if generate_audio and msg.content:
        audio_bytes = text_to_speech(msg.content)
        audio_element = cl.Audio(
            name="response_audio",
            content=audio_bytes,
            mime="audio/mp3",
            auto_play=True,
        )
        msg.elements = [audio_element]

    await msg.update()
    return msg.content


def _extract_cancellation_order_id(text: str) -> str | None:
    """Check if the agent response indicates a cancellation is ready.

    Only triggers for positive eligibility — NOT for rejections like
    'cannot be cancelled' or 'already delivered'.
    """
    lower = text.lower()

    # Reject: the agent is telling the user the order CANNOT be cancelled
    rejection_phrases = [
        "cannot be cancelled",
        "can't be cancelled",
        "already cancelled",
        "already been delivered",
        "has already been delivered",
        "not found",
    ]
    if any(phrase in lower for phrase in rejection_phrases):
        return None

    # Accept: positive cancellation eligibility language
    eligibility_phrases = [
        "eligible for cancellation",
        "would you like to proceed",
        "would you like to confirm",
        "would you like to cancel",
        "ready to cancel",
        "can be cancelled",
        "do you want to cancel",
        "shall i cancel",
        "confirm the cancellation",
    ]
    if any(phrase in lower for phrase in eligibility_phrases):
        match = re.search(r"(ORD-\d+)", text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


# ─── Action Callbacks (HITL) ──────────────────────────────────────
@cl.action_callback("confirm_cancel")
async def on_confirm_cancel(action: cl.Action):
    """Execute the order cancellation after human confirmation."""
    order_id = action.payload.get("order_id")
    db_conn = cl.user_session.get("db_conn")

    try:
        cursor = db_conn.cursor()
        cursor.execute(
            "UPDATE orders SET status = 'Cancelled', expected_delivery = NULL WHERE order_id = ?",
            (order_id,),
        )
        db_conn.commit()

        await cl.Message(
            content=f"✅ **Order {order_id} has been successfully cancelled.**"
        ).send()
    except Exception as e:
        await cl.Message(
            content=f"⚠️ Failed to cancel order {order_id}: {str(e)}"
        ).send()


@cl.action_callback("abort_cancel")
async def on_abort_cancel(action: cl.Action):
    """Abort the cancellation — keep the order active."""
    order_id = action.payload.get("order_id")
    await cl.Message(
        content=f"👍 **Cancellation aborted.** Order {order_id} remains active."
    ).send()


# ─── Chainlit Lifecycle ───────────────────────────────────────────
@cl.on_chat_start
async def on_chat_start():
    """Initialise session state and show the persona selector."""
    cl.user_session.set("agent_message_history", [])
    cl.user_session.set("db_conn", get_db_connection())
    cl.user_session.set("persona", "customer")
    cl.user_session.set("audio_buffer", bytearray())

    # Show persona selector in Chat Settings
    await cl.ChatSettings([
        Select(
            id="Persona",
            label="Mode",
            values=["💊 Customer Support", "🔍 Admin Analyst"],
            initial_index=0,
            description="Switch between customer support and admin SQL analyst mode.",
        ),
    ]).send()


@cl.on_settings_update
async def on_settings_update(settings):
    """Handle persona toggle changes."""
    selection = settings.get("Persona", "💊 Customer Support")

    if "Admin" in selection:
        cl.user_session.set("persona", "admin")
        cl.user_session.set("agent_message_history", [])
        await cl.Message(
            content="🔍 **Switched to Admin Analyst mode.**\n\n"
            "You can now ask analytical questions about the database. "
            "I'll generate and run SQL queries for you.\n\n"
            "*Example: \"How many orders are shipped?\"*"
        ).send()
    else:
        cl.user_session.set("persona", "customer")
        cl.user_session.set("agent_message_history", [])
        await cl.Message(
            content="💊 **Switched to Customer Support mode.**\n\n"
            "Ask about your orders, product availability, or general pharmacy questions."
        ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle text messages and prescription file uploads."""
    # Detect prescription attachments (image or PDF)
    rx_files = [
        elem for elem in (message.elements or [])
        if hasattr(elem, "mime") and elem.mime in PRESCRIPTION_MIME_TYPES
    ]

    if not rx_files:
        await process_query(message.content)
        return

    # ── Prescription upload path ───────────────────────────────────────
    loading = cl.Message(content="📋 Reading your prescription...")
    await loading.send()

    try:
        medications = await extract_prescription(rx_files[0].path, rx_files[0].mime)
    except Exception as e:
        await loading.remove()
        await cl.Message(
            content=f"⚠️ Could not read the prescription: {str(e)}. "
                    "Please try a clearer image or type your medications manually."
        ).send()
        return

    if not medications:
        await loading.remove()
        await cl.Message(
            content="⚠️ I couldn't find any medications in that image. "
                    "Please try a clearer photo or describe what you need."
        ).send()
        return

    # Show a preview of what was extracted
    med_lines = "\n".join(
        f"- **{m['name'].title()}** {m.get('dosage', '')} × {m.get('quantity', 1)}"
        for m in medications
    )
    await loading.remove()
    await cl.Message(
        content=f"📋 Found in your prescription:\n{med_lines}\n\n"
                "Let me check availability and prepare your invoice."
    ).send()

    # Build the agent query from the extracted list
    items_desc = ", ".join(
        f"{m['name']} x{m.get('quantity', 1)}" for m in medications
    )
    agent_query = (
        f"The customer uploaded a prescription. Extracted medications: {items_desc}. "
        f"Customer note: '{message.content or 'Please process my prescription'}'. "
        "Check inventory for each item then, once confirmed, generate the invoice."
    )
    await process_query(agent_query)


# ─── Audio Lifecycle (Voice Mode) ─────────────────────────────────
@cl.on_audio_start
async def on_audio_start():
    """Initialise the audio buffer when recording starts."""
    cl.user_session.set("audio_buffer", bytearray())
    return True  # Enable the audio connection


@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    """Accumulate audio chunks as they stream from the microphone."""
    audio_buffer = cl.user_session.get("audio_buffer")
    if audio_buffer is not None:
        audio_buffer.extend(chunk.data)


@cl.on_audio_end
async def on_audio_end():
    """Process the completed audio recording: transcribe and respond."""
    audio_buffer = cl.user_session.get("audio_buffer")

    if not audio_buffer:
        await cl.Message(content="No audio was captured. Please try again.").send()
        return

    # Transcribe using Gemini (free with GOOGLE_API_KEY)
    try:
        audio_b64 = base64.b64encode(bytes(audio_buffer)).decode("utf-8")

        response = await gemini_client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {
                    "inline_data": {
                        "mime_type": "audio/webm",
                        "data": audio_b64,
                    }
                },
                "Transcribe this audio exactly. Return ONLY the transcription text, nothing else.",
            ],
        )

        transcript_text = response.text.strip() if response.text else ""
        if not transcript_text:
            await cl.Message(content="Could not transcribe audio. Please try again.").send()
            return

        # Display the transcription as a user message
        await cl.Message(content=transcript_text, author="User").send()

        # Process the transcribed text with TTS enabled
        await process_query(transcript_text, generate_audio=True)

    except Exception as e:
        await cl.Message(
            content=f"⚠️ Transcription error: {str(e)}"
        ).send()


@cl.on_chat_end
async def on_chat_end():
    """Clean up resources when the chat ends."""
    db_conn = cl.user_session.get("db_conn")
    if db_conn:
        db_conn.close()