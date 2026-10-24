from unittest.mock import MagicMock, patch

import pytest

from sago.tui.app import SagoApp


@pytest.mark.asyncio
async def test_tui_commands_exhaustive_part1():
    app = SagoApp()
    async with app.run_test() as pilot:
        # Help and info commands
        app._handle_command("/help")
        app._handle_command("/?")
        app._handle_command("/shortcuts")
        app._handle_command("/keys")
        app._handle_command("/status")
        app._handle_command("/version")
        app._handle_command("/cost")
        app._handle_command("/summary")

        # Themes and dev
        app._handle_command("/theme cyberpunk")
        app._handle_command("/themes nord")
        app._handle_command("/dev on")
        app._handle_command("/dev off")
        app._handle_command("/developer")

        # Unknown
        app._handle_command("/not_a_real_command")
        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_commands_exhaustive_part2():
    app = SagoApp()
    async with app.run_test() as pilot:
        # Agents and orchestration
        app._handle_command("/agents")
        app._handle_command("/agent python-engineer")
        app._handle_command("/agents-color")
        app._handle_command("/handoff")

        # Tools and registry
        app._handle_command("/tools")
        app._handle_command("/tool read_file")
        app._handle_command("/skills")
        app._handle_command("/skill")
        app._handle_command("/plugins")
        app._handle_command("/mcp")
        app._handle_command("/mcp list")

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_commands_exhaustive_part3():
    app = SagoApp()
    async with app.run_test() as pilot:
        # Permissions and YOLO
        app._handle_command("/yolo")
        app._handle_command("/perms")
        app._handle_command("/permissions")
        app._handle_command("/allow read_file")
        app._handle_command("/block write_file")
        app._handle_command("/approve")
        app._handle_command("/deny")

        # Todos and tasks
        app._handle_command("/todo add Write test case")
        app._handle_command("/todo")
        app._handle_command("/todos")
        app._handle_command("/done 1")
        app._handle_command("/tasks")
        app._handle_command("/cancel 999")

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_commands_exhaustive_part4():
    app = SagoApp()
    with (
        patch("sago.engine.verifier.ProjectVerifier") as mock_pv_cls,
        patch("sago.memory.hybrid_indexer.get_hybrid_code_indexer") as mock_indexer_fn,
        patch("sago.tools.vcs.pr_workflow.create_pr_workflow") as mock_pr_fn,
        patch("sago.memory.symbol_graph.SymbolGraph") as mock_sg_cls,
    ):
        mock_pv = MagicMock()
        mock_pv.verify_project.return_value = MagicMock(passed=True, summary="All good")
        mock_pv_cls.return_value = mock_pv

        mock_indexer = MagicMock()
        mock_indexer.search.return_value = []
        mock_indexer_fn.return_value = mock_indexer

        mock_pr_fn.return_value = {"success": True, "message": "PR created"}

        mock_sg = MagicMock()
        mock_sg.root_dir = MagicMock(name="sago")
        mock_sg.generate_clean_tui_map.return_value = "# Repo Map"
        mock_sg_cls.return_value = mock_sg

        async with app.run_test() as pilot:
            # VCS, Diff, and Map
            app._handle_command("/git status")
            app._handle_command("/git")
            app._handle_command("/changes")
            app._handle_command("/undo")
            app._handle_command("/checkpoint list")
            app._handle_command("/checkpoint create Save point")
            app._handle_command("/map")
            app._handle_command("/verify")
            app._handle_command("/search def")
            app._handle_command("/copy")
            app._handle_command("/buttons")
            app._handle_command("/pr")
            app._handle_command("/reload")
            app._handle_command("/collapse all")
            app._handle_command("/collapse none")
            app._handle_command("/clean")

            await pilot.pause()


