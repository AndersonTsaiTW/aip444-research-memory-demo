import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from pydantic import ValidationError

from src.decision import (
    CONTRADICTION_SIMILARITY_THRESHOLD,
    DeleteMemoryArgs,
    SaveMemoryArgs,
    UpdateMemoryArgs,
    _check_near_duplicate,
    _format_recall_line,
    _is_broad_recall_query,
    _recency_score,
    _rescore,
    execute_tool_call,
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


class TestCheckNearDuplicate(unittest.TestCase):
    @patch("src.decision.long_term.query_active")
    def test_returns_match_at_or_above_threshold(self, mock_query):
        mock_query.return_value = [
            {"id": "abc123", "content": "User is vegetarian", "similarity": CONTRADICTION_SIMILARITY_THRESHOLD}
        ]
        result = _check_near_duplicate("I'm vegetarian too")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "abc123")

    @patch("src.decision.long_term.query_active")
    def test_returns_none_below_threshold(self, mock_query):
        mock_query.return_value = [{"id": "abc123", "content": "User is vegetarian", "similarity": 0.10}]
        self.assertIsNone(_check_near_duplicate("I like pizza"))

    @patch("src.decision.long_term.query_active")
    def test_returns_none_when_no_candidates(self, mock_query):
        mock_query.return_value = []
        self.assertIsNone(_check_near_duplicate("anything"))


class TestExecuteToolCallSaveMemory(unittest.TestCase):
    @patch("src.decision.long_term.save_memory")
    @patch("src.decision._check_near_duplicate")
    def test_surfaces_near_duplicate_instead_of_saving(self, mock_check_dup, mock_save):
        mock_check_dup.return_value = {"id": "abc123", "content": "User is vegetarian", "similarity": 0.49}

        result = json.loads(
            execute_tool_call(
                "save_memory",
                json.dumps(
                    {
                        "content": "I'm vegetarian too",
                        "label": "dietary preference",
                        "importance": 3,
                        "reason": "user restated diet",
                    }
                ),
                source="I'm vegetarian too, by the way.",
            )
        )

        self.assertEqual(result["status"], "near_duplicate_found")
        self.assertEqual(result["existing_id"], "abc123")
        mock_save.assert_not_called()

    @patch("src.decision.long_term.save_memory")
    @patch("src.decision._check_near_duplicate")
    def test_override_skips_near_duplicate_check_and_saves(self, mock_check_dup, mock_save):
        # Escape hatch for a false-positive near-duplicate (found via a live-testing transcript: two
        # short, unrelated "User's X is Y" facts about the same person can score above
        # CONTRADICTION_SIMILARITY_THRESHOLD on raw cosine similarity alone). override=True must bypass
        # the check entirely, not just override its result.
        mock_save.return_value = {"id": "new-id", "content": "User's favourite sport is cricket", "status": "active"}

        result = json.loads(
            execute_tool_call(
                "save_memory",
                json.dumps(
                    {
                        "content": "User's favourite sport is cricket",
                        "label": "favorite sport",
                        "importance": 3,
                        "reason": "user explicitly asked to remember",
                        "override": True,
                    }
                ),
                source="My favourite sport is cricket. Please remember that.",
            )
        )

        self.assertEqual(result["status"], "saved")
        mock_check_dup.assert_not_called()
        mock_save.assert_called_once()

    @patch("src.decision.long_term.save_memory")
    @patch("src.decision._check_near_duplicate")
    def test_saves_normally_when_no_duplicate(self, mock_check_dup, mock_save):
        mock_check_dup.return_value = None
        mock_save.return_value = {"id": "new-id", "content": "User has a dog", "status": "active"}

        result = json.loads(
            execute_tool_call(
                "save_memory",
                json.dumps(
                    {"content": "User has a dog", "label": "pet", "importance": 3, "reason": "new fact"}
                ),
                source="I have a dog.",
            )
        )

        self.assertEqual(result["status"], "saved")
        mock_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
