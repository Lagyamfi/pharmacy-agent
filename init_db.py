"""Database initialisation script for the Pharmacy Support Agent.

Creates the SQLite database schema and seeds inventory from the real product
dataset (data/Products_Database_Clean.xlsx). Orders are generated synthetically.
Safe to re-run — existing tables are dropped and recreated on each execution.
"""

import json
import random
import re
import sqlite3
from datetime import date, timedelta

import pandas as pd

BASE_DATE = date(2026, 3, 5)
random.seed(42)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _atc_to_category(atc_string: str) -> str:
    """Map a full ATC classification string to a simplified category label."""
    s = atc_string.upper()
    if "J01" in s:
        return "Antibiotic"
    if "P01B" in s:
        return "Antimalarial"
    if "P01" in s:
        return "Antiprotozoal"
    if "M01" in s:
        return "Anti-Inflammatory"
    if "N02A" in s:
        return "Opioid Analgesic"
    if "N02" in s:
        return "Analgesic"
    if "N05" in s:
        return "Psycholeptic"
    if "H02" in s:
        return "Corticosteroid"
    if "D01" in s:
        return "Antifungal"
    if "R06" in s:
        return "Antihistamine"
    if "R03" in s or "R05" in s:
        return "Respiratory"
    if "B03" in s and "A11" not in s:
        return "Antianemic"
    if "A11" in s:
        return "Vitamin/Supplement"
    if "A02" in s:
        return "Antacid/GI"
    if "V06" in s:
        return "Nutritional Supplement"
    m = re.match(r"([A-Z])", s)
    return f"Other ({m.group(1)})" if m else "Other"


def _parse_schedule(schedule: str) -> tuple[int, int]:
    """Return (requires_prescription, is_controlled) from medicine schedule string."""
    if "Controlled Drug" in schedule:
        return 1, 1
    if "Prescription Only" in schedule:
        return 1, 0
    return 0, 0


def _extract_dosage_form(route: str) -> str:
    """Extract dosage form from 'Oral (Enteral), Tablet' → 'Tablet'."""
    if "," in route:
        return route.split(",")[-1].strip()
    return route.strip()


