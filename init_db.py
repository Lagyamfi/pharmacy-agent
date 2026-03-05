"""Database initialisation script for the Pharmacy Support Agent.

Creates the SQLite database schema and seeds it with realistic pharmacy data.
Safe to re-run — existing tables are dropped and recreated on each execution.
"""

import json
import random
import sqlite3
from datetime import date, timedelta

BASE_DATE = date(2026, 3, 5)
random.seed(42)


def setup_database():
    """Create and seed the pharmacy SQLite database."""
    print("Initializing pharmacy database...")

    conn = sqlite3.connect("pharmacy.db")
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS orders")
    cursor.execute("DROP TABLE IF EXISTS inventory")

    cursor.execute("""
        CREATE TABLE inventory (
            product_name          TEXT PRIMARY KEY,
            dosage                TEXT NOT NULL,
            category              TEXT NOT NULL,
            requires_prescription INTEGER NOT NULL DEFAULT 0,
            stock                 INTEGER NOT NULL,
            price                 REAL NOT NULL
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

    # ── Inventory ─────────────────────────────────────────────────────────────
    # (product_name, dosage, category, requires_prescription, stock, price_GHS)
    inventory = [
        # Analgesics ────────────────────────────────────────────────────────────
        ("paracetamol",             "500mg tablet",          "Analgesic",          0, 500,  15.0),
        ("ibuprofen",               "200mg tablet",          "Analgesic",          0, 150,  25.0),
        ("ibuprofen 400mg",         "400mg tablet",          "Analgesic",          0, 120,  30.0),
        ("aspirin",                 "100mg tablet",          "Analgesic",          0, 300,  20.0),
        ("diclofenac",              "50mg tablet",           "Analgesic",          1,  80,  35.0),
        ("naproxen",                "250mg tablet",          "Analgesic",          1,  60,  40.0),
        ("tramadol",                "50mg capsule",          "Analgesic",          1,  45,  50.0),
        ("mefenamic acid",          "250mg capsule",         "Analgesic",          1,  70,  45.0),
        ("piroxicam",               "20mg capsule",          "Analgesic",          1,  30,  45.0),
        # Antibiotics ───────────────────────────────────────────────────────────
        ("amoxicillin",             "500mg capsule",         "Antibiotic",         1,   0,  80.0),
        ("amoxicillin 250mg",       "250mg capsule",         "Antibiotic",         1,  90,  65.0),
        ("amoxiclav",               "625mg tablet",          "Antibiotic",         1,  55, 120.0),
        ("ciprofloxacin",           "500mg tablet",          "Antibiotic",         1,  65,  90.0),
        ("erythromycin",            "500mg tablet",          "Antibiotic",         1,  40,  85.0),
        ("metronidazole",           "400mg tablet",          "Antibiotic",         1, 100,  55.0),
        ("doxycycline",             "100mg capsule",         "Antibiotic",         1,  50,  70.0),
        ("cotrimoxazole",           "480mg tablet",          "Antibiotic",         1,  75,  45.0),
        ("azithromycin",            "500mg tablet",          "Antibiotic",         1,  30, 130.0),
        ("clindamycin",             "300mg capsule",         "Antibiotic",         1,  25, 110.0),
        ("cephalexin",              "500mg capsule",         "Antibiotic",         1,  35,  95.0),
        ("tetracycline",            "250mg capsule",         "Antibiotic",         1,  20,  60.0),
        ("ampicillin",              "500mg capsule",         "Antibiotic",         1,  45,  75.0),
        ("gentamicin injection",    "80mg/2ml injection",    "Antibiotic",         1,  15, 180.0),
        # Antimalarials ─────────────────────────────────────────────────────────
        ("artemether lumefantrine", "20/120mg tablet",       "Antimalarial",       1,  80, 150.0),
        ("artesunate",              "50mg tablet",           "Antimalarial",       1,  60, 120.0),
        ("quinine",                 "300mg tablet",          "Antimalarial",       1,  40,  95.0),
        ("chloroquine",             "150mg tablet",          "Antimalarial",       0, 100,  40.0),
        ("fansidar",                "500/25mg tablet",       "Antimalarial",       1,  55,  85.0),
        ("amodiaquine",             "200mg tablet",          "Antimalarial",       1,  70,  75.0),
        # Antihypertensives ─────────────────────────────────────────────────────
        ("amlodipine",              "5mg tablet",            "Antihypertensive",   1, 120,  60.0),
        ("amlodipine 10mg",         "10mg tablet",           "Antihypertensive",   1,  85,  75.0),
        ("lisinopril",              "10mg tablet",           "Antihypertensive",   1,  90,  65.0),
        ("atenolol",                "50mg tablet",           "Antihypertensive",   1,  75,  55.0),
        ("hydrochlorothiazide",     "25mg tablet",           "Antihypertensive",   1, 110,  45.0),
        ("methyldopa",              "250mg tablet",          "Antihypertensive",   1,  50,  70.0),
        ("enalapril",               "10mg tablet",           "Antihypertensive",   1,  65,  60.0),
        ("nifedipine",              "10mg tablet",           "Antihypertensive",   1,  80,  55.0),
        ("losartan",                "50mg tablet",           "Antihypertensive",   1,  45,  80.0),
        ("furosemide",              "40mg tablet",           "Antihypertensive",   1,  95,  40.0),
        ("spironolactone",          "25mg tablet",           "Antihypertensive",   1,  35,  65.0),
        # Vitamins / Supplements ────────────────────────────────────────────────
        ("vitamin c 500mg",         "500mg tablet",          "Vitamin/Supplement", 0, 320,  40.0),
        ("vitamin c 1000mg",        "1000mg tablet",         "Vitamin/Supplement", 0, 200,  55.0),
        ("vitamin b complex",       "tablet",                "Vitamin/Supplement", 0, 250,  35.0),
        ("vitamin d3",              "1000IU capsule",        "Vitamin/Supplement", 0, 180,  50.0),
        ("folic acid",              "5mg tablet",            "Vitamin/Supplement", 0, 300,  20.0),
        ("ferrous sulphate",        "200mg tablet",          "Vitamin/Supplement", 0, 150,  25.0),
        ("zinc sulphate",           "20mg tablet",           "Vitamin/Supplement", 0, 200,  30.0),
        ("calcium carbonate",       "500mg tablet",          "Vitamin/Supplement", 0, 175,  35.0),
        ("multivitamin",            "tablet",                "Vitamin/Supplement", 0, 400,  45.0),
        ("cod liver oil",           "capsule",               "Vitamin/Supplement", 0, 220,  40.0),
        # Antacids / GI ─────────────────────────────────────────────────────────
        ("omeprazole",              "20mg capsule",          "Antacid/GI",         0, 130,  55.0),
        ("omeprazole 40mg",         "40mg capsule",          "Antacid/GI",         1,  90,  70.0),
        ("ranitidine",              "150mg tablet",          "Antacid/GI",         0, 100,  45.0),
        ("metoclopramide",          "10mg tablet",           "Antacid/GI",         0,  80,  30.0),
        ("loperamide",              "2mg capsule",           "Antacid/GI",         0,  70,  35.0),
        ("oral rehydration salts",  "sachet",                "Antacid/GI",         0, 500,  10.0),
        ("bisacodyl",               "5mg tablet",            "Antacid/GI",         0,  90,  25.0),
        ("antacid",                 "400mg tablet",          "Antacid/GI",         0, 150,  20.0),
        ("domperidone",             "10mg tablet",           "Antacid/GI",         0,  85,  35.0),
        # Respiratory ───────────────────────────────────────────────────────────
        ("salbutamol",              "2mg tablet",            "Respiratory",        1,  85,  35.0),
        ("salbutamol inhaler",      "100mcg/dose inhaler",   "Respiratory",        1,  45, 120.0),
        ("ambroxol",                "30mg tablet",           "Respiratory",        0, 100,  30.0),
        ("bromhexine",              "8mg tablet",            "Respiratory",        0,  75,  25.0),
        ("cough syrup",             "100ml syrup",           "Respiratory",        0,  60,  35.0),
        ("loratadine",              "10mg tablet",           "Respiratory",        0, 110,  30.0),
        ("cetirizine",              "10mg tablet",           "Respiratory",        0, 120,  30.0),
        ("chlorpheniramine",        "4mg tablet",            "Respiratory",        0, 200,  20.0),
        ("beclomethasone inhaler",  "50mcg/dose inhaler",    "Respiratory",        1,  30, 150.0),
        ("theophylline",            "200mg tablet",          "Respiratory",        1,  25,  50.0),
        # Antidiabetics ─────────────────────────────────────────────────────────
        ("metformin",               "500mg tablet",          "Antidiabetic",       1, 100,  50.0),
        ("metformin 1000mg",        "1000mg tablet",         "Antidiabetic",       1,  65,  70.0),
        ("glibenclamide",           "5mg tablet",            "Antidiabetic",       1,  75,  45.0),
        ("glimepiride",             "2mg tablet",            "Antidiabetic",       1,  40,  80.0),
        # Dermatology ───────────────────────────────────────────────────────────
        ("hydrocortisone cream",    "1% cream 30g",          "Dermatology",        0,  90,  30.0),
        ("betamethasone cream",     "0.1% cream 30g",        "Dermatology",        1,  55,  45.0),
        ("clotrimazole cream",      "1% cream 30g",          "Dermatology",        0,  70,  35.0),
        ("calamine lotion",         "100ml lotion",          "Dermatology",        0,  80,  25.0),
        ("whitfield ointment",      "30g ointment",          "Dermatology",        0,  60,  20.0),
        ("miconazole cream",        "2% cream 30g",          "Dermatology",        0,  65,  40.0),
        ("permethrin cream",        "5% cream 30g",          "Dermatology",        0,  35,  55.0),
        # Antifungals ───────────────────────────────────────────────────────────
        ("fluconazole",             "150mg capsule",         "Antifungal",         1,  40,  80.0),
        ("ketoconazole",            "200mg tablet",          "Antifungal",         1,  35,  70.0),
        ("griseofulvin",            "125mg tablet",          "Antifungal",         1,  25,  55.0),
        # Ophthalmic / Otic ─────────────────────────────────────────────────────
        ("gentamicin eye drops",    "0.3% 5ml eye drops",   "Ophthalmic",         1,  50,  40.0),
        ("chloramphenicol eye drops","0.5% 5ml eye drops",  "Ophthalmic",         0,  45,  35.0),
        ("artificial tears",        "5ml eye drops",         "Ophthalmic",         0,  80,  25.0),
        ("ear drops",               "10ml ear drops",        "Otic",               0,  60,  30.0),
        # Other ─────────────────────────────────────────────────────────────────
        ("prednisolone",            "5mg tablet",            "Corticosteroid",     1,  90,  30.0),
        ("dexamethasone",           "0.5mg tablet",          "Corticosteroid",     1,  70,  35.0),
        ("digoxin",                 "0.25mg tablet",         "Cardiac",            1,  40,  45.0),
        ("albendazole",             "400mg tablet",          "Antiparasitic",      0, 120,  35.0),
        ("mebendazole",             "100mg tablet",          "Antiparasitic",      0, 150,  25.0),
        ("piperazine",              "500mg tablet",          "Antiparasitic",      0,  80,  20.0),
        ("melatonin",               "5mg tablet",            "Sleep Aid",          0,  75,  55.0),
        ("antihistamine",           "10mg tablet",           "Antihistamine",      0,  45,  30.0),
        ("hand sanitizer",          "500ml gel",             "Hygiene",            0, 500,  15.0),
        ("surgical spirit",         "500ml",                 "Hygiene",            0, 300,  12.0),
        ("cotton wool",             "100g roll",             "Supplies",           0, 400,   8.0),
        ("bandage",                 "5cm x 4m roll",         "Supplies",           0, 250,  10.0),
        ("plaster strips",          "box of 20",             "Supplies",           0, 350,  15.0),
    ]

    cursor.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?)", inventory)

    # ── Orders ────────────────────────────────────────────────────────────────
    CUSTOMERS = [
        "Kwame Asante",     "Ama Boateng",      "Kofi Mensah",      "Abena Owusu",
        "Kweku Darko",      "Akosua Amoah",     "Yaw Appiah",       "Adwoa Frimpong",
        "Fiifi Quaye",      "Efua Aidoo",       "Nana Kwarteng",    "Esi Tetteh",
        "Kwabena Ofori",    "Abena Sarpong",    "Kofi Boakye",      "Akua Amponsah",
        "Kojo Asare",       "Ama Kyei",         "Kwame Osei",       "Adjoa Dankwa",
        "Yaw Darko",        "Akua Mensah",      "Kwabena Agyei",    "Abena Adjei",
        "Kofi Amoah",       "Esi Bonsu",        "Kweku Acheampong", "Adwoa Opoku",
        "Nana Asante",      "Efua Boateng",
    ]

    ITEM_POOLS = [
        ["Paracetamol 500mg x30"],
        ["Ibuprofen 200mg x30"],
        ["Aspirin 100mg x50"],
        ["Amoxicillin 250mg x21"],
        ["Ciprofloxacin 500mg x10"],
        ["Metronidazole 400mg x21"],
        ["Artemether Lumefantrine 20/120mg x24"],
        ["Artesunate 50mg x12"],
        ["Quinine 300mg x21"],
        ["Metformin 500mg x60"],
        ["Amlodipine 5mg x30"],
        ["Lisinopril 10mg x30"],
        ["Vitamin C 500mg x60"],
        ["Vitamin B Complex x30"],
        ["Folic Acid 5mg x90"],
        ["Ferrous Sulphate 200mg x60"],
        ["Omeprazole 20mg x30"],
        ["Salbutamol Inhaler x1"],
        ["Fluconazole 150mg x3"],
        ["Prednisolone 5mg x30"],
        ["Albendazole 400mg x2"],
        ["Mebendazole 100mg x6"],
        ["Azithromycin 500mg x3"],
        ["Loratadine 10mg x14"],
        ["Multivitamin x60"],
        ["Ibuprofen 200mg x30", "Omeprazole 20mg x30"],
        ["Amoxicillin 250mg x21", "Metronidazole 400mg x21", "Paracetamol 500mg x30"],
        ["Amlodipine 5mg x30", "Lisinopril 10mg x30"],
        ["Metformin 500mg x60", "Glibenclamide 5mg x30"],
        ["Vitamin C 500mg x60", "Vitamin B Complex x30", "Zinc Sulphate 20mg x30"],
        ["Artemether Lumefantrine 20/120mg x24", "Oral Rehydration Salts x5", "Paracetamol 500mg x20"],
        ["Ibuprofen 400mg x30", "Cough Syrup 100ml x2"],
        ["Cetirizine 10mg x14", "Ambroxol 30mg x14"],
        ["Doxycycline 100mg x14", "Metronidazole 400mg x14"],
        ["Calcium Carbonate 500mg x60", "Vitamin D3 1000IU x30", "Folic Acid 5mg x90"],
        ["Hand Sanitizer 500ml x2", "Cotton Wool 100g x1"],
        ["Bandage 5cm x 4m x3", "Plaster Strips x2", "Surgical Spirit 500ml x1"],
        ["Chloramphenicol Eye Drops x2", "Artificial Tears x1"],
        ["Betamethasone Cream x2", "Clotrimazole Cream x1"],
        ["Fansidar 500/25mg x3", "Paracetamol 500mg x20"],
        ["Cotrimoxazole 480mg x14", "Vitamin C 500mg x30"],
        ["Atenolol 50mg x30", "Hydrochlorothiazide 25mg x30"],
        ["Cod Liver Oil x30", "Multivitamin x30", "Calcium Carbonate 500mg x60"],
        ["Domperidone 10mg x14", "Omeprazole 20mg x14"],
        ["Chlorpheniramine 4mg x20", "Bromhexine 8mg x14", "Paracetamol 500mg x20"],
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
    print(f"✅ Database seeded: {len(inventory)} inventory items, {len(orders)} orders.")


if __name__ == "__main__":
    setup_database()
