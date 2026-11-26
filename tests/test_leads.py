import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.config import Config
from muse_top.leads import (
    grade_for_score,
    mock_angle,
    parse_leads_csv,
    score_all,
    score_lead,
    score_leads_file,
    score_leads_text,
)
from muse_top.memory import Memory
from muse_top.tools import build_default_registry

SAMPLE_CSV = """name,email,phone,company,website,industry,employees,source,budget,consent
Acme Dental,jane@acmedental.com,+1 555 123 4567,Acme Dental,https://acmedental.com,dental,120,referral,5000,yes
Free Mail,joe@gmail.com,555-111-2222,Joe Plumbing,https://joeplumbing.com,plumbing,8,website form,800,yes
No Consent,sara@bestroofing.com,5551234567,Best Roofing,https://bestroofing.com,roofing,60,google ads,2000,no
Bad Email,bob-at-example,5551234567,Bob Legal,boblegal.com,legal,30,cold list,,yes
Empty Co,,,,,,,,,yes
"""


def _lead(**overrides):
    lead = {
        "name": "Test",
        "email": "a@company.com",
        "phone": "+1 555 123 4567",
        "company": "Test Co",
        "website": "https://company.com",
        "industry": "dental",
        "employees": "25",
        "source": "referral",
        "budget": "5000",
        "consent": "yes",
    }
    lead.update(overrides)
    return lead


class TestGradeBands(unittest.TestCase):
    def test_grade_boundaries(self):
        self.assertEqual(grade_for_score(100), "A")
        self.assertEqual(grade_for_score(80), "A")
        self.assertEqual(grade_for_score(79), "B")
        self.assertEqual(grade_for_score(60), "B")
        self.assertEqual(grade_for_score(59), "C")
        self.assertEqual(grade_for_score(40), "C")
        self.assertEqual(grade_for_score(39), "D")
        self.assertEqual(grade_for_score(0), "D")


class TestScoreLead(unittest.TestCase):
    def test_full_lead_scores_high(self):
        # 15 email + 10 phone + 10 website + 10 size + 15 industry
        # + 15 source + 15 budget + 5 consent = 95
        score, grade, reasons, contact_ok = score_lead(_lead())
        self.assertEqual(score, 95)
        self.assertEqual(grade, "A")
        self.assertTrue(contact_ok)
        self.assertIn("business email domain (+15)", reasons)

    def test_free_email_scores_less(self):
        score, _, _, _ = score_lead(_lead(email="a@gmail.com"))
        self.assertEqual(score, 85)  # 95 - 15 + 5

    def test_invalid_email_penalised(self):
        score, _, reasons, _ = score_lead(_lead(email="not-an-email"))
        self.assertEqual(score, 70)  # 95 - 15 - 10
        self.assertIn("invalid email (-10)", reasons)

    def test_no_email_no_phone(self):
        score, _, _, _ = score_lead(_lead(email="", phone=""))
        self.assertEqual(score, 70)  # 95 - 15 - 10

    def test_employees_ranges(self):
        self.assertEqual(score_lead(_lead(employees="5"))[0], 90)   # +5
        self.assertEqual(score_lead(_lead(employees="11-50"))[0], 95)  # +10
        self.assertEqual(score_lead(_lead(employees="51-200"))[0], 100)  # +15, clamped
        self.assertEqual(score_lead(_lead(employees="500"))[0], 95)  # +10
        self.assertEqual(score_lead(_lead(employees=""))[0], 85)  # +0

    def test_industry_fit(self):
        self.assertEqual(score_lead(_lead(industry="saas"))[0], 95)
        self.assertEqual(score_lead(_lead(industry="mining"))[0], 85)  # +5
        self.assertEqual(score_lead(_lead(industry=""))[0], 80)  # +0

    def test_source_scores(self):
        self.assertEqual(score_lead(_lead(source="referral"))[0], 95)
        self.assertEqual(score_lead(_lead(source="scraped"))[0], 80)  # +0
        self.assertEqual(score_lead(_lead(source="cold list"))[0], 82)  # +2
        self.assertEqual(score_lead(_lead(source=""))[0], 80)  # +0
        self.assertEqual(score_lead(_lead(source="mystery"))[0], 85)  # +5 default

    def test_budget_signals(self):
        self.assertEqual(score_lead(_lead(budget="$5k/mo"))[0], 95)
        self.assertEqual(score_lead(_lead(budget="500"))[0], 88)  # +8
        self.assertEqual(score_lead(_lead(budget=""))[0], 80)  # +0

    def test_no_consent_flagged_do_not_contact(self):
        score, _, reasons, contact_ok = score_lead(_lead(consent="no"))
        self.assertFalse(contact_ok)
        self.assertEqual(score, 90)  # 95 - 5
        self.assertIn("NO consent — do not contact (+0)", reasons)

    def test_consent_variants(self):
        for yes in ("yes", "Y", "true", "1", "opt-in", "opt in"):
            self.assertTrue(score_lead(_lead(consent=yes))[3], yes)
        for no in ("no", "", "maybe"):
            self.assertFalse(score_lead(_lead(consent=no))[3], repr(no))

    def test_score_clamped_at_zero(self):
        score, grade, _, _ = score_lead(_lead(email="bad", phone="", website="",
                                               industry="", employees="",
                                               source="", budget="", consent="no"))
        self.assertEqual(score, 0)
        self.assertEqual(grade, "D")


