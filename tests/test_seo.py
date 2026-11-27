import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.config import Config
from muse_top.memory import Memory
from muse_top.seo import (
    audit_page,
    audit_seo_url,
    count_syllables,
    flesch_reading_ease,
    grade_for_score,
    keyword_stats,
    parse_html,
    render_audit,
    word_count,
)
from muse_top.tools import build_default_registry

KEYWORD = "wordpress developer"

# 320 words of body text containing the keyword several times.
BODY_SENTENCE = (
    "Our wordpress developer team builds fast websites for small "
    "businesses, with clear prices and friendly support every day. "
)
GOOD_BODY = (BODY_SENTENCE * 20).strip()  # 20 x 16 = 320 words

GOOD_HTML = f"""<!doctype html><html><head>
<title>WordPress Developer Services for Small Business</title>
<meta name="description" content="Hire a WordPress developer for fast, SEO-ready websites. 15 years of experience, 50+ sites built, clear pricing and friendly support.">
<link rel="canonical" href="https://example.com/services">
<meta property="og:title" content="WordPress Developer Services">
<meta property="og:description" content="Fast, SEO-ready WordPress websites.">
<meta property="og:image" content="https://example.com/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="WordPress Developer Services">
<script type="application/ld+json">{{"@type": "LocalBusiness", "name": "NZGenix"}}</script>
</head><body>
<h1>WordPress Developer for Small Business</h1>
<h2>What we build</h2>
<p>{GOOD_BODY}</p>
<h2>How it works</h2>
<p>{GOOD_BODY}</p>
<img src="hero.jpg" alt="WordPress developer at work">
<img src="team.jpg" alt="Our small team in the office">
<a href="/pricing">Pricing</a>
<a href="https://example.com/contact">Contact us</a>
</body></html>"""

BAD_HTML = """<!doctype html><html><head>
</head><body>
<p>Short page.</p>
<img src="a.jpg">
<img src="b.jpg" alt="">
<a href="#">Click here</a>
<a href="javascript:void(0)">Do nothing</a>
</body></html>"""


class TestParseHtml(unittest.TestCase):
    def test_extracts_all_fields(self):
        page = parse_html(GOOD_HTML)
        self.assertEqual(
            page.title, "WordPress Developer Services for Small Business")
        self.assertTrue(page.meta_description.startswith("Hire a WordPress"))
        self.assertEqual(page.canonical, "https://example.com/services")
        self.assertEqual(page.h1, ["WordPress Developer for Small Business"])
        self.assertEqual([lvl for lvl, _ in page.headings], [1, 2, 2])
        self.assertEqual(len(page.images), 2)
        self.assertEqual(page.images[0][1], "WordPress developer at work")
        self.assertTrue(page.has_json_ld)
        self.assertEqual(page.meta["og:title"], "WordPress Developer Services")
        self.assertEqual(len(page.links), 2)

    def test_bad_page_fields(self):
        page = parse_html(BAD_HTML)
        self.assertEqual(page.title, "")
        self.assertEqual(page.meta_description, "")
        self.assertEqual(page.h1, [])
        self.assertFalse(page.has_json_ld)
        self.assertEqual(page.images[0][1], None)


