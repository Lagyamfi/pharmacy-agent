"""Unit tests for extract_prescription() in app.py."""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# stubs already in conftest.py for chainlit/fpdf
sys.modules.setdefault("agents", MagicMock())

import google as _g; _g.genai = MagicMock(); sys.modules["google.genai"] = _g.genai

from app import extract_prescription

# ── helpers ──────────────────────────────────────────────────────────────────

def _gemini_response(text):
    m = MagicMock()
    m.text = text
    return m

# ── tests ─────────────────────────────────────────────────────────────────────

async def test_extract_clean_json(tmp_path):
    fake_file = tmp_path / "rx.jpg"
    fake_file.write_bytes(b"fake-image-data")
    payload = json.dumps({"medications": [{"name": "ibuprofen", "dosage": "400mg", "quantity": 30}]})
    with patch("app.gemini_client") as mock_client:
        mock_client.aio.models.generate_content = AsyncMock(return_value=_gemini_response(payload))
        result = await extract_prescription(str(fake_file), "image/jpeg")
    assert result == [{"name": "ibuprofen", "dosage": "400mg", "quantity": 30}]

async def test_extract_strips_markdown_fences(tmp_path):
    fake_file = tmp_path / "rx.png"
    fake_file.write_bytes(b"fake")
    payload = "```json\n" + json.dumps({"medications": [{"name": "aspirin", "dosage": "100mg", "quantity": 50}]}) + "\n```"
    with patch("app.gemini_client") as mock_client:
        mock_client.aio.models.generate_content = AsyncMock(return_value=_gemini_response(payload))
        result = await extract_prescription(str(fake_file), "image/png")
    assert result[0]["name"] == "aspirin"

async def test_extract_empty_when_no_prescription(tmp_path):
    fake_file = tmp_path / "rx.pdf"
    fake_file.write_bytes(b"fake")
    with patch("app.gemini_client") as mock_client:
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_gemini_response('{"medications": []}')
        )
        result = await extract_prescription(str(fake_file), "application/pdf")
    assert result == []

async def test_extract_returns_empty_on_bad_json(tmp_path):
    fake_file = tmp_path / "rx.jpg"
    fake_file.write_bytes(b"fake")
    with patch("app.gemini_client") as mock_client:
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_gemini_response("not json at all")
        )
        result = await extract_prescription(str(fake_file), "image/jpeg")
    assert result == []
