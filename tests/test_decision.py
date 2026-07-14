import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from src.decision import (
    DeleteMemoryArgs,
    SaveMemoryArgs,
    UpdateMemoryArgs,
    _format_recall_line,
    _is_broad_recall_query,
    _recency_score,
    _rescore,
)


class TestSaveMemoryArgs(unittest.TestCase):
    def test_accepts_integer_importance(self):
        args = SaveMemoryArgs(content="User is vegetarian", label="dietary preference", importance=4, reason="stable preference")
        self.assertEqual(args.importance, 4)

    def test_coerces_qualitative_word_to_integer(self):
        # cheap models sometimes send a word instead of an int (see §8 "LLM decisions are inconsistent")
        args = SaveMemoryArgs(content="x", label="y", importance="high", reason="z")
        self.assertEqual(args.importance, 4)

    def test_coerces_numeric_string_to_integer(self):
        args = SaveMemoryArgs(content="x", label="y", importance="3", reason="z")
        self.assertEqual(args.importance, 3)

    def test_rejects_unrecognized_importance(self):
        with self.assertRaises(ValidationError):
            SaveMemoryArgs(content="x", label="y", importance="extremely important", reason="z")

    def test_rejects_out_of_range_importance(self):
        with self.assertRaises(ValidationError):
            SaveMemoryArgs(content="x", label="y", importance=9, reason="z")

    def test_requires_all_fields(self):
        with self.assertRaises(ValidationError):
            SaveMemoryArgs(content="x", importance=3, reason="z")  # missing label


class TestUpdateMemoryArgs(unittest.TestCase):
    def test_requires_id_and_new_content(self):
        args = UpdateMemoryArgs(id="abc123", new_content="User is pescatarian", reason="changed diet")
        self.assertEqual(args.id, "abc123")

    def test_rejects_missing_id(self):
        with self.assertRaises(ValidationError):
            UpdateMemoryArgs(new_content="x", reason="z")


class TestDeleteMemoryArgs(unittest.TestCase):
    def test_requires_id_and_reason(self):
        args = DeleteMemoryArgs(id="abc123", reason="user asked to forget")
        self.assertEqual(args.id, "abc123")

    def test_rejects_missing_reason(self):
        with self.assertRaises(ValidationError):
            DeleteMemoryArgs(id="abc123")


class TestRecencyScore(unittest.TestCase):
    def test_recent_timestamp_scores_near_one(self):
        now = datetime.now(timezone.utc).isoformat()
        self.assertAlmostEqual(_recency_score(now), 1.0, delta=0.01)

    def test_older_timestamp_scores_lower(self):
        recent = datetime.now(timezone.utc).isoformat()
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        self.assertGreater(_recency_score(recent), _recency_score(week_ago))


class TestRescore(unittest.TestCase):
    def test_combines_recency_importance_relevance_and_sorts_descending(self):
        now = datetime.now(timezone.utc).isoformat()
        candidates = [
            {"updated_at": now, "importance": 1, "rerank_score": 0.1, "content": "low everything"},
            {"updated_at": now, "importance": 5, "rerank_score": 0.9, "content": "high everything"},
        ]
        rescored = _rescore(candidates)
        self.assertEqual(rescored[0]["content"], "high everything")
        self.assertGreater(rescored[0]["combined_score"], rescored[1]["combined_score"])


class TestFormatRecallLine(unittest.TestCase):
    def test_includes_id_label_importance_content_and_date(self):
        now = datetime.now(timezone.utc).isoformat()
        memory = {
            "id": "abc123",
            "label": "dietary preference",
            "importance": 4,
            "content": "User is vegetarian",
            "updated_at": now,
        }
        line = _format_recall_line(memory)
        self.assertIn("abc123", line)
        self.assertIn("dietary preference", line)
        self.assertIn("importance=4", line)
        self.assertIn("User is vegetarian", line)
        self.assertIn("today", line)


class TestIsBroadRecallQuery(unittest.TestCase):
    def test_detects_broad_recall_phrasing(self):
        self.assertTrue(_is_broad_recall_query("What do you remember about me?"))
        self.assertTrue(_is_broad_recall_query("Tell me about myself"))
        self.assertTrue(_is_broad_recall_query("WHAT DO YOU KNOW ABOUT ME"))

    def test_does_not_flag_specific_queries(self):
        self.assertFalse(_is_broad_recall_query("What's my favorite programming language?"))
        self.assertFalse(_is_broad_recall_query("What do you know about my diet?"))


if __name__ == "__main__":
    unittest.main()
