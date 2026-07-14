from typing import Callable

from src.config import CHAT_MODEL, client

CHARS_PER_TOKEN = 4  # rough OpenAI rule-of-thumb for English text; no tokenizer library in requirements.txt


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def summarize_messages(messages: list[dict]) -> str:
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Summarize the following conversation excerpt concisely, preserving any "
                    "facts, names, or preferences mentioned."
                ),
            },
            {"role": "user", "content": transcript},
        ],
    )
    return response.choices[0].message.content


class ConversationBuffer:
    def __init__(self, max_tokens: int = 4000, summarizer: Callable[[list[dict]], str] = summarize_messages):
        self.max_tokens = max_tokens
        self.messages: list[dict] = []
        self._summarizer = summarizer
        self.last_summary: str | None = None

    def add(self, role: str, content: str) -> bool:
        """Appends a message. Returns True if adding it triggered an overflow summarization."""
        self.messages.append({"role": role, "content": content})
        if self.token_count() > self.max_tokens:
            return self._summarize_oldest_half()
        return False

    def token_count(self) -> int:
        return sum(estimate_tokens(m["content"]) for m in self.messages)

    def usage_ratio(self) -> float:
        return self.token_count() / self.max_tokens if self.max_tokens else 0.0

    def _summarize_oldest_half(self) -> bool:
        split = len(self.messages) // 2
        if split == 0:
            return False
        oldest, rest = self.messages[:split], self.messages[split:]
        summary = self._summarizer(oldest)
        self.last_summary = summary
        self.messages = [{"role": "system", "content": f"[Conversation summary] {summary}"}] + rest
        return True
