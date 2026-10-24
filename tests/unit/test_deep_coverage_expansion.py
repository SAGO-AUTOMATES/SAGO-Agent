"""Deep coverage expansion tests.

Directly targets previously uncovered modules:
- sago.main (Click CLI commands)
- sago.memory.profiles (User profiles, preferences, project context)
- sago.peers.manager (Distributed peer network manager)
- sago.engine.production & sago.engine.unified (Production engine & unified execution)
- sago.tui.modals (TUI modal screens)
- sago.tui.commands (Deep slash command invocation)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from sago.main import cli


class TestMainCliCommands:
    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_cli_version_and_help(self, runner: CliRunner) -> None:
        res = runner.invoke(cli, ["--version"])
        assert res.exit_code == 0
        assert "0.1." in res.output

        res = runner.invoke(cli, ["--help"])
        assert res.exit_code == 0
        assert "Sago - Sophisticated Multi-Agent Orchestration System" in res.output

    def test_cli_doctor(self, runner: CliRunner) -> None:
        res = runner.invoke(cli, ["doctor"])
        assert res.exit_code == 0
        assert "System Health Check" in res.output

    def test_cli_tools_commands(self, runner: CliRunner) -> None:
        res = runner.invoke(cli, ["tools", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["tools"])
        assert res.exit_code == 0
        assert "Tools Registry" in res.output

        res = runner.invoke(cli, ["tools", "verify_edit"])
        assert res.exit_code == 0
        assert "verify_edit" in res.output

        res = runner.invoke(cli, ["tools", "nonexistent_tool_xyz"])
        assert res.exit_code == 0

    def test_cli_agents_commands(self, runner: CliRunner) -> None:
        res = runner.invoke(cli, ["agents", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["agents"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["agents", "architect"])
        assert res.exit_code == 0

    def test_cli_skills_and_plugins(self, runner: CliRunner) -> None:
        res = runner.invoke(cli, ["skills", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["skills"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["plugins", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["plugins"])
        assert res.exit_code == 0

    def test_cli_telemetry_and_usage(self, runner: CliRunner) -> None:
        res = runner.invoke(cli, ["telemetry", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["usage", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["usage"])
        assert res.exit_code == 0

    def test_cli_checkpoint_and_clean(self, runner: CliRunner) -> None:
        res = runner.invoke(cli, ["checkpoint", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["checkpoint", "list"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["clean", "--help"])
        assert res.exit_code == 0

    def test_cli_status_and_logs(self, runner: CliRunner) -> None:
        res = runner.invoke(cli, ["status", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["status"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["logs", "--help"])
        assert res.exit_code == 0

    def test_cli_sessions_and_history(self, runner: CliRunner) -> None:
        res = runner.invoke(cli, ["sessions", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["sessions"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["history", "--help"])
        assert res.exit_code == 0

    def test_cli_code_intel_cmds(self, runner: CliRunner) -> None:
        res = runner.invoke(cli, ["map", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["project-graph", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["search", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["verify", "--help"])
        assert res.exit_code == 0

        res = runner.invoke(cli, ["parse", "--help"])
        assert res.exit_code == 0


class TestMemoryProfiles:
    def test_user_preferences_lifecycle(self) -> None:
        from sago.memory.profiles import UserPreferences

        prefs = UserPreferences(
            default_effort="high",
            show_thinking=True,
            theme="cyberpunk",
            preferred_agents=["architect", "developer"],
        )
        d = prefs.to_dict()
        assert d["default_effort"] == "high"
        assert d["show_thinking"] is True
        assert d["theme"] == "cyberpunk"
        assert "architect" in d["preferred_agents"]

    def test_user_profile_manager(self, tmp_path: Path) -> None:
        from sago.memory.profiles import UserProfileManager

        mgr = UserProfileManager(persist_dir=tmp_path / "profiles")
        prof = mgr.create_profile("Alice", email="alice@test.com")
        assert prof.name == "Alice"

        fetched = mgr.get_profile(prof.id)
        assert fetched is not None
        assert fetched.email == "alice@test.com"

        mgr.update_profile(prof.id, email="alice_new@test.com")
        updated = mgr.get_profile(prof.id)
        assert updated is not None
        assert updated.email == "alice_new@test.com"

        # Projects
        proj = mgr.create_project(str(tmp_path), name="SagoTest")
        assert proj.name == "SagoTest"
        mgr.add_project_decision(str(tmp_path), "Use PostgreSQL for database")
        mgr.add_known_issue(str(tmp_path), "Rate limit on OpenRouter API")

        ctx = mgr.get_project_context(str(tmp_path))
        assert "Use PostgreSQL" in ctx
        assert "Rate limit" in ctx


class TestPeerManager:
    def test_peer_dataclass_and_status(self) -> None:
        from sago.peers.manager import PeerInfo, PeerStatus

        peer = PeerInfo(
            hostname="192.168.1.100",
            alias="prod-node-1",
            ssh_user="deploy",
            status=PeerStatus.CONNECTING,
            tags=["production", "backend"],
        )
        d = peer.to_dict()
        assert d["hostname"] == "192.168.1.100"
        assert d["alias"] == "prod-node-1"
        assert d["status"] == PeerStatus.CONNECTING.value
        assert "production" in d["tags"]

    def test_peer_manager_operations(self, tmp_path: Path) -> None:
        from sago.peers.manager import PeerManager, PeerStatus

        mgr = PeerManager(config_path=tmp_path / "peers.json")
        p1 = mgr.add_peer("worker1.local", alias="w1")
        mgr.add_peer("worker2.local", alias="w2")

        assert len(mgr.list_peers()) == 2
        assert mgr.get_peer("worker1.local") is not None
        assert mgr.get_peer("w2") is not None

        p1.status = PeerStatus.CONNECTED
        assert mgr.get_peer("w1").status == PeerStatus.CONNECTED

        removed = mgr.remove_peer("worker2.local")
        assert removed is True
        assert len(mgr.list_peers()) == 1


class TestProductionAndUnifiedEngine:
    def test_production_engine_basics(self) -> None:
        from sago.engine.production import EngineConfig, ProductionEngine

        engine = ProductionEngine(config=EngineConfig(max_workers=2, timeout=60.0))
        assert engine is not None
        session = engine.create_session("Coverage Test Session")
        assert session is not None
        assert session.title == "Coverage Test Session"

    def test_unified_engine_basics(self) -> None:
        from sago.engine.unified import UnifiedExecutor

        executor = UnifiedExecutor(model="openrouter/free")
        assert executor is not None
        assert executor.model == "openrouter/free"


class TestTuiModalsAndCommands:
    def test_tui_modals_creation(self) -> None:
        from sago.tui.modals import (
            DiffViewerScreen,
            FileExplorerScreen,
            SessionManagerScreen,
        )

        diff_modal = DiffViewerScreen()
        assert diff_modal is not None

        file_modal = FileExplorerScreen()
        assert file_modal is not None

        session_modal = SessionManagerScreen()
        assert session_modal is not None

    @pytest.mark.anyio
    async def test_deep_tui_slash_commands(self) -> None:
        from sago.tui.app import SagoApp

        app = SagoApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Execute commands
            app._show_status()
            await pilot.pause()

            app._show_version()
            await pilot.pause()

            app._show_cost()
            await pilot.pause()

            app._show_history()
            await pilot.pause()

            app._show_sessions()
            await pilot.pause()

            app._set_effort("high")
            await pilot.pause()
            assert app.current_effort == "high"

            app._show_agents()
            await pilot.pause()

            app._show_tools("verify_edit")
            await pilot.pause()

            app._show_tools("coding")
            await pilot.pause()
