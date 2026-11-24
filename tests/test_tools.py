import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.memory import Memory
from muse_top.tools import ToolRegistry, build_default_registry, parse_tool_call


class TestToolRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.tmp.name) / "memory.json")
        self.registry = build_default_registry(self.memory)

    def tearDown(self):
        self.tmp.cleanup()

    def test_builtins_registered(self):
        self.assertEqual(
            self.registry.names(),
            [
                "draft_email",
                "get_current_time",
                "list_drafts",
                "read_file",
                "recall_fact",
                "remember_fact",
                "web_fetch",
                "write_file",
            ],
        )

    def test_get_current_time_returns_text(self):
        result = self.registry.call("get_current_time")
        self.assertIn("2026", result)

    def test_remember_and_recall_tools(self):
        self.assertIn("Remembered", self.registry.call("remember_fact", {"key": "x", "value": "y"}))
        self.assertIn("x = y", self.registry.call("recall_fact", {"key": "x"}))
        self.assertIn("No fact", self.registry.call("recall_fact", {"key": "missing"}))

    def test_unknown_tool_returns_error_text(self):
        self.assertIn("no tool named", self.registry.call("does_not_exist"))

    def test_bad_args_return_error_text(self):
        self.assertIn("Error", self.registry.call("remember_fact", {"key": "only-key"}))

    def test_custom_tool_registration(self):
        registry = ToolRegistry()
        registry.register("shout", "Uppercase text.", lambda text: text.upper())
        self.assertEqual(registry.call("shout", {"text": "hi"}), "HI")
        self.assertIn("shout: Uppercase", registry.describe())

    def test_parse_tool_call(self):
        self.assertEqual(
            parse_tool_call('CALL remember_fact {"key": "a", "value": "b"}'),
            ("remember_fact", {"key": "a", "value": "b"}),
        )
        self.assertEqual(parse_tool_call("CALL get_current_time"), ("get_current_time", {}))
        self.assertIsNone(parse_tool_call("hello world"))
        self.assertIsNone(parse_tool_call('CALL bad {not json'))
        self.assertIsNone(parse_tool_call("CALL "))


if __name__ == "__main__":
    unittest.main()
