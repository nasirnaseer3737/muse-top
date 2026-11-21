"""Fetching web pages for Muse Top — stdlib only.

``fetch_url`` downloads a page and returns its title plus readable text.
It is deliberately boring: http(s) only, a timeout, a size cap, and no
JavaScript. Anything it cannot fetch comes back as an error string, so
the agent loop never crashes on a bad URL.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_BYTES = 512_000  # 512 KB of raw page is plenty for a summary

_USER_AGENT = "MuseTop/0.2 (https://github.com/nasirnaseer3737/muse-top)"

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


def _html_to_text(html: str) -> tuple[str, str]:
    """Return (title, visible text) from an HTML document."""
    title_match = _TITLE_RE.search(html)
    title = _WHITESPACE_RE.sub(" ", title_match.group(1)).strip() if title_match else ""
    body = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", body)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return title, text


def fetch_url(
    url: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    """Fetch ``url`` and return ``Title: ...`` + readable text, or an error."""
    url = (url or "").strip()
    if not url:
        return "Error: no URL given."
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return f"Error: only http(s) URLs can be fetched, got '{url}'."

    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(max_bytes + 1)
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset("utf-8") or "utf-8"
    except urllib.error.HTTPError as exc:
        return f"Error fetching {url}: HTTP {exc.code} {exc.reason}."
    except urllib.error.URLError as exc:
        return f"Error fetching {url}: {exc.reason}."
    except (TimeoutError, OSError) as exc:
        return f"Error fetching {url}: {exc}."
    except ValueError as exc:
        return f"Error fetching {url}: {exc}."

    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]
    text = raw.decode(charset, errors="replace")

    if "html" in content_type:
        title, clean = _html_to_text(text)
    else:
        title, clean = "", _WHITESPACE_RE.sub(" ", text).strip()

    lines = [f"URL: {url}"]
    if title:
        lines.append(f"Title: {title}")
    lines.append(f"Text: {clean}" if clean else "Text: (page has no readable text)")
    if truncated:
        lines.append(f"(Note: page cut off after {max_bytes} bytes.)")
    return "\n".join(lines)
