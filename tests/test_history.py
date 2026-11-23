import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.agent import Agent
from muse_top.config import Config
from muse_top.history import History
from muse_top.memory import Memory
from muse_top.tools import build_default_registry


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def generate(self, prompt):
        self.last_prompt = prompt
        if self.replies:
            return self.replies.pop(0)
        return "done."


def make_agent(replies, tmpdir):
    config = Config(api_key="", data_dir=Path(tmpdir) / "data")
    memory = Memory(config.memory_path)
    registry = build_default_registry(memory)
    return Agent(config=config, llm=FakeLLM(replies), memory=memory, registry=registry)


class TestHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "history.json"
        self.history = History(self.path, max_turns=3)

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_and_turns(self):
        self.history.append("User", "hello")
        self.history.append("Assistant", "hi there")
        self.assertEqual(
            self.history.turns(), [("User", "hello"), ("Assistant", "hi there")]
        )

    def test_persists_across_instances(self):
        self.history.append("User", "my name is Nasir")
        self.history.append("Assistant", "noted")
        again = History(self.path, max_turns=3)
        self.assertEqual(again.turns(), [("User", "my name is Nasir"), ("Assistant", "noted")])

    def test_cap_keeps_only_last_n_turns(self):
        for i in range(5):
            self.history.append("User", f"q{i}")
            self.history.append("Assistant", f"a{i}")
        # max_turns=3 -> 6 messages kept, the first two turns dropped.
        self.assertEqual(len(self.history), 6)
        self.assertEqual(self.history.turns()[0], ("User", "q2"))
        self.assertEqual(self.history.turns()[-1], ("Assistant", "a4"))

    def test_corrupt_file_starts_empty(self):
        self.path.write_text("{not json", encoding="utf-8")
        history = History(self.path, max_turns=3)
        self.assertEqual(history.turns(), [])

    def test_invalid_entries_ignored(self):
        self.path.write_text(
            json.dumps(
                [
                    {"role": "User", "text": "ok"},
                    {"role": "System", "text": "not a turn"},
                    {"role": "User"},
                    "just a string",
                    {"role": "Assistant", "text": 42},
                ]
            ),
            encoding="utf-8",
        )
        history = History(self.path, max_turns=3)
        self.assertEqual(history.turns(), [("User", "ok")])

    def test_bad_role_rejected(self):
        with self.assertRaises(ValueError):
            self.history.append("System", "nope")

    def test_clear(self):
        self.history.append("User", "hi")
        self.history.clear()
        self.assertEqual(self.history.turns(), [])
        self.assertEqual(History(self.path, max_turns=3).turns(), [])

    def test_render(self):
        self.assertEqual(self.history.render(), "")
        self.history.append("User", "hello")
        self.history.append("Assistant", "hi")
        self.assertEqual(self.history.render(), "User: hello\nAssistant: hi")

    def test_missing_file_starts_empty(self):
        self.assertEqual(History(Path(self.tmp.name) / "nope.json").turns(), [])


class TestAgentHistoryPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_agent_loads_history_on_start(self):
        agent = make_agent(["one", "two"], self.tmp.name)
        agent.chat("first")
        agent.chat("second")
        # A fresh agent on the same data dir sees the previous turns.
        agent2 = make_agent(["three"], self.tmp.name)
        self.assertEqual(len(agent2.history), 4)
        self.assertEqual(agent2.history[0], ("User", "first"))
        self.assertEqual(agent2.history[-1], ("Assistant", "two"))

    def test_prompt_includes_previous_turns(self):
        agent = make_agent(["one", "two"], self.tmp.name)
        agent.chat("my city is Islamabad")
        prompt = agent._build_prompt("what is my city?")
        self.assertIn("User: my city is Islamabad", prompt)
        self.assertIn("Assistant: one", prompt)

    def test_history_file_written_to_data_dir(self):
        agent = make_agent(["hi"], self.tmp.name)
        agent.chat("hello")
        history_file = Path(self.tmp.name) / "data" / "history.json"
        self.assertTrue(history_file.exists())
        data = json.loads(history_file.read_text(encoding="utf-8"))
        self.assertEqual(data[0], {"role": "User", "text": "hello"})


if __name__ == "__main__":
    unittest.main()
