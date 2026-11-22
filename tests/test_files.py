import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.config import Config
from muse_top.files import (
    DEFAULT_FILE_MAX_BYTES,
    read_file,
    resolve_workspace_path,
    write_file,
)
from muse_top.memory import Memory
from muse_top.tools import build_default_registry


class TestResolveWorkspacePath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        self.workspace.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_relative_path(self):
        resolved = resolve_workspace_path(self.workspace, "notes/todo.txt")
        self.assertEqual(resolved, (self.workspace / "notes" / "todo.txt").resolve())

    def test_dotdot_escape_refused(self):
        self.assertIsNone(resolve_workspace_path(self.workspace, "../secret.txt"))
        self.assertIsNone(resolve_workspace_path(self.workspace, "a/../../secret.txt"))

    def test_absolute_path_refused(self):
        self.assertIsNone(resolve_workspace_path(self.workspace, "/etc/passwd"))
        self.assertIsNone(resolve_workspace_path(self.workspace, str(self.workspace / "ok.txt")))

    def test_empty_path_refused(self):
        self.assertIsNone(resolve_workspace_path(self.workspace, ""))
        self.assertIsNone(resolve_workspace_path(self.workspace, "   "))

    def test_symlink_escape_refused(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        link = self.workspace / "link.txt"
        link.symlink_to(outside)
        self.assertIsNone(resolve_workspace_path(self.workspace, "link.txt"))

    def test_symlink_inside_workspace_allowed(self):
        target = self.workspace / "real.txt"
        target.write_text("hi", encoding="utf-8")
        link = self.workspace / "alias.txt"
        link.symlink_to(target)
        self.assertEqual(
            resolve_workspace_path(self.workspace, "alias.txt"), target.resolve()
        )


class TestReadWriteFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        self.workspace.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_then_read_roundtrip(self):
        self.assertIn("Wrote", write_file(self.workspace, "notes/hello.txt", "hello world"))
        result = read_file(self.workspace, "notes/hello.txt")
        self.assertIn("File: notes/hello.txt", result)
        self.assertIn("hello world", result)

    def test_write_creates_parent_folders(self):
        write_file(self.workspace, "a/b/c/deep.txt", "deep")
        self.assertEqual((self.workspace / "a" / "b" / "c" / "deep.txt").read_text(), "deep")

    def test_write_overwrites(self):
        write_file(self.workspace, "x.txt", "one")
        write_file(self.workspace, "x.txt", "two")
        self.assertIn("two", read_file(self.workspace, "x.txt"))

    def test_read_missing_file(self):
        self.assertIn("not found", read_file(self.workspace, "nope.txt"))

    def test_read_directory(self):
        (self.workspace / "folder").mkdir()
        self.assertIn("directory", read_file(self.workspace, "folder"))

    def test_write_outside_workspace_refused(self):
        result = write_file(self.workspace, "../evil.txt", "x")
        self.assertIn("outside the workspace", result)
        self.assertFalse((Path(self.tmp.name) / "evil.txt").exists())

    def test_read_outside_workspace_refused(self):
        outside = Path(self.tmp.name) / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        self.assertIn("outside the workspace", read_file(self.workspace, "../secret.txt"))

    def test_read_truncates_large_file(self):
        big = "A" * (DEFAULT_FILE_MAX_BYTES + 100)
        (self.workspace / "big.txt").write_text(big, encoding="utf-8")
        result = read_file(self.workspace, "big.txt")
        self.assertIn("cut off after", result)
        self.assertLess(len(result), len(big))

    def test_read_empty_file(self):
        write_file(self.workspace, "empty.txt", "")
        self.assertIn("(file is empty)", read_file(self.workspace, "empty.txt"))


class TestFileToolsInRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        self.workspace.mkdir()
        config = Config(workspace_dir=self.workspace)
        memory = Memory(Path(self.tmp.name) / "memory.json")
        self.registry = build_default_registry(memory, config)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_tools_registered(self):
        self.assertIn("read_file", self.registry.names())
        self.assertIn("write_file", self.registry.names())

    def test_registry_write_then_read(self):
        self.assertIn(
            "Wrote",
            self.registry.call(
                "write_file", {"path": "note.txt", "content": "via registry"}
            ),
        )
        self.assertIn("via registry", self.registry.call("read_file", {"path": "note.txt"}))

    def test_registry_refuses_escape(self):
        result = self.registry.call("write_file", {"path": "../evil.txt", "content": "x"})
        self.assertIn("outside the workspace", result)
        self.assertFalse((Path(self.tmp.name) / "evil.txt").exists())


if __name__ == "__main__":
    unittest.main()
