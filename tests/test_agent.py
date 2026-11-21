import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.agent import Agent
from muse_top.config import Config
from muse_top.memory import Memory
from muse_top.tools import build_default_registry


class FakeLLM:
    """Returns canned replies in order, whatever the prompt."""

    def __init__(self, replies):
        self.replies = list(replies)

    def generate(self, prompt):
        if self.replies:
            return self.replies.pop(0)
        return "done."


def make_agent(replies, tmpdir):
    config = Config(api_key="", data_dir=Path(tmpdir) / "data")
    memory = Memory(config.memory_path)
    registry = build_default_registry(memory)
    return Agent(config=config, llm=FakeLLM(replies), memory=memory, registry=registry)


class TestAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_reply_returned(self):
        agent = make_agent(["Hello, how can I help?"], self.tmp.name)
        self.assertEqual(agent.chat("hi"), "Hello, how can I help?")

    def test_tool_call_executed_and_final_answer_returned(self):
        agent = make_agent(
            ['CALL get_current_time {}', "The current time is shown above."],
            self.tmp.name,
        )
        reply = agent.chat("what time is it?")
        self.assertEqual(reply, "The current time is shown above.")

    def test_remember_fact_tool_persists(self):
        agent = make_agent(
            ['CALL remember_fact {"key": "city", "value": "Islamabad"}', "Remembered it."],
            self.tmp.name,
        )
        agent.chat("remember my city is Islamabad")
        self.assertEqual(agent.memory.recall("city"), "Islamabad")

    def test_unknown_tool_does_not_crash(self):
        agent = make_agent(
            ['CALL no_such_tool {}', "I could not run that tool."],
            self.tmp.name,
        )
        self.assertEqual(agent.chat("do the thing"), "I could not run that tool.")

    def test_history_kept(self):
        agent = make_agent(["one", "two"], self.tmp.name)
        agent.chat("first")
        agent.chat("second")
        self.assertEqual(len(agent.history), 4)
        self.assertEqual(agent.history[0], ("User", "first"))

    def test_empty_message(self):
        agent = make_agent(["x"], self.tmp.name)
        self.assertIn("type a message", agent.chat("   ").lower())

    def test_prompt_includes_memory_and_tools(self):
        agent = make_agent(["ok"], self.tmp.name)
        agent.memory.remember("role", "developer")
        prompt = agent._build_prompt("hello")
        self.assertIn("role: developer", prompt)
        self.assertIn("get_current_time", prompt)


if __name__ == "__main__":
    unittest.main()
