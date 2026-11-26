"""Lead scoring for Muse Top — stdlib only.

Scores a leads CSV (0-100, grades A-D) using the same rule-based logic
as the NZ AI Lead Scorer daily build (2026-11-14): email quality, phone,
website, company size, industry fit, lead source, budget signal and
TCPA consent. The scoring itself is fully offline and deterministic.

Consent matters: a lead without TCPA consent is scored but flagged
DO-NOT-CONTACT and excluded from the ranked outreach list — the agent
must never contact those leads.

Each top lead also gets a one-line outreach angle. It is a deterministic
template, always labelled ``[MOCK — no API key]`` — it is not model
output. (If the agent wants a real AI angle it can ask the LLM itself,
which has the scored summary in context.)

The tool reads the CSV from inside the agent workspace via the same
sandbox as ``read_file`` — paths outside the workspace are refused.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from .files import resolve_workspace_path

MAX_LEADS = 500

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "protonmail.com", "mail.com", "gmx.com", "yandex.com",
}

# Industries the user's web-dev / AI-automation business serves best.
TARGET_INDUSTRIES = {
    "ecommerce", "e-commerce", "real estate", "healthcare", "dental",
    "legal", "law", "home services", "plumbing", "hvac", "roofing",
    "saas", "fitness", "restaurant", "hospitality", "education",
    "finance", "insurance", "automotive", "construction",
}

SOURCE_SCORES = {
    "referral": 15,
    "website form": 12,
    "website": 12,
    "inbound": 12,
    "facebook lead ad": 10,
    "facebook": 10,
    "google ads": 10,
    "quiz funnel": 10,
    "trade show": 8,
    "purchased list": 5,
    "cold list": 2,
    "scraped": 0,
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
PHONE_DIGITS_RE = re.compile(r"\D")
URL_RE = re.compile(r"^(https?://)?([\w-]+\.)+[\w-]{2,}(/\S*)?$", re.I)
BUDGET_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def _clean(value) -> str:
    return (value or "").strip()


def _domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower() if "@" in email else ""


def _employees_number(raw) -> int | None:
    """Parse '25', '11-50', '50+' into an int (upper bound of a range)."""
    raw = _clean(raw)
    if not raw:
        return None
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", raw)]
    if not nums:
        return None
    return max(nums)


def _budget_number(raw) -> float | None:
    """Parse '$5k/mo' / '5000' into a rough USD number (k = thousands)."""
    raw = _clean(raw).lower()
    if not raw:
        return None
    match = BUDGET_RE.search(raw)
    if not match:
        return None
    value = float(match.group(0).replace(",", ""))
    if "k" in raw:
        value *= 1000
    return value


def grade_for_score(score: int) -> str:
    """Grade bands: A >= 80, B >= 60, C >= 40, else D."""
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def score_lead(lead: dict) -> tuple[int, str, list[str], bool]:
    """Score one lead dict. Returns (score 0-100, grade, reasons,
    contact_ok bool)."""
    reasons: list[str] = []
    score = 0

    email = _clean(lead.get("email"))
    if email and EMAIL_RE.match(email):
        domain = _domain(email)
        if domain in FREE_EMAIL_DOMAINS:
            score += 5
            reasons.append("free email domain (+5)")
        else:
            score += 15
            reasons.append("business email domain (+15)")
    elif email:
        score -= 10
        reasons.append("invalid email (-10)")
    else:
        reasons.append("no email (+0)")

    phone = PHONE_DIGITS_RE.sub("", _clean(lead.get("phone")))
    if len(phone) >= 10:
        score += 10
        reasons.append("reachable phone (+10)")
    elif phone:
        score += 3
        reasons.append("partial phone (+3)")
    else:
        reasons.append("no phone (+0)")

    website = _clean(lead.get("website"))
    if website and URL_RE.match(website):
        score += 10
        reasons.append("has website (+10)")
    elif website:
        score += 2
        reasons.append("website looks malformed (+2)")
    else:
        reasons.append("no website (+0)")

    employees = _employees_number(lead.get("employees"))
    if employees is None:
        reasons.append("company size unknown (+0)")
    elif employees <= 10:
        score += 5
        reasons.append("small team 1-10 (+5)")
    elif employees <= 50:
        score += 10
        reasons.append("team 11-50 (+10)")
    elif employees <= 200:
        score += 15
        reasons.append("team 51-200 (+15)")
    else:
        score += 10
        reasons.append("large team 200+ (+10)")

    industry = _clean(lead.get("industry")).lower()
    if industry in TARGET_INDUSTRIES:
        score += 15
        reasons.append(f"target industry '{industry}' (+15)")
    elif industry:
        score += 5
        reasons.append(f"non-target industry '{industry}' (+5)")
    else:
        reasons.append("industry unknown (+0)")

    source = _clean(lead.get("source")).lower()
    source_points = SOURCE_SCORES.get(source, 5 if source else 0)
    score += source_points
    reasons.append(f"source '{source or 'unknown'}' (+{source_points})")

    budget = _budget_number(lead.get("budget"))
    if budget is None:
        reasons.append("no budget signal (+0)")
    elif budget >= 1000:
        score += 15
        reasons.append("budget >= $1000 (+15)")
    else:
        score += 8
        reasons.append("budget stated, under $1000 (+8)")

    consent = _clean(lead.get("consent")).lower()
    contact_ok = consent in ("yes", "y", "true", "1", "opt-in", "opt in")
    if contact_ok:
        score += 5
        reasons.append("TCPA consent given (+5)")
    else:
        reasons.append("NO consent — do not contact (+0)")

    score = max(0, min(100, score))
    return score, grade_for_score(score), reasons, contact_ok


def mock_angle(lead: dict, score: int, grade: str, reasons: list[str]) -> str:
    """Deterministic offline outreach angle. Always labelled MOCK."""
    industry = _clean(lead.get("industry")) or "their business"
    company = _clean(lead.get("company")) or "this lead"
    top = reasons[0].split(" (")[0] if reasons else "general fit"
    return (
        f"[MOCK — no API key] Pitch {company} on a {industry} website / "
        f"automation upgrade; strongest signal: {top} "
        f"(grade {grade}, {score}/100)."
    )


def parse_leads_csv(text: str) -> list[dict]:
    """Parse CSV text into lead dicts. Headers are case-insensitive and
    stripped; rows with no data at all are skipped."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return []
    leads: list[dict] = []
    for row in reader:
        lead = {
            (key or "").strip().lower(): (value or "")
            for key, value in row.items()
            if key is not None
        }
        if not any(value.strip() for value in lead.values()):
            continue
        leads.append(lead)
    return leads