@pytest.mark.asyncio
async def test_tui_commands_exhaustive_part5():
    app = SagoApp()
    async with app.run_test() as pilot:
        # Model, provider, effort
        app._handle_command("/model gemini/gemini-2.5-flash")
        app._handle_command("/model")
        app._handle_command("/provider gemini")
        app._handle_command("/effort medium")
        app._handle_command("/compact")
        app._handle_command("/retry")
        app._handle_command("/continue")
        app._handle_command("/reset")
        app._handle_command("/history")
        app._handle_command("/export")
        app._handle_command("/save test_session")

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_commands_exhaustive_part6(tmp_path):
    import uuid

    from sago.database import MessageStore, Session, ToolUsageStore, init_db

    init_db()
    sess_id = f"switch_sess_{uuid.uuid4().hex[:8]}"
    with Session(sess_id) as s:
        s.create(title="Switch Test Session", metadata={"workspace_cwd": str(tmp_path)})

    ms = MessageStore(sess_id)
    ms.add("user", "Hello world from user")
    ms.add("assistant", "Hello from assistant <thinking>deep reasoning</thinking>done")
    ms.close()

    tus = ToolUsageStore(sess_id)
    tus.log("read_file", {"path": "a.txt"}, "content", True)
    tus.flush()
    tus.close()

    app = SagoApp()
    async with app.run_test() as pilot:
        # Switch session
        app._handle_command(f"/session switch {sess_id}")
        await pilot.pause()

        # Load session
        app._handle_command(f"/load {sess_id}")
        await pilot.pause()

        # Session list and export
        app._handle_command("/resume")
        app._handle_command(f"/export {tmp_path / 'export.md'}")

        # Plan command with pending orchestration
        app.pending_orchestration = {
            "plan": [
                {"agent": "coder", "task": "Write code"},
                {"agent": "reviewer", "task": "Review code"},
            ]
        }
        app._handle_command("/plan")
        app._handle_command("/plan edit 1 New write code task")
        app._handle_command("/plan add 2 tester: Run tests")
        app._handle_command("/plan remove 2")

        # Project graph
        with (
            patch("sago.memory.project_graph.get_cached_project_graph") as mock_pg_fn,
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_pg = MagicMock()
            mock_pg.nodes = []
            mock_pg.data_models = []
            mock_pg.to_architecture_diagram.return_value = "Box"
            mock_pg.to_er_diagram.return_value = "ER"
            mock_pg.to_ascii_tree.return_value = "Tree"
            mock_pg.to_json.return_value = "{}"
            mock_pg.to_llm_context.return_value = "Context"
            mock_pg_fn.return_value = mock_pg

            mock_thread_cls.side_effect = lambda target, **kw: MagicMock(start=lambda: target())

            app._handle_command("/graph er")
            app._handle_command("/graph tree")
            app._handle_command("/graph json")
            app._handle_command("/graph llm")

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_commands_exhaustive_part7():
    app = SagoApp()
    async with app.run_test() as pilot:
        # Delegation and chaining
        app._process_delegation = MagicMock()
        app._process_orchestration = MagicMock()
        app._handle_command("/delegate @python-engineer write tests")
        app._handle_command("/chain python-engineer -> qa-engineer: write code")
        app._handle_command("/orchestrate Build feature")

        # Parallel and dashboard
        with patch("sago.agents.spawner.AgentSpawner") as mock_spawner_cls:
            mock_sp = MagicMock()
            mock_spawner_cls.return_value = mock_sp
            app._handle_command("/parallel 1. python-engineer: code | 2. qa-engineer: test")

        app._handle_command("/dashboard")
        app._handle_command("/detach")

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_commands_exhaustive_part8(tmp_path):
    app = SagoApp()
    async with app.run_test() as pilot:
        # Tools & Agents queries
        app._show_tools("read")
        app._show_agents("engineer")
        app._set_agent("")
        app._delegate_task("")
        app._chain_agents("")
        app._chain_agents("build something")

        # Git commands
        app._git_commit("")
        app._git_commit("feat: test commit")
        app._git_diff("")
        app._git_diff("test.py")
        app._handle_git_command("branch")
        app._handle_git_command("log -n 1")

        # Approval & Denial
        app.pending_action = {"type": "git_commit", "message": "feat: test"}
        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0, stdout="Committed", stderr="")
            app._approve_action()

        app.pending_action = {
            "type": "user_input",
            "plan_id": "p1",
            "todo_id": "t1",
            "input": "yes",
        }
        with patch("sago.tasks.get_task_manager") as mock_tm_fn:
            mock_tm = MagicMock()
            mock_tm_fn.return_value = mock_tm
            app._approve_action()

        app._deny_action()

        # Plans & Todos
        app._show_plan_inner("show")
        app._show_todo("nonexistent")
        app._ask_user("")
        app._ask_user("Do you confirm?")

        # Skills & Plugins
        app._show_skills("file")
        app._show_plugins()
        app._handle_mcp_command("reload")
        app._handle_mcp_command("test")
        app._handle_mcp_command("test demo-server")

        # Edit plan branches
        app.pending_orchestration = None
        app._plan_command("")
        app.pending_orchestration = {
            "plan": [{"agent": "python-engineer", "task": "original task"}]
        }
        app._plan_command("")
        app._plan_command("edit 1 modified task")
        app._plan_command("edit 99 modified task")
        app._plan_command("edit invalid modified task")
        app._plan_command("add single_task")
        app._plan_command("add reviewer: review code")
        app._plan_command("remove 99")
        app._plan_command("remove invalid")
        app._plan_command("remove 1")
        app._plan_command("unknown_action")

        # Model command branches
        app._change_model("list")
        with patch("sago.tui.models.refresh_models_from_openrouter") as mock_ref:
            mock_ref.return_value = "Refreshed"
            app._change_model("refresh")
        app._change_model("add test-vendor/custom-model")
        app._change_model("remove test-vendor/custom-model")
        app.command_history = ["/help", "/status", "/model"]
        app._show_history()

        # Session switch branches
        app._switch_session("")
        app._switch_session("clean")
        app._switch_session(f"export {tmp_path / 'export2.md'}")
        app._switch_session("save named_sess")

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_commands_exhaustive_part9(tmp_path):
    app = SagoApp()
    async with app.run_test() as pilot:
        # Themes & Checkpoints
        app._set_theme("list")
        app._set_theme("matrix")
        app._handle_checkpoint_command("restore")
        app._handle_checkpoint_command("restore nonexistent")
        app._handle_checkpoint_command("prune 2")

        # Dev commands
        from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

        tracer = get_dev_tracer()
        tracer.set_enabled(True)
        tracer.record(TraceEventType.TOOL_DISPATCH, "tool", "read_file", data={"path": "main.py"})

        otel_file = tmp_path / "otel.json"
        prom_file = tmp_path / "prom.txt"
        app._handle_command(f"/dev export otel {otel_file}")
        app._handle_command(f"/dev export prom {prom_file}")
        app._handle_command("/dev logs")
        app._handle_command("/dev clear")

        # Search & Copy
        app._handle_search_command("")
        app.messages = [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "```python\nprint('code block')\n```\nHere is code.",
            },
        ]
        with patch("sago.tools.session.clipboard.ClipboardTool._write_clipboard"):
            app._handle_copy_command("code")
            app._handle_copy_command("all")
            app._handle_copy_command("")

        # Buttons command
        app._handle_buttons_command("show")
        app._handle_buttons_command("hide")
        app._handle_buttons_command("toggle")

        # Clean command
        app._handle_clean_command("--confirm")

        # PR command
        with patch("sago.tools.vcs.pr_workflow.create_pr_workflow") as mock_pr:
            mock_pr.return_value = {"success": False, "error": "test failure"}
            app._handle_pr_command("")

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_commands_deep_coverage_booster(tmp_path):
    import uuid

    from sago.database import MessageStore, Session, ToolUsageStore, init_db
    from sago.tasks import get_task_manager

    init_db()
    sess_id = f"booster_{uuid.uuid4().hex[:8]}"
    with Session(sess_id) as s:
        s.create(title="Booster Session", metadata={"workspace_cwd": str(tmp_path)})

    ms = MessageStore(sess_id)
    ms.add(
        "user",
        "/delegate @python-engineer write tests",
        metadata={
            "enhancement": {
                "original_prompt": "write tests",
                "enhanced_prompt": "write pytest tests",
                "intent_summary": "unit testing",
            }
        },
    )
    ms.add(
        "assistant",
        "Here are tests <thinking>logic</thinking>done",
        metadata={"thinking_blocks": [{"seq": 1, "text": "deep logic"}]},
    )
    ms.add("user", "/orchestrate build feature")
    ms.add("user", "/chain python-engineer -> qa-engineer: ship")
    ms.add("user", "/parallel a: task1 | b: task2")
    ms.add("user", "/plan full plan")
    ms.close()

    tus = ToolUsageStore(sess_id)
    tus.log("read_file", {"path": "main.py"}, "code content", True)
    tus.flush()
    tus.close()

    app = SagoApp()
    async with app.run_test() as pilot:
        # Load session with rich metadata and slash command types
        app._load_session(sess_id)
        await pilot.pause()

        # Compaction
        app.messages = [
            {"role": "user", "content": "Hello 1"},
            {"role": "assistant", "content": "Reply 1"},
            {"role": "user", "content": "Hello 2"},
            {"role": "assistant", "content": "Reply 2"},
        ]
        app._compact()
        await pilot.pause()

        # Continue session
        app.messages = [{"role": "user", "content": "Interrupted task"}]
        with patch.object(app, "_process_message"):
            app._continue_last()

        # Active plan with completed and pending todos
        tm = get_task_manager()
        plan = tm.create_plan("Comprehensive Test Plan")
        t1 = tm.add_todo(plan.id, "Step 1: Write code", "python-engineer")
        _ = tm.add_todo(plan.id, "Step 2: Run tests", "qa-engineer")
        tm.complete_todo(plan.id, t1.id, result="Done")
        app._show_plan_inner("")
        await pilot.pause()

        # Parallel command
        app._process_parallel = MagicMock()
        app._run_parallel("python-engineer: code, qa-engineer: test")

        # Collapse chat turns
        from textual.widgets import Collapsible, Static

        app.query_one("#messages").mount(Collapsible(Static("Content"), title="Card"))
        app._collapse_chats("open")
        app._collapse_chats("all")

        # Dashboard and tasks
        from sago.tui.widgets import get_task_manager as get_bg_tm

        bg_tm = get_bg_tm()
        bg_task = bg_tm.create_task("python-engineer", "Build app")
        app._toggle_dashboard()
        app._toggle_dashboard()
        app._show_tasks()
        app._cancel_task(bg_task.agent_id)

        # Exit session with developer mode enabled and real messages
        app.developer_mode = True
        app.current_session_id = sess_id
        app.messages = [{"role": "user", "content": "User question"}]
        with patch.object(app, "exit"):
            app._exit_session()

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_commands_exhaustive_part10(tmp_path, monkeypatch):
    """Deeply test model/provider changes, effort, plugins, search, retry, sessions, plan prompt, and shortcuts fallback."""
    import uuid
    from unittest.mock import MagicMock, patch

    from sago.database import MessageStore, Session, ToolUsageStore, init_db
    from sago.memory.hybrid_indexer import HybridCodeChunk, HybridSearchResult
    from sago.plugins import PluginMetadata, get_plugin_manager
    from sago.tui.app import SagoApp

    init_db()
    sess_id = str(uuid.uuid4())
    s = Session(sess_id)
    s.create(title="Export & Deep Test Session")
    s.close()

    ms = MessageStore(sess_id)
    ms.add("user", "Hello world")
    ms.add("assistant", "How can I help?")
    ms.close()

    tus = ToolUsageStore(sess_id)
    tus.log(
        "spawn_agent", {"agent_name": "qa-engineer", "task": "run tests"}, "All tests passed", True
    )
    tus.log("run_command", {"command": "pytest invalid"}, "Error: command failed", False)
    tus.flush()
    tus.close()

    app = SagoApp()
    async with app.run_test() as pilot:
        app.current_session_id = sess_id

        # 1. Model switching paths
        app._change_model("gemini-2.5-flash")
        app._change_model("google/gemini-2.5-pro")
        app._change_model("openai/gpt-4o")
        app._change_model("openrouter/deepseek/deepseek-r1:free")
        app._change_model("claude-3-7-sonnet")  # substring / prefix match
        app._change_model("custom-finetuned-local-model")  # custom model path

        # 2. Provider switching paths
        app._change_provider("")  # provider list overview
        app._change_provider("nonexistent_provider_xyz")  # unknown
        app._change_provider("google")
        app._change_provider("openai")
        app._change_provider("deepseek")

        # 3. Effort levels
        app._set_effort("")  # show collapsible list
        app._set_effort("invalid_level")
        app._set_effort("high")
        app._set_effort("max")

        # 4. Version and shortcuts fallback
        app._show_version()
        with patch.object(app, "push_screen", side_effect=RuntimeError("Screen push failed")):
            app._handle_shortcuts_command()

        # 5. Plugins listing
        pm = get_plugin_manager()
        fake_plugin = PluginMetadata(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
            author="Tester",
            enabled=True,
        )
        with patch.object(pm, "list_plugins", return_value=[fake_plugin]):
            app._show_plugins()

        # 6. Hybrid search
        app._handle_search_command("")  # empty
        fake_chunk = HybridCodeChunk(
            file_path="src/main.py",
            start_line=1,
            end_line=20,
            content="def run():\n    pass",
            language="python",
            chunk_type="function",
            name="run",
        )
        fake_result = HybridSearchResult(
            chunk=fake_chunk,
            bm25_score=0.9,
            semantic_score=0.85,
            combined_score=0.88,
        )
        with patch("sago.memory.hybrid_indexer.get_hybrid_code_indexer") as mock_indexer_fn:
            mock_indexer = MagicMock()
            mock_indexer.search.return_value = [fake_result]
            mock_indexer_fn.return_value = mock_indexer
            app._handle_search_command("def run")

        # 7. Plan command with user task (interactive prompt generation)
        with patch.object(app, "_process_message"):
            app._show_plan("refactor database connection pool")

        # 8. Retry last user message
        app.messages = []
        app._retry_last()
        app.messages = [{"role": "system", "content": "only system"}]
        app._retry_last()
        app.messages = [
            {"role": "user", "content": "original question"},
            {"role": "assistant", "content": "broken response"},
        ]
        with patch.object(app, "_process_message") as mock_proc:
            app._retry_last()
            assert mock_proc.called

        # 9. Session management commands: export and list
        app._list_sessions()
        export_file = str(tmp_path / "test_session_export.md")
        app._export_session(export_file)
        assert (tmp_path / "test_session_export.md").exists()

        # 10. Direct action exit with human messages
        app.developer_mode = True
        app.session_tool_calls = [{"tool": "read_file"}, {"tool": "search"}]
        app.total_input_tokens = 100
        app.total_output_tokens = 50
        with (
            patch("sago.database.Session.has_human_messages", return_value=True),
            patch.object(app, "exit"),
        ):
            app._exit_session()

        # 11. Detach session
        with patch.object(app, "exit"):
            app._detach_session()

        await pilot.pause()
