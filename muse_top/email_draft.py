"""Email drafts for Muse Top — stdlib only.

The agent can build an email draft and save it as a JSON file under
``~/.muse-top/drafts/``. It can NEVER send mail: there is no SMTP code
anywhere in this module, and a draft stays a draft (status ``"draft"``)
until a human approves and sends it by hand. That is the whole point —
drafting is safe, sending needs a person.

A draft file is named ``draft-YYYYMMDD-HHMMSS-001.json`` and holds:
``id``, ``to`` / ``cc`` / ``bcc`` (address lists), ``subject``, ``body``,
``created_at`` (ISO timestamp) and ``status``.
"""
from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path

# Good enough for a draft tool: local@domain with a dot in the domain.
_ADDRESS_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def is_valid_address(address: str) -> bool:
    """True when ``address`` looks like a deliverable email address."""
    if not isinstance(address, str):
        return False
    _, addr = parseaddr(address.strip())
    return bool(addr) and _ADDRESS_RE.match(addr) is not None


def parse_addresses(value) -> tuple[list[str], list[str]]:
    """Parse ``value`` (a string or list of strings) into addresses.

    Returns ``(addresses, invalid)`` — comma-separated strings are split,
    surrounding whitespace is stripped, and anything that is not a valid
    address lands in ``invalid`` instead of raising.
    """
    if value is None:
        return [], []
    if isinstance(value, str):
        raw = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        raw = [str(part).strip() for part in value]
    else:
        return [], [str(value)]
    addresses: list[str] = []
    invalid: list[str] = []
    for item in raw:
        if not item:
            continue
        if is_valid_address(item):
            addresses.append(parseaddr(item)[1])
        else:
            invalid.append(item)
    return addresses, invalid


def _next_draft_path(drafts_dir: Path, when: datetime) -> Path:
    """A unique filename for a new draft: timestamp + a 3-digit counter."""
    stamp = when.strftime("%Y%m%d-%H%M%S")
    for counter in range(1, 1000):
        candidate = drafts_dir / f"draft-{stamp}-{counter:03d}.json"
        if not candidate.exists():
            return candidate
    raise OSError("too many drafts created in one second")


def create_draft(
    drafts_dir: Path,
    to,
    subject: str,
    body: str = "",
    cc=None,
    bcc=None,
    when: datetime | None = None,
) -> str:
    """Build an email draft and save it. Returns a confirmation or error text.

    Nothing is ever sent. ``to`` is required; ``subject`` must not be
    empty; ``cc``/``bcc`` are optional. Bad addresses are reported, not
    silently dropped.
    """
    to_list, to_bad = parse_addresses(to)
    if to_bad:
        return f"Error: invalid recipient address(es): {', '.join(to_bad)}."
    if not to_list:
        return "Error: a draft needs at least one recipient (to)."
    cc_list, cc_bad = parse_addresses(cc)
    if cc_bad:
        return f"Error: invalid cc address(es): {', '.join(cc_bad)}."
    bcc_list, bcc_bad = parse_addresses(bcc)
    if bcc_bad:
        return f"Error: invalid bcc address(es): {', '.join(bcc_bad)}."
    if not isinstance(subject, str) or not subject.strip():
        return "Error: a draft needs a subject."
    if body is None:
        body = ""
    if not isinstance(body, str):
        return "Error: body must be text."

    when = when or datetime.now(timezone.utc)
    drafts_dir = Path(drafts_dir)
    drafts_dir.mkdir(parents=True, exist_ok=True)
    try:
        path = _next_draft_path(drafts_dir, when)
    except OSError as exc:
        return f"Error creating draft: {exc}."
    draft = {
        "id": path.stem,
        "to": to_list,
        "cc": cc_list,
        "bcc": bcc_list,
        "subject": subject.strip(),
        "body": body,
        "created_at": when.isoformat(),
        "status": "draft",
        "note": "Draft only — not sent. Sending needs a human's approval.",
    }
    payload = json.dumps(draft, indent=2, ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(drafts_dir), prefix=".draft-", suffix=".tmp"
    )
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        Path(tmp_name).replace(path)
    except OSError as exc:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass
        return f"Error saving draft: {exc}."
    return (
        f"Draft saved: {draft['id']} — to {', '.join(to_list)} "
        f"(subject: {subject.strip()}). Not sent."
    )


def list_drafts(drafts_dir: Path) -> str:
    """List saved drafts, newest first. Returns a short text summary."""
    drafts_dir = Path(drafts_dir)
    if not drafts_dir.exists():
        return "No drafts saved yet."
    drafts: list[dict] = []
    for path in drafts_dir.glob("draft-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or data.get("status") != "draft":
            continue
        drafts.append(data)
    if not drafts:
        return "No drafts saved yet."
    drafts.sort(key=lambda d: str(d.get("created_at", "")), reverse=True)
    lines = [f"{len(drafts)} draft(s):"]
    for draft in drafts:
        to = ", ".join(draft.get("to", [])) or "(no recipient)"
        lines.append(
            f"- {draft.get('id', '?')} | to {to} | "
            f"{draft.get('subject', '(no subject)')}"
        )
    return "\n".join(lines)
