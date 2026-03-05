# 💊 Pharmacy Support Agent

![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg)
![Pydantic AI](https://img.shields.io/badge/Framework-Pydantic_AI-FF4B4B.svg)
![Chainlit](https://img.shields.io/badge/UI-Chainlit-F9A826.svg)
![Gemini 2.5](https://img.shields.io/badge/LLM-Gemini_2.5_Flash-8E75B2.svg)
![Logfire](https://img.shields.io/badge/Observability-Logfire-000000.svg)

An AI-powered **multi-agent** customer support chatbot for an online pharmacy. Features intelligent query routing, streaming responses, prescription upload via OCR, interactive quick-actions, a secure **Text-to-SQL admin mode**, and **voice input/output** — built with pydantic-ai and Chainlit.

![Pharmacy Support Agent Demo](docs/demo.png)

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.13+ |
| Agent Framework | [Pydantic AI](https://ai.pydantic.dev/) |
| LLM | Google Gemini 2.5 Flash |
| UI | [Chainlit](https://docs.chainlit.io/) |
| Database | SQLite |
| Observability | [Pydantic Logfire](https://logfire.pydantic.dev/) |

## Features

- **Multi-Agent Architecture** — Triage agent routes queries to specialised support and pharmacist agents, each with their own persistent conversation history
- **Dual Persona Modes** — Toggle between Customer Support and Admin Analyst via Chat Settings
- **Prescription Upload (OCR)** — Upload a prescription image or PDF; Gemini Vision extracts medications, checks stock, and prepares an invoice automatically
- **Richer Inventory Queries** — Search by partial name or active ingredient, browse by therapeutic category, and get proactive substitution suggestions when a product is out of stock
- **Prescription Safety Warnings** — Every Rx drug triggers a mandatory prescription reminder; controlled drugs (e.g. Tramadol, Librium) display an additional ⛔ warning
- **Order Tracking** — Look up order status, items, and expected delivery by order ID or customer name
- **Automated Invoicing** — Calculates totals in GHS and generates a downloadable PDF attached inline to the chat
- **Drug Interaction Checker** — Checks potential interactions between two medications via the openFDA API
- **FDA Drug Warnings** — Fetches official FDA boxed warnings for specific medications
- **Voice Mode** — Speak questions via microphone (Gemini STT) and hear answers read aloud (gTTS)
- **Text-to-SQL** — Admin mode converts natural language to SQL queries against the pharmacy database
- **Streaming Responses** — Word-by-word output for a responsive chat experience
- **Human-in-the-Loop Cancellation** — Order cancellations require explicit confirmation via UI action buttons
- **SQL Safety Guardrails** — Admin queries restricted to SELECT-only; all write operations blocked
- **Medical Safety Guardrails** — Declines diagnosis/prescription requests and directs users to healthcare professionals
- **Observability** — Full tracing of agent runs, tool calls, and SQLite queries via Logfire

## Architecture

```mermaid
flowchart LR
    A[User Input] --> B[Triage Agent]
    B -->|orders/inventory/FDA/Rx| C[Support Agent]
    B -->|drug education/wellness| D[Pharmacist Agent]
    A -->|Admin mode| SQ[SQL Agent]
    C --> E["Tools (DB + API)"]
    E --> F[(SQLite)]
    E --> G[openFDA API]
    SQ -->|SELECT queries| F
    C --> B
    D --> B
    B --> H[Chainlit Chat UI]
    H -.->|traces| I[Logfire]
```

1. User sends a message (or voice recording, or prescription file) via Chainlit
2. Based on the active persona (set via Chat Settings):
   - **Customer mode** → triage agent routes to Support or Pharmacist, each maintaining their own conversation history
   - **Admin mode** → SQL agent generates and executes read-only queries directly
3. Customer queries are routed to the appropriate specialist:
   - **Support agent** → orders, inventory, Rx safety, invoicing, FDA warnings, drug interactions
   - **Pharmacist agent** → drug education, general wellness, medication information
4. The specialist's response is streamed back word-by-word

## Project Structure

```
pharmacy-agent/
├── agents.py              # Agent definitions (triage, support, pharmacist, SQL)
├── app.py                 # Chainlit UI, persona toggle, streaming, voice, prescription upload
├── init_db.py             # Database schema + real product seed data (74 products)
├── tools.py               # Tool functions & PharmacyDeps dependency class
├── data/
│   └── Products_Database_Clean.xlsx   # Source product data (pre-processed into init_db.py)
├── docs/
│   ├── demo.png
│   └── original-spec.md   # Original POC brief (historical)
├── tests/
│   ├── conftest.py
│   ├── test_tools.py      # 28 unit tests for all tool functions
│   ├── test_app.py
│   └── test_prescription.py
├── .env.example           # Template — copy to .env and fill in your keys
├── chainlit.md            # In-app welcome message
├── pyproject.toml         # Project config & dependencies
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- A [Google AI Studio](https://aistudio.google.com/apikey) API key

### Setup

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd pharmacy-agent
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Configure your API key**
   ```bash
   cp .env.example .env
   # Edit .env and replace the placeholder with your actual key
   ```

4. **Initialise the database**
   ```bash
   uv run python init_db.py
   ```

5. **Run the app**
   ```bash
   uv run chainlit run app.py -w
   ```

   The app opens at [http://localhost:8000](http://localhost:8000).

### Logfire (Optional)

To enable observability tracing, authenticate with Logfire:

```bash
uv run logfire auth
uv run logfire projects use <your-project>
```

Traces will appear at your [Logfire dashboard](https://logfire.pydantic.dev/).

## Available Tools

### Support Agent Tools

| Tool | Parameter(s) | Source | Description |
|---|---|---|---|
| `check_inventory` | `product_name` | SQLite | Returns stock, dosage, active ingredients, category, and Rx/controlled drug warnings |
| `search_inventory` | `query` | SQLite | Partial name or active-ingredient search; returns up to 6 matches |
| `get_drugs_by_category` | `category` | SQLite | Lists all products in a therapeutic category (in-stock / OOS) |
| `suggest_alternatives` | `product_name` | SQLite | When OOS, finds in-stock alternatives in the same drug class |
| `get_customer_orders` | `customer_name` | SQLite | Returns full order history for a customer by name (partial match) |
| `get_order_status` | `order_id` | SQLite | Returns status, items, and expected delivery date for a specific order |
| `prepare_order_cancellation` | `order_id` | SQLite | Checks eligibility and stages an order for HITL cancellation |
| `generate_invoice` | `items` | SQLite / fpdf2 | Calculates total in GHS and generates a downloadable PDF invoice |
| `get_fda_warnings` | `drug_name` | openFDA API | Returns FDA boxed warnings for a medication |
| `check_drug_interactions` | `drug_name_1`, `drug_name_2` | openFDA API | Returns interaction data for two medications |

### Admin Agent Tools

| Tool | Parameter(s) | Source | Description |
|---|---|---|---|
| `execute_sql_query` | `sql_query` | SQLite | Executes read-only SELECT queries against the pharmacy database |

## Inventory

The database is seeded with **74 real products** from Letap Pharmaceuticals and partner brands. Each product includes:

| Field | Description |
|---|---|
| `product_name` | Lowercase product name (primary key) |
| `brand` | Brand name (e.g. Letap, Ecl, Exeter) |
| `active_ingredients` | Full active ingredient list |
| `dosage` | Strength (e.g. "250mg", "125mg/5ml") |
| `dosage_form` | Form (Tablet, Capsule, Suspension, Syrup, Solution) |
| `category` | Simplified therapeutic class (e.g. Antibiotic, Antimalarial) |
| `atc_code` | Full ATC classification string |
| `requires_prescription` | 1 = Rx required, 0 = OTC |
| `is_controlled` | 1 = controlled drug (e.g. Tramadol, Librium) |
| `stock` | Units currently in stock |
| `unit` | Pack unit (Blister, Box, Bottle, Packet) |
| `price` | Sales price in GHS |
| `cost` | Cost price in GHS |

**Category breakdown:** Antibiotic (37), Vitamin/Supplement (9), Antiprotozoal (4), Antianemic (4), Antimalarial (3), Anti-Inflammatory (3), Psycholeptic (2), Antihistamine (2), Antifungal (2), Antacid/GI (2), Analgesic (2), Opioid Analgesic (1), Corticosteroid (2), Respiratory (2), Nutritional Supplement (1).

## Example Queries

### Customer Support Mode

| Query | Tool(s) Used | Expected Behaviour |
|---|---|---|
| *"What's the status of ORD-101?"* | `get_order_status` | Returns status, items, delivery date |
| *"Show all my orders — Kwame Asante"* | `get_customer_orders` | Returns full order history by name |
| *"Do you have Augmentin?"* | `search_inventory` | Partial match finds amoxicillin + clavulanate products |
| *"Is tramadol available?"* | `check_inventory` | Stock count + ⚠️ Rx required + ⛔ Controlled Drug warning |
| *"What malaria drugs do you carry?"* | `get_drugs_by_category` | Lists all Antimalarial products with stock and price |
| *"Ampicillin caps are OOS — what else do you have?"* | `suggest_alternatives` | Lists in-stock alternatives in the Antibiotic category |
| *"Can I take co-trimoxazole and metronidazole together?"* | `check_drug_interactions` | Returns FDA interaction data |
| *"What are the FDA warnings for chloramphenicol?"* | `get_fda_warnings` | Returns official FDA boxed warnings |
| *"I'd like 2x ampicillin susp and 1x paracetamol syr"* | `generate_invoice` | Confirms items → generates PDF invoice in GHS |
| *"What is metronidazole generally used for?"* | Pharmacist Agent | Educational info + disclaimer |
| *"What should I take for malaria?"* | Pharmacist Agent | Guardrail activates → declines, directs to doctor |

### Admin Analyst Mode

| Query | Description |
|---|---|
| *"How many orders per status?"* | Counts orders grouped by status |
| *"Which products are out of stock?"* | Lists products with stock = 0 |
| *"Show all controlled drugs in inventory"* | Filters by is_controlled = 1 |
| *"What is our total stock value at cost?"* | Sums stock × cost across all products |
| *"Show all Rx-only antibiotics with stock > 50"* | Filters by category, requires_prescription, stock |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Google AI Studio key (Gemini LLM + STT) |
| `LOGFIRE_TOKEN` | No | Pydantic Logfire token for observability tracing |

## Running Tests

```bash
uv run pytest tests/ -v
```

28 unit tests covering all tool functions with an in-memory SQLite fixture.

## License

This project is a Proof of Concept for demonstration purposes.
