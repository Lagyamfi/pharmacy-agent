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