class TestAuditPage(unittest.TestCase):
    def test_good_page_scores_high(self):
        result = audit_page(parse_html(GOOD_HTML), "https://example.com",
                            KEYWORD)
        self.assertGreaterEqual(result["score"], 90)
        self.assertEqual(result["grade"], "A")
        self.assertEqual(result["failed_checks"], [])
        self.assertEqual(result["images_missing_alt"], 0)
        self.assertGreaterEqual(result["word_count"], 300)

    def test_bad_page_scores_low(self):
        result = audit_page(parse_html(BAD_HTML), "https://example.com/bad")
        self.assertLess(result["score"], 40)
        self.assertEqual(result["grade"], "F")
        for check in ("Title tag", "Meta description", "H1 heading",
                      "Image alt text"):
            self.assertIn(check, result["failed_checks"])
        self.assertTrue(result["fixes"])  # rule-based fixes present

    def test_title_too_short_warns(self):
        page = parse_html("<html><head><title>Hi</title></head>"
                          "<body><h1>Hi</h1></body></html>")
        result = audit_page(page, "x")
        title = next(c for c in result["checks"] if c["check"] == "Title tag")
        self.assertEqual(title["status"], "warn")

    def test_title_too_long_warns(self):
        page = parse_html("<html><head><title>" + "A" * 70 + "</title></head>"
                          "<body><h1>Hi</h1></body></html>")
        result = audit_page(page, "x")
        title = next(c for c in result["checks"] if c["check"] == "Title tag")
        self.assertEqual(title["status"], "warn")

    def test_multiple_h1_warns(self):
        page = parse_html("<html><head><title>" + "A" * 40 + "</title></head>"
                          "<body><h1>One</h1><h1>Two</h1></body></html>")
        result = audit_page(page, "x")
        h1 = next(c for c in result["checks"] if c["check"] == "H1 heading")
        self.assertEqual(h1["status"], "warn")

    def test_skipped_heading_level_warns(self):
        page = parse_html("<html><head><title>" + "A" * 40 + "</title></head>"
                          "<body><h1>Top</h1><h3>Skipped</h3></body></html>")
        result = audit_page(page, "x")
        order = next(c for c in result["checks"]
                     if c["check"] == "Heading order")
        self.assertEqual(order["status"], "warn")

    def test_images_all_alt_pass(self):
        page = parse_html(GOOD_HTML)
        result = audit_page(page, "x")
        alt = next(c for c in result["checks"]
                   if c["check"] == "Image alt text")
        self.assertEqual(alt["status"], "pass")

    def test_canonical_and_social_warns_when_missing(self):
        page = parse_html(BAD_HTML)
        result = audit_page(page, "x")
        by_name = {c["check"]: c for c in result["checks"]}
        self.assertEqual(by_name["Canonical URL"]["status"], "warn")
        self.assertEqual(by_name["Social tags (OG/Twitter)"]["status"], "warn")
        self.assertEqual(by_name["Schema.org markup"]["status"], "warn")

    def test_content_length_warns_when_short(self):
        page = parse_html(BAD_HTML)
        result = audit_page(page, "x")
        length = next(c for c in result["checks"]
                      if c["check"] == "Content length")
        self.assertEqual(length["status"], "warn")

    def test_placeholder_links_warn(self):
        page = parse_html(BAD_HTML)
        result = audit_page(page, "x")
        links = next(c for c in result["checks"] if c["check"] == "Links")
        self.assertEqual(links["status"], "warn")
        self.assertIn("2 placeholder", links["detail"])

    def test_keyword_absent_fails(self):
        result = audit_page(parse_html(GOOD_HTML), "x", "plumber chicago")
        kw = next(c for c in result["checks"]
                  if c["check"] == "Target keyword")
        self.assertEqual(kw["status"], "fail")
        self.assertIn("Target keyword", result["failed_checks"])

    def test_keyword_in_body_only_warns(self):
        # Keyword in body but not in title or H1.
        html = GOOD_HTML.replace(
            "WordPress Developer Services for Small Business",
            "Fast Websites for Small Business Owners Today")
        html = html.replace(
            "WordPress Developer for Small Business",
            "Websites for Small Business Owners")
        result = audit_page(parse_html(html), "x", KEYWORD)
        kw = next(c for c in result["checks"]
                  if c["check"] == "Target keyword")
        self.assertEqual(kw["status"], "warn")

    def test_keyword_in_title_and_h1_passes(self):
        result = audit_page(parse_html(GOOD_HTML), "x", KEYWORD)
        kw = next(c for c in result["checks"]
                  if c["check"] == "Target keyword")
        self.assertEqual(kw["status"], "pass")

    def test_no_keyword_check_without_keyword(self):
        result = audit_page(parse_html(GOOD_HTML), "x")
        names = [c["check"] for c in result["checks"]]
        self.assertNotIn("Target keyword", names)


