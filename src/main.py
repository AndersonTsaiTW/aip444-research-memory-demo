import sys

from src import long_term
from src.agent import get_reply
from src.short_term import ConversationBuffer

# Windows terminals often default to a non-UTF-8 codepage (e.g. cp950), which raises
# UnicodeEncodeError on emoji or other characters outside that codepage.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

USAGE = "Usage: python -m src.main <chat|memories [--all]>"


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
        reply, new_messages = get_reply(buffer.messages, source=user_input)
        summarized = buffer.extend(new_messages) or summarized
        print(f"Agent: {reply}\n")
        if summarized:
            print(f"[STM] token cap exceeded — oldest half summarized: {buffer.last_summary}")
        print(f"[STM] buffer at {buffer.usage_ratio():.0%} ({buffer.token_count()}/{buffer.max_tokens} tokens)\n")


def run_memories(show_all: bool) -> None:
    memories = long_term.list_memories(include_inactive=show_all)
    if not memories:
        print("No memories stored yet.")
        return

    for m in memories:
        status_tag = f" [{m['status']}]" if show_all else ""
        supersedes = f" (supersedes {m['supersedes']})" if m.get("supersedes") else ""
        print(f"[{m['id']}]{status_tag} ({m['label']}, imp={m['importance']}) {m['content']}{supersedes}")


def main() -> None:
    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(1)

    command = sys.argv[1]
    if command == "chat":
        run_chat()
    elif command == "memories":
        run_memories(show_all="--all" in sys.argv[2:])
    else:
        print(f"Unknown command: {command}")
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
