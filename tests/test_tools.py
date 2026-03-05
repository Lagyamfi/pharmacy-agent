"""Unit tests for tool functions in tools.py.

Uses an in-memory SQLite database seeded inline and unittest.mock to
patch outbound HTTP calls so no real network requests are made.

Heavy runtime dependencies (chainlit, fpdf, etc.) are stubbed in conftest.py
before this module is collected.
"""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from tools import (
    PharmacyDeps,
    check_drug_interactions,
    check_inventory,
    generate_invoice,
    get_fda_warnings,
    get_order_status,
    get_customer_orders,
    get_drugs_by_category,
    prepare_order_cancellation,
    search_inventory,
    suggest_alternatives,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    """In-memory SQLite DB seeded with test data."""
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE orders (
            order_id TEXT PRIMARY KEY,
            customer_name TEXT NOT NULL,
            status TEXT NOT NULL,
            expected_delivery TEXT,
            items TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE inventory (
            product_name TEXT PRIMARY KEY,
            dosage TEXT NOT NULL,
            category TEXT NOT NULL,
            requires_prescription INTEGER NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL,
            price REAL NOT NULL
        )
    """)
    orders = [
        ("ORD-101", "Kwame Asante", "Shipped", "2026-03-10", json.dumps(["Ibuprofen 200mg x30"])),
        ("ORD-102", "Ama Mensah", "Processing", "2026-03-15", json.dumps(["Vitamin C 500mg x60"])),
        ("ORD-103", "Kwame Asante", "Delivered", "2026-02-20", json.dumps(["Aspirin 100mg x50"])),
        ("ORD-104", "John Doe", "Cancelled", None, json.dumps(["Melatonin 5mg x30"])),
    ]
    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", orders)
    inventory = [
        ("ibuprofen", "200mg tablet", "Analgesic", 0, 150, 25.0),
        ("vitamin c", "500mg tablet", "Vitamin/Supplement", 0, 10, 40.0),
        ("amoxicillin", "500mg capsule", "Antibiotic", 1, 0, 80.0),
        ("tramadol", "50mg capsule", "Analgesic", 1, 45, 50.0),
        ("ciprofloxacin", "500mg tablet", "Antibiotic", 1, 65, 90.0),
    ]
    cur.executemany("INSERT INTO inventory VALUES (?,?,?,?,?,?)", inventory)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def ctx(db):
    """Fake RunContext with PharmacyDeps."""
    fake_ctx = MagicMock()
    fake_ctx.deps = PharmacyDeps(db_conn=db)
    return fake_ctx


# ---------------------------------------------------------------------------
# get_order_status
# ---------------------------------------------------------------------------

def test_get_order_status_found(ctx):
    result = json.loads(get_order_status(ctx, "ORD-101"))
    assert result["order_id"] == "ORD-101"
    assert result["status"] == "Shipped"
    assert result["expected_delivery"] == "2026-03-10"


def test_get_order_status_not_found(ctx):
    result = get_order_status(ctx, "ORD-999")
    assert "not found" in result.lower()


def test_get_order_status_cancelled(ctx):
    result = json.loads(get_order_status(ctx, "ORD-104"))
    assert result["expected_delivery"] == "N/A (order cancelled)"


# ---------------------------------------------------------------------------
# check_inventory
# ---------------------------------------------------------------------------

def test_check_inventory_in_stock(ctx):
    result = check_inventory(ctx, "ibuprofen")
    assert "150" in result


def test_check_inventory_out_of_stock(ctx):
    result = check_inventory(ctx, "amoxicillin")
    assert "out of stock" in result.lower()


def test_check_inventory_not_found(ctx):
    result = check_inventory(ctx, "unicorn dust")
    assert "not found" in result.lower()


# ---------------------------------------------------------------------------
# prepare_order_cancellation
# ---------------------------------------------------------------------------

def test_prepare_cancellation_eligible(ctx):
    result = json.loads(prepare_order_cancellation(ctx, "ORD-101"))
    assert result["cancellation_ready"] is True
    assert result["order_id"] == "ORD-101"


def test_prepare_cancellation_delivered(ctx):
    result = prepare_order_cancellation(ctx, "ORD-103")
    assert "cannot be cancelled" in result.lower() or "already been delivered" in result.lower()


def test_prepare_cancellation_already_cancelled(ctx):
    result = prepare_order_cancellation(ctx, "ORD-104")
    assert "already cancelled" in result.lower()


def test_prepare_cancellation_not_found(ctx):
    result = prepare_order_cancellation(ctx, "ORD-999")
    assert "not found" in result.lower()


# ---------------------------------------------------------------------------
# get_fda_warnings
# ---------------------------------------------------------------------------

def test_get_fda_warnings_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [{"boxed_warning": ["Serious cardiovascular risk."]}]
    }
    with patch("tools.requests.get", return_value=mock_response):
        result = get_fda_warnings("ibuprofen")
    assert "ibuprofen" in result.lower()
    assert "cardiovascular" in result.lower()


def test_get_fda_warnings_not_found():
    mock_response = MagicMock()
    mock_response.status_code = 404
    with patch("tools.requests.get", return_value=mock_response):
        result = get_fda_warnings("unknowndrug")
    assert "could not find" in result.lower() or "not listed" in result.lower()


# ---------------------------------------------------------------------------
# check_drug_interactions
# ---------------------------------------------------------------------------

def test_check_drug_interactions_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [{"drug_interactions": ["May increase bleeding risk."]}]
    }
    with patch("tools.requests.get", return_value=mock_response):
        result = check_drug_interactions("ibuprofen", "aspirin")
    assert "ibuprofen" in result.lower()
    assert "aspirin" in result.lower()


# ---------------------------------------------------------------------------
# generate_invoice
# ---------------------------------------------------------------------------

def test_generate_invoice_success(ctx):
    with patch("tools.cl") as mock_cl, patch("tools.FPDF") as mock_fpdf:
        mock_fpdf_instance = MagicMock()
        mock_fpdf.return_value = mock_fpdf_instance
        mock_cl.run_sync = MagicMock()

        result = generate_invoice(ctx, {"ibuprofen": 2, "vitamin c": 1})

    # Correct totals: 2*25.0 + 1*40.0 = 90.0
    assert "90" in result
    assert "Invoice Summary" in result
    assert "Ibuprofen" in result
    assert "Vitamin C" in result


def test_generate_invoice_out_of_stock(ctx):
    with patch("tools.cl"), patch("tools.FPDF"):
        result = generate_invoice(ctx, {"amoxicillin": 5})
    assert "failed" in result.lower() or "cannot fulfill" in result.lower()


def test_generate_invoice_product_not_found(ctx):
    with patch("tools.cl"), patch("tools.FPDF"):
        result = generate_invoice(ctx, {"dragon scales": 1})
    assert "failed" in result.lower() or "not found" in result.lower()


# ---------------------------------------------------------------------------
# check_inventory — prescription warning
# ---------------------------------------------------------------------------

def test_check_inventory_includes_rx_warning(ctx):
    result = check_inventory(ctx, "tramadol")
    assert "PRESCRIPTION REQUIRED" in result


def test_check_inventory_otc_no_warning(ctx):
    result = check_inventory(ctx, "ibuprofen")
    assert "PRESCRIPTION" not in result


# ---------------------------------------------------------------------------
# search_inventory
# ---------------------------------------------------------------------------

def test_search_inventory_partial_match(ctx):
    result = search_inventory(ctx, "ibu")
    assert "ibuprofen" in result.lower()


def test_search_inventory_no_match(ctx):
    result = search_inventory(ctx, "zzz")
    assert "no products found" in result.lower()


# ---------------------------------------------------------------------------
# get_drugs_by_category
# ---------------------------------------------------------------------------

def test_get_drugs_by_category_found(ctx):
    result = get_drugs_by_category(ctx, "Analgesic")
    assert "ibuprofen" in result.lower()
    assert "tramadol" in result.lower()


def test_get_drugs_by_category_not_found(ctx):
    result = get_drugs_by_category(ctx, "Neurology")
    assert "no products found" in result.lower()
    assert "available categories" in result.lower()


# ---------------------------------------------------------------------------
# suggest_alternatives
# ---------------------------------------------------------------------------

def test_suggest_alternatives_oos(ctx):
    result = suggest_alternatives(ctx, "amoxicillin")
    assert "ciprofloxacin" in result.lower()


def test_suggest_alternatives_in_stock(ctx):
    result = suggest_alternatives(ctx, "ibuprofen")
    assert "no substitution needed" in result.lower()


# ---------------------------------------------------------------------------
# get_customer_orders
# ---------------------------------------------------------------------------

def test_get_customer_orders_found(ctx):
    result = get_customer_orders(ctx, "Kwame Asante")
    assert "ORD-101" in result
    assert "ORD-103" in result


def test_get_customer_orders_not_found(ctx):
    result = get_customer_orders(ctx, "Unknown Person")
    assert "no orders found" in result.lower()