def score_all(leads: list[dict], max_rows: int = MAX_LEADS) -> tuple[list[dict], bool]:
    """Score every lead, attach a mock angle, sort best first.

    Returns ``(scored, truncated)`` — ``truncated`` is True when the
    input had more rows than ``max_rows`` and the rest were skipped.
    """
    truncated = len(leads) > max_rows
    scored: list[dict] = []
    for lead in leads[:max_rows]:
        score, grade, reasons, contact_ok = score_lead(lead)
        scored.append({
            **lead,
            "score": score,
            "grade": grade,
            "reasons": reasons,
            "angle": mock_angle(lead, score, grade, reasons),
            "contact_ok": contact_ok,
        })
    scored.sort(key=lambda row: row["score"], reverse=True)
    return scored, truncated


def render_summary(scored: list[dict], top: int = 5, truncated: bool = False) -> str:
    """Render the scored list as short text for the agent."""
    contactable = [row for row in scored if row["contact_ok"]]
    blocked = len(scored) - len(contactable)
    grades = {g: sum(1 for row in scored if row["grade"] == g) for g in "ABCD"}
    lines = [
        f"Scored {len(scored)} lead(s) | "
        f"A:{grades['A']} B:{grades['B']} C:{grades['C']} D:{grades['D']} | "
        f"contactable: {len(contactable)} | "
        f"DO-NOT-CONTACT (no consent): {blocked}"
    ]
    if truncated:
        lines.append(f"Note: only the first {len(scored)} rows were scored.")
    shown = contactable[: max(0, top)]
    if shown:
        lines.append(f"\nTop {len(shown)} contactable lead(s):")
        for index, row in enumerate(shown, start=1):
            name = _clean(row.get("name")) or "(no name)"
            company = _clean(row.get("company")) or "(no company)"
            industry = _clean(row.get("industry")) or "unknown industry"
            email = _clean(row.get("email")) or "(no email)"
            lines.append(
                f"{index}. {row['score']}/100 ({row['grade']}) — {name}, "
                f"{company} ({industry}) — {email}"
            )
            lines.append(f"   Signals: {'; '.join(row['reasons'][:3])}")
            lines.append(f"   Angle: {row['angle']}")
    else:
        lines.append("\nNo contactable leads — every lead lacks TCPA consent.")
    if blocked:
        lines.append(
            f"\n{blocked} lead(s) flagged DO-NOT-CONTACT (no TCPA consent) "
            "— scored but excluded from outreach."
        )
    return "\n".join(lines)


def score_leads_text(text: str, top: int = 5, max_rows: int = MAX_LEADS) -> str:
    """Score CSV text and return the summary. Errors return text, never raise."""
    try:
        leads = parse_leads_csv(text)
    except (csv.Error, UnicodeDecodeError) as exc:
        return f"Error: could not parse leads CSV: {exc}."
    if not leads:
        return "No leads found in the CSV."
    scored, truncated = score_all(leads, max_rows=max_rows)
    return render_summary(scored, top=top, truncated=truncated)


def score_leads_file(
    workspace: Path,
    path: str,
    top: int = 5,
    max_bytes: int = 64_000,
    max_rows: int = MAX_LEADS,
) -> str:
    """Score a leads CSV inside the workspace. Returns summary or error text.

    Uses the same sandbox resolver as ``read_file`` — paths outside the
    workspace are refused — but reads the raw bytes itself so the CSV
    parser gets clean input (``read_file`` wraps its output in a header).
    """
    resolved = resolve_workspace_path(workspace, path)
    if resolved is None:
        return f"Error: '{path}' is outside the workspace."
    if not resolved.exists():
        return f"Error: file not found: '{path}'."
    if resolved.is_dir():
        return f"Error: '{path}' is a directory, not a file."
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        return f"Error reading '{path}': {exc}."
    if len(raw) > max_bytes:
        return (
            "Error: leads CSV is larger than the read cap "
            f"({max_bytes} bytes) — split it into smaller files."
        )
    text = raw.decode("utf-8-sig", errors="replace")
    return score_leads_text(text, top=top, max_rows=max_rows)
