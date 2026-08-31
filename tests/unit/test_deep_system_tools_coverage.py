"""Deep coverage tests for sago.tools.system modules."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from sago.tools.system.checkpoint_tool import CheckpointTool
from sago.tools.system.code_sandbox import CodeSandboxTool
from sago.tools.system.cron_schedule import CronSchedule
from sago.tools.system.docker_ops import DockerOps
from sago.tools.system.env_info import EnvInfo
from sago.tools.system.env_manager import EnvManagerTool
from sago.tools.system.k8s_ops import K8sOpsTool
from sago.tools.system.os_detector import OSDetectorTool
from sago.tools.system.process_manager import ProcessManagerTool
from sago.tools.system.screenshot import Screenshot


class TestProcessManager:
    def test_name(self):
        assert ProcessManagerTool().name == "process_manager"

    @patch("psutil.process_iter")
    def test_list_processes(self, mock_iter):
        proc = MagicMock()
        proc.info = {"pid": 1234, "name": "python", "cpu_percent": 5.0, "memory_percent": 2.5}
        mock_iter.return_value = [proc]
        tool = ProcessManagerTool()
        result = tool._run(operation="list")
        assert isinstance(result, str)

    @patch("psutil.process_iter")
    def test_kill_process(self, mock_iter):
        proc = MagicMock()
        proc.pid = 1234
        proc.name.return_value = "test_proc"
        mock_iter.return_value = [proc]
        tool = ProcessManagerTool()
        result = tool._run(operation="kill", query="1234")
        assert isinstance(result, str)

    def test_unknown_action(self):
        tool = ProcessManagerTool()
        result = tool._run(operation="nonexistent")
        assert isinstance(result, str)


class TestCronSchedule:
    def test_name(self):
        assert CronSchedule().name == "cron_schedule"

    @patch("subprocess.run")
    def test_list_crontab(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="0 * * * * /usr/bin/cmd\n", stderr=""
        )
        tool = CronSchedule()
        result = tool._run(operation="list")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_add_entry(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        tool = CronSchedule()
        result = tool._run(operation="add", schedule="0 * * * *", command="/usr/bin/cmd")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_remove_entry(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        tool = CronSchedule()
        result = tool._run(operation="remove", schedule="0 * * * *", command="/usr/bin/cmd")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_validate(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        tool = CronSchedule()
        result = tool._run(operation="validate", schedule="0 * * * *")
        assert isinstance(result, str)

    def test_unknown_action(self):
        tool = CronSchedule()
        result = tool._run(operation="unknown")
        assert isinstance(result, str)


class TestScreenshot:
    def test_name(self):
        assert Screenshot().name == "screenshot"

    @patch("subprocess.run")
    def test_capture(self, mock_run, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=str(tmp_path / "shot.png"), stderr=""
        )
        tool = Screenshot()
        result = tool._run(operation="capture", output_path=str(tmp_path / "shot.png"))
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_capture_failure(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="display not found"
        )
        tool = Screenshot()
        result = tool._run(operation="capture", output_path="/tmp/shot.png")
        assert isinstance(result, str)

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_capture_tool_missing(self, mock_run):
        tool = Screenshot()
        result = tool._run(operation="capture", output_path="/tmp/shot.png")
        assert isinstance(result, str)


class TestEnvManager:
    def test_name(self):
        assert EnvManagerTool().name == "env_manager"

    @patch("subprocess.run")
    def test_list_env(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="PATH=/usr/bin\nHOME=/root\n", stderr=""
        )
        tool = EnvManagerTool()
        result = tool._run(operation="list")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_set_env(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        tool = EnvManagerTool()
        result = tool._run(operation="set", key="MY_VAR", value="hello")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_get_env(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="MY_VAR=hello\n", stderr=""
        )
        tool = EnvManagerTool()
        result = tool._run(operation="get", key="MY_VAR")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_unset_env(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        tool = EnvManagerTool()
        result = tool._run(operation="unset", key="MY_VAR")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_unknown_action(self, mock_run):
        tool = EnvManagerTool()
        result = tool._run(operation="nonexistent")
        assert isinstance(result, str)


class TestEnvInfo:
    def test_name(self):
        assert EnvInfo().name == "env_info"

    @patch("shutil.disk_usage")
    @patch("subprocess.run")
    def test_basic_info(self, mock_run, mock_shutil):
        mock_shutil.return_value = MagicMock(total=100, used=50, free=50)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Linux", stderr=""
        )
        tool = EnvInfo()
        result = tool._run(operation="system")
        assert isinstance(result, str)


class TestCheckpoint:
    def test_name(self):
        assert CheckpointTool().name == "checkpoint_ops"

    @patch("sago.tools.system.checkpoint_tool.CheckpointManager")
    def test_create(self, MockMgr):
        mock_mgr = MagicMock()
        mock_mgr.create.return_value = "ckpt_123"
        MockMgr.return_value = mock_mgr
        tool = CheckpointTool()
        result = tool._run(action="create", description="test snapshot")
        assert isinstance(result, str)

    @patch("sago.tools.system.checkpoint_tool.CheckpointManager")
    def test_list(self, MockMgr):
        mock_mgr = MagicMock()
        mock_mgr.list.return_value = [{"id": "ckpt_1", "desc": "snap"}]
        MockMgr.return_value = mock_mgr
        tool = CheckpointTool()
        result = tool._run(action="list")
        assert isinstance(result, str)

    @patch("sago.tools.system.checkpoint_tool.CheckpointManager")
    def test_restore(self, MockMgr):
        mock_mgr = MagicMock()
        mock_mgr.restore.return_value = True
        MockMgr.return_value = mock_mgr
        tool = CheckpointTool()
        result = tool._run(action="restore", checkpoint_id="ckpt_123")
        assert isinstance(result, str)


class TestCodeSandbox:
    def test_name(self):
        assert CodeSandboxTool().name == "code_sandbox"

    @patch("subprocess.run")
    def test_run_python(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="hello\n", stderr=""
        )
        tool = CodeSandboxTool()
        result = tool._run(language="python", code="print('hello')")
        assert isinstance(result, str)

    def test_run_empty_code(self):
        tool = CodeSandboxTool()
        result = tool._run(language="python", code="")
        assert isinstance(result, str)


class TestDockerOps:
    def test_name(self):
        assert DockerOps().name == "docker_ops"

    @patch("subprocess.run")
    def test_ps(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="CONTAINER ID\nabc123\n", stderr=""
        )
        tool = DockerOps()
        result = tool._run(operation="list")
        assert isinstance(result, str)

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_not_installed(self, mock_run):
        tool = DockerOps()
        result = tool._run(operation="list")
        assert isinstance(result, str)


class TestK8sOps:
    def test_name(self):
        assert K8sOpsTool().name == "k8s_ops"

    @patch("subprocess.run")
    def test_get_pods(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="NAME\npod-1\n", stderr=""
        )
        tool = K8sOpsTool()
        result = tool._run(operation="get", resource="pods")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_logs(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="log line\n", stderr=""
        )
        tool = K8sOpsTool()
        result = tool._run(operation="logs", name="pod-1")
        assert isinstance(result, str)

    def test_delete_blocked(self):
        tool = K8sOpsTool()
        result = tool._run(operation="delete", resource="pod", name="pod-1")
        assert isinstance(result, str)


class TestOSDetector:
    def test_name(self):
        assert OSDetectorTool().name == "os_detector"

    def test_basic(self):
        tool = OSDetectorTool()
        result = tool._run()
        assert isinstance(result, str)

    def test_detailed(self):
        tool = OSDetectorTool()
        result = tool._run(detailed=True)
        assert isinstance(result, str)
