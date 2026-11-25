import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.agent import Agent
from muse_top.config import Config
from muse_top.memory import Memory
from muse_top.schedule import Scheduler, parse_when
from muse_top.tools import build_default_registry


NOW = datetime(2026, 11, 25, 13, 47)


class TestParseWhen(unittest.TestCase):
    def test_iso_datetime(self):
        self.assertEqual(parse_when("2026-11-26 14:00", now=NOW), datetime(2026, 11, 26, 14, 0))

    def test_iso_t_separator_and_date_only(self):
        self.assertEqual(parse_when("2026-11-26T09:30", now=NOW), datetime(2026, 11, 26, 9, 30))
        self.assertEqual(parse_when("2026-11-26", now=NOW), datetime(2026, 11, 26, 0, 0))

    def test_relative_minutes_hours_days(self):
        self.assertEqual(parse_when("in 30 minutes", now=NOW), NOW + timedelta(minutes=30))
        self.assertEqual(parse_when("in 2 hours", now=NOW), NOW + timedelta(hours=2))
        self.assertEqual(parse_when("in 1 day", now=NOW), NOW + timedelta(days=1))

    def test_today_and_tomorrow(self):
        self.assertEqual(parse_when("tomorrow 14:00", now=NOW), datetime(2026, 11, 26, 14, 0))
        self.assertEqual(parse_when("today 09:00", now=NOW), datetime(2026, 11, 25, 9, 0))

    def test_unparseable_returns_none(self):
        self.assertIsNone(parse_when("soon", now=NOW))
        self.assertIsNone(parse_when("tomorrow 25:00", now=NOW))
        self.assertIsNone(parse_when("", now=NOW))
        self.assertIsNone(parse_when(None, now=NOW))


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "schedule.json"
        self.scheduler = Scheduler(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_and_list(self):
        result = self.scheduler.add("remind me to call Ali", "tomorrow 14:00", now=NOW)
        self.assertIn("Scheduled:", result)
        self.assertIn("26 November 2026", result)
        self.assertTrue(self.path.exists())
        self.assertIn("call Ali", self.scheduler.render_list())
        self.assertEqual(len(self.scheduler.pending()), 1)

    def test_add_rejects_empty_task_and_bad_when(self):
        self.assertIn("Error", self.scheduler.add("   ", "tomorrow 14:00", now=NOW))
        self.assertIn("Error", self.scheduler.add("do it", "whenever", now=NOW))
        self.assertEqual(len(self.scheduler), 0)

    def test_due_only_when_time_has_come(self):
        self.scheduler.add("past task", "2026-11-25 13:00", now=NOW)
        self.scheduler.add("future task", "2026-11-26 14:00", now=NOW)
        due = self.scheduler.due(now=NOW)
        self.assertEqual([t["task"] for t in due], ["past task"])

    def test_cancel(self):
        self.scheduler.add("do it", "tomorrow 14:00", now=NOW)
        task_id = self.scheduler.pending()[0]["id"]
        self.assertIn("Cancelled:", self.scheduler.cancel(task_id))
        self.assertEqual(self.scheduler.pending(), [])
        self.assertIn("Error", self.scheduler.cancel(task_id))  # already cancelled
        self.assertIn("Error", self.scheduler.cancel("task-nope"))

    def test_mark_done_removes_from_due(self):
        self.scheduler.add("do it", "2026-11-25 13:00", now=NOW)
        task_id = self.scheduler.pending()[0]["id"]
        self.scheduler.mark_done(task_id, "ran fine", now=NOW)
        self.assertEqual(self.scheduler.due(now=NOW), [])
        self.assertEqual(self.scheduler.pending(), [])
        self.assertEqual(self.scheduler._tasks[0]["status"], "done")
        self.assertEqual(self.scheduler._tasks[0]["result"], "ran fine")

    def test_persists_across_instances(self):
        self.scheduler.add("do it", "tomorrow 14:00", now=NOW)
        reloaded = Scheduler(self.path)
        self.assertEqual(len(reloaded.pending()), 1)
        self.assertEqual(reloaded.pending()[0]["task"], "do it")

    def test_corrupt_file_starts_empty(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(Scheduler(self.path).pending(), [])

    def test_list_sorted_soonest_first(self):
        self.scheduler.add("later", "2026-11-27 09:00", now=NOW)
        self.scheduler.add("sooner", "2026-11-26 09:00", now=NOW)
        tasks = self.scheduler.pending()
        self.assertEqual([t["task"] for t in tasks], ["sooner", "later"])

    def test_empty_list_message(self):
        self.assertEqual(self.scheduler.render_list(), "No tasks scheduled.")


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def generate(self, prompt):
        if self.replies:
            return self.replies.pop(0)
        return "done."


class TestRunDueTasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(
            api_key="",
            data_dir=Path(self.tmp.name) / "data",
            schedule_path=Path(self.tmp.name) / "data" / "schedule.json",
        )
        self.memory = Memory(self.config.memory_path)
        self.registry = build_default_registry(self.memory, self.config)
        self.agent = Agent(
            config=self.config,
            llm=FakeLLM(["Task done — called Ali."]),
            memory=self.memory,
            registry=self.registry,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_nothing_due(self):
        self.assertEqual(self.agent.run_due_tasks(now=NOW), "No tasks due.")

    def test_due_task_runs_once_and_is_marked_done(self):
        scheduler = Scheduler(self.config.schedule_path)
        scheduler.add("call Ali", "2026-11-25 13:00", now=NOW)
        summary = self.agent.run_due_tasks(now=NOW)
        self.assertIn("Running 1 due task", summary)
        self.assertIn("call Ali", summary)
        self.assertIn("called Ali", summary)
        self.assertEqual(self.agent.run_due_tasks(now=NOW), "No tasks due.")
        self.assertEqual(Scheduler(self.config.schedule_path).pending(), [])

    def test_future_task_not_run(self):
        Scheduler(self.config.schedule_path).add("call Ali", "tomorrow 14:00", now=NOW)
        self.assertEqual(self.agent.run_due_tasks(now=NOW), "No tasks due.")


class TestScheduleTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(
            api_key="",
            data_dir=Path(self.tmp.name) / "data",
            schedule_path=Path(self.tmp.name) / "data" / "schedule.json",
        )
        self.memory = Memory(self.config.memory_path)
        self.registry = build_default_registry(self.memory, self.config)

    def tearDown(self):
        self.tmp.cleanup()

    def test_schedule_list_cancel_tools(self):
        self.assertIn("Scheduled:", self.registry.call("schedule", {"task": "call Ali", "when": "tomorrow 14:00"}))
        listed = self.registry.call("list_tasks")
        self.assertIn("call Ali", listed)
        task_id = Scheduler(self.config.schedule_path).pending()[0]["id"]
        self.assertIn("Cancelled:", self.registry.call("cancel_task", {"id": task_id}))
        self.assertIn("No tasks scheduled", self.registry.call("list_tasks"))

    def test_schedule_tool_bad_when(self):
        self.assertIn("Error", self.registry.call("schedule", {"task": "x", "when": "soon"}))


if __name__ == "__main__":
    unittest.main()
