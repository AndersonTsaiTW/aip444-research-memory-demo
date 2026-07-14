import unittest

from pydantic import ValidationError

from src.decision import DeleteMemoryArgs, SaveMemoryArgs, UpdateMemoryArgs


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


if __name__ == "__main__":
    unittest.main()
