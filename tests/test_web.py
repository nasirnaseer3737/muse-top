import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.config import Config
from muse_top.memory import Memory
from muse_top.tools import build_default_registry
from muse_top.web import fetch_url

HTML_PAGE = b"""<!doctype html><html><head>
<title>Test Page Title</title>
<style>body { color: red; }</style>
<script>var secret = "not visible";</script>
</head><body>
<h1>Hello World</h1>
<p>Some readable text here.</p>
</body></html>"""

TEXT_PAGE = b"Just plain text,\nsecond line."


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/page":
            body, ctype = HTML_PAGE, "text/html; charset=utf-8"
        elif self.path == "/text":
            body, ctype = TEXT_PAGE, "text/plain; charset=utf-8"
        elif self.path == "/big":
            body, ctype = b"x" * 5000, "text/plain; charset=utf-8"
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


class TestWebFetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_html_title_and_text(self):
        result = fetch_url(self.url("/page"))
        self.assertIn("Title: Test Page Title", result)
        self.assertIn("Hello World", result)
        self.assertIn("Some readable text here.", result)
        self.assertNotIn("not visible", result)  # script content stripped
        self.assertNotIn("color: red", result)  # style content stripped

    def test_plain_text_page(self):
        result = fetch_url(self.url("/text"))
        self.assertIn("Just plain text,", result)
        self.assertIn("second line.", result)

    def test_404_returns_error_text(self):
        result = fetch_url(self.url("/missing"))
        self.assertIn("Error fetching", result)
        self.assertIn("404", result)

    def test_non_http_scheme_rejected(self):
        self.assertIn("only http(s)", fetch_url("ftp://example.com/file"))
        self.assertIn("only http(s)", fetch_url("file:///etc/passwd"))

    def test_empty_url_rejected(self):
        self.assertIn("no URL given", fetch_url(""))

    def test_size_cap_truncates(self):
        result = fetch_url(self.url("/big"), max_bytes=100)
        self.assertIn("cut off after 100 bytes", result)
        self.assertLess(len(result), 500)

    def test_unreachable_host_returns_error(self):
        # Port 1 on localhost refuses connections.
        result = fetch_url("http://127.0.0.1:1/", timeout_seconds=2)
        self.assertIn("Error fetching", result)


class TestWebFetchTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.tmp.name) / "memory.json")
        self.registry = build_default_registry(self.memory, Config())

    def tearDown(self):
        self.tmp.cleanup()

    def test_web_fetch_registered(self):
        self.assertIn("web_fetch", self.registry.names())

    def test_web_fetch_via_registry(self):
        result = self.registry.call("web_fetch", {"url": "notaurl"})
        self.assertIn("only http(s)", result)


class TestWebConfig(unittest.TestCase):
    def test_config_defaults(self):
        config = Config()
        self.assertEqual(config.web_timeout_seconds, 15)
        self.assertEqual(config.web_max_bytes, 512_000)

    def test_config_from_env(self):
        import os

        os.environ["MUSE_TOP_WEB_TIMEOUT"] = "7"
        os.environ["MUSE_TOP_WEB_MAX_BYTES"] = "12345"
        try:
            config = Config.from_env()
        finally:
            del os.environ["MUSE_TOP_WEB_TIMEOUT"]
            del os.environ["MUSE_TOP_WEB_MAX_BYTES"]
        self.assertEqual(config.web_timeout_seconds, 7)
        self.assertEqual(config.web_max_bytes, 12345)


if __name__ == "__main__":
    unittest.main()
