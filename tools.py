"""Tool functions for the Pharmacy Support Agent.

These are registered with the pydantic-ai Agent so the LLM can 
invoke them through function calling.
"""

import json
import requests
import sqlite3
from dataclasses import dataclass
from pydantic_ai import RunContext

# 1. Define the Dependency object that holds our database connection
@dataclass
class PharmacyDeps:
    db_conn: sqlite3.Connection


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
    cursor.execute("SELECT stock FROM inventory WHERE product_name = ?", (name,))
    result = cursor.fetchone()

    if result is None:
        return (
            f"Product '{product_name}' was not found in our inventory. "
            "Please check the product name and try again."
        )

    stock = result[0]
    if stock == 0:
        return f"{product_name.title()} is currently out of stock."

    return f"{product_name.title()} is in stock with {stock} units available."


# 4. No context needed here, it just hits the internet!
def get_fda_warnings(drug_name: str) -> str:
    """
    Use this when a customer asks about the side effects, risks, or FDA warnings 
    of a specific medication.
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
    import json

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
    import os
    import tempfile
    import datetime
    import chainlit as cl
    from fpdf import FPDF
    
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