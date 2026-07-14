import unittest
from unittest.mock import patch

from src.main import USAGE, main, run_memories


class TestRunMemories(unittest.TestCase):
    @patch("src.main.long_term.list_memories")
    def test_prints_message_when_store_is_empty(self, mock_list):
        mock_list.return_value = []
        with patch("builtins.print") as mock_print:
            run_memories(show_all=False)
        mock_print.assert_called_once_with("No memories stored yet.")

    @patch("src.main.long_term.list_memories")
    def test_active_only_omits_status_tag(self, mock_list):
        mock_list.return_value = [
            {"id": "abc123", "label": "diet", "importance": 4, "content": "User is vegetarian", "status": "active"}
        ]
        with patch("builtins.print") as mock_print:
            run_memories(show_all=False)
        mock_list.assert_called_once_with(include_inactive=False)
        printed = mock_print.call_args[0][0]
        self.assertIn("[abc123]", printed)
        self.assertNotIn("[active]", printed)
        self.assertIn("User is vegetarian", printed)

    @patch("src.main.long_term.list_memories")
    def test_show_all_includes_status_and_supersedes(self, mock_list):
        mock_list.return_value = [
            {
                "id": "def456",
                "label": "diet",
                "importance": 4,
                "content": "User is pescatarian",
                "status": "active",
                "supersedes": "abc123",
            }
        ]
        with patch("builtins.print") as mock_print:
            run_memories(show_all=True)
        mock_list.assert_called_once_with(include_inactive=True)
        printed = mock_print.call_args[0][0]
        self.assertIn("[active]", printed)
        self.assertIn("(supersedes abc123)", printed)


class TestMainDispatch(unittest.TestCase):
    @patch("src.main.run_chat")
    def test_chat_command_dispatches_to_run_chat(self, mock_run_chat):
        with patch("sys.argv", ["main.py", "chat"]):
            main()
        mock_run_chat.assert_called_once()

    @patch("src.main.run_memories")
    def test_memories_command_defaults_show_all_false(self, mock_run_memories):
        with patch("sys.argv", ["main.py", "memories"]):
            main()
        mock_run_memories.assert_called_once_with(show_all=False)

    @patch("src.main.run_memories")
    def test_memories_command_with_all_flag(self, mock_run_memories):
        with patch("sys.argv", ["main.py", "memories", "--all"]):
            main()
        mock_run_memories.assert_called_once_with(show_all=True)

    def test_no_command_prints_usage_and_exits(self):
        with patch("sys.argv", ["main.py"]), patch("builtins.print") as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)
        mock_print.assert_called_once_with(USAGE)

    def test_unknown_command_prints_usage_and_exits(self):
        with patch("sys.argv", ["main.py", "bogus"]), patch("builtins.print") as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)
        printed = [call.args[0] for call in mock_print.call_args_list]
        self.assertIn("Unknown command: bogus", printed)
        self.assertIn(USAGE, printed)


if __name__ == "__main__":
    unittest.main()
