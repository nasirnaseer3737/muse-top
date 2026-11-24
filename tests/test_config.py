import os
import unittest
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_top.config import Config


class TestConfigFromEnv(unittest.TestCase):
    def test_defaults_point_at_home_not_cwd(self):
        # Regression: Path("") is truthy, so `Path(env or default)` must
        # apply the `or` to the string — otherwise an unset variable
        # silently pointed every path at the current working directory.
        env = {"HOME": "/tmp/fake-home"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            home = Path.home()
        self.assertEqual(config.data_dir, home / ".muse-top")
        self.assertEqual(config.workspace_dir, home / ".muse-top" / "workspace")
        self.assertEqual(config.drafts_dir, home / ".muse-top" / "drafts")
        self.assertEqual(config.memory_path, home / ".muse-top" / "memory.json")
        self.assertEqual(config.history_path, home / ".muse-top" / "history.json")

    def test_env_overrides_respected(self):
        env = {
            "MUSE_TOP_DATA_DIR": "/tmp/mt-data",
            "MUSE_TOP_WORKSPACE": "/tmp/mt-ws",
            "MUSE_TOP_DRAFTS_DIR": "/tmp/mt-drafts",
            "MUSE_TOP_MAX_HISTORY": "3",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        self.assertEqual(config.data_dir, Path("/tmp/mt-data"))
        self.assertEqual(config.workspace_dir, Path("/tmp/mt-ws"))
        self.assertEqual(config.drafts_dir, Path("/tmp/mt-drafts"))
        self.assertEqual(config.max_history_turns, 3)

    def test_empty_string_env_falls_back_to_default(self):
        env = {"HOME": "/tmp/fake-home", "MUSE_TOP_DATA_DIR": "", "MUSE_TOP_DRAFTS_DIR": ""}
        with mock.patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            home = Path.home()
        self.assertEqual(config.data_dir, home / ".muse-top")
        self.assertEqual(config.drafts_dir, home / ".muse-top" / "drafts")


if __name__ == "__main__":
    unittest.main()
