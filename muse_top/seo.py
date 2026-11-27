"""On-page SEO audit for Muse Top — stdlib only.

``audit_seo`` fetches a URL and audits it against on-page SEO best
practice, reusing the rule logic of the NZ AI SEO Auditor daily build
(2026-11-20):

  * title tag present + length 30-60 chars
  * meta description present + length 120-160 chars
  * exactly one H1, sensible heading order (no skipped levels)
  * images: every <img> has non-empty alt text
  * canonical link present, Open Graph + Twitter Card tags present
  * JSON-LD schema.org markup present
  * internal / external link counts, broken-looking hrefs (#, javascript:)
  * word count, target-keyword usage in title / H1 / body + density
  * readability estimate (Flesch reading-ease approximation)

Each check is pass / warn / fail and rolls up into a 0-100 score with a
grade (A/B/C/D/F). Every failed or warning check carries a short,
rule-based fix — those fixes are deterministic templates, not AI
output. (If the agent wants real AI suggestions it can ask the LLM
itself, which has the audit summary in context.)

The audit itself is fully offline and deterministic once the page is
fetched. Fetching is http(s) only, with a timeout and a size cap, and
any fetch problem comes back as an error string, never an exception.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_BYTES = 512_000  # 512 KB of raw page is plenty for an audit

_USER_AGENT = "MuseTop/0.2 (https://github.com/nasirnaseer3737/muse-top)"

# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


class PageData:
    """Everything the audit needs from one HTML document."""

    def __init__(self):
        self.title = ""
        self.meta_description = ""
        self.meta = {}            # name/property -> content
        self.canonical = ""
        self.h1 = []
        self.headings = []        # list of (level, text)
        self.images = []          # list of (src, alt or None)
        self.links = []           # list of (href, text)
        self.has_json_ld = False
        self.body_text = ""
        self.raw_length = 0


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.data = PageData()
        self._in_title = False
        self._in_body = False
        self._in_script_style = False
        self._heading_level = 0
        self._heading_buf = []
        self._link_href = None
        self._link_buf = []
        self._body_chunks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self._in_script_style = True
            if tag == "script" and attrs.get("type") == "application/ld+json":
                self.data.has_json_ld = True
            return
        if tag == "title":
            self._in_title = True
        elif tag == "body":
            self._in_body = True
        elif tag == "meta":
            name = attrs.get("name") or attrs.get("property") or ""
            content = attrs.get("content", "")
            if name:
                self.data.meta[name.lower()] = content
            if name.lower() == "description":
                self.data.meta_description = content
        elif tag == "link" and attrs.get("rel") == "canonical":
            self.data.canonical = attrs.get("href", "")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading_level = int(tag[1])
            self._heading_buf = []
        elif tag == "img":
            self.data.images.append((attrs.get("src", ""), attrs.get("alt")))
        elif tag == "a":
            self._link_href = attrs.get("href", "")
            self._link_buf = []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._in_script_style = False
        elif tag == "title":
            self._in_title = False
        elif tag == "body":
            self._in_body = False
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._heading_level:
            text = " ".join("".join(self._heading_buf).split())
            self.data.headings.append((self._heading_level, text))
            if self._heading_level == 1:
                self.data.h1.append(text)
            self._heading_level = 0
        elif tag == "a" and self._link_href is not None:
            text = " ".join("".join(self._link_buf).split())
            self.data.links.append((self._link_href, text))
            self._link_href = None

    def handle_data(self, text):
        if self._in_script_style:
            return
        if self._in_title:
            self.data.title += text
        if self._heading_level:
            self._heading_buf.append(text)
        if self._link_href is not None:
            self._link_buf.append(text)
        if self._in_body:
            self._body_chunks.append(text)

    def finish(self):
        self.data.title = " ".join(self.data.title.split())
        self.data.meta_description = " ".join(
            self.data.meta_description.split())
        self.data.body_text = " ".join("".join(self._body_chunks).split())
        return self.data


def parse_html(html_text: str) -> PageData:
    """Parse an HTML string into a PageData object."""
    parser = _PageParser()
    parser.feed(html_text)
    parser.close()
    page = parser.finish()
    page.raw_length = len(html_text)
    return page


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z0-9']+")


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def count_syllables(word: str) -> int:
    """Rough syllable count for readability estimation."""
    word = word.lower().strip()
    word = re.sub(r"[^a-z]", "", word)
    if not word:
        return 0
    if len(word) <= 3:
        return 1
    word = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", word)
    word = re.sub(r"^y", "", word)
    groups = re.findall(r"[aeiouy]+", word)
    return max(1, len(groups))


def flesch_reading_ease(text: str) -> float | None:
    """Approximate Flesch reading-ease score (0-100, higher = easier)."""
    words = _WORD_RE.findall(text)
    if len(words) < 10:
        return None
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    sentences = sentences or [text]
    syllables = sum(count_syllables(w) for w in words)
    avg_words = len(words) / len(sentences)
    avg_syll = syllables / len(words)
    score = 206.835 - 1.015 * avg_words - 84.6 * avg_syll
    return round(max(0.0, min(100.0, score)), 1)


def keyword_stats(text: str, keyword: str) -> tuple[int, float]:
    """Return (occurrences, density %) of keyword (case-insensitive)."""
    if not keyword:
        return 0, 0.0
    words = word_count(text)
    if words == 0:
        return 0, 0.0
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    occ = len(pattern.findall(text))
    return occ, round(occ / words * 100, 2)


# ---------------------------------------------------------------------------
# Audit checks
# ---------------------------------------------------------------------------

def grade_for_score(score: int) -> str:
    """Grade bands: A >= 90, B >= 75, C >= 60, D >= 40, else F."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _check(title, status, detail, weight=1, fix=""):
    return {
        "check": title, "status": status, "detail": detail,
        "weight": weight, "fix": fix,
    }


