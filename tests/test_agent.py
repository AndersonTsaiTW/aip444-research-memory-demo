import unittest

from src.agent import _build_recall_query


class TestBuildRecallQuery(unittest.TestCase):
    def test_joins_recent_user_messages(self):
        history = [
            {"role": "user", "content": "I'm vegetarian."},
            {"role": "assistant", "content": "Got it, noted!"},
            {"role": "user", "content": "Actually, pescatarian now."},
        ]
        query = _build_recall_query(history)
        self.assertIn("vegetarian", query)
        self.assertIn("pescatarian", query)

    def test_excludes_assistant_messages(self):
        # An assistant reply right after a RECALL often restates recalled content (e.g. "I remember
        # you're pescatarian...") — including it would make an unrelated next question look related.
        history = [
            {"role": "user", "content": "What do you remember about me?"},
            {"role": "assistant", "content": "I remember you're pescatarian and your name is Anderson."},
            {"role": "user", "content": "What's my favorite programming language?"},
        ]
        query = _build_recall_query(history)
        self.assertNotIn("pescatarian", query)
        self.assertNotIn("Anderson", query)
        self.assertIn("favorite programming language", query)

    def test_empty_history_returns_empty_string(self):
        self.assertEqual(_build_recall_query([]), "")


if __name__ == "__main__":
    unittest.main()
