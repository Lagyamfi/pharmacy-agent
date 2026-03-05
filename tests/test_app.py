"""Unit tests for helper functions in app.py.

Stubs agents (prevents pydantic_ai/google provider import chain) and
patches google.genai so genai.Client() succeeds without an API key.
chainlit and fpdf are already stubbed in conftest.py.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Stub `agents` before app.py is imported so pydantic_ai's Google provider
# import chain is never triggered.
sys.modules["agents"] = MagicMock()

# Inject a mock google.genai onto the real `google` namespace package so
# `from google import genai; genai.Client()` succeeds without an API key.
import google as _google_pkg  # noqa: E402 — must come after agents stub

_mock_genai = MagicMock()
_mock_genai.Client.return_value = MagicMock()
_google_pkg.genai = _mock_genai
sys.modules["google.genai"] = _mock_genai

from app import _extract_cancellation_order_id, text_to_speech  # noqa: E402


# ---------------------------------------------------------------------------
# _extract_cancellation_order_id
# ---------------------------------------------------------------------------

def test_extract_cancellation_positive():
    text = "Order ORD-102 is eligible for cancellation. Would you like to proceed?"
    result = _extract_cancellation_order_id(text)
    assert result == "ORD-102"


def test_extract_cancellation_rejection():
    text = "Order ORD-103 cannot be cancelled because it has already been delivered."
    result = _extract_cancellation_order_id(text)
    assert result is None


def test_extract_cancellation_no_match():
    text = "Your order is being prepared and will ship soon."
    result = _extract_cancellation_order_id(text)
    assert result is None


# ---------------------------------------------------------------------------
# text_to_speech
# ---------------------------------------------------------------------------

def test_text_to_speech_returns_bytes():
    """text_to_speech should return bytes produced by gTTS write_to_fp."""
    fake_audio = b"fake-mp3-audio-data"

    mock_tts_instance = MagicMock()

    def fake_write_to_fp(buf):
        buf.write(fake_audio)

    mock_tts_instance.write_to_fp.side_effect = fake_write_to_fp

    with patch("app.gTTS", return_value=mock_tts_instance):
        result = text_to_speech("Hello, this is a test.")

    assert isinstance(result, bytes)
    assert result == fake_audio