class TestMockAngle(unittest.TestCase):
    def test_angle_is_labelled_mock(self):
        lead = _lead()
        score, grade, reasons, _ = score_lead(lead)
        angle = mock_angle(lead, score, grade, reasons)
        self.assertIn("[MOCK — no API key]", angle)
        self.assertIn("Test Co", angle)
        self.assertIn("grade A", angle)


class TestParseLeadsCsv(unittest.TestCase):
    def test_case_insensitive_headers(self):
        leads = parse_leads_csv("Name,EMAIL,Consent\nAcme,a@b.com,yes\n")
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["name"], "Acme")
        self.assertEqual(leads[0]["email"], "a@b.com")
        self.assertEqual(leads[0]["consent"], "yes")

    def test_empty_text(self):
        self.assertEqual(parse_leads_csv(""), [])
        self.assertEqual(parse_leads_csv("name,email\n"), [])

    def test_blank_rows_skipped(self):
        leads = parse_leads_csv("name,email\nAcme,a@b.com\n,,\n")
        self.assertEqual(len(leads), 1)


class TestScoreAll(unittest.TestCase):
    def test_sorted_best_first_and_truncation(self):
        leads = parse_leads_csv(SAMPLE_CSV)
        scored, truncated = score_all(leads, max_rows=3)
        self.assertTrue(truncated)
        self.assertEqual(len(scored), 3)
        scores = [row["score"] for row in scored]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_scored_rows_carry_grade_and_angle(self):
        scored, _ = score_all(parse_leads_csv(SAMPLE_CSV))
        for row in scored:
            self.assertIn(row["grade"], "ABCD")
            self.assertIn("[MOCK — no API key]", row["angle"])
            self.assertIsInstance(row["contact_ok"], bool)


class TestScoreLeadsText(unittest.TestCase):
    def test_sample_summary(self):
        result = score_leads_text(SAMPLE_CSV, top=2)
        self.assertIn("Scored 5 lead(s)", result)
        self.assertIn("contactable: 4", result)
        self.assertIn("DO-NOT-CONTACT (no consent): 1", result)
        self.assertIn("Acme Dental", result)  # top lead
        self.assertIn("Top 2 contactable lead(s)", result)
        self.assertIn("[MOCK — no API key]", result)

    def test_empty_csv(self):
        self.assertIn("No leads found", score_leads_text("name,email\n"))

    def test_all_blocked(self):
        result = score_leads_text(
            "name,email,consent\nA,a@b.com,no\nB,c@d.com,no\n", top=5
        )
        self.assertIn("No contactable leads", result)
        self.assertIn("DO-NOT-CONTACT (no consent): 2", result)


class TestScoreLeadsFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        self.workspace.mkdir()
        (self.workspace / "leads.csv").write_text(SAMPLE_CSV, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_scores_workspace_csv(self):
        result = score_leads_file(self.workspace, "leads.csv", top=2)
        self.assertIn("Scored 5 lead(s)", result)
        self.assertIn("Acme Dental", result)

    def test_missing_file(self):
        self.assertIn("file not found", score_leads_file(self.workspace, "nope.csv"))

    def test_path_escape_refused(self):
        result = score_leads_file(self.workspace, "../outside.csv")
        self.assertIn("outside the workspace", result)

    def test_oversized_file_refused(self):
        big = self.workspace / "big.csv"
        big.write_text("x" * 100, encoding="utf-8")
        result = score_leads_file(self.workspace, "big.csv", max_bytes=10)
        self.assertIn("larger than the read cap", result)


class TestScoreLeadsTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.workspace = self.data / "workspace"
        self.workspace.mkdir()
        (self.workspace / "leads.csv").write_text(SAMPLE_CSV, encoding="utf-8")
        config = Config(data_dir=self.data, workspace_dir=self.workspace)
        memory = Memory(self.data / "memory.json")
        self.registry = build_default_registry(memory, config)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tool_registered_and_scores(self):
        self.assertIn("score_leads", self.registry.names())
        result = self.registry.call("score_leads", {"path": "leads.csv", "top": 2})
        self.assertIn("Scored 5 lead(s)", result)
        self.assertIn("Acme Dental", result)

    def test_tool_missing_file_returns_error_text(self):
        result = self.registry.call("score_leads", {"path": "missing.csv"})
        self.assertIn("file not found", result)


if __name__ == "__main__":
    unittest.main()
