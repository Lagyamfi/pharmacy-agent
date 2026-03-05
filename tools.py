"""Tool functions for the Pharmacy Support Agent.

These are registered with the pydantic-ai Agent so the LLM can 
invoke them through function calling.
"""

import datetime
import json
import os
import tempfile

import chainlit as cl
import requests
import sqlite3
from dataclasses import dataclass
from fpdf import FPDF
from pydantic_ai import RunContext

# 1. Define the Dependency object that holds our database connection
@dataclass
class PharmacyDeps:
    db_conn: sqlite3.Connection
    support_history: list = None
    pharmacist_history: list = None

    def __post_init__(self):
        if self.support_history is None:
            self.support_history = []
        if self.pharmacist_history is None:
            self.pharmacist_history = []


# 2. Update to require ctx: RunContext[PharmacyDeps]
def get_order_status(ctx: RunContext[PharmacyDeps], order_id: str) -> str:
    """Look up the status of a customer order.

    Use this when a customer asks about tracking, shipping,
    or the status of their purchase.

    Args:
        order_id: The order identifier, e.g. "ORD-101".

    Returns:
        A string with the order details or a not-found message.
    """
    clean_id = order_id.upper().strip()
    cursor = ctx.deps.db_conn.cursor()
    
    # Securely query the SQLite database
    cursor.execute(
        "SELECT status, expected_delivery, items FROM orders WHERE order_id = ?", 
        (clean_id,)
    )
    result = cursor.fetchone()

    if result is None:
        return f"Order '{clean_id}' not found. Please verify the order ID and try again."

    status, delivery, items_json = result
    items_list = json.loads(items_json)

    return json.dumps(
        {
            "order_id": clean_id,
            "status": status,
            "items": items_list,
            "expected_delivery": delivery or "N/A (order cancelled)",
        },
        indent=2,
    )


# 3. Update to require ctx: RunContext[PharmacyDeps]
def check_inventory(ctx: RunContext[PharmacyDeps], product_name: str) -> str:
    """Check whether a specific product is currently in stock.

    Use this when a customer asks if a specific item is available
    or in stock.

    Args:
        product_name: The name of the product, e.g. "ibuprofen".

    Returns:
        A string with the current stock level or a not-found message.
    """
    name = product_name.lower().strip()
    cursor = ctx.deps.db_conn.cursor()
    
    # Securely query the SQLite database
    cursor.execute(
        """
        SELECT stock, dosage, dosage_form, category, active_ingredients,
               requires_prescription, is_controlled
        FROM inventory WHERE product_name = ?
        """,
        (name,),
    )
    result = cursor.fetchone()

    if result is None:
        return (
            f"Product '{product_name}' was not found in our inventory. "
            "Please check the product name and try again."
        )

    stock, dosage, dosage_form, category, active_ingredients, requires_prescription, is_controlled = result
    if stock == 0:
        return f"{product_name.title()} is currently out of stock."

    dosage_str = f"{dosage} " if dosage else ""
    rx_line = (
        "⚠️ PRESCRIPTION REQUIRED — a valid prescription must be presented before dispensing."
        if requires_prescription
        else "OTC (no prescription required)"
    )
    controlled_line = (
        "\n⛔ CONTROLLED DRUG — special regulatory requirements apply."
        if is_controlled
        else ""
    )
    return (
        f"{product_name.title()} is in stock — {stock} units available.\n"
        f"Active Ingredients: {active_ingredients} | {dosage_str}{dosage_form} | "
        f"Category: {category} | {rx_line}{controlled_line}"
    )


# 4. No context needed here, it just hits the internet!
def get_fda_warnings(drug_name: str) -> str:
    """Fetch official FDA boxed warnings for a specific medication.

    Use this when a customer asks about the side effects, risks, or FDA warnings
    of a specific medication.

    Args:
        drug_name: The name of the drug, e.g. "ibuprofen".

    Returns:
        A string with the FDA boxed warning text, or a not-found message.
    """
    url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:\"{drug_name}\"&limit=1"
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            warnings = data['results'][0].get('boxed_warning', ["No strict boxed warnings found."])[0]
            return f"FDA Warning for {drug_name}: {warnings}"
        else:
            return f"Could not find FDA data for {drug_name}. It may be spelled incorrectly or not listed."
    except Exception as e:
        return f"Error connecting to FDA database: {str(e)}"


