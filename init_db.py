"""Database initialisation script for the Pharmacy Support Agent.

Creates the SQLite database schema and seeds inventory from pre-processed
real product data. Orders are generated synthetically.
Safe to re-run — existing tables are dropped and recreated on each execution.

Inventory data was sourced from data/Products_Database_Clean.xlsx and
embedded here to avoid a pandas/openpyxl runtime dependency.
"""

import json
import random
import sqlite3
from datetime import date, timedelta

BASE_DATE = date(2026, 3, 5)
random.seed(42)

# ── Inventory data ────────────────────────────────────────────────────────────
# Columns: (product_name, internal_reference, brand, active_ingredients,
#           dosage, dosage_form, category, atc_code,
#           requires_prescription, is_controlled, stock, unit, price, cost)
INVENTORY = [
    ('co-trimoxazole tab (loose)', 'LTP-', 'Letap', 'Trimethoprim, Sulfamethoxazole', '80mg, 400mg', 'Tablet', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01E - Sulfonamides and trimethoprim', 1, 0, 180, 'Blister(s)', 1.45, 1.28),
    ('chloramphenicol caps (loose)', 'LTP-', 'Letap', 'Chloramphenicol', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01B - Amphenicols', 1, 0, 95, 'Blister(s)', 3.5, 3.1),
    ('indometacin cap (loose)', 'LTP-', 'Letap', 'Indometacin', '25mg', 'Capsule', 'Anti-Inflammatory', 'M01 Anti-Inflammatory And Antirheumatic Products, M01AB - Acetic acid derivatives and related substances', 1, 0, 0, 'Blister(s)', 0.9, 0.756),
    ('librium (loose)', 'LTP-', 'Letap', 'Chlordiazepoxide Hydrochloride', '10mg', 'Capsule', 'Psycholeptic', 'N05 Psycholeptics, N05BA - Benzodiazepine derivatives', 1, 1, 20, 'Blister(s)', 1.8, 1.54),
    ('vitamin b-complex tabs (loose)', 'LTP-', 'Letap', 'Nicotinamide, Riboflavin, Thiamine (Vitamin B1)', None, 'Tablet', 'Vitamin/Supplement', 'A11 Vitamins, A11E - Vitamin B-complex; including combinations', 0, 0, 70, 'Blister(s)', 0.31, 0.26),
    ('chloramphenicol caps', 'LTP-', 'Letap', 'Chloramphenicol', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01B - Amphenicols', 1, 0, 5, 'Bx', 175.0, 154.75),
    ('alusil plus susp', 'LTP-03', None, 'Aluminium Hydroxide, Magnesium Trisilicate, Magnesium Hydroxide, Simethicone', '125ml', 'Suspension', 'Antacid/GI', 'A02A - Antacids, A02AF - Antacids with antiflatulents', 0, 0, 5, 'Btl(s)', 3.85, 3.45),
    ('ampicillin caps', 'LTP-09', 'Letap', 'Ampicillin', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CA - Penicillins with extended spectrum', 1, 0, 0, 'Bx', 128.0, 100.29),
    ('ampicillin susp', 'LTP-10', 'Letap', 'Ampicillin', '125mg/5ml / 100ml', 'Suspension', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CA - Penicillins with extended spectrum', 1, 0, 25, 'Btl(s)', 5.58, 5.08),
    ('amciclox caps', 'LTP-11', 'Letap', 'Ampicillin, Cloxacillin', '250mg, 250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CR - Combinations of penicillins; including beta-lactamase inhibitors', 1, 0, 0, 'Bx', 38.98, 34.29),
    ('amciclox susp', 'LTP-12', 'Letap', 'Ampicillin, Cloxacillin', '125mg/5ml, 125mg/5ml / 100ml', 'Suspension', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CR - Combinations of penicillins; including beta-lactamase inhibitors', 1, 0, 42, 'Btl(s)', 6.18, 5.6),
    ('arfan susp', 'LTP-13', None, 'Artemether, Lumefantrine', '20/120mg / 60ml', 'Suspension', 'Antimalarial', 'P01B - Antimalarials, P01BF - Artemisinin and derivatives; combinations', 0, 0, 0, 'Btl(s)', 4.6, 4.05),
    ('arfan tab', 'LTP-14', 'Letap', 'Artemether, Lumefantrine', '20/120mg', 'Tablet', 'Antimalarial', 'P01B - Antimalarials, P01BF - Artemisinin and derivatives; combinations', 0, 0, 31, 'Bx', 59.98, 54.75),
    ('arfan tab (monopack)', 'LTP-15', 'Letap', 'Artemether, Lumefantrine', '20/120mg', 'Tablet', 'Antimalarial', 'P01B - Antimalarials, P01BF - Artemisinin and derivatives; combinations', 0, 0, 68, 'Pkt', 4.05, 3.65),
    ('ascorbin tab (vitamin c)', 'LTP-16', 'Letap', 'Ascorbic Acid (Vitamin C)', '100mg', 'Tablet', 'Vitamin/Supplement', 'A11 Vitamins, A11GA - Ascorbic acid (Vitamin C)', 0, 0, 5, 'Bx', 17.98, 15.99),
    ('letaplex-b syrup', 'LTP-17', 'Letap', 'Thiamine (Vitamin B1), Riboflavin, Pyridoxine (Vitamin B6), Nicotinamide', '125ml', 'Syrup', 'Vitamin/Supplement', 'A11 Vitamins, A11E - Vitamin B-complex; including combinations', 0, 0, 15, 'Btl(s)', 3.25, 2.86),
    ('cafaprin tab', 'LTP-21', None, 'Caffeine, Aspirin', '30mg, 450mg', 'Tablet', 'Analgesic', 'N – Nervous System, N02B - Analgesics and Antipyretics', 0, 0, 5, 'Bx', 18.0, 16.39),
    ('calcium b12 syr', 'LTP-22', 'Letap', 'Cholecalciferol (Vitamin D3), Vitamin B12, Calcium Phosphate', '200 iu/5ml, 2.5 mcg/5ml, 240mg/5ml / 200ml', 'Suspension', 'Vitamin/Supplement', 'A11 Vitamins, A11A - Multivitamins; combinations', 0, 0, 43, 'Btl(s)', 5.78, 5.23),
    ('cetrizine 10mg tab (letap)', 'LTP-23', 'Letap', 'Cetrizine Hydrochloride', '10mg', 'Tablet', 'Antihistamine', 'R – Respiratory System, R06 Antihistamines For Systemic Use', 0, 0, 0, 'Bx', 4.14, 3.84),
    ('child care (letafen) syr', 'LTP-24', None, 'Ibuprofen', '100mg/5ml / 100ml', 'Syrup', 'Anti-Inflammatory', 'M01 Anti-Inflammatory And Antirheumatic Products, M01AE - Propionic acid derivatives', 0, 0, 14, 'Btl(s)', 3.48, 2.93),
    ('child care syr (vitamin c)', 'LTP-25', None, 'Ascorbic Acid (Vitamin C)', '50mg/5ml / 100ml', 'Syrup', 'Vitamin/Supplement', 'A11 Vitamins, A11GA - Ascorbic acid (Vitamin C)', 0, 0, 42, 'Btl(s)', 3.5, 3.09),
    ('chloramphenicol susp', 'LTP-28', 'Letap', 'Chloramphenicol', '125mg/5ml / 100ml', 'Suspension', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01B - Amphenicols', 1, 0, 27, 'Btl(s)', 6.32, 5.7),
    ('cloxacillin caps (loose)', 'LTP-29', 'Letap', 'Cloxacillin', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CF: Beta-lactamase Resistant Penicillins', 1, 0, 9, 'Blister(s)', 2.33, 2.095),
    ('cloxacillin caps', 'LTP-30', 'Letap', 'Cloxacillin', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CF: Beta-lactamase Resistant Penicillins', 1, 0, 4, 'Bx', 118.0, 104.85),
    ('cloxacillin susp', 'LTP-31', None, 'Cloxacillin', '125mg/5ml / 100ml', 'Suspension', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CF: Beta-lactamase Resistant Penicillins', 1, 0, 21, 'Btl(s)', 5.6, 4.97),
    ('dexamethasone tab (letap)', 'LTP-32', 'Letap', 'Dexamethasone', '0.5mg', 'Tablet', 'Corticosteroid', 'H02 Corticosteroids For Systemic Use, H02AB - Glucocorticoids', 1, 0, 42, 'Pkt', 2.56, 2.3),
    ('dynewell syr', 'LTP-34', None, 'Cyproheptadine Hcl, Lysine Hydrochloride, Proteolysed Liver Extract', '2mg/5ml, 150mg/5ml, 25mg/5ml / 200ml', 'Syrup', 'Vitamin/Supplement', 'A11 Vitamins, A11A - Multivitamins; combinations', 0, 0, 36, 'Btl(s)', 6.98, 6.25),
    ('dynewell tab', 'LTP-35', 'Letap', 'Cyproheptadine Hcl, Thiamine (Vitamin B1), Pyridoxine (Vitamin B6), Calcium Pantothenate', None, 'Tablet', 'Vitamin/Supplement', 'A11 Vitamins, A11A - Multivitamins; combinations', 0, 0, 0, 'Bx', 18.76, 16.88),
    ('erythromycin susp', 'LTP-36', 'Letap', 'Erythromycin Ethylsuccinate', '125mg/5ml / 100ml', 'Suspension', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01F - Macrolides, lincosamides, and streptogramins', 1, 0, 0, 'Btl(s)', 6.98, 6.4),
    ('foliron tonic (letap)', 'LTP-43', None, 'Haemoglobin, Ferric Ammonium Citrate, Cyanocobalamin, Folic Acid', '200ml', 'Syrup', 'Antianemic', 'B – Blood And Blood Forming Organs, B03 Antianemic Preparations', 0, 0, 9, 'Btl(s)', 7.4, 6.55),
    ('indometacin cap', 'LTP-47', 'Letap', 'Indometacin', '25mg', 'Capsule', 'Anti-Inflammatory', 'M01 Anti-Inflammatory And Antirheumatic Products, M01AB - Acetic acid derivatives and related substances', 1, 0, 0, 'Bx', 42.0, 37.8),
    ('letacam caps (piroxicam)', 'LTP-49', 'Letap', 'Piroxicam', '20mg', 'Capsule', 'Anti-Inflammatory', 'M01 Anti-Inflammatory And Antirheumatic Products, M01AB - Acetic acid derivatives and related substances', 1, 0, 38, 'Bx', 8.5, 7.65),
    ('letafen tab 400mg (ibuprofen)', 'LTP-50', 'Letap', 'Ibuprofen', '400mg', 'Tablet', 'Anti-Inflammatory', 'M01 Anti-Inflammatory And Antirheumatic Products, M01AE - Propionic acid derivatives', 1, 0, 6, 'Bx', 58.0, 50.29),
    ('letalin cough syr (letap)', 'LTP-51', None, 'Diphenhydramine Hydrochloride, Ammonium Chloride, Menthol, Sodium Citrate', '10mg/5ml, 100mg/5ml, 1mg/5ml, 40mg/5ml / 125ml', 'Syrup', 'Respiratory', 'R – Respiratory System, R05 Cough And Cold Preparations', 0, 0, 14, 'Btl(s)', 3.55, 3.17),
    ('letamin caps', 'LTP-52', 'Letap', 'Ampicillin, Cloxacillin', '250mg, 250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CR - Combinations of penicillins; including beta-lactamase inhibitors', 1, 0, 0, 'Pkt', 7.6, 7.6),
    ('letaron syr', 'LTP-53', None, 'Iron (III) Polymaltose, Cyanocobalamin, Folic Acid', '200ml', 'Syrup', 'Antianemic', 'B – Blood And Blood Forming Organs, B03 Antianemic Preparations', 0, 0, 17, 'Btl(s)', 6.5, 5.8),
    ('milk of magnesia susp (letap)', 'LTP-60', 'Letap', 'Magnesium Hydroxide', '400mg/5ml / 125ml', 'Suspension', 'Antacid/GI', 'A02 Drugs For Acid Related Disorders, A02A - Antacids', 0, 0, 0, 'Btl(s)', 2.46, 2.24),
    ('multivite tabs (letab)', 'LTP-62', 'Letap', 'Multivitamins with Minerals', None, 'Tablet', 'Vitamin/Supplement', 'A11 Vitamins, A11A - Multivitamins with minerals', 0, 0, 5, 'Bx', 32.0, 28.79),
    ('multivite tabs (loose)', 'LTP-63', 'Letap', 'Multivitamins with Minerals', None, 'Tablet', 'Vitamin/Supplement', 'A11 Vitamins, A11A - Multivitamins with minerals', 0, 0, 42, 'Blister(s)', 0.3, 0.27),
    ('paracetamol 500mg tab (letamol)', 'LTP-64', 'Letap', 'Paracetamol', '500mg', 'Tablet', 'Analgesic', 'N – Nervous System, N02B - Analgesics and Antipyretics', 0, 0, 13, 'Bx', 49.98, 44.4),
    ('amoxicillin 250mg caps (loose)', 'WBS_LTP-06', 'Letap', 'Amoxicillin', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CA - Penicillins with extended spectrum', 1, 0, 64, 'Blister(s)', 2.72, 2.47),
    ('ampicillin 250mg cap (loose)', 'WBS_LTP-08', 'Letap', 'Ampicillin', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CA - Penicillins with extended spectrum', 1, 0, 30, 'Blister(s)', 2.7, 2.4),
    ('metronidazole susp', None, 'Ecl', 'Metronidazole', '200mg/5ml / 100ml', 'Suspension', 'Antiprotozoal', 'P01 Antiprotozoals, P01A - Agents against amoebiasis and other protozoal diseases', 1, 0, 141, 'Btl(s)', 4.2, 0.0),
    ('metronidazole tab', None, 'Ecl', 'Metronidazole', '200mg', 'Tablet', 'Antiprotozoal', 'P01 Antiprotozoals, P01A - Agents against amoebiasis and other protozoal diseases', 1, 0, 24, 'Bx', 31.5, 0.0),
    ('metronidazole tab (loose)', None, 'Letap', 'Metronidazole', '200mg', 'Tablet', 'Antiprotozoal', 'P01 Antiprotozoals, P01A - Agents against amoebiasis and other protozoal diseases', 1, 0, 100, 'Blister(s)', 0.64, 0.57),
    ('doxycycline caps', None, 'Ecl', 'Doxycycline Hyclate', '100mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01A - Tetracyclines', 1, 0, 7, 'Bx', 34.38, 0.0),
    ('folic acid tab (28s)', None, 'Exeter', 'Folic Acid', '5mg', 'Tablet', 'Antianemic', 'B03 Antianemic Preparations, B03BB - Folic acid and derivatives', 0, 0, 40, 'Bx', 13.27, 0.0),
    ('multivitamin syr', None, 'Ecl', 'Multivitamins with Minerals', None, 'Syrup', 'Vitamin/Supplement', 'A11 Vitamins, A11A - Multivitamins with minerals', 0, 0, 71, 'Btl(s)', 3.98, 0.0),
    ('folic acid tab', None, 'Ecl', 'Folic Acid', '5mg', 'Tablet', 'Antianemic', 'B03 Antianemic Preparations, B03BB - Folic acid and derivatives', 0, 0, 19, 'Bx', 13.27, 0.0),
    ('amoxicillin 500mg caps', None, 'Entrance', 'Amoxicillin', '500mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CA - Penicillins with extended spectrum', 1, 0, 14, 'Bx', 41.9, 0.0),
    ('amoxicillin susp', None, 'Exeter', 'Amoxicillin', '125mg/5ml / 100ml', 'Suspension', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CA - Penicillins with extended spectrum', 1, 0, 80, 'Btl(s)', 32.5, 0.0),
    ('paracetamol syr', None, 'Exeter', 'Paracetamol', '125mg/5ml / 100ml', 'Syrup', 'Analgesic', 'N – Nervous System, N02B - Analgesics and Antipyretics', 0, 0, 339, 'Btl(s)', 3.55, 0.0),
    ('amoxicillin 250mg caps', None, 'Entrance', 'Amoxicillin', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CA - Penicillins with extended spectrum', 1, 0, 11, 'Bx', 108.0, 0.0),
    ('prednisolone tab', None, 'Ecl', 'Prednisolone', '5mg', 'Tablet', 'Corticosteroid', 'H02 Corticosteroids For Systemic Use, H02AB - Glucocorticoids', 1, 0, 3, 'Bx', 60.98, 0.0),
    ('co-trimoxazole susp', None, 'Ecl', 'Sulfamethoxazole, Trimethoprim', '240mg/5ml / 100ml', 'Suspension', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01E - Sulfonamides and trimethoprim', 1, 0, 20, 'Btl(s)', 4.28, 0.0),
    ('promethazine syr', None, 'Ecl', 'Promethazine', '5mg/5ml / 60ml', 'Syrup', 'Antihistamine', 'R – Respiratory System, R06 Antihistamines For Systemic Use', 1, 0, 26, 'Btl(s)', 4.06, 0.0),
    ('tetracycline caps (loose)', None, 'Ecl', 'Oxytetracycline Hydrochloride', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01A - Tetracyclines', 1, 0, 81, 'Blister(s)', 1.89, 0.0),
    ('flucloxacillin caps', None, 'Entrance', 'Flucloxacillin', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01C - Beta-lactam antibacterials; penicillins', 1, 0, 21, 'Bx', 5.5, 0.0),
    ('salbutamol tab', None, 'Ecl', 'Salbutamol Sulfate', '4mg', 'Tablet', 'Respiratory', 'R – Respiratory System, R03 Drugs For Obstructive Airway Diseases', 1, 0, 0, 'Bx', 40.85, 0.0),
    ('letavin tab (loose)', None, 'Letap', 'Griseofulvin', '500mg', 'Tablet', 'Antifungal', 'D – Dermatologicals, D01B - Antifungals for systemic use', 1, 0, 0, 'Blister(s)', 2.5, 0.0),
    ('co-trimoxazole tab', None, 'Ecl', 'Trimethoprim, Sulfamethoxazole', '80mg, 400mg', 'Tablet', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01E - Sulfonamides and trimethoprim', 1, 0, 1, 'Bx', 144.98, 0.0),
    ('letavin tab', None, 'Letap', 'Griseofulvin', '500mg', 'Tablet', 'Antifungal', 'D – Dermatologicals, D01B - Antifungals for systemic use', 1, 0, 8, 'Bx', 105.0, 0.0),
    ('flucloxacillin susp', None, 'Vega', 'Flucloxacillin', '125mg/5ml / 100ml', 'Suspension', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01C - Beta-lactam antibacterials; penicillins', 1, 0, 65, 'Btl(s)', 5.5, 0.0),
    ('amoxicillin + clavulanate susp', None, 'Exeter', 'Amoxicillin, Clavulanic Acid', '228.5mg/5ml / 100ml', 'Suspension', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01CR - Combinations of penicillins; including beta-lactamase inhibitors', 1, 0, 0, 'Btl(s)', 32.5, 0.0),
    ('glucose solution (letap)', None, 'Letap', 'Glucose, Ascorbic Acid (Vitamin C)', None, 'Solution', 'Nutritional Supplement', 'V06 General Nutrients, V06D - Carbohydrates', 0, 0, 0, 'Container(s)', 8.8, 0.0),
    ('vitamin b-complex tabs', None, 'Ecl', 'Nicotinamide, Riboflavin, Thiamine (Vitamin B1)', None, 'Tablet', 'Vitamin/Supplement', 'A11 Vitamins, A11E - Vitamin B-complex; including combinations', 0, 0, 12, 'Bx', 29.2, 0.0),
    ('librium', None, 'Eskay', 'Chlordiazepoxide Hydrochloride', '10mg', 'Capsule', 'Psycholeptic', 'N05 Psycholeptics, N05BA - Benzodiazepine derivatives', 1, 1, 10, 'Bx', 78.0, 0.0),
    ('haemoglobin syr', None, 'Ayrton', 'Haemoglobin, Vitamin B12', '200ml', 'Syrup', 'Antianemic', 'A11A - Multivitamins with minerals, B03 Antianemic Preparations', 0, 0, 75, 'Btl(s)', 6.48, 0.0),
    ('pen v tab', None, 'Letap', 'Phenoxymethylpenicillin Potassium', '125mg', 'Tablet', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01C - Beta-lactam antibacterials; penicillins', 1, 0, 3, 'Bx', 142.98, 0.0),
    ('prednisolone tab (loose)', None, 'Letap', 'Prednisolone', '5mg', 'Tablet', 'Corticosteroid', 'H02 Corticosteroids For Systemic Use, H02AB - Glucocorticoids', 1, 0, 65, 'Blister(s)', 0.9, 0.78),
    ('aluminium hydroxide tab', None, 'Entrance', 'Aluminium Hydroxide', '500mg', 'Tablet', 'Antacid/GI', 'A02 Drugs For Acid Related Disorders, A02A - Antacids', 0, 0, 0, 'Bx', 78.34, 0.0),
    ('pen v tab (loose)', None, 'Letap', 'Phenoxymethylpenicillin Potassium', '125mg', 'Tablet', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01C - Beta-lactam antibacterials; penicillins', 1, 0, 219, 'Blister(s)', 1.5, 0.0),
    ('tetracycline caps', None, 'Ecl', 'Oxytetracycline Hydrochloride', '250mg', 'Capsule', 'Antibiotic', 'J01 Antibacterials For Systemic Use, J01A - Tetracyclines', 1, 0, 1, 'Bx', 57.5, 0.0),
    ('tramadol caps', None, 'Ecl', 'Tramadol Hydrochloride', '50mg', 'Capsule', 'Opioid Analgesic', 'N02 Analgesics, N02A - Opioids', 1, 1, 2, 'Bx', 609.0, 0.0),
]


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

    # Clamp negative stock values (data entry errors in source)
    clean_inventory = [
        (*row[:10], max(0, row[10]), *row[11:])
        for row in INVENTORY
    ]
    cursor.executemany(
        "INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        clean_inventory,
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
        ["Arfan Tab x24"],
        ["Paracetamol Syr x2"],
        ["Metronidazole Tab (Loose) x14"],
        ["Folic Acid Tab x90"],
        ["Doxycycline Caps x14"],
        ["Co-Trimoxazole Tab (Loose) x14", "Paracetamol Syr x1"],
        ["Ampicillin Caps x21", "Vitamin B-Complex Tabs (Loose) x30"],
        ["Chloramphenicol Caps x10", "Folic Acid Tab x30"],
        ["Arfan Tab x24", "Paracetamol 500mg Tab (Letamol) x20"],
        ["Amciclox Caps x14", "Doxycycline Caps x14"],
        ["Metronidazole Susp x1", "Co-Trimoxazole Tab (Loose) x14"],
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
    print(f"✅ Database seeded: {len(clean_inventory)} inventory items, {len(orders)} orders.")


if __name__ == "__main__":
    setup_database()
