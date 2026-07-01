import anthropic
import json
from dotenv import load_dotenv

# ============================================================
# Load environment variables (e.g. ANTHROPIC_API_KEY) from .env
# ============================================================
load_dotenv()

# Initialise the Anthropic client; reads ANTHROPIC_API_KEY from env automatically
client = anthropic.Anthropic()


# ============================================================
# Tool Definition
# Describe to Claude what tools are available and how to call them.
# Each tool has:
#   - name:        How Claude refers to the tool in its response
#   - description: Tells Claude *when* to use this tool
#   - input_schema: The JSON Schema the model must fill in when calling
# ============================================================
tools = [
    {
        "name": "lookup_order",
        "description": (
            "Look up an order by its order ID or order number. "
            "Returns current status, estimated delivery date and carrier name. "
            "Use this when the customer asks where their order is or when it will arrive"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID or order number to look up (e.g. #1111)"
                }
            },
            "required": ["order_id"]
        }
    }
]


# ============================================================
# Tool Execution Layer
# Takes a tool name + input dict, runs the real logic, and
# returns a JSON string result that will be sent back to Claude.
# ============================================================
def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Run a tool and return its result as a JSON string."""
    if tool_name == "lookup_order":
        order_id = tool_input.get("order_id", "")

        # TODO: Replace with a real database/API call in production
        # For now we simulate an order lookup with mock data.
        mock_orders = {
            "#4821": {
                "status": "Shipped",
                "estimated_delivery": "2024-07-05",
                "carrier": "UPS"
            },
            "#9910": {
                "status": "Processing",
                "estimated_delivery": "2026-07-10",
                "carrier": "UPS"
            },
            "#8042": {
                "status": "delivered",
                "estimated_delivery": "2026-06-10",
                "carrier": "FedEx"
            }
        }

        if order_id in mock_orders:
            return json.dumps(mock_orders[order_id])
        else:
            return json.dumps({"error": f"Order {order_id} not found"})

    # If we reach here, Claude called a tool name we don't recognise
    return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ============================================================
# Tool Call Handler (with structured error categories)
# Wraps execute_tool() with error handling that categorises failures.
#
# Error categories (from the Anthropic pattern guide):
#   transient   - Infrastructure hiccup (e.g. timeout); safe to retry
#   permission  - Access denied; escalate, do NOT retry
#   validation  - Bad params sent by the model; self-correct before retry
#   internal    - Unexpected bug; surface for human investigation
#
# Claude reads the errorCategory and decides how to respond.
# ============================================================
def handle_tool_call(tool_name: str, tool_id: str, tool_input: dict) -> dict:
    """
    Execute one tool call and return a complete tool_result dict
    that the Messages API expects inside a user message.
    """
    print(f"Calling tool: {tool_name} with input: {tool_input}")

    try:
        # --- Happy path: tool runs successfully ---
        content = execute_tool(tool_name, tool_input)
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": content,
        }

    except TimeoutError as e:
        # transient – retryable after a short delay
        print(f"ERROR: TimeoutError on {tool_name}")
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "is_error": True,
            "content": json.dumps({
                "errorCategory": "transient",
                "isRetryable": True,
                "description": f"Timeout calling {tool_name}: {str(e)}",
                "retryAfterMs": 2000
            }),
        }

    except PermissionError as e:
        # permission – agent lacks access; escalate, do NOT retry
        print(f"ERROR: PermissionError on {tool_name}")
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "is_error": True,
            "content": json.dumps({
                "errorCategory": "permission",
                "isRetryable": False,
                "description": f"Permission denied calling {tool_name}: {str(e)}"
            }),
        }

    except ValueError as e:
        # validation – Claude sent bad params; it should self-correct
        print(f"ERROR: ValueError on {tool_name}")
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "is_error": True,
            "content": json.dumps({
                "errorCategory": "validation",
                "isRetryable": False,
                "description": f"Invalid parameters calling {tool_name}: {str(e)}"
            }),
        }

    except Exception as e:
        # internal – unexpected error; surface to the developer / human
        print(f"  ← ERROR: {type(e).__name__} on {tool_name}")
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "is_error": True,
            "content": json.dumps({
                "errorCategory": "internal",
                "isRetryable": False,
                "description": f"Unexpected error in {tool_name}: {str(e)}",
            }),
        }


# ============================================================
# Main Agent Loop
#
# The agentic loop works as follows:
#   1. Send the current message history (including any tool results)
#      to the Anthropic API.
#   2. Examine the response's stop_reason:
#       a) "end_turn"  → Claude is done; return the final text.
#       b) "tool_use"  → Claude wants to call one or more tools.
#          i.   Append the assistant's tool_use response to history.
#          ii.  Execute each tool and collect results.
#          iii. Append a user message containing the tool_results.
#          iv.  Loop back to step 1 so Claude can continue.
#   3. If Claude never finishes after MAX_ITERATIONS, bail out.
# ============================================================
def run_agent(user_message: str) -> str:
    """
    Run the agentic loop until Claude produces a final answer.
    Returns the final text response.
    """
    # Initialise conversation with the user's question
    messages = [
        {
            "role": "user",
            "content": user_message
        }
    ]

    MAX_ITERATIONS = 50   # Safety limit to prevent infinite loops
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1

        # --- Send the full conversation to Claude ---
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1000,
            messages=messages,
            tools=tools
        )

        # --- Case A: Claude has finished answering ---
        if response.stop_reason == "end_turn":
            # Extract the final text block (the first text block in the response)
            final_text = response.content[0].text
            print(f"Final Answer: {final_text}")
            return final_text

        # --- Case B: Claude wants to call one or more tools ---
        elif response.stop_reason == "tool_use":

            # Step 1: Persist Claude's tool_use blocks into the conversation
            # The API requires that tool_result blocks always reference a
            # tool_use block that exists in the *previous* assistant message.
            messages.append({
                "role": "assistant",
                "content": response.content
            })

            # Step 2: Execute every tool Claude requested
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name       # e.g. "lookup_order"
                    tool_id = block.id           # unique ID for matching tool_result → tool_use
                    tool_input = block.input     # already a dict, no json.loads needed

                    tool_result = handle_tool_call(tool_name, tool_id, tool_input)
                    tool_results.append(tool_result)

            # Step 3: Send tool results back as a user message
            messages.append({
                "role": "user",
                "content": tool_results
            })

            # Loop continues – Claude will now see the tool results
            # and decide whether to answer or call more tools.

    # --- Safety net: should never happen in practice ---
    return "Error: agent did not complete within the iteration limit"


# ============================================================
# Entry Point
# ============================================================
if __name__ == "__main__":
    print("running agent....")
    answer = run_agent("Where is my order #4821?")
    print(f"\nFinal Answer: {answer}")