def check_drug_interactions(drug_name_1: str, drug_name_2: str) -> str:
    """Check potential interactions between two medications.

    Use this when a customer asks whether two drugs can be taken together,
    or about interactions between medications.

    Args:
        drug_name_1: The first drug name, e.g. "ibuprofen".
        drug_name_2: The second drug name, e.g. "aspirin".

    Returns:
        A string with interaction information for both drugs.
    """
    results = []

    for drug_name in [drug_name_1, drug_name_2]:
        url = (
            f'https://api.fda.gov/drug/label.json'
            f'?search=openfda.generic_name:"{drug_name}"&limit=1'
        )
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                interactions = data["results"][0].get(
                    "drug_interactions",
                    ["No interaction data found in FDA label."],
                )
                results.append(f"**{drug_name.title()}** interactions:\n{interactions[0]}")
            else:
                results.append(
                    f"**{drug_name.title()}**: No FDA label data found."
                )
        except Exception as e:
            results.append(
                f"**{drug_name.title()}**: Error fetching data — {str(e)}"
            )

    return "\n\n---\n\n".join(results)


def prepare_order_cancellation(
    ctx: RunContext[PharmacyDeps], order_id: str
) -> str:
    """Stage an order for cancellation. This does NOT cancel the order —
    it checks eligibility and returns a confirmation payload for the UI.

    Use this when a customer asks to cancel an order.

    Args:
        order_id: The order ID to cancel, e.g. "ORD-101".

    Returns:
        A JSON string indicating whether cancellation is ready
        or an error message explaining why it cannot be cancelled.
    """
    cursor = ctx.deps.db_conn.cursor()
    cursor.execute(
        "SELECT order_id, status, items FROM orders WHERE order_id = ?",
        (order_id,),
    )
    row = cursor.fetchone()

    if not row:
        return f"Order {order_id} was not found in the system."

    current_status = row[1]
    items = row[2]

    if current_status == "Cancelled":
        return f"Order {order_id} is already cancelled."

    if current_status == "Delivered":
        return f"Order {order_id} has already been delivered and cannot be cancelled."

    # Eligible for cancellation (Processing or Shipped)
    return json.dumps({
        "cancellation_ready": True,
        "order_id": order_id,
        "current_status": current_status,
        "items": items,
        "message": (
            f"Order {order_id} (status: {current_status}) is eligible for cancellation. "
            "Please ask the customer to confirm using the buttons below."
        ),
    })


def search_inventory(ctx: RunContext[PharmacyDeps], query: str) -> str:
    """Search for products by partial name or brand name.

    Use this when a customer mentions a brand name, misspells a drug, or
    provides only a partial product name.

    Args:
        query: Partial or full product name to search for, e.g. "augmentin".

    Returns:
        A formatted list of matching products or a not-found message.
    """
    cursor = ctx.deps.db_conn.cursor()
    cursor.execute(
        """
        SELECT product_name, active_ingredients, dosage, dosage_form,
               category, requires_prescription, is_controlled, stock, price
        FROM inventory
        WHERE product_name LIKE ? OR active_ingredients LIKE ?
        ORDER BY stock DESC
        LIMIT 6
        """,
        (f"%{query.lower()}%", f"%{query.lower()}%"),
    )
    rows = cursor.fetchall()

    if not rows:
        return (
            f"No products found matching '{query}'. "
            "Try searching by a generic name or browse by category."
        )

    lines = [f"Search results for '{query}':"]
    for name, active_ingredients, dosage, dosage_form, category, rx, controlled, stock, price in rows:
        rx_flag = "⚠️ Rx" if rx else "OTC"
        if controlled:
            rx_flag += " (Controlled)"
        dosage_str = f"{dosage} " if dosage else ""
        stock_str = f"{stock} units" if stock > 0 else "OUT OF STOCK"
        lines.append(
            f"• {name.title()} | {active_ingredients} | {dosage_str}{dosage_form} | "
            f"{category} | {rx_flag} | {stock_str} | GH\u20b5{price:.2f}"
        )
    return "\n".join(lines)


