from src.config import CHAT_MODEL, client
from src.prompts import SYSTEM_PROMPT


def build_messages(history: list[dict]) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}] + history


def get_reply(history: list[dict]) -> str:
    messages = build_messages(history)
    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
    )
    return response.choices[0].message.content
