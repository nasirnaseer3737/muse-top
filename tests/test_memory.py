import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nz_agent.memory import Memory


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "memory.json"
        self.memory = Memory(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_remember_and_recall(self):
        self.memory.remember("City", "Islamabad")
        self.assertEqual(self.memory.recall("city"), "Islamabad")
        self.assertEqual(self.memory.recall("CITY"), "Islamabad")

    def test_recall_missing_returns_none(self):
        self.assertIsNone(self.memory.recall("nope"))

    def test_forget(self):
        self.memory.remember("a", "1")
        self.assertTrue(self.memory.forget("a"))
        self.assertIsNone(self.memory.recall("a"))
        self.assertFalse(self.memory.forget("a"))

    def test_persists_across_instances(self):
        self.memory.remember("name", "Nasir")
        again = Memory(self.path)
        self.assertEqual(again.recall("name"), "Nasir")

    def test_search(self):
        self.memory.remember("favourite colour", "orange")
        self.memory.remember("city", "Rawalpindi")
        self.assertEqual(self.memory.search("orange"), {"favourite colour": "orange"})
        self.assertEqual(self.memory.search("CITY"), {"city": "Rawalpindi"})

    def test_corrupt_file_starts_empty(self):
        self.path.write_text("{not json", encoding="utf-8")
        memory = Memory(self.path)
        self.assertEqual(memory.all(), {})

    def test_render_for_prompt(self):
        self.assertIn("No facts", self.memory.render_for_prompt())
        self.memory.remember("role", "developer")
        self.assertIn("role: developer", self.memory.render_for_prompt())


if __name__ == "__main__":
    unittest.main()