def audit_page(page: PageData, source: str, keyword: str = "") -> dict:
    """Run all checks on a parsed page. Returns a result dict."""
    checks = []
    title = page.title
    if not title:
        checks.append(_check("Title tag", "fail", "No <title> tag found.",
                             3, "Add a unique <title> of 30-60 characters."))
    elif len(title) < 30:
        checks.append(_check("Title tag", "warn",
                             f"Title is {len(title)} chars (too short, aim 30-60).",
                             2, "Expand the title to 30-60 chars, lead with the keyword."))
    elif len(title) > 60:
        checks.append(_check("Title tag", "warn",
                             f"Title is {len(title)} chars (too long, aim 30-60).",
                             2, "Trim the title to under 60 chars; keep the keyword near the front."))
    else:
        checks.append(_check("Title tag", "pass",
                             f"Title is {len(title)} chars.", 1))

    desc = page.meta_description
    if not desc:
        checks.append(_check("Meta description", "fail", "No meta description.",
                             3, "Add a 120-160 char meta description with a call to action."))
    elif len(desc) < 120:
        checks.append(_check("Meta description", "warn",
                             f"Meta description is {len(desc)} chars (aim 120-160).",
                             2, "Expand the meta description to 120-160 chars."))
    elif len(desc) > 160:
        checks.append(_check("Meta description", "warn",
                             f"Meta description is {len(desc)} chars (aim 120-160).",
                             2, "Trim the meta description to under 160 chars."))
    else:
        checks.append(_check("Meta description", "pass",
                             f"Meta description is {len(desc)} chars.", 1))

    if len(page.h1) == 0:
        checks.append(_check("H1 heading", "fail", "No H1 on the page.",
                             3, "Add exactly one H1 that states the page topic."))
    elif len(page.h1) > 1:
        checks.append(_check("H1 heading", "warn",
                             f"{len(page.h1)} H1 tags found (aim for exactly one).",
                             2, "Keep one H1; demote the others to H2."))
    else:
        checks.append(_check("H1 heading", "pass",
                             f'One H1: "{page.h1[0][:60]}"', 1))

    # Heading order: no skipped levels (H1 -> H3 with no H2).
    levels = [lvl for lvl, _ in page.headings]
    skipped = any(levels[i + 1] > levels[i] + 1 for i in range(len(levels) - 1))
    if skipped:
        checks.append(_check("Heading order", "warn",
                             "Heading levels are skipped (e.g. H1 straight to H3).",
                             1, "Use headings in order: H1, then H2, then H3."))
    else:
        checks.append(_check("Heading order", "pass",
                             f"{len(page.headings)} headings in order.", 1))

    missing_alt = [src for src, alt in page.images if alt is None or not alt.strip()]
    if page.images and missing_alt:
        checks.append(_check("Image alt text", "fail",
                             f"{len(missing_alt)} of {len(page.images)} images "
                             "have no alt text.",
                             2, "Write descriptive alt text (under 125 chars) for every image."))
    elif page.images:
        checks.append(_check("Image alt text", "pass",
                             f"All {len(page.images)} images have alt text.", 1))
    else:
        checks.append(_check("Image alt text", "pass",
                             "No images on the page.", 1))

    if not page.canonical:
        checks.append(_check("Canonical URL", "warn", "No canonical link tag.",
                             1, 'Add <link rel="canonical" href="..."> with the preferred URL.'))
    else:
        checks.append(_check("Canonical URL", "pass",
                             f"Canonical set: {page.canonical[:60]}", 1))

    og_missing = [t for t in ("og:title", "og:description", "og:image")
                  if t not in page.meta]
    tw_missing = [t for t in ("twitter:card", "twitter:title")
                  if t not in page.meta]
    if og_missing or tw_missing:
        missing = ", ".join(og_missing + tw_missing)
        checks.append(_check("Social tags (OG/Twitter)", "warn",
                             f"Missing social tags: {missing}.",
                             1, "Add Open Graph + Twitter Card tags so shares look right."))
    else:
        checks.append(_check("Social tags (OG/Twitter)", "pass",
                             "Open Graph and Twitter Card tags present.", 1))

    if page.has_json_ld:
        checks.append(_check("Schema.org markup", "pass",
                             "JSON-LD structured data found.", 1))
    else:
        checks.append(_check("Schema.org markup", "warn",
                             "No JSON-LD structured data found.",
                             1, "Add JSON-LD schema (e.g. LocalBusiness, Article or WebPage)."))

    words = word_count(page.body_text)
    if words < 300:
        checks.append(_check("Content length", "warn",
                             f"Only {words} words of body text (aim 300+).",
                             2, "Add useful content — aim for at least 300 words on the topic."))
    else:
        checks.append(_check("Content length", "pass",
                             f"{words} words of body text.", 1))

    internal = [h for h, _ in page.links
                if h.startswith("/") or h.startswith("#") or not h.startswith("http")]
    external = [h for h, _ in page.links if h.startswith("http")]
    broken = [h for h, _ in page.links
              if h.strip() in ("", "#") or h.startswith("javascript:")]
    if broken:
        checks.append(_check("Links", "warn",
                             f"{len(broken)} placeholder/broken-looking links "
                             f"({len(internal)} internal, {len(external)} external).",
                             1, "Fix or remove placeholder links (#, javascript:)."))
    else:
        checks.append(_check("Links", "pass",
                             f"{len(internal)} internal, {len(external)} external links.", 1))

    ease = flesch_reading_ease(page.body_text)
    if ease is None:
        checks.append(_check("Readability", "warn",
                             "Too little text to judge readability.", 1,
                             "Add more body text."))
    elif ease < 50:
        checks.append(_check("Readability", "warn",
                             f"Flesch reading ease {ease} (hard to read, aim 60+).",
                             1, "Shorten sentences and use simpler words."))
    else:
        checks.append(_check("Readability", "pass",
                             f"Flesch reading ease {ease}.", 1))

    if keyword:
        occ, density = keyword_stats(page.body_text, keyword)
        in_title = keyword.lower() in title.lower()
        in_h1 = any(keyword.lower() in h.lower() for h in page.h1)
        kw_detail = (f'"{keyword}" appears {occ}x in body '
                     f"(density {density}%), "
                     f"in title: {'yes' if in_title else 'no'}, "
                     f"in H1: {'yes' if in_h1 else 'no'}.")
        if occ == 0:
            checks.append(_check("Target keyword", "fail",
                                 kw_detail, 3,
                                 f'Use "{keyword}" in the title, H1 and naturally in the body.'))
        elif not in_title or not in_h1:
            checks.append(_check("Target keyword", "warn", kw_detail, 2,
                                 f'Put "{keyword}" in the title and the H1.'))
        else:
            checks.append(_check("Target keyword", "pass", kw_detail, 1))

    # Score: weighted — pass = full weight, warn = half, fail = 0.
    total_weight = sum(c["weight"] for c in checks)
    earned = sum(c["weight"] for c in checks if c["status"] == "pass")
    earned += sum(c["weight"] * 0.5 for c in checks if c["status"] == "warn")
    score = round(earned / total_weight * 100) if total_weight else 0

    fails = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]

    return {
        "source": source,
        "keyword": keyword,
        "score": score,
        "grade": grade_for_score(score),
        "word_count": words,
        "readability": ease,
        "images": len(page.images),
        "images_missing_alt": len(missing_alt),
        "links_internal": len(internal),
        "links_external": len(external),
        "checks": checks,
        "failed_checks": [c["check"] for c in fails],
        "warning_checks": [c["check"] for c in warns],
        # Rule-based fixes (deterministic templates, not AI output).
        "fixes": [c["fix"] for c in fails + warns if c["fix"]],
    }


