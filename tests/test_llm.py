import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.llm import MOCK_PREFIX, GeminiClient


class TestGeminiClient(unittest.TestCase):
    def test_mock_mode_without_key(self):
        client = GeminiClient(api_key="")
        self.assertTrue(client.is_mock)
        reply = client.generate("What time is it?")
        self.assertTrue(reply.startswith(MOCK_PREFIX))

    def test_mock_never_claims_real_answer(self):
        client = GeminiClient(api_key="")
        self.assertIn("no API key", client.generate("hello"))

    def test_with_key_is_not_mock(self):
        client = GeminiClient(api_key="fake-key-for-test")
        self.assertFalse(client.is_mock)


if __name__ == "__main__":
    unittest.main()
