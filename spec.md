# Project Specification: E-Commerce Pharmacy AI Agent (POC)

## 1. Project Overview
Build a Python-based Proof of Concept (POC) for a customer-facing AI chatbot used by an online pharmacy. The agent must intelligently route user queries using **LLM Tool Calling (Function Calling)**.

It handles two distinct tracks:
* **General Inquiries:** Answers general policy or basic pharmacological questions using its base knowledge, strictly adhering to medical safety guardrails.
* **Transactional Inquiries:** Uses defined tools to query mock internal databases for order statuses and inventory levels.

---

## 2. Tech Stack Requirements
* **Language:** Python 3.10+
* **UI Framework:** Streamlit (`streamlit`)
* **Agent Framework:** Pydantic AI (`pydantic-ai`)
* **LLM Integration:** Configured directly through Pydantic AI's model settings (e.g., `gemini-2.5-flash`, `gpt-4o`, or `claude-3-5-sonnet`). *Note to AI coder: Default to the API environment variables available in the workspace.*
* **Data Storage:** In-memory Python dictionaries (Mock Data).

---

## 3. Core Architecture & Application Flow



The application must leverage Pydantic AI to orchestrate the LLM and tool execution, completely replacing manual function routing. The flow is as follows:

1. **Agent Initialization:** Define a globally accessible Pydantic AI `Agent` instance containing the System Prompt.
2. **Tool Registration:** Register the mock database functions using the `@agent.tool` decorator. Pydantic AI will automatically generate the JSON schemas based on the Python type hints.
3. **Streamlit UI Loop:**
    * Capture user input via Streamlit's `st.chat_input`.
    * Append user input to the session's message history (`st.session_state.messages`).
4. **Agent Execution:**
    * Pass the user prompt and the current conversation history to the agent using `agent.run_sync()` (or `agent.run()`).
    * *Crucial:* Allow Pydantic AI to automatically handle the internal loop of triggering tools, validating parameters, executing the Python functions, and feeding the data back to the LLM.
5. **Response Rendering:**
    * Extract the final natural language response from the agent's `RunResult`.
    * Display the text to the user via `st.chat_message`.
    * Save the newly updated, complete message history (including the hidden tool calls) back to `st.session_state` so the agent maintains context for the next turn.
---

## 4. Mock Data Definitions
Create a separate module or section for mock data.

**Orders Database (`mock_orders` dict):**
* **Keys:** Order IDs (e.g., `"ORD-123"`, `"ORD-456"`).
* **Values:** Dictionaries containing `status` (e.g., `"Shipped"`, `"Processing"`, `"Cancelled"`), `items` (list of strings), and `expected_delivery` (date string).

**Inventory Database (`mock_inventory` dict):**
* **Keys:** Product names (lowercase, e.g., `"ibuprofen"`, `"vitamin c"`, `"melatonin"`).
* **Values:** Integer representing current stock level.

---

## 5. Tool / Function Definitions
The LLM must be provided with these two explicit tools:

| Function Name | Parameters | Description / Purpose |
| :--- | :--- | :--- |
| `get_order_status` | `order_id` (string, required) | Use this when a customer asks about tracking, shipping, or the status of their purchase. Returns the status, items, and delivery date. |
| `check_inventory` | `product_name` (string, required) | Use this when a customer asks if a specific item is in stock or available to buy. Returns the current stock count. |

> **Requirement:** The functions must handle edge cases gracefully (e.g., if `order_id` is not in the dictionary, return *"Order not found. Please verify the ID."*).

---

## 6. System Prompt & Guardrails
The LLM must be initialized with the following system instructions:

> "You are a helpful, professional customer support assistant for an online e-commerce pharmacy.
> 
> **CRITICAL GUARDRAILS:**
> 1. **NO MEDICAL ADVICE:** You are NOT a doctor. If a user asks for diagnoses, symptom checking, or medical advice (e.g., 'What should I take for a rash?'), you MUST decline and advise them to consult a healthcare professional. You may only provide factual, publicly available information about over-the-counter products if asked generally.
> 2. **TOOL USAGE:** Always use your provided tools to look up specific order statuses or inventory. Never guess or hallucinate stock levels or order updates.
> 3. **MISSING INFO:** If a user asks to check an order but doesn't provide the order number, ask them for it before attempting to use the tool."

---

## 7. Streamlit UI Requirements
* **Page title:** "Pharmacy Support Agent".
* Maintain chat history using `st.session_state.messages`.
* Display user messages and assistant messages using `st.chat_message`.
* Show a loading spinner (`st.spinner`) while the LLM is generating a response or executing a tool.