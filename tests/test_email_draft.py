import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.config import Config
from muse_top.email_draft import (
    create_draft,
    is_valid_address,
    list_drafts,
    parse_addresses,
)
from muse_top.memory import Memory
from muse_top.tools import build_default_registry


class TestAddresses(unittest.TestCase):
    def test_valid_addresses(self):
        for addr in ("a@b.com", "first.last+tag@sub.example.co.uk", "x@y.io"):
            self.assertTrue(is_valid_address(addr), addr)

    def test_invalid_addresses(self):
        for addr in ("", "plain-text", "a@b", "a@.com", "@b.com", "a b@c.com", 123, None):
            self.assertFalse(is_valid_address(addr), repr(addr))

    def test_parse_string_and_list(self):
        addresses, invalid = parse_addresses("a@b.com, c@d.org")
        self.assertEqual(addresses, ["a@b.com", "c@d.org"])
        self.assertEqual(invalid, [])
        addresses, invalid = parse_addresses(["a@b.com", "not-an-email"])
        self.assertEqual(addresses, ["a@b.com"])
        self.assertEqual(invalid, ["not-an-email"])

    def test_parse_empty(self):
        self.assertEqual(parse_addresses(None), ([], []))
        self.assertEqual(parse_addresses(""), ([], []))


class TestCreateDraft(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.drafts_dir = Path(self.tmp.name) / "drafts"
        self.when = datetime(2026, 11, 24, 13, 47, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def _saved(self):
        files = sorted(self.drafts_dir.glob("draft-*.json"))
        self.assertEqual(len(files), 1)
        return files[0], json.loads(files[0].read_text(encoding="utf-8"))

    def test_draft_saved_with_all_fields(self):
        result = create_draft(
            self.drafts_dir,
            "client@example.com",
            "Your new website",
            "Hi, here is the draft.",
            cc="boss@example.com",
            when=self.when,
        )
        self.assertIn("Draft saved", result)
        self.assertIn("Not sent", result)
        path, draft = self._saved()
        self.assertEqual(path.name, "draft-20261124-134700-001.json")
        self.assertEqual(draft["id"], "draft-20261124-134700-001")
        self.assertEqual(draft["to"], ["client@example.com"])
        self.assertEqual(draft["cc"], ["boss@example.com"])
        self.assertEqual(draft["bcc"], [])
        self.assertEqual(draft["subject"], "Your new website")
        self.assertEqual(draft["body"], "Hi, here is the draft.")
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["created_at"], "2026-11-24T13:47:00+00:00")

    def test_multiple_recipients(self):
        result = create_draft(
            self.drafts_dir, "a@b.com, c@d.org", "Hi", "Hello.", when=self.when
        )
        self.assertIn("Draft saved", result)
        _, draft = self._saved()
        self.assertEqual(draft["to"], ["a@b.com", "c@d.org"])

    def test_two_drafts_same_second_get_unique_names(self):
        create_draft(self.drafts_dir, "a@b.com", "One", "1", when=self.when)
        create_draft(self.drafts_dir, "a@b.com", "Two", "2", when=self.when)
        names = sorted(p.name for p in self.drafts_dir.glob("draft-*.json"))
        self.assertEqual(
            names,
            ["draft-20261124-134700-001.json", "draft-20261124-134700-002.json"],
        )

    def test_invalid_recipient_rejected(self):
        result = create_draft(self.drafts_dir, "not-an-email", "Hi", "x")
        self.assertIn("Error", result)
        self.assertIn("not-an-email", result)
        self.assertFalse(list(self.drafts_dir.glob("draft-*.json")))

    def test_missing_recipient_rejected(self):
        self.assertIn("Error", create_draft(self.drafts_dir, "", "Hi", "x"))
        self.assertIn("Error", create_draft(self.drafts_dir, None, "Hi", "x"))

    def test_empty_subject_rejected(self):
        result = create_draft(self.drafts_dir, "a@b.com", "   ", "x")
        self.assertIn("Error", result)
        self.assertIn("subject", result)

    def test_invalid_cc_bcc_rejected(self):
        self.assertIn(
            "Error", create_draft(self.drafts_dir, "a@b.com", "Hi", "x", cc="bad")
        )
        self.assertIn(
            "Error", create_draft(self.drafts_dir, "a@b.com", "Hi", "x", bcc="bad")
        )

    def test_module_contains_no_sending_code(self):
        # The docstring may *say* "no SMTP" — check the code itself.
        source = (Path(__file__).resolve().parents[1] / "muse_top" / "email_draft.py").read_text()
        code_lines = [
            line for line in source.splitlines()
            if not line.strip().startswith(("#", '"""', "'''" ))
            and "no SMTP" not in line
        ]
        code = "\n".join(code_lines)
        self.assertNotIn("smtplib", code)
        self.assertNotIn("SMTP(", code)
        self.assertNotIn("sendmail", code)


class TestListDrafts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.drafts_dir = Path(self.tmp.name) / "drafts"

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_dir(self):
        self.assertIn("No drafts", list_drafts(self.drafts_dir))

    def test_missing_dir(self):
        self.assertIn("No drafts", list_drafts(Path(self.tmp.name) / "nope"))

    def test_lists_newest_first_and_skips_corrupt(self):
        create_draft(
            self.drafts_dir, "a@b.com", "Old", "x",
            when=datetime(2026, 11, 23, 9, 0, 0, tzinfo=timezone.utc),
        )
        create_draft(
            self.drafts_dir, "c@d.org", "New", "y",
            when=datetime(2026, 11, 24, 9, 0, 0, tzinfo=timezone.utc),
        )
        (self.drafts_dir / "draft-20261120-000000-001.json").write_text("{broken")
        result = list_drafts(self.drafts_dir)
        self.assertIn("2 draft(s)", result)
        self.assertLess(result.index("New"), result.index("Old"))
        self.assertNotIn("broken", result)


class TestDraftTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.tmp.name) / "memory.json")
        config = Config(
            api_key="",
            data_dir=Path(self.tmp.name) / "data",
            drafts_dir=Path(self.tmp.name) / "drafts",
        )
        self.registry = build_default_registry(self.memory, config)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tools_registered(self):
        self.assertIn("draft_email", self.registry.names())
        self.assertIn("list_drafts", self.registry.names())

    def test_draft_email_tool_round_trip(self):
        result = self.registry.call(
            "draft_email",
            {"to": "client@example.com", "subject": "Hello", "body": "Hi there."},
        )
        self.assertIn("Draft saved", result)
        listed = self.registry.call("list_drafts")
        self.assertIn("1 draft(s)", listed)
        self.assertIn("client@example.com", listed)
        self.assertIn("Hello", listed)

    def test_draft_email_tool_rejects_bad_address(self):
        result = self.registry.call(
            "draft_email", {"to": "nope", "subject": "Hi", "body": "x"}
        )
        self.assertIn("Error", result)


if __name__ == "__main__":
    unittest.main()
