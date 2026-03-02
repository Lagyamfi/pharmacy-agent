"""Agent definitions for the Pharmacy Support Agent.

Defines a multi-agent system with a triage agent that delegates
to specialised support and pharmacist agents, plus an admin SQL
analyst agent for text-to-SQL queries.
"""

import re
import json
from pydantic_ai import Agent, RunContext

from tools import (
    PharmacyDeps,
    get_order_status,
    check_inventory,
    get_fda_warnings,
    check_drug_interactions,
    prepare_order_cancellation,
    generate_invoice,
)

# ─── Support Agent ─────────────────────────────────────────────────
# Handles transactional queries: orders, inventory, FDA warnings, interactions.

support_agent = Agent(
    "google-gla:gemini-2.5-flash",
    deps_type=PharmacyDeps,
    instructions="""\
You are the customer support specialist for an online pharmacy.
Your job is to help customers with order tracking, product availability,
FDA drug warnings, drug interaction checks, and generating invoices.

RULES:
1. Always use your tools — never guess order statuses, stock levels, or prices.
2. If a customer asks about an order but doesn't give an order ID, ask for it.
3. Be concise, professional, and friendly.
4. When a user requests to buy items or asks for an invoice, ALWAYS use the generate_invoice tool to calculate totals and create a PDF.
5. All prices are in GHS (Ghanaian Cedi).
6. Before calling generate_invoice, ALWAYS confirm the final list of items and their quantities with the user.\
""",
)

support_agent.tool(get_order_status)
support_agent.tool(check_inventory)
support_agent.tool_plain(get_fda_warnings)
support_agent.tool_plain(check_drug_interactions)
support_agent.tool(prepare_order_cancellation)
support_agent.tool(generate_invoice)


# ─── Pharmacist Agent ──────────────────────────────────────────────
# Handles pharmacological knowledge questions with strict guardrails.

pharmacist_agent = Agent(
    "google-gla:gemini-2.5-flash",
    instructions="""\
You are a knowledgeable pharmacy information assistant.
You provide factual, publicly available information about over-the-counter
medications, general drug education, and wellness topics.

STRICT GUARDRAILS:
1. You are NOT a doctor. Never diagnose, prescribe, or recommend treatments.
2. If asked "What should I take for [symptom]?", decline and advise the user
   to consult a healthcare professional.
3. You MAY provide general factual info like: what a drug is used for,
   common OTC categories, how medications are generally classified.
4. Always add a disclaimer that the user should verify with a pharmacist
   or doctor for their specific situation.\
""",
)


# ─── Triage Agent ──────────────────────────────────────────────────
# Orchestrator that routes queries to the appropriate specialist.

triage_agent = Agent(
    "google-gla:gemini-2.5-flash",
    deps_type=PharmacyDeps,
    system_prompt="""\
You are the front-desk triage assistant for an online pharmacy.
Your ONLY job is to route customer queries to the right specialist
using your tools and relay their response.

ROUTING RULES:
- Order tracking, shipping, delivery, order status → use ask_support_agent
- Product availability, stock checks → use ask_support_agent
- FDA warnings, drug interactions → use ask_support_agent
- Drug information, medication questions, how a drug works,
  side effects education, wellness → use ask_pharmacist_agent
- If the query is a simple greeting, respond directly with a brief,
  friendly welcome.

CRITICAL RULES:
1. You must use one of your tools for any substantive question.
2. Forward the customer's full question to the appropriate agent.
3. After receiving the tool response, relay it EXACTLY to the customer.
   DO NOT add your own commentary like "I've forwarded your question".
   Simply present the sub-agent's answer as your own response.\
""",
)


@triage_agent.tool
async def ask_support_agent(
    ctx: RunContext[PharmacyDeps], customer_query: str
) -> str:
    """Route to the support agent for order tracking, inventory checks,
    FDA warnings, and drug interaction queries.

    Args:
        customer_query: The customer's full question, forwarded as-is.
    """
    result = await support_agent.run(
        customer_query,
        deps=ctx.deps,
        usage=ctx.usage,
    )
    return result.output


@triage_agent.tool_plain
async def ask_pharmacist_agent(customer_query: str) -> str:
    """Route to the pharmacist agent for medication information,
    drug education, and general wellness questions.

    Args:
        customer_query: The customer's full question, forwarded as-is.
    """
    result = await pharmacist_agent.run(
        customer_query,
    )
    return result.output


# ─── SQL Analyst Agent ─────────────────────────────────────────────
# Admin-only agent for text-to-SQL analytical queries.

DB_SCHEMA = """\
TABLE: orders
  - order_id     TEXT PRIMARY KEY   (e.g. "ORD-101")
  - status       TEXT NOT NULL      (Shipped | Processing | Delivered | Cancelled)
  - expected_delivery TEXT          (date string or NULL if cancelled)
  - items        TEXT NOT NULL      (JSON array of item strings)

TABLE: inventory
  - product_name TEXT PRIMARY KEY   (lowercase, e.g. "ibuprofen")
  - stock        INTEGER NOT NULL   (0 = out of stock)
"""

# Regex to detect non-SELECT statements
_UNSAFE_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|ATTACH|DETACH|PRAGMA)\b",
    re.IGNORECASE,
)

sql_agent = Agent(
    "google-gla:gemini-2.5-flash",
    deps_type=PharmacyDeps,
    system_prompt=f"""\
You are an expert SQL analyst for an online pharmacy's database.
Your job is to convert natural language questions into SQL queries
and execute them to provide answers.

DATABASE SCHEMA:
{DB_SCHEMA}

RULES:
1. Generate ONLY SELECT queries. Never modify data.
2. Use the execute_sql_query tool to run your SQL.
3. If a query returns no results, say so clearly.
4. Present results in a clean, readable format.
5. The 'items' column in orders is a JSON array — use LIKE for searching.
6. Product names in inventory are lowercase.
7. If the user's question is ambiguous, ask for clarification.\
""",
)


@sql_agent.tool
async def execute_sql_query(
    ctx: RunContext[PharmacyDeps], sql_query: str
) -> str:
    """Execute a read-only SQL query against the pharmacy database.

    Args:
        sql_query: A SELECT SQL query to execute.

    Returns:
        Query results formatted as a JSON string, or an error message.
    """
    # Safety: block any non-SELECT statement
    if _UNSAFE_SQL_PATTERN.search(sql_query):
        return "⛔ BLOCKED: Only SELECT queries are allowed. Write operations are forbidden."

    sql_stripped = sql_query.strip().rstrip(";")
    if not sql_stripped.upper().startswith("SELECT"):
        return "⛔ BLOCKED: Query must begin with SELECT."

    try:
        cursor = ctx.deps.db_conn.cursor()
        cursor.execute(sql_stripped)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()

        if not rows:
            return "Query returned 0 rows."

        # Format as list of dicts for clean output
        result_list = [dict(zip(columns, row)) for row in rows]
        return json.dumps(result_list, indent=2, default=str)

    except Exception as e:
        return f"SQL Error: {str(e)}"
