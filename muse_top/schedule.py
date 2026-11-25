"""Scheduled tasks for Muse Top — stdlib only.

The agent can schedule a task (a message for itself) to run at a later
time, and ``python -m muse_top run --once`` executes every task whose
time has come. Tasks live in a JSON file (default
``~/.muse-top/schedule.json``).

A task is: ``id``, ``task`` (the message text), ``when`` (ISO local
datetime), ``created_at``, ``status`` (``pending`` / ``done`` /
``cancelled``), ``last_run`` and ``result``.

``when`` accepts a few friendly forms:
- ``2026-11-26 14:00`` (or ``2026-11-26T14:00``, or just a date)
- ``in 30 minutes`` / ``in 2 hours`` / ``in 3 days``
- ``tomorrow 14:00`` / ``today 14:00``

Times are naive local times. A task whose time has passed is due and
runs on the next ``run --once``. Writes are atomic (temp file +
replace); a corrupt or oddly-shaped file starts empty instead of
crashing.
"""
from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_RELATIVE_RE = re.compile(
    r"^in\s+(\d+)\s+(minute|minutes|hour|hours|day|days)\s*$", re.IGNORECASE
)
_DAY_RE = re.compile(r"^(today|tomorrow)\s+(\d{1,2}):(\d{2})\s*$", re.IGNORECASE)

_STATUSES = ("pending", "done", "cancelled")


def parse_when(text: str, now: datetime | None = None) -> datetime | None:
    """Parse a ``when`` string into a datetime, or None if not understood."""
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if not raw:
        return None
    now = now or datetime.now()

    match = _RELATIVE_RE.match(raw)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        deltas = {
            "minute": timedelta(minutes=amount),
            "minutes": timedelta(minutes=amount),
            "hour": timedelta(hours=amount),
            "hours": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "days": timedelta(days=amount),
        }
        return now + deltas[unit]

    match = _DAY_RE.match(raw)
    if match:
        day = now.date()
        if match.group(1).lower() == "tomorrow":
            day += timedelta(days=1)
        hour, minute = int(match.group(2)), int(match.group(3))
        if hour > 23 or minute > 59:
            return None
        return datetime.combine(day, datetime.min.time()).replace(
            hour=hour, minute=minute
        )

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    # Stored/compared as naive local time; drop any offset instead of
    # crashing on aware-vs-naive comparisons later.
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


class Scheduler:
    """A persistent list of scheduled tasks, stored as JSON."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._tasks: list[dict] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._tasks = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None
        tasks: list[dict] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                if item.get("status") not in _STATUSES:
                    continue
                if not isinstance(item.get("id"), str):
                    continue
                if not isinstance(item.get("task"), str):
                    continue
                if not isinstance(item.get("when"), str):
                    continue
                if parse_when(item["when"]) is None:
                    continue
                tasks.append(
                    {
                        "id": item["id"],
                        "task": item["task"],
                        "when": item["when"],
                        "created_at": item.get("created_at", ""),
                        "status": item["status"],
                        "last_run": item.get("last_run"),
                        "result": item.get("result"),
                    }
                )
        self._tasks = tasks

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._tasks, indent=2, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".schedule-", suffix=".tmp"
        )
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            Path(tmp_name).replace(self.path)
        except OSError:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _next_id(self, now: datetime) -> str:
        stamp = now.strftime("%Y%m%d-%H%M%S")
        for counter in range(1, 1000):
            task_id = f"task-{stamp}-{counter:03d}"
            if not any(task["id"] == task_id for task in self._tasks):
                return task_id
        raise OSError("too many tasks created in one second")

    def add(self, task: str, when_text: str, now: datetime | None = None) -> str:
        """Schedule a task. Returns a confirmation or error text."""
        now = now or datetime.now()
        if not isinstance(task, str) or not task.strip():
            return "Error: a scheduled task needs some text (what should I do?)."
        target = parse_when(when_text, now=now)
        if target is None:
            return (
                "Error: I could not understand when that is. Try e.g. "
                "'tomorrow 14:00', 'in 30 minutes', or '2026-11-26 14:00'."
            )
        try:
            task_id = self._next_id(now)
        except OSError as exc:
            return f"Error scheduling task: {exc}."
        entry = {
            "id": task_id,
            "task": task.strip(),
            "when": target.isoformat(timespec="minutes"),
            "created_at": now.isoformat(timespec="seconds"),
            "status": "pending",
            "last_run": None,
            "result": None,
        }
        self._tasks.append(entry)
        self.save()
        return (
            f"Scheduled: {task_id} — '{task.strip()}' "
            f"at {target.strftime('%A, %d %B %Y, %H:%M')}."
        )

    def pending(self) -> list[dict]:
        """Pending tasks, soonest first."""
        pending = [t for t in self._tasks if t["status"] == "pending"]
        pending.sort(key=lambda t: t["when"])
        return pending

    def due(self, now: datetime | None = None) -> list[dict]:
        """Pending tasks whose time has come, soonest first."""
        now = now or datetime.now()
        due = []
        for task in self.pending():
            when = parse_when(task["when"])
            if when is not None and when <= now:
                due.append(task)
        return due

    def cancel(self, task_id: str) -> str:
        """Cancel a pending task. Returns a confirmation or error text."""
        for task in self._tasks:
            if task["id"] == task_id:
                if task["status"] != "pending":
                    return f"Error: task {task_id} is already {task['status']}."
                task["status"] = "cancelled"
                self.save()
                return f"Cancelled: {task_id} — '{task['task']}'."
        return f"Error: no task with id '{task_id}'."

    def mark_done(self, task_id: str, result: str | None = None, now: datetime | None = None) -> None:
        """Mark a task done, recording when it ran and what came back."""
        for task in self._tasks:
            if task["id"] == task_id:
                task["status"] = "done"
                task["last_run"] = (now or datetime.now()).isoformat(timespec="seconds")
                task["result"] = (result or "")[:500]
                self.save()
                return

    def render_list(self) -> str:
        """Pending tasks as short text, soonest first."""
        pending = self.pending()
        if not pending:
            return "No tasks scheduled."
        lines = [f"{len(pending)} scheduled task(s):"]
        for task in pending:
            when = parse_when(task["when"])
            when_text = (
                when.strftime("%A, %d %B, %H:%M") if when else task["when"]
            )
            lines.append(f"- {task['id']} | {when_text} | {task['task']}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._tasks)