class TestGradeBoundaries(unittest.TestCase):
    def test_grades(self):
        self.assertEqual(grade_for_score(100), "A")
        self.assertEqual(grade_for_score(90), "A")
        self.assertEqual(grade_for_score(89), "B")
        self.assertEqual(grade_for_score(75), "B")
        self.assertEqual(grade_for_score(74), "C")
        self.assertEqual(grade_for_score(60), "C")
        self.assertEqual(grade_for_score(59), "D")
        self.assertEqual(grade_for_score(40), "D")
        self.assertEqual(grade_for_score(39), "F")
        self.assertEqual(grade_for_score(0), "F")


class TestTextHelpers(unittest.TestCase):
    def test_word_count(self):
        self.assertEqual(word_count("one two three"), 3)
        self.assertEqual(word_count(""), 0)

    def test_count_syllables(self):
        self.assertEqual(count_syllables("cat"), 1)
        self.assertGreaterEqual(count_syllables("development"), 3)

    def test_flesch_none_for_short_text(self):
        self.assertIsNone(flesch_reading_ease("Too short."))

    def test_flesch_number_for_long_text(self):
        ease = flesch_reading_ease(GOOD_BODY)
        self.assertIsNotNone(ease)
        self.assertGreaterEqual(ease, 0)
        self.assertLessEqual(ease, 100)

    def test_keyword_stats(self):
        occ, density = keyword_stats("WordPress developer and wordpress "
                                     "DEVELOPER work.", KEYWORD)
        self.assertEqual(occ, 2)
        self.assertGreater(density, 0)
        self.assertEqual(keyword_stats("nothing here", KEYWORD), (0, 0.0))
        self.assertEqual(keyword_stats(GOOD_BODY, ""), (0, 0.0))


class TestRenderAudit(unittest.TestCase):
    def test_render_contains_score_and_fixes(self):
        result = audit_page(parse_html(BAD_HTML), "https://example.com/bad")
        text = render_audit(result)
        self.assertIn("SEO audit: https://example.com/bad", text)
        self.assertIn(f"Score: {result['score']}/100", text)
        self.assertIn("Fixes (rule-based, not AI output):", text)
        self.assertIn("[FAIL] Title tag", text)

    def test_render_good_page_has_no_fixes_section(self):
        result = audit_page(parse_html(GOOD_HTML), "https://example.com",
                            KEYWORD)
        text = render_audit(result)
        self.assertIn("Grade A", text)
        self.assertNotIn("Fixes (rule-based", text)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/good":
            body, ctype = GOOD_HTML.encode("utf-8"), "text/html; charset=utf-8"
        elif self.path == "/bad":
            body, ctype = BAD_HTML.encode("utf-8"), "text/html; charset=utf-8"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TestAuditSeoUrl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_good_page_end_to_end(self):
        result = audit_seo_url(self.url("/good"), keyword=KEYWORD)
        self.assertIn("Grade A", result)
        self.assertIn("Score:", result)

    def test_bad_page_end_to_end(self):
        result = audit_seo_url(self.url("/bad"))
        self.assertIn("Grade F", result)
        self.assertIn("[FAIL] Title tag", result)

    def test_404_returns_error_text(self):
        result = audit_seo_url(self.url("/missing"))
        self.assertIn("Error fetching", result)
        self.assertIn("404", result)

    def test_non_http_scheme_rejected(self):
        self.assertIn("only http(s)", audit_seo_url("ftp://example.com/x"))
        self.assertIn("only http(s)", audit_seo_url("file:///etc/passwd"))

    def test_empty_url_rejected(self):
        self.assertIn("no URL given", audit_seo_url(""))

    def test_unreachable_host_returns_error(self):
        result = audit_seo_url("http://127.0.0.1:1/", timeout_seconds=2)
        self.assertIn("Error fetching", result)


class TestAuditSeoTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.tmp.name) / "memory.json")
        self.registry = build_default_registry(self.memory, Config())

    def tearDown(self):
        self.tmp.cleanup()

    def test_audit_seo_registered(self):
        self.assertIn("audit_seo", self.registry.names())

    def test_audit_seo_via_registry_bad_url(self):
        result = self.registry.call("audit_seo", {"url": "notaurl"})
        self.assertIn("only http(s)", result)


if __name__ == "__main__":
    unittest.main()
