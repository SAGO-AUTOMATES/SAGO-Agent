"""Hardened tests for Detach Mode and Attach CLI workflows."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from sago.main import cli


class TestDetachModeHardened(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sago_home = Path(self.temp_dir.name) / ".sago"
        self.sago_home.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_run_detach_mode_spawns_process(self):
        with patch("sago.paths.get_sago_home", return_value=self.sago_home):
            with patch("subprocess.Popen") as mock_popen:
                result = self.runner.invoke(
                    cli,
                    ["run", "Build unit tests", "--agent", "python-engineer", "--detach"],
                )
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task started in detached background mode", result.output)
                self.assertIn("Task ID:", result.output)
                self.assertIn("sago attach", result.output)
                self.assertTrue(mock_popen.called)

    def test_attach_without_target_lists_sessions_and_logs(self):
        logs_dir = self.sago_home / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        dummy_log = logs_dir / "task_1700000000.log"
        dummy_log.write_text("Dummy task log output\n")

        with patch("sago.paths.get_sago_home", return_value=self.sago_home):
            result = self.runner.invoke(cli, ["attach"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Available Detached Sessions & Tasks", result.output)
            self.assertIn("task_1700000000", result.output)

    def test_attach_with_task_log_streams_content(self):
        logs_dir = self.sago_home / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        task_id = "task_99999"
        log_file = logs_dir / f"{task_id}.log"
        log_file.write_text(
            "Starting autonomous task...\nTool execution: read_file\nTask completed successfully.\n"
        )

        with patch("sago.paths.get_sago_home", return_value=self.sago_home):
            with patch("time.sleep", side_effect=KeyboardInterrupt):
                result = self.runner.invoke(cli, ["attach", task_id])
                self.assertIn("Streaming detached task log", result.output)
                self.assertIn("Starting autonomous task", result.output)
                self.assertIn("Detached from log", result.output)


if __name__ == "__main__":
    unittest.main()
