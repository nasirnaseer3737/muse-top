import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.config import Config
from muse_top.memory import Memory
from muse_top.outreach import (
    CALL_CTA_PHRASES,
    build_outreach_email,
    draft_outreach_file,
    problem_line,
    subject_options,
)
from muse_top.tools import build_default_registry

SAMPLE_CSV = """name,email,phone,company,website,industry,employees,source,budget,consent
Sarah Khan,sarah@acmedental.com,+1 555 123 4567,Acme Dental,https://acmedental.com,dental,120,referral,5000,yes
Joe Plumber,joe@gmail.com,555-111-2222,Joe Plumbing,,plumbing,8,website form,800,yes
No Consent,sara@bestroofing.com,5551234567,Best Roofing,https://bestroofing.com,roofing,60,google ads,2000,no
No Email,,5551234567,No Mail Co,https://nomail.com,legal,30,cold list,,yes
"""


def _lead(**overrides):
    lead = {
        "name": "Sarah Khan",
        "email": "sarah@acmedental.com",
        "phone": "+1 555 123 4567",
        "company": "Acme Dental",
        "website": "https://acmedental.com",
        "industry": "dental",
        "employees": "120",
        "source": "referral",
        "budget": "5000",
        "consent": "yes",
    }
    lead.update(overrides)
    return lead


