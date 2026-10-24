"""Unit tests for session loading, file import, and module exports."""

import json

import pytest
from click.testing import CliRunner

from sago import load_session as sago_load_session
from sago.database import MessageStore, init_db
from sago.database import Session as DbSession
from sago.database import load_session as db_load_session
from sago.main import cli
from sago.sessions import (
    SessionManager,
    export_session,
    import_session,
)
from sago.sessions import (
    load_session as sessions_load_session,
)
from sago.tools.session import load_session as tools_load_session
from sago.tui.app import SagoApp


class TestSessionLoadingAndImports:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        init_db()
        # Seed a test session
        with DbSession() as s:
            created = s.create(title="Session Loading Verification", metadata={"test_key": "val"})
            self.sid = created["id"]
        ms = MessageStore(self.sid)
        ms.add(role="user", content="Hello Sago", agent_name="user")
        ms.add(role="assistant", content="Hello human!", agent_name="sago")
        ms.flush()
        ms.close()

    def test_import_paths(self):
        """Verify all canonical and backward-compatible import paths work without ImportError."""
        import sago

        assert hasattr(sago, "load_session")

        import sago.session

        assert hasattr(sago.session, "load_session")
        assert hasattr(sago.session, "Session")
        assert hasattr(sago.session, "SessionManager")

        import sago.session.manager

        assert hasattr(sago.session.manager, "SessionManager")

        import sago.sessions

        assert hasattr(sago.sessions, "load_session")
        assert hasattr(sago.sessions, "import_session")
        assert hasattr(sago.sessions, "export_session")

        import sago.database

        assert hasattr(sago.database, "load_session")

        import sago.tools.session

        assert hasattr(sago.tools.session, "load_session")
        assert hasattr(sago.tools.session, "SessionManagerTool")

    def test_load_session_from_db(self):
        """Test loading session by ID prefix across all APIs."""
        # Top-level sago.load_session
        sess = sago_load_session(self.sid[:8])
        assert sess is not None
        assert sess.id == self.sid
        assert len(sess.messages) == 2

        # sessions_load_session
        sess2 = sessions_load_session(self.sid)
        assert sess2 is not None
        assert sess2.id == self.sid

        # db_load_session
        db_res = db_load_session(self.sid[:8])
        assert db_res is not None
        assert db_res["id"] == self.sid
        assert len(db_res["messages"]) == 2

    def test_export_and_import_session(self, tmp_path):
        """Test exporting session to JSON and loading from string / file."""
        exported_str = export_session(self.sid)
        assert exported_str is not None
        assert self.sid in exported_str

        # Import via import_session
        imported = import_session(exported_str)
        assert imported is not None
        assert imported.id == self.sid
        assert len(imported.messages) == 2

        # Load from file path
        export_file = tmp_path / "test_session.json"
        export_session(self.sid, output_path=export_file)
        assert export_file.exists()

        loaded_from_file = sessions_load_session(export_file)
        assert loaded_from_file is not None
        assert loaded_from_file.id == self.sid
        assert len(loaded_from_file.messages) == 2

    def test_session_manager_class_methods(self):
        """Test SessionManager instance methods."""
        sm = SessionManager()
        sess = sm.load_session(self.sid[:8])
        assert sess is not None
        assert sess.id in sm.sessions

    def test_tools_session_helper(self):
        """Test tools session helper function."""
        res = tools_load_session("nonexistent")
        assert isinstance(res, dict)

    def test_cli_session_commands(self):
        """Test sago session, load, and resume CLI commands."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            # sago sessions list
            res_list = runner.invoke(cli, ["session", "list"])
            assert res_list.exit_code == 0

            # sago session export
            res_export = runner.invoke(cli, ["session", "export", self.sid[:8]])
            assert res_export.exit_code == 0
            assert "Session exported" in res_export.output

            # sago session export missing target
            res_exp_err = runner.invoke(cli, ["session", "export"])
            assert "Usage" in res_exp_err.output

            # sago session load missing target
            res_load_err = runner.invoke(cli, ["session", "load"])
            assert "Usage" in res_load_err.output

            # sago load without args lists sessions
            res_load_none = runner.invoke(cli, ["load"])
            assert res_load_none.exit_code == 0

            # sago resume without args lists sessions
            res_res_none = runner.invoke(cli, ["resume"])
            assert res_res_none.exit_code == 0

    def test_load_session_edge_cases(self):
        """Test load_session with dict, raw JSON string, and invalid sources."""
        # Raw JSON string
        raw_json = json.dumps(
            {
                "id": "raw-123",
                "title": "Raw Session",
                "status": "idle",
                "messages": [],
                "threads": [],
            }
        )
        sess_str = sessions_load_session(raw_json)
        assert sess_str is not None
        assert sess_str.id == "raw-123"

        # Dict source
        sess_dict = sessions_load_session(
            {
                "id": "dict-123",
                "title": "Dict Session",
                "status": "idle",
                "messages": [],
                "threads": [],
            }
        )
        assert sess_dict is not None
        assert sess_dict.id == "dict-123"

        # Invalid source types / non-existent
        assert sessions_load_session(12345) is None  # type: ignore[arg-type]
        assert sessions_load_session("nonexistent-prefix-999999") is None
        assert db_load_session("nonexistent-prefix-999999") is None
        assert export_session("nonexistent-prefix-999999") is None

    @pytest.mark.asyncio
    async def test_tui_load_session_with_file_and_commands(self, tmp_path):
        """Test TUI session loading via file and slash commands."""
        # Export sample session file
        exported_str = export_session(self.sid)
        file_path = tmp_path / "imported_session.json"
        file_path.write_text(exported_str, encoding="utf-8")

        app = SagoApp()
        async with app.run_test() as pilot:
            # Load via file path
            app._load_session(str(file_path))
            await pilot.pause()
            assert app.current_session_id == self.sid
            assert len(app.messages) >= 2

            # Load via /session load prefix
            app._switch_session(f"load {self.sid[:8]}")
            await pilot.pause()
            assert app.current_session_id == self.sid

            # Load via /session switch prefix
            app._switch_session(f"switch {self.sid[:8]}")
            await pilot.pause()
            assert app.current_session_id == self.sid
