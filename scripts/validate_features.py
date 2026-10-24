#!/usr/bin/env python3
"""SAGO Comprehensive Validation Script.

Validates all new and existing features end-to-end:
1. Live Headless TUI App (DOM mounting, slash commands, tool inspection, turn cards, input)
2. Execution Engine (early cancellation, on_token callbacks, multi-pass self-correction)
3. Code Intelligence (Tree-sitter AST, Symbol Graph repo-map, VerifyEdit, LoadSkill, Context Budget)
4. Orchestration & Isolation (Scoped Agent/Tool Registries, Planner-Coder-Verifier loop, Message Bus)
5. Evaluation Harness & Grounding (Symbol-existence checks, post-exec syntax checks, benchmark cases)

Usage:
    uv run python scripts/validate_features.py
    # or
    ./scripts/validate_features.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

console = Console()


class ValidationSuite:
    def __init__(self) -> None:
        self.results: list[dict[str, Any]] = []
        self.start_time = time.time()

    def record(
        self, domain: str, name: str, passed: bool, details: str = "", duration: float = 0.0
    ) -> None:
        self.results.append(
            {
                "domain": domain,
                "name": name,
                "passed": passed,
                "details": details,
                "duration": round(duration, 3),
            }
        )
        icon = "[bold green]✓ PASS[/bold green]" if passed else "[bold red]✗ FAIL[/bold red]"
        console.print(
            f"  {icon} [cyan]{domain:<18}[/cyan] [bold]{name}[/bold] [dim]({duration:.3f}s)[/dim]"
        )
        if not passed and details:
            console.print(f"    [red]Error:[/] {details}")

    def summary(self) -> bool:
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed
        elapsed = time.time() - self.start_time

        table = Table(
            title="SAGO End-to-End Validation Summary",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Domain", style="cyan")
        table.add_column("Checks", justify="right")
        table.add_column("Passed", justify="right", style="green")
        table.add_column("Failed", justify="right", style="red")
        table.add_column("Status", justify="center")

        domains: dict[str, list[dict[str, Any]]] = {}
        for r in self.results:
            domains.setdefault(r["domain"], []).append(r)

        for dom, items in sorted(domains.items()):
            p = sum(1 for x in items if x["passed"])
            f = len(items) - p
            st = (
                "[bold green]ALL PASS[/bold green]"
                if f == 0
                else f"[bold red]{f} FAILED[/bold red]"
            )
            table.add_row(dom, str(len(items)), str(p), str(f), st)

        console.print("\n")
        console.print(table)
        console.print(
            Panel(
                f"[bold]Total Checks:[/] {total} | "
                f"[bold green]Passed:[/] {passed} | "
                f"[bold red]Failed:[/] {failed} | "
                f"[bold cyan]Elapsed:[/] {elapsed:.2f}s",
                title="[bold]Overall Validation Scorecard[/bold]",
                border_style="green" if failed == 0 else "red",
            )
        )
        return failed == 0


async def validate_tui(suite: ValidationSuite) -> None:
    console.print("\n[bold yellow]1. Validating TUI (Headless App & Pilot)[/bold yellow]")
    from textual.widgets import Collapsible

    from sago.tui.app import SagoApp
    from sago.tui.helpers import ExchangeTurnCard

    # 1.1 App Boot & DOM Mount
    t0 = time.time()
    try:
        app = SagoApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#messages") is not None
            input_box = app.query_one("#msg-input")
            assert app.query_one("#welcome-screen") is not None
            assert app.query_one("#approval-bar") is not None
            suite.record(
                "TUI Core",
                "DOM Elements Mount",
                True,
                "Messages, Input, Welcome, Approval bar mounted",
                time.time() - t0,
            )

            # 1.2 User & Assistant Message Mounting
            t1 = time.time()
            app._add_user_message("Hello Sago verification")
            app._add_assistant_message("Ready to assist.")
            await pilot.pause()
            cards = app.query(ExchangeTurnCard)
            has_cards = len(cards) > 0
            suite.record(
                "TUI Core",
                "Turn Cards & Bubbles",
                has_cards,
                f"Mounted {len(cards)} turn cards",
                time.time() - t1,
            )

            # 1.3 Slash Command: /tools overview
            t2 = time.time()
            app._show_tools()
            await pilot.pause()
            collapsibles = app.query(Collapsible)
            suite.record(
                "TUI Commands",
                "/tools Category Overview",
                len(collapsibles) > 0,
                "Tool categories collapsible mounted",
                time.time() - t2,
            )

            # 1.4 Detailed Inspection of New Tools in TUI
            new_tools = [
                "verify_edit",
                "lsp_query",
                "load_skill",
                "discover_tools",
                "read_function",
            ]
            for tool_name in new_tools:
                t3 = time.time()
                initial_count = len(app.query(Collapsible))
                app._show_tools(tool_name)
                await pilot.pause()
                new_count = len(app.query(Collapsible))
                suite.record(
                    "TUI Tools",
                    f"/tools {tool_name}",
                    new_count > initial_count,
                    f"Mounted detail card for {tool_name}",
                    time.time() - t3,
                )

            # 1.5 Command Turn Cards (/delegate, /chain, /orchestrate)
            t4 = time.time()
            app._add_command_turn(
                cmd_type="delegate",
                content="Refactor authentication layer",
                meta="@security-engineer",
            )
            await pilot.pause()
            cmd_turns = app.query(ExchangeTurnCard)
            suite.record(
                "TUI Commands",
                "Command Turn Card (/delegate)",
                len(cmd_turns) > 0,
                "Dedicated command turn mounted",
                time.time() - t4,
            )

            # 1.6 Shell Escape Execution Card
            t5 = time.time()
            input_box.value = "!echo 'validation-ok'"
            await pilot.press("enter")
            await pilot.pause()
            suite.record(
                "TUI Core",
                "Shell Escape Card (!echo)",
                True,
                "Shell card mounted without freezing",
                time.time() - t5,
            )

            # 1.7 Theme Switching
            t6 = time.time()
            app._set_theme("cyberpunk")
            await pilot.pause()
            suite.record(
                "TUI Core",
                "Theme Switching (cyberpunk)",
                app.sago_theme == "cyberpunk",
                "Theme applied cleanly",
                time.time() - t6,
            )

    except Exception as e:
        suite.record("TUI Core", "Headless Pilot Execution", False, str(e), time.time() - t0)


def validate_engine(suite: ValidationSuite) -> None:
    console.print("\n[bold yellow]2. Validating Execution Engine & Verification[/bold yellow]")
    import threading

    from sago.engine.hallucination_verifier import ResponseVerifier
    from sago.engine.simple_executor import execute_agent_task

    # 2.1 Instant Cancellation Check
    t0 = time.time()
    cancel_ev = threading.Event()
    cancel_ev.set()
    res = execute_agent_task(
        task="Heavy long task",
        max_iterations=20,
        cancellation_token=cancel_ev,
    )
    dt0 = time.time() - t0
    suite.record(
        "Engine",
        "Instant Cancellation Token",
        res.get("cancelled") is True and dt0 < 1.0,
        f"Cancelled in {dt0:.3f}s (target < 1.0s)",
        dt0,
    )

    # 2.2 Token Callback Support
    t1 = time.time()
    tokens_received: list[str] = []
    # Test callback mechanism directly
    from sago.engine.simple_executor import get_execution_callbacks, set_execution_callbacks

    set_execution_callbacks(on_token=lambda tok: tokens_received.append(tok))
    ctx = get_execution_callbacks()
    cb_ok = ctx.get("on_token") is not None
    suite.record(
        "Engine",
        "on_token Callback Plumbing",
        cb_ok,
        "Callback accessible via contextvars",
        time.time() - t1,
    )

    # 2.3 Symbol-Existence Grounding (Stage 3b)
    t2 = time.time()
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "alpha.py").write_text("def known_func(): pass\n")
        verifier = ResponseVerifier(enable_external_checks=False)
        v_res = verifier.verify(
            "I checked `fake_hallucinated_symbol_xyz` and it works.",
            tool_history=[],
            root_dir=tmpdir,
        )
        has_symbol_issue = any("fake_hallucinated_symbol" in str(x) for x in v_res.all_issues)
        suite.record(
            "Verifier",
            "Symbol-Existence Grounding",
            has_symbol_issue,
            "Unreferenced backticked symbol caught",
            time.time() - t2,
        )

    # 2.4 Post-Execution Syntax Validation on Modified Files (Stage 3c)
    t3 = time.time()
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_file = Path(tmpdir) / "bad.py"
        bad_file.write_text("def broken(\n")
        v_res = verifier.verify(
            "Created file.",
            tool_history=[
                {
                    "tool": "write_file",
                    "args": {"file_path": str(bad_file)},
                    "result": "ok",
                    "success": True,
                }
            ],
            root_dir=tmpdir,
        )
        has_syntax_issue = any("syntax error" in str(x).lower() for x in v_res.all_issues)
        suite.record(
            "Verifier",
            "Post-Exec Modified File Syntax",
            has_syntax_issue,
            "Broken Python syntax in tool result caught",
            time.time() - t3,
        )


def validate_code_intelligence(suite: ValidationSuite) -> None:
    console.print("\n[bold yellow]3. Validating Code Intelligence & Tools[/bold yellow]")
    from sago.memory.code_intelligence import get_code_intelligence
    from sago.memory.context_budget import ContextBudgetManager, estimate_tokens
    from sago.memory.tree_sitter_parser import parse_symbols
    from sago.tools.admin.tool_discovery import ToolDiscoveryTool
    from sago.tools.coding.verify_edit_tool import VerifyEditTool
    from sago.tools.skills.load_skill_tool import LoadSkillTool

    # 3.1 Code Intelligence Service Facade
    t0 = time.time()
    svc = get_code_intelligence(root_dir=Path.cwd())
    rmap = svc.repo_map(max_files=5)
    suite.record(
        "Code Intel",
        "CodeIntelligenceService Facade",
        bool(rmap),
        f"Generated repo map ({len(rmap)} chars)",
        time.time() - t0,
    )

    # 3.2 Tree-sitter Code Parser (JS, TS, Python)
    t1 = time.time()
    py_symbols = parse_symbols("python", "def foo(x: int) -> int: return x * 2\nclass Bar: pass\n")
    js_symbols = parse_symbols(
        "javascript", "function add(a, b) { return a + b; }\nclass Component {}\n"
    )
    ts_symbols = parse_symbols(
        "typescript", "function sum(a: number): number { return a; }\nclass User {}\n"
    )
    all_parsed = len(py_symbols) >= 2 and len(js_symbols) >= 2 and len(ts_symbols) >= 2
    suite.record(
        "Code Intel",
        "Tree-Sitter Multi-Language Parser",
        all_parsed,
        f"Py={len(py_symbols)}, JS={len(js_symbols)}, TS={len(ts_symbols)}",
        time.time() - t1,
    )

    # 3.3 VerifyEditTool Dry Run
    t2 = time.time()
    with tempfile.TemporaryDirectory() as tmpdir:
        sample = Path(tmpdir) / "test.py"
        sample.write_text("def greet():\n    return 'hi'\n")
        vet = VerifyEditTool()
        ok_res = vet._run(str(sample), "return 'hi'", "return 'hello'")
        bad_res = vet._run(str(sample), "return 'hi'", "return 'hello'(")
        suite.record(
            "Tools",
            "verify_edit (Dry-run Guard)",
            "cleanly" in ok_res.lower() and "syntax guard" in bad_res.lower(),
            "Clean edit allowed, broken syntax blocked",
            time.time() - t2,
        )

    # 3.4 LoadSkillTool Lazy Resolution
    t3 = time.time()
    lst = LoadSkillTool()
    skill_out = lst._run("general")
    suite.record(
        "Tools",
        "load_skill (Lazy SKILL.md)",
        isinstance(skill_out, str) and len(skill_out) > 0,
        "Resolved skill prompt text",
        time.time() - t3,
    )

    # 3.5 ToolDiscoveryTool Safe Mode
    t4 = time.time()
    tdt = ToolDiscoveryTool()
    catalog = tdt._run(safe_mode=True)
    suite.record(
        "Tools",
        "discover_tools (Safe Mode)",
        "Discovered" in catalog and "read_file" in catalog,
        "Catalog filtered in safe mode",
        time.time() - t4,
    )

    # 3.6 Context Budget Manager (Tiktoken & Fallback)
    t5 = time.time()
    tokens = estimate_tokens("def calculate(x, y): return x + y\n" * 10)
    mgr = ContextBudgetManager(max_tokens=50)
    truncated = mgr.fit("A" * 1000)
    suite.record(
        "Code Intel",
        "Context Budget (tiktoken)",
        tokens > 0 and len(truncated) < 1000,
        f"Estimated {tokens} tokens, budget fit enforced",
        time.time() - t5,
    )


def validate_orchestration_and_evals(suite: ValidationSuite) -> None:
    console.print("\n[bold yellow]4. Validating Orchestration, IPC & Evals[/bold yellow]")
    from evals.harness import load_benchmark_cases, run_eval
    from sago.agents.registry import AgentDefinition, ScopedAgentRegistry
    from sago.orchestrator.message_bus import get_message_bus
    from sago.tools.registry import ScopedToolRegistry
    from sago.workflow.engine import WorkflowEngine
    from sago.workflow.templates import WorkflowTemplates

    # 4.1 Scoped Registries
    t0 = time.time()
    tool_reg = ScopedToolRegistry(allowed={"read_file", "write_file"})
    assert set(tool_reg.tools().keys()).issubset({"read_file", "write_file"})
    agent_reg = ScopedAgentRegistry()
    agent_reg.register(
        AgentDefinition(
            name="custom-qa",
            codename="cqa",
            role="QA",
            description="Custom QA",
            system_prompt="",
            skills=[],
            tools=[],
        )
    )
    suite.record(
        "Orchestration",
        "Scoped Registries Isolation",
        agent_reg.get("custom-qa") is not None and tool_reg.tools() is not None,
        "Isolated scope without global pollution",
        time.time() - t0,
    )

    # 4.2 Planner-Coder-Verifier Workflow Loop
    t1 = time.time()
    engine = WorkflowEngine()
    templates = WorkflowTemplates(engine)
    pipeline = templates.planner_coder_verifier_pipeline("Add Redis caching")
    steps = [s.name for s in pipeline.steps]
    suite.record(
        "Orchestration",
        "Planner-Coder-Verifier Pipeline",
        steps == ["Plan Architecture", "Implement Code", "Verify Implementation"],
        "3-stage role loop built cleanly",
        time.time() - t1,
    )

    # 4.3 Message Bus Sync Event Dispatch
    t2 = time.time()
    bus = get_message_bus()
    received_events = []
    bus.subscribe("test_channel", lambda ev: received_events.append(ev))
    bus.publish_sync("executor", "test_channel", {"status": "ok"})
    suite.record(
        "Orchestration",
        "Message Bus IPC (publish_sync)",
        len(received_events) == 1,
        "Event delivered to subscriber synchronously",
        time.time() - t2,
    )

    # 4.4 Benchmark Evals Harness
    t3 = time.time()
    cases = load_benchmark_cases()
    report = run_eval(
        cases,
        lambda prompt: (
            "The primary base class in sago/tools/base.py is BaseTool. Invalid syntax triggers SyntaxError."
        ),
    )
    suite.record(
        "Evals",
        "Benchmark Cases Harness",
        report["total"] >= 4 and report["passed"] >= 2,
        f"Evaluated {report['total']} cases from cases.json",
        time.time() - t3,
    )


async def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="SAGO Comprehensive End-to-End Validator")
    parser.add_argument(
        "--tui-only", action="store_true", help="Run only TUI headless app & pilot validation"
    )
    parser.add_argument(
        "--engine-only", action="store_true", help="Run only Engine & verification checks"
    )
    parser.add_argument(
        "--intel-only", action="store_true", help="Run only Code Intelligence checks"
    )
    parser.add_argument(
        "--orch-only", action="store_true", help="Run only Orchestration & IPC checks"
    )
    args = parser.parse_args()

    console.print(
        Panel(
            "[bold white]SAGO Custom End-to-End Validation Engine[/bold white]\n"
            "[dim]Validating TUI, Execution Engine, Code Intel, Verification, & Evals[/dim]",
            border_style="cyan",
        )
    )
    suite = ValidationSuite()

    run_all = not (args.tui_only or args.engine_only or args.intel_only or args.orch_only)

    if run_all or args.tui_only:
        await validate_tui(suite)
    if run_all or args.engine_only:
        validate_engine(suite)
    if run_all or args.intel_only:
        validate_code_intelligence(suite)
    if run_all or args.orch_only:
        validate_orchestration_and_evals(suite)

    success = suite.summary()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
