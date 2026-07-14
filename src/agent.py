from src.config import CHAT_MODEL, client
from src.decision import TOOLS, execute_tool_call, recall
from src.prompts import SYSTEM_PROMPT

MAX_ITERATIONS = 5
RECALL_QUERY_WINDOW = 3  # latest message + a short window of recent STM, per §4.3 step 1


def _build_recall_query(history: list[dict]) -> str:
    # User messages only, deliberately — an assistant reply right after a RECALL often restates the
    # recalled content ("I remember you're pescatarian..."), which would otherwise feed that content
    # back into the next turn's embedding and make an unrelated follow-up question look related to it.
    user_messages = [m for m in history if m.get("role") == "user"]
    recent = user_messages[-RECALL_QUERY_WINDOW:]
    return " ".join(m.get("content") or "" for m in recent)


def build_messages(history: list[dict]) -> list[dict]:
    latest_message = (history[-1].get("content") or "") if history else ""
    recalled = recall(_build_recall_query(history), latest_message=latest_message)
    system_content = SYSTEM_PROMPT
    if recalled:
        system_content += (
            "\n\nRelevant memories about this user (only reference facts listed here — if something "
            "isn't listed, you have no stored information about it, so say so honestly instead of "
            "guessing):\n" + recalled
        )
    return [{"role": "system", "content": system_content}] + history


def get_reply(history: list[dict], source: str) -> tuple[str, list[dict]]:
    """Runs the tool-calling loop for one turn (RECALL, then call -> execute tools -> feed results
    back -> call again, per §0/§4.5). Returns (final_reply_text, new_messages) where new_messages is
    every assistant/tool message generated this turn, in order — the caller is responsible for
    appending these to the STM buffer.
    """
    messages = build_messages(history)
    new_messages: list[dict] = []
    any_tool_called = False

    for _ in range(MAX_ITERATIONS):
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        assistant_message = response.choices[0].message

        if not assistant_message.tool_calls:
            final_message = {"role": "assistant", "content": assistant_message.content}
            new_messages.append(final_message)
            if not any_tool_called:
                print("[MEMORY] IGNORE     (no memory operation)")
            return assistant_message.content, new_messages

        any_tool_called = True
        assistant_dict = {
            "role": "assistant",
            "content": assistant_message.content,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in assistant_message.tool_calls
            ],
        }
        messages.append(assistant_dict)
        new_messages.append(assistant_dict)

        for tool_call in assistant_message.tool_calls:
            result = execute_tool_call(tool_call.function.name, tool_call.function.arguments, source)
            tool_message = {"role": "tool", "tool_call_id": tool_call.id, "content": result}
            messages.append(tool_message)
            new_messages.append(tool_message)

    fallback = "Sorry, I got stuck processing that — could you rephrase?"
    new_messages.append({"role": "assistant", "content": fallback})
    return fallback, new_messages
