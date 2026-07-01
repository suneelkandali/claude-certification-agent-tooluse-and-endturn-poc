# Claude Agentic Loop Demo

A minimal, self-contained demonstration of the **Anthropic tool-use agentic loop** pattern in Python.

The agent answers customer questions about orders by calling a `lookup_order` tool (currently backed by mock data). It showcases:

- The **request → tool-call → result → continue** loop
- **Structured error categories** (`transient`, `permission`, `validation`, `internal`) that let Claude decide how to respond
- Proper message history construction required by the Anthropic Messages API

---

## Project Structure

```
claude-certification-agent-tooluse-and-endturn-poc/
├── agent.py          # The agentic loop implementation
├── api_check.py      # (optional) quick API connectivity test
├── requirements.txt  # Python dependencies
├── .env              # Your ANTHROPIC_API_KEY (not committed)
└── README.md         # This file
```

---

## Prerequisites

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)

---

## Setup

1. **Clone the repo** (or copy the files to your machine).

2. **Create a virtual environment** (recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate    # macOS / Linux
   venv\Scripts\activate       # Windows
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set your API key:**

   Create a `.env` file in the project root:

   ```env
   ANTHROPIC_API_KEY=sk-ant-...
   ```

   The code loads it automatically via `python-dotenv`.

---

## Run

```bash
python agent.py
```

You should see output similar to:

```
running agent....
Calling tool: lookup_order with input: {'order_id': '#4821'}
Final Answer: Your order #4821 has been shipped and is expected to arrive on 2024-07-05 via UPS.
```

---

## How It Works

The agent follows a simple loop:

```
┌─────────────────────────────────────────────────┐
│  1. Send messages (including any tool results)  │
│     to Claude via client.messages.create()      │
└───────────────────────┬─────────────────────────┘
                        │
                        ▼
           ┌─────────────────────┐
           │   response has      │
           │   stop_reason = ?   │
           └─────────┬───────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
   "end_turn"              "tool_use"
         │                       │
   Return text           ┌───────┴───────┐
                         │ 1. Append     │
                         │ assistant     │
                         │ response      │
                         │ 2. Execute    │
                         │ each tool     │
                         │ 3. Append     │
                         │ tool_results  │
                         │ as user msg   │
                         └───────┬───────┘
                                 │
                         Loop back to top
```

### Key Concepts

| Concept | Explanation |
|---------|-------------|
| **`tools`** | A list of tool definitions that describes to Claude what tools exist, when to use them, and what parameters they need. |
| **`stop_reason`** | Tells you why Claude stopped generating: `"end_turn"` means the answer is ready; `"tool_use"` means Claude wants to call one or more tools. |
| **`tool_use` block** | A content block in Claude's response containing `name` (which tool), `id` (unique identifier), and `input` (the parameters). |
| **`tool_result` block** | A content block you send back in a user message, containing `tool_use_id` (matching the `id` from the `tool_use` block) and `content` (the tool's output). |
| **Message ordering** | The API requires that `tool_result` blocks always appear in a **user** message that immediately follows an **assistant** message containing the corresponding `tool_use` blocks. |

### Error Categories

When a tool fails, `handle_tool_call()` wraps the error with a category so Claude can react intelligently:

| Category | Meaning | Claude's likely action |
|----------|---------|----------------------|
| `transient` | Temporary glitch (timeout) | Wait and retry |
| `permission` | Access denied | Escalate to human |
| `validation` | Bad parameters | Self-correct and retry |
| `internal` | Unexpected bug | Surface for investigation |

---

## Customising

- **Add more tools** — Extend the `tools` list and add `elif` branches in `execute_tool()`.
- **Replace mock data** — Swap the `mock_orders` dict in `execute_tool()` with a real database or API call.
- **Change the model** — Update the `model` parameter in `client.messages.create()` (e.g. `"claude-sonnet-4-20250514"`).

---

## Resources

- [Anthropic Tool Use Documentation](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [Anthropic Messages API Reference](https://docs.anthropic.com/en/api/messages)