class TestBuildOutreach(unittest.TestCase):
    def test_subject_options_personalised(self):
        subjects = subject_options(_lead())
        self.assertEqual(len(subjects), 3)
        for subject in subjects:
            self.assertIn("Acme Dental", subject)
        self.assertEqual(len(set(subjects)), 3)

    def test_body_uses_first_name_and_company(self):
        built = build_outreach_email(_lead())
        self.assertTrue(built["body"].startswith("Hi Sarah,"))
        self.assertIn("Acme Dental", built["body"])
        self.assertIn("dental", built["body"])

    def test_body_has_experience_line(self):
        built = build_outreach_email(_lead())
        self.assertIn("15+ years", built["body"])
        self.assertIn("50+ websites", built["body"])
        self.assertIn("30 built and launched", built["body"])

    def test_body_cta_is_reply_or_whatsapp_not_a_call(self):
        built = build_outreach_email(_lead())
        body = built["body"]
        self.assertIn("reply to this email", body)
        self.assertIn("https://wa.me/923339845505", body)
        lowered = body.lower()
        for phrase in CALL_CTA_PHRASES:
            self.assertNotIn(phrase, lowered)

    def test_body_explains_problem_and_solution(self):
        built = build_outreach_email(_lead())
        self.assertIn("isn't set up to catch", built["body"])
        self.assertIn("local SEO", built["body"])
        self.assertIn("AI replies", built["body"])

    def test_no_website_problem_line(self):
        built = build_outreach_email(_lead(website=""))
        self.assertIn("has no website yet", built["body"])
        self.assertIn("can't find", built["body"])

    def test_problem_line_mentions_company(self):
        self.assertIn("Acme Dental", problem_line(_lead()))
        self.assertIn("Acme Dental", problem_line(_lead(website="")))

    def test_score_and_grade_attached(self):
        built = build_outreach_email(_lead())
        self.assertEqual(built["score"], 100)
        self.assertEqual(built["grade"], "A")
        self.assertEqual(built["email"], "sarah@acmedental.com")

    def test_no_consent_refuses(self):
        with self.assertRaises(ValueError) as ctx:
            build_outreach_email(_lead(consent="no"))
        self.assertIn("DO-NOT-CONTACT", str(ctx.exception))

    def test_no_email_refuses(self):
        with self.assertRaises(ValueError):
            build_outreach_email(_lead(email=""))

    def test_no_name_no_company_refuses(self):
        with self.assertRaises(ValueError):
            build_outreach_email(_lead(name="", company=""))

    def test_name_only_still_works(self):
        built = build_outreach_email(_lead(company=""))
        self.assertTrue(built["body"].startswith("Hi Sarah,"))

    def test_custom_sender_and_whatsapp(self):
        built = build_outreach_email(
            _lead(), sender_name="Test Sender", whatsapp="1234567890"
        )
        self.assertIn("Test Sender", built["body"])
        self.assertIn("https://wa.me/1234567890", built["body"])

    def test_no_smtp_anywhere_in_module(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "muse_top", "outreach.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("smtplib", source)
        self.assertNotIn("SMTP", source)


class TestDraftOutreachFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.drafts = self.base / "drafts"
        (self.workspace / "prospects.csv").write_text(
            SAMPLE_CSV, encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _drafts(self):
        return sorted(self.drafts.glob("draft-*.json"))

    def test_draft_by_row_saves_draft(self):
        result = draft_outreach_file(
            self.workspace, "prospects.csv", self.drafts, row=1
        )
        self.assertIn("Outreach draft for Acme Dental", result)
        self.assertIn("100/100 (grade A)", result)
        self.assertIn("Draft saved", result)
        self.assertIn("Not sent", result)
        saved = self._drafts()
        self.assertEqual(len(saved), 1)
        import json

        data = json.loads(saved[0].read_text(encoding="utf-8"))
        self.assertEqual(data["to"], ["sarah@acmedental.com"])
        self.assertEqual(data["status"], "draft")
        self.assertIn("Acme Dental", data["subject"])
        self.assertIn("Hi Sarah,", data["body"])

    def test_draft_by_email_case_insensitive(self):
        result = draft_outreach_file(
            self.workspace, "prospects.csv", self.drafts,
            email="JOE@GMAIL.COM",
        )
        self.assertIn("Outreach draft for Joe Plumbing", result)
        self.assertEqual(len(self._drafts()), 1)

    def test_no_consent_row_creates_no_draft(self):
        result = draft_outreach_file(
            self.workspace, "prospects.csv", self.drafts, row=3
        )
        self.assertIn("DO-NOT-CONTACT", result)
        self.assertEqual(self._drafts(), [])

    def test_no_email_row_creates_no_draft(self):
        result = draft_outreach_file(
            self.workspace, "prospects.csv", self.drafts, row=4
        )
        self.assertIn("Error", result)
        self.assertEqual(self._drafts(), [])

    def test_row_out_of_range(self):
        result = draft_outreach_file(
            self.workspace, "prospects.csv", self.drafts, row=99
        )
        self.assertIn("out of range", result)

    def test_unknown_email(self):
        result = draft_outreach_file(
            self.workspace, "prospects.csv", self.drafts,
            email="nobody@example.com",
        )
        self.assertIn("No prospect with email", result)

    def test_neither_row_nor_email(self):
        result = draft_outreach_file(
            self.workspace, "prospects.csv", self.drafts
        )
        self.assertIn("Give a row number or an email", result)

    def test_missing_file(self):
        result = draft_outreach_file(
            self.workspace, "missing.csv", self.drafts, row=1
        )
        self.assertIn("file not found", result)

    def test_outside_workspace_refused(self):
        result = draft_outreach_file(
            self.workspace, "../escape.csv", self.drafts, row=1
        )
        self.assertIn("outside the workspace", result)

    def test_subject_options_listed_in_result(self):
        result = draft_outreach_file(
            self.workspace, "prospects.csv", self.drafts, row=2
        )
        self.assertIn("Subject options:", result)
        self.assertIn("Joe Plumbing", result)


class TestOutreachToolRegistry(unittest.TestCase):
    def test_tool_registered_and_callable(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            workspace = base / "workspace"
            workspace.mkdir()
            (workspace / "prospects.csv").write_text(SAMPLE_CSV, encoding="utf-8")
            config = Config(
                workspace_dir=workspace,
                drafts_dir=base / "drafts",
                sender_name="Nasir Naseer",
                sender_whatsapp="923339845505",
            )
            registry = build_default_registry(Memory(base / "memory.json"), config)
            self.assertIn("draft_outreach", registry.names())
            result = registry.call(
                "draft_outreach", {"path": "prospects.csv", "row": 1}
            )
            self.assertIn("Outreach draft for Acme Dental", result)
            self.assertTrue((base / "drafts").exists())


if __name__ == "__main__":
    unittest.main()