def _build_dosage(row: pd.Series) -> str | None:
    """Combine Dosage Unit and Volume into a single dosage string."""
    dosage_unit = row.get("Dosage Unit")
    volume = row.get("Volume")
    has_unit = pd.notna(dosage_unit) and str(dosage_unit).strip()
    has_volume = pd.notna(volume) and str(volume).strip()

    if has_unit and has_volume:
        return f"{str(dosage_unit).strip()} / {str(volume).strip()}"
    if has_unit:
        return str(dosage_unit).strip()
    if has_volume:
        return str(volume).strip()
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def setup_database():
    """Create and seed the pharmacy SQLite database."""
    print("Initializing pharmacy database...")

    conn = sqlite3.connect("pharmacy.db")
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS orders")
    cursor.execute("DROP TABLE IF EXISTS inventory")

    # ── Schema ────────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE inventory (
            product_name          TEXT PRIMARY KEY,
            internal_reference    TEXT,
            brand                 TEXT,
            active_ingredients    TEXT NOT NULL,
            dosage                TEXT,
            dosage_form           TEXT NOT NULL,
            category              TEXT NOT NULL,
            atc_code              TEXT NOT NULL,
            requires_prescription INTEGER NOT NULL DEFAULT 0,
            is_controlled         INTEGER NOT NULL DEFAULT 0,
            stock                 INTEGER NOT NULL,
            unit                  TEXT NOT NULL,
            price                 REAL NOT NULL,
            cost                  REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE orders (
            order_id          TEXT PRIMARY KEY,
            customer_name     TEXT NOT NULL,
            status            TEXT NOT NULL,
            expected_delivery TEXT,
            items             TEXT NOT NULL
        )
    """)

    # ── Inventory — loaded from Excel ─────────────────────────────────────────
    df = pd.read_excel("data/Products_Database_Clean.xlsx")

    inventory_rows = []
    for _, row in df.iterrows():
        product_name = str(row["Name"]).strip().lower()
        internal_ref = (
            str(row["Internal Reference"]).strip()
            if pd.notna(row["Internal Reference"])
            else None
        )
        brand = str(row["Brand"]).strip() if pd.notna(row["Brand"]) else None
        active_ingredients = str(row["Active Ingredients"]).strip()
        dosage = _build_dosage(row)
        dosage_form = _extract_dosage_form(str(row["Route of Administration"]).strip())
        atc_code = str(row["Therapeutic Classification"]).strip()
        category = _atc_to_category(atc_code)
        requires_prescription, is_controlled = _parse_schedule(
            str(row["Medicine Schedule"]).strip()
        )
        stock = int(row["Qty On Hand"])
        unit = str(row["Unit"]).strip()
        price = float(row["Sales Price"])
        cost = float(row["Cost"])

        inventory_rows.append((
            product_name,
            internal_ref,
            brand,
            active_ingredients,
            dosage,
            dosage_form,
            category,
            atc_code,
            requires_prescription,
            is_controlled,
            stock,
            unit,
            price,
            cost,
        ))

    cursor.executemany(
        "INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        inventory_rows,
    )

    # ── Orders — synthetic ────────────────────────────────────────────────────
    CUSTOMERS = [
        "Kwame Asante",     "Ama Boateng",      "Kofi Mensah",      "Abena Owusu",
        "Kweku Darko",      "Akosua Amoah",     "Yaw Appiah",       "Adwoa Frimpong",
        "Fiifi Quaye",      "Efua Aidoo",        "Nana Kwarteng",    "Esi Tetteh",
        "Kwabena Ofori",    "Abena Sarpong",    "Kofi Boakye",      "Akua Amponsah",
        "Kojo Asare",       "Ama Kyei",          "Kwame Osei",       "Adjoa Dankwa",
        "Yaw Darko",        "Akua Mensah",      "Kwabena Agyei",    "Abena Adjei",
        "Kofi Amoah",       "Esi Bonsu",         "Kweku Acheampong", "Adwoa Opoku",
        "Nana Asante",      "Efua Boateng",
    ]

    ITEM_POOLS = [
        ["Co-Trimoxazole Tab (Loose) x14"],
        ["Chloramphenicol Caps x10"],
        ["Vitamin B-Complex Tabs (Loose) x30"],
        ["Ampicillin Caps x21"],
        ["Amciclox Caps x14"],
        ["Vitamin C Tabs x60"],
        ["Artemether/Lumefantrine Tab x24"],
        ["Erythromycin Tabs x14"],
        ["Folic Acid Tabs x90"],
        ["Doxycycline Caps x14"],
        ["Co-Trimoxazole Tab (Loose) x14", "Vitamin C Tabs x30"],
        ["Ampicillin Caps x21", "Vitamin B-Complex Tabs (Loose) x30"],
        ["Chloramphenicol Caps x10", "Folic Acid Tabs x30"],
        ["Artemether/Lumefantrine Tab x24", "Vitamin C Tabs x30"],
        ["Amciclox Caps x14", "Doxycycline Caps x14"],
        ["Erythromycin Tabs x10", "Co-Trimoxazole Tab (Loose) x14"],
    ]

    statuses = (
        ["Delivered"] * 45 +
        ["Shipped"]   * 30 +
        ["Processing"] * 25 +
        ["Cancelled"]  * 15
    )
    random.shuffle(statuses)

    orders = []
    for i, status in enumerate(statuses, start=101):
        if status == "Delivered":
            delivery = (BASE_DATE - timedelta(days=random.randint(3, 90))).isoformat()
        elif status in ("Shipped", "Processing"):
            delivery = (BASE_DATE + timedelta(days=random.randint(1, 10))).isoformat()
        else:
            delivery = None

        orders.append((
            f"ORD-{i}",
            random.choice(CUSTOMERS),
            status,
            delivery,
            json.dumps(random.choice(ITEM_POOLS)),
        ))

    cursor.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)

    conn.commit()
    conn.close()
    print(f"✅ Database seeded: {len(inventory_rows)} inventory items, {len(orders)} orders.")


if __name__ == "__main__":
    setup_database()
