import unittest

from src.short_term import ConversationBuffer, estimate_tokens


def stub_summarizer(messages: list[dict]) -> str:
    return f"stub summary of {len(messages)} messages"


class TestEstimateTokens(unittest.TestCase):
    def test_estimates_roughly_four_chars_per_token(self):
        self.assertEqual(estimate_tokens("a" * 40), 10)
        self.assertEqual(estimate_tokens(""), 0)


class TestConversationBuffer(unittest.TestCase):
    def test_add_appends_messages(self):
        buffer = ConversationBuffer(max_tokens=1000, summarizer=stub_summarizer)
        buffer.add("user", "hello")
        buffer.add("assistant", "hi there")
        self.assertEqual(
            buffer.messages,
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
        )

    def test_usage_ratio_reflects_token_count(self):
        buffer = ConversationBuffer(max_tokens=100, summarizer=stub_summarizer)
        buffer.add("user", "a" * 40)  # 10 tokens
        self.assertAlmostEqual(buffer.usage_ratio(), 0.1)

    def test_overflow_summarizes_oldest_half(self):
        buffer = ConversationBuffer(max_tokens=20, summarizer=stub_summarizer)
        for _ in range(4):
            buffer.add("user", "x" * 20)  # 5 tokens each; 4 messages = 20 tokens, at (not over) the cap
        self.assertEqual(len(buffer.messages), 4)

        # the 5th message (25 tokens total) pushes it over the cap and triggers summarization
        summarized = buffer.add("user", "x" * 20)

        self.assertTrue(summarized)
        self.assertEqual(buffer.messages[0]["role"], "system")
        self.assertIn("[Conversation summary]", buffer.messages[0]["content"])
        self.assertIn("stub summary of 2 messages", buffer.messages[0]["content"])
        self.assertEqual(len(buffer.messages), 4)  # 1 summary + 3 remaining originals
        self.assertEqual(buffer.last_summary, "stub summary of 2 messages")

    def test_last_summary_is_none_before_any_overflow(self):
        buffer = ConversationBuffer(max_tokens=1000, summarizer=stub_summarizer)
        buffer.add("user", "hello")
        self.assertIsNone(buffer.last_summary)

    def test_add_returns_true_only_when_summarization_triggered(self):
        buffer = ConversationBuffer(max_tokens=1000, summarizer=stub_summarizer)
        self.assertFalse(buffer.add("user", "short message"))

        overflow_buffer = ConversationBuffer(max_tokens=10, summarizer=stub_summarizer)
        overflow_buffer.add("user", "x" * 20)  # 5 tokens
        overflow_buffer.add("user", "x" * 20)  # 10 tokens total, at (not over) the cap
        # 3rd message pushes total to 15 > 10, and with 3 messages present, split=1 so it's a real summarize
        self.assertTrue(overflow_buffer.add("user", "x" * 20))

    def test_single_oversized_message_does_not_crash(self):
        buffer = ConversationBuffer(max_tokens=5, summarizer=stub_summarizer)
        # split == 0 for a single message; should not attempt to summarize
        summarized = buffer.add("user", "x" * 100)
        self.assertFalse(summarized)
        self.assertEqual(len(buffer.messages), 1)


if __name__ == "__main__":
    unittest.main()
