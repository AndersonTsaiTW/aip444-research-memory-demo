from src.config import CHAT_MODEL, client
from src.decision import TOOLS, execute_tool_call
from src.prompts import SYSTEM_PROMPT

MAX_ITERATIONS = 5


def build_messages(history: list[dict]) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}] + history


def get_reply(history: list[dict], source: str) -> tuple[str, list[dict]]:
    """Runs the tool-calling loop for one turn (call -> execute tools -> feed results back ->
    call again, per §0/§4.5). Returns (final_reply_text, new_messages) where new_messages is every
    assistant/tool message generated this turn, in order — the caller is responsible for appending
    these to the STM buffer.
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
