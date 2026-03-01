import sqlite3
import json

def setup_database():
    print("Initializing pharmacy database...")
    
    # Connect to SQLite (this will create 'pharmacy.db' in the current directory)
    conn = sqlite3.connect("pharmacy.db")
    cursor = conn.cursor()
    
    # 1. Clear existing tables if they exist (great for resetting your tests)
    cursor.execute("DROP TABLE IF EXISTS orders")
    cursor.execute("DROP TABLE IF EXISTS inventory")
    
    # 2. Create the Orders table
    # We use TEXT for items and store it as a JSON string for easy retrieval
    cursor.execute("""
        CREATE TABLE orders (
            order_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            expected_delivery TEXT,
            items TEXT NOT NULL
        )
    """)
    
    # 3. Create the Inventory table
    cursor.execute("""
        CREATE TABLE inventory (
            product_name TEXT PRIMARY KEY,
            stock INTEGER NOT NULL
        )
    """)
    
    # 4. Insert Mock Orders
    mock_orders = [
        ("ORD-101", "Shipped", "2026-03-04", json.dumps(["Ibuprofen 200mg x30", "Vitamin C 500mg x60"])),
        ("ORD-102", "Processing", "2026-03-07", json.dumps(["Melatonin 5mg x30"])),
        ("ORD-103", "Delivered", "2026-02-25", json.dumps(["Cough Syrup 200ml", "Hand Sanitizer 500ml"])),
        ("ORD-104", "Cancelled", None, json.dumps(["Amoxicillin 500mg x21"])),
        ("ORD-105", "Shipped", "2026-03-05", json.dumps(["Aspirin 100mg x50", "Antihistamine 10mg x14", "Vitamin C 1000mg x30"]))
    ]
    cursor.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", mock_orders)
    
    # 5. Insert Mock Inventory
    mock_inventory = [
        ("ibuprofen", 150),
        ("vitamin c", 320),
        ("melatonin", 75),
        ("amoxicillin", 0),
        ("aspirin", 200),
        ("antihistamine", 45),
        ("cough syrup", 60),
        ("hand sanitizer", 500)
    ]
    cursor.executemany("INSERT INTO inventory VALUES (?, ?)", mock_inventory)
    
    # Commit the changes and close
    conn.commit()
    conn.close()
    
    print("✅ Database 'pharmacy.db' created and seeded successfully!")

if __name__ == "__main__":
    setup_database()