# ---------------------------------------------------------------------------
# Fetching + rendering
# ---------------------------------------------------------------------------

def fetch_html(url: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
               max_bytes: int = DEFAULT_MAX_BYTES) -> tuple[str | None, str | None]:
    """Fetch ``url`` and return (html, None), or (None, error text)."""
    url = (url or "").strip()
    if not url:
        return None, "Error: no URL given."
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None, f"Error: only http(s) URLs can be fetched, got '{url}'."

    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(max_bytes + 1)
            charset = response.headers.get_content_charset("utf-8") or "utf-8"
    except urllib.error.HTTPError as exc:
        return None, f"Error fetching {url}: HTTP {exc.code} {exc.reason}."
    except urllib.error.URLError as exc:
        return None, f"Error fetching {url}: {exc.reason}."
    except (TimeoutError, OSError) as exc:
        return None, f"Error fetching {url}: {exc}."
    except ValueError as exc:
        return None, f"Error fetching {url}: {exc}."

    raw = raw[:max_bytes]
    return raw.decode(charset, errors="replace"), None


def render_audit(result: dict) -> str:
    """Render an audit result dict as readable text for the agent."""
    lines = [
        f"SEO audit: {result['source']}",
        f"Score: {result['score']}/100 (Grade {result['grade']})",
        f"Words: {result['word_count']}  |  Readability (Flesch): "
        f"{result['readability'] if result['readability'] is not None else 'n/a'}",
        f"Images: {result['images']} ({result['images_missing_alt']} missing alt)  |  "
        f"Links: {result['links_internal']} internal, {result['links_external']} external",
        "",
        "Checks:",
    ]
    for c in result["checks"]:
        lines.append(f"  [{c['status'].upper()}] {c['check']}: {c['detail']}")
    if result["fixes"]:
        lines.append("")
        lines.append("Fixes (rule-based, not AI output):")
        for fix in result["fixes"]:
            lines.append(f"  - {fix}")
    return "\n".join(lines)


def audit_seo_url(url: str, keyword: str = "",
                  timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
                  max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    """Fetch ``url`` and return its on-page SEO audit as text.

    Errors (bad URL, fetch failure) come back as text, never raise.
    """
    html, error = fetch_html(url, timeout_seconds=timeout_seconds,
                             max_bytes=max_bytes)
    if error is not None:
        return error
    page = parse_html(html)
    return render_audit(audit_page(page, url, keyword))
