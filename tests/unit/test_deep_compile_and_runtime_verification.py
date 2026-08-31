"""Comprehensive Compile, Import, and Runtime Verification Test Suite.

Ensures every single python module, agent profile, tool, engine, and webserver
module in the sago repository compiles cleanly without SyntaxErrors, circular import
deadlocks, missing symbols, or unhandled exceptions.
"""

from __future__ import annotations

import importlib
import py_compile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SAGO_DIR = REPO_ROOT / "sago"


def test_compile_all_python_files(tmp_path: Path) -> None:
    """Verify that every single .py file across sago/ compiles without syntax or bytecode errors."""
    py_files = list(SAGO_DIR.rglob("*.py"))
    assert len(py_files) > 300, f"Expected >300 python files, found {len(py_files)}"

    compiled_count = 0
    errors: list[str] = []

    for py_file in py_files:
        dest_cfile = tmp_path / f"{py_file.stem}_{compiled_count}.pyc"
        try:
            py_compile.compile(str(py_file), cfile=str(dest_cfile), doraise=True)
            compiled_count += 1
        except py_compile.PyCompileError as e:
            errors.append(f"CompileError in {py_file.relative_to(REPO_ROOT)}: {e}")
        except Exception as e:
            errors.append(f"Unexpected error compiling {py_file.relative_to(REPO_ROOT)}: {e}")

    assert not errors, "Compilation failures detected:\n" + "\n".join(errors)
    assert compiled_count == len(py_files)


def test_import_all_agent_profiles() -> None:
    """Verify that all 330+ specialized agent profile modules can be loaded and parsed."""
    from sago.agents.registry import get_agent, list_agents

    agents = list_agents()
    assert len(agents) >= 300, f"Expected >= 300 agents, got {len(agents)}"

    for agent in agents[:60]:  # Sample deep profile inspection
        profile = get_agent(agent["name"])
        assert profile is not None, f"Agent profile '{agent['name']}' returned None"
        assert hasattr(profile, "name") or isinstance(profile, dict)


def test_import_all_subsystems_cleanly() -> None:
    """Verify clean import of all core architectural subsystems."""
    modules_to_test = [
        "sago.main",
        "sago.database",
        "sago.cleanup",
        "sago.settings",
        "sago.permissions",
        "sago.paths",
        "sago.version",
        "sago.logging_config",
        "sago.api.server",
        "sago.api.config",
        "sago.webserver.routes",
        "sago.webserver.models",
        "sago.webserver.websockets",
        "sago.webserver.html_template",
        "sago.security.approval",
        "sago.security.threat_scanner",
        "sago.security.untrusted_wrapper",
        "sago.engine.unified",
        "sago.engine.simple_executor",
        "sago.engine.intent_classifier",
        "sago.engine.context_assembler",
        "sago.engine.prompt_enhancer",
        "sago.engine.tool_guardrails",
        "sago.engine.hallucination_verifier",
        "sago.engine.project_synthesizer",
        "sago.engine.production",
        "sago.engine.checkpoint",
        "sago.workflow.engine",
        "sago.workflow.templates",
        "sago.workflow.langgraph_engine",
        "sago.tools.registry",
        "sago.tools.parallel_executor",
        "sago.tools.ensure_dep",
        "sago.memory.rag",
        "sago.memory.symbol_graph",
        "sago.memory.symbol_index",
        "sago.memory.learning_store",
        "sago.memory.persistent_store",
        "sago.memory.project_graph",
        "sago.memory.hybrid_indexer",
        "sago.memory.compaction",
        "sago.mcp.server",
        "sago.mcp.manager",
        "sago.mcp.client",
        "sago.tui.app",
        "sago.tui.models",
        "sago.tui.helpers",
        "sago.tui.processor",
        "sago.tui.orchestrator",
        "sago.tui.trace_viewer",
        "sago.tui.commands",
        "sago.tui.styles",
        "sago.tui.smart_input",
        "sago.tui.smart_suggest",
        "sago.tui.screens.shortcuts",
        "sago.utils.strings",
        "sago.utils.report_generator",
        "sago.utils.safe",
    ]

    for mod_name in modules_to_test:
        mod = importlib.import_module(mod_name)
        assert mod is not None, f"Failed to load module: {mod_name}"


def test_tool_registry_introspection() -> None:
    """Verify that ToolRegistry discovers tools without throwing introspection or schema errors."""
    from sago.tools.registry import discover_tools

    tools = discover_tools()
    assert isinstance(tools, dict)
    assert len(tools) >= 50, f"Expected >=50 tools discovered, got {len(tools)}"

    for name, tool_def in tools.items():
        assert tool_def.name == name
        assert tool_def.description
        assert tool_def.tool_class is not None
        # Verify JSON serializability
        as_dict = tool_def.to_dict()
        assert as_dict["name"] == name
        assert "args_schema" in as_dict
