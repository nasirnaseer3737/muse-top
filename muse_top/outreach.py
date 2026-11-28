"""Outreach drafting for Muse Top — stdlib only.

Drafts a personalised outreach email from a prospect row (a leads CSV
row, as scored by ``leads.py``) and saves it as a draft via
``email_draft.create_draft`` — it NEVER sends mail.

Rules baked in (the user's standing outreach rules):
- Never tell the recipient to call — the CTA is: reply to the email
  OR chat on WhatsApp (``wa.me/<number>``).
- State the experience: 15+ years, 50+ websites built, 30 built and
  launched in the last 12 months.
- Name the prospect's problem, how it will be solved, and why web +
  local SEO + AI automation are necessary.
- No prices in a cold first mail.
- TCPA consent gate: a prospect without consent is DO-NOT-CONTACT —
  no draft is created for them.

The email text is built from deterministic templates personalised with
the prospect's own fields (name, company, industry, website, score).
It is labelled as template-built, not AI output.
"""
from __future__ import annotations

from pathlib import Path

from .email_draft import create_draft
from .files import resolve_workspace_path
from .leads import _clean, parse_leads_csv, score_lead

DEFAULT_SENDER_NAME = "Nasir Naseer"
DEFAULT_WHATSAPP = "923339845505"  # digits only; wa.me/<number>

EXPERIENCE_LINE = (
    "I build websites like that: 15+ years in web development, "
    "50+ websites built, 30 built and launched in the last 12 months, "
    "each one SEO-ready with AI automation built in."
)

CALL_CTA_PHRASES = (
    "call me",
    "give me a call",
    "book a call",
    "schedule a call",
    "jump on a call",
    "hop on a call",
    "let's talk on the phone",
)


def _first_name(name: str) -> str:
    """First word of a full name, or '' when there is no name."""
    return _clean(name).split(" ")[0] if _clean(name) else ""


def problem_line(lead: dict) -> str:
    """The prospect's problem, in one sentence, from their own fields."""
    company = _clean(lead.get("company")) or "your business"
    industry = _clean(lead.get("industry")) or "your industry"
    website = _clean(lead.get("website"))
    if website:
        return (
            f"{company}'s website is live, but it isn't set up to catch "
            "enquiries the moment they arrive — no instant reply, no "
            "online booking — so visitors leave and contact the next "
            f"{industry} business on the list instead."
        )
    return (
        f"{company} has no website yet, so people searching for "
        f"{industry} on Google can't find {company} at all — every one "
        "of those searches goes to a competitor instead."
    )


def subject_options(lead: dict) -> list[str]:
    """Three subject-line options, personalised with the company name."""
    company = _clean(lead.get("company")) or "your business"
    return [
        f"Quick idea for {company}'s website",
        f"{company} — turning missed enquiries into bookings",
        f"A faster website + AI replies for {company}",
    ]


def build_outreach_email(
    lead: dict,
    sender_name: str = DEFAULT_SENDER_NAME,
    whatsapp: str = DEFAULT_WHATSAPP,
) -> dict:
    """Build a personalised outreach email for one prospect row.

    Returns ``{"subject_options", "subject", "body"}``. Raises
    ``ValueError`` when no draft may be built: no TCPA consent
    (DO-NOT-CONTACT), no usable email address, or no name/company to
    address the mail to.
    """
    score, grade, reasons, contact_ok = score_lead(lead)
    if not contact_ok:
        raise ValueError(
            "DO-NOT-CONTACT: this prospect has not given consent — "
            "no outreach draft will be built."
        )
    email = _clean(lead.get("email"))
    if not email:
        raise ValueError("Cannot draft outreach: the prospect has no email.")
    first = _first_name(lead.get("name"))
    company = _clean(lead.get("company"))
    industry = _clean(lead.get("industry")) or "your industry"
    if not first and not company:
        raise ValueError(
            "Cannot draft outreach: the prospect has neither a name "
            "nor a company to address."
        )
    greeting = f"Hi {first}," if first else "Hello,"
    subjects = subject_options(lead)
    body = "\n\n".join(
        [
            greeting,
            f"I came across {company or 'your business'} while researching "
            f"{industry} businesses — {problem_line(lead)}",
            "A fast, SEO-ready website with instant AI replies and online "
            f"booking turns those missed enquiries into booked jobs, and "
            f"local SEO puts your business in front of people searching "
            f"for it on Google. That is why the website, the local SEO "
            "and the AI automation have to work together — one without "
            "the others still leaks enquiries.",
            EXPERIENCE_LINE,
            "If it sounds useful, just reply to this email or message me "
            f"on WhatsApp: https://wa.me/{whatsapp} — happy to chat there.",
            "Best regards,\n"
            f"{sender_name}\n"
            "NZGenix — Web Development, Local SEO & AI Automation",
        ]
    )
    return {
        "subject_options": subjects,
        "subject": subjects[0],
        "body": body,
        "score": score,
        "grade": grade,
        "reasons": reasons,
        "email": email,
    }


def _pick_row(leads: list[dict], row: int | None, email: str | None) -> dict:
    """Pick one prospect row by 1-based row number or by email address."""
    if row is not None:
        if row < 1 or row > len(leads):
            raise ValueError(
                f"Row {row} is out of range — the CSV has {len(leads)} lead(s)."
            )
        return leads[row - 1]
    if email:
        wanted = _clean(email).lower()
        for lead in leads:
            if _clean(lead.get("email")).lower() == wanted:
                return lead
        raise ValueError(f"No prospect with email '{email}' in the CSV.")
    raise ValueError("Give a row number or an email to pick the prospect.")


def draft_outreach_file(
    workspace: Path,
    path: str,
    drafts_dir: Path,
    row: int | None = None,
    email: str | None = None,
    sender_name: str = DEFAULT_SENDER_NAME,
    whatsapp: str = DEFAULT_WHATSAPP,
    max_bytes: int = 64_000,
    max_rows: int = 500,
) -> str:
    """Draft a personalised outreach email for one prospect in a CSV.

    The CSV must live inside the workspace (same sandbox as
    ``read_file``); the prospect is picked by 1-based ``row`` or by
    ``email``. The draft is saved via ``create_draft`` — never sent.
    Errors return text, never raise.
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
            "Error: prospects CSV is larger than the read cap "
            f"({max_bytes} bytes) — split it into smaller files."
        )
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        leads = parse_leads_csv(text)
    except Exception as exc:  # noqa: BLE001 — CSV errors return text
        return f"Error: could not parse prospects CSV: {exc}."
    if not leads:
        return "No prospects found in the CSV."
    if len(leads) > max_rows:
        leads = leads[:max_rows]
    try:
        lead = _pick_row(leads, row, email)
        built = build_outreach_email(lead, sender_name=sender_name, whatsapp=whatsapp)
    except ValueError as exc:
        return f"Error: {exc}"
    saved = create_draft(
        drafts_dir, built["email"], built["subject"], built["body"]
    )
    if saved.startswith("Error:"):
        return saved
    company = _clean(lead.get("company")) or "(no company)"
    preview = "\n".join(
        [
            f"Outreach draft for {company} — lead score "
            f"{built['score']}/100 (grade {built['grade']}).",
            f"Subject options: {'; '.join(built['subject_options'])}",
            "Draft built from a template personalised with the prospect's "
            "own details (not AI-written).",
            saved,
        ]
    )
    return preview
