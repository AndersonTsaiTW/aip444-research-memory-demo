import sys

from src.agent import get_reply
from src.short_term import ConversationBuffer

# Windows terminals often default to a non-UTF-8 codepage (e.g. cp950), which raises
# UnicodeEncodeError on emoji or other characters outside that codepage.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

USAGE = "Usage: python -m src.main chat"


def run_chat() -> None:
    print("Chat started. Type 'exit' or 'quit' to end the session.\n")
    buffer = ConversationBuffer()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if user_input.lower() in ("exit", "quit"):
            print("Goodbye.")
            break
        if not user_input:
            continue

        summarized = buffer.add("user", user_input)
        reply = get_reply(buffer.messages)
        summarized = buffer.add("assistant", reply) or summarized
        print(f"Agent: {reply}\n")
        if summarized:
            print("[STM] token cap exceeded — oldest half of the conversation summarized.")
        print(f"[STM] buffer at {buffer.usage_ratio():.0%} ({buffer.token_count()}/{buffer.max_tokens} tokens)\n")


def main() -> None:
    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(1)

    command = sys.argv[1]
    if command == "chat":
        run_chat()
    else:
        print(f"Unknown command: {command}")
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
