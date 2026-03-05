"""Pytest configuration: stub heavy runtime dependencies before test collection.

Registers MagicMock replacements for modules that require a running Chainlit
server or external binaries so the real source modules (tools.py) can be
imported in unit tests without errors.
"""

import sys
from unittest.mock import MagicMock

# Chainlit — would fail without a running event loop / server
sys.modules.setdefault("chainlit", MagicMock())
sys.modules.setdefault("chainlit.input_widget", MagicMock())

# fpdf2 — optional heavy dep; FPDF class is patched per-test where needed
_fpdf_mod = MagicMock()
_fpdf_mod.FPDF = MagicMock
sys.modules.setdefault("fpdf", _fpdf_mod)