def get_drugs_by_category(ctx: RunContext[PharmacyDeps], category: str) -> str:
    """Browse all products in a drug category or therapeutic class.

    Use this when a customer asks what you carry for a condition or drug class,
    e.g. "malaria drugs", "blood pressure medications", "pain relief".

    Args:
        category: The drug category to browse, e.g. "Analgesic", "Antimalarial".

    Returns:
        A formatted listing of products in the category, grouped by availability.
    """
    cursor = ctx.deps.db_conn.cursor()
    cursor.execute(
        """
        SELECT product_name, active_ingredients, dosage, dosage_form,
               requires_prescription, is_controlled, stock, price
        FROM inventory
        WHERE LOWER(category) = LOWER(?)
        ORDER BY stock DESC
        """,
        (category,),
    )
    rows = cursor.fetchall()

    if not rows:
        cursor.execute("SELECT DISTINCT category FROM inventory ORDER BY category")
        categories = [r[0] for r in cursor.fetchall()]
        return (
            f"No products found in the '{category}' category. "
            f"Available categories: {', '.join(categories)}."
        )

    in_stock = [r for r in rows if r[6] > 0]
    out_of_stock = [r for r in rows if r[6] == 0]

    lines = [f"Products in '{category}' category:"]
    if in_stock:
        lines.append("\n**In Stock:**")
        for name, active_ingredients, dosage, dosage_form, rx, controlled, stock, price in in_stock:
            rx_flag = "⚠️ Rx (Controlled)" if controlled else ("⚠️ Rx" if rx else "OTC")
            dosage_str = f"{dosage} " if dosage else ""
            lines.append(
                f"• {name.title()} | {active_ingredients} | {dosage_str}{dosage_form} | "
                f"{rx_flag} | {stock} units | GH\u20b5{price:.2f}"
            )
    if out_of_stock:
        lines.append("\n**Out of Stock:**")
        for name, active_ingredients, dosage, dosage_form, rx, controlled, stock, price in out_of_stock:
            rx_flag = "⚠️ Rx (Controlled)" if controlled else ("⚠️ Rx" if rx else "OTC")
            dosage_str = f"{dosage} " if dosage else ""
            lines.append(f"• {name.title()} | {active_ingredients} | {dosage_str}{dosage_form} | {rx_flag}")
    return "\n".join(lines)


def suggest_alternatives(ctx: RunContext[PharmacyDeps], product_name: str) -> str:
    """Suggest in-stock alternatives when a product is out of stock.

    Use this proactively when a product is out of stock to offer drugs in the
    same therapeutic class before ending your response.

    Args:
        product_name: The name of the product to find alternatives for, e.g. "amoxicillin".

    Returns:
        A formatted list of in-stock alternatives, or a message if none exist.
    """
    name = product_name.lower().strip()
    cursor = ctx.deps.db_conn.cursor()
    cursor.execute(
        "SELECT category, stock FROM inventory WHERE product_name = ?", (name,)
    )
    row = cursor.fetchone()

    if row is None:
        return f"Product '{product_name}' not found in our inventory."

    category, stock = row
    if stock > 0:
        return (
            f"{product_name.title()} is currently in stock ({stock} units available) — "
            "no substitution needed."
        )

    cursor.execute(
        """
        SELECT product_name, active_ingredients, dosage, dosage_form,
               requires_prescription, is_controlled, stock, price
        FROM inventory
        WHERE category = ? AND product_name != ? AND stock > 0
        ORDER BY price ASC
        """,
        (category, name),
    )
    alternatives = cursor.fetchall()

    if not alternatives:
        return (
            f"{product_name.title()} is currently out of stock and we have no "
            f"in-stock alternatives in the '{category}' category at this time."
        )

    lines = [
        f"{product_name.title()} is out of stock. "
        f"Here are in-stock alternatives in the '{category}' category:"
    ]
    for alt_name, active_ingredients, dosage, dosage_form, rx, controlled, alt_stock, price in alternatives:
        rx_flag = "⚠️ Rx (Controlled)" if controlled else ("⚠️ Rx" if rx else "OTC")
        dosage_str = f"{dosage} " if dosage else ""
        lines.append(
            f"• {alt_name.title()} | {active_ingredients} | {dosage_str}{dosage_form} | "
            f"{rx_flag} | {alt_stock} units | GH\u20b5{price:.2f}"
        )
    return "\n".join(lines)


def get_customer_orders(ctx: RunContext[PharmacyDeps], customer_name: str) -> str:
    """Look up all orders associated with a customer name.

    Use this when a customer asks about their order history or past purchases
    by name. Do not ask for an order ID in this case.

    Args:
        customer_name: Full or partial customer name, e.g. "Kwame Asante".

    Returns:
        A formatted summary of all matching orders, or a not-found message.
    """
    cursor = ctx.deps.db_conn.cursor()
    cursor.execute(
        """
        SELECT order_id, status, expected_delivery, items
        FROM orders
        WHERE LOWER(customer_name) LIKE LOWER(?)
        ORDER BY order_id DESC
        """,
        (f"%{customer_name}%",),
    )
    rows = cursor.fetchall()

    if not rows:
        return (
            f"No orders found for '{customer_name}'. "
            "Please confirm the name as registered with us."
        )

    lines = [f"Orders for '{customer_name}':"]
    for order_id, status, delivery, items_json in rows:
        items = json.loads(items_json)
        delivery_str = delivery or "N/A (cancelled)"
        lines.append(
            f"\n• {order_id} — {status} | Expected: {delivery_str}"
            f"\n  Items: {', '.join(items)}"
        )
    return "\n".join(lines)


def generate_invoice(
    ctx: RunContext[PharmacyDeps], items: dict[str, int]
) -> str:
    """Generate a total price and a downloadable PDF invoice for requested items.

    Use this when a user has decided on items to purchase and wants to 
    see the total cost or explicitly asks for an invoice/receipt.

    Args:
        items: A dictionary of product names to integer quantities requested. 
               e.g., {"vitamin c": 2, "ibuprofen": 1}

    Returns:
        A Markdown formatted table summarizing the invoice. 
        The actual PDF file will be attached to the chat automatically.
    """
    cursor = ctx.deps.db_conn.cursor()
    
    line_items = []
    grand_total = 0.0
    errors = []

    for item_name, req_qty in items.items():
        clean_name = item_name.lower().strip()
        
        # Check stock and price
        cursor.execute(
            "SELECT stock, price FROM inventory WHERE product_name = ?", 
            (clean_name,)
        )
        row = cursor.fetchone()
        
        if not row:
            errors.append(f"Product not found: '{item_name}'")
            continue
            
        stock, price = row
        if stock < req_qty:
            errors.append(
                f"Cannot fulfill '{item_name}': {req_qty} requested, but only {stock} in stock."
            )
            continue
            
        line_total = price * req_qty
        grand_total += line_total
        line_items.append({
            "name": item_name.title(),
            "qty": req_qty,
            "price": price,
            "total": line_total
        })

    if errors and not line_items:
        return "Invoice generation failed:\n" + "\n".join(errors)
        
    error_msg = ""
    if errors:
        error_msg = "\n**Note:** Some items could not be included:\n- " + "\n- ".join(errors) + "\n\n"

    # 1. Generate Markdown Table for LLM
    md_lines = [
        "### Invoice Summary",
        "| Item | Qty | Unit Price (GHS) | Total (GHS) |",
        "|---|---|---|---|"
    ]
    for item in line_items:
        md_lines.append(f"| {item['name']} | {item['qty']} | GH₵{item['price']:.2f} | GH₵{item['total']:.2f} |")
    md_lines.append(f"| **Grand Total** | | | **GH₵{grand_total:.2f}** |")
    
    markdown_table = error_msg + "\n".join(md_lines)

    # 2. Generate PDF using fpdf2
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("helvetica", "B", 20)
    pdf.cell(0, 15, "Pharmacy Support Invoice", new_x="LMARGIN", new_y="NEXT", align="C")
    
    # Date
    pdf.set_font("helvetica", "", 12)
    today = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    pdf.cell(0, 10, f"Date: {today}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Table Header
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(70, 10, "Item")
    pdf.cell(30, 10, "Qty", align="C")
    pdf.cell(40, 10, "Unit Price", align="R")
    pdf.cell(50, 10, "Total (GHS)", align="R", new_x="LMARGIN", new_y="NEXT")
    
    # Add a line
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    
    # Table Rows
    pdf.set_font("helvetica", "", 12)
    for item in line_items:
        pdf.cell(70, 10, item["name"])
        pdf.cell(30, 10, str(item["qty"]), align="C")
        pdf.cell(40, 10, f"GHS {item['price']:.2f}", align="R")
        pdf.cell(50, 10, f"GHS {item['total']:.2f}", align="R", new_x="LMARGIN", new_y="NEXT")
    
    # Add a line
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    
    # Grand Total
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(140, 10, "Grand Total:", align="R")
    pdf.cell(50, 10, f"GHS {grand_total:.2f}", align="R", new_x="LMARGIN", new_y="NEXT")
    
    # Save PDF to temporary file
    temp_dir = tempfile.gettempdir()
    pdf_path = os.path.join(temp_dir, "invoice.pdf")
    pdf.output(pdf_path)

    # 3. Inject PDF directly into UI
    try:
        cl.run_sync(
            cl.Message(
                content="🧾 *Invoice generated automatically.*",
                elements=[cl.File(name="Invoice.pdf", path=pdf_path, display="inline")]
            ).send()
        )
    except Exception as e:
        print(f"Failed to inject invoice PDF into UI: {e}")

    return markdown_table