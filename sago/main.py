"""Sago - Multi-Agent Orchestration System.

Main entry point for the Sago application.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from sago import __version__
from sago.logging_config import setup_logging
from sago.utils.safe import log_exception

setup_logging()

logger = logging.getLogger("sago.main")

console = Console()

# Chat configuration constants
_CHAT_HISTORY_MAX_SIZE = 50
_CHAT_SYSTEM_PROMPT = (
    "You are Sago, a helpful, knowledgeable, and friendly AI assistant.\n"
    "- Answer questions, conversation, greetings, explanations, and general requests naturally.\n"
    "- Respond conversationally without engineering templates or code scaffolding.\n"
    "- Keep responses concise and natural.\n"
    "- You have NO tools, NO function calling, NO web search. Never output <function=...> or XML tool tags. "
    "Only respond with plain text. If you don't know something, say so directly."
)


def _mask_secret(value: str, show_chars: int = 4) -> str:
    """Mask a secret string, showing only the first and last few characters."""
    if not value or len(value) <= show_chars * 2:
        return "****" if value else ""
    return f"{value[:show_chars]}...{value[-show_chars:]}"


def _sanitize_error_message(msg: str) -> str:
    """Remove potential API keys/secrets from error messages."""
    import os as _os

    secret_keys = [
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
    ]
    sanitized = msg
    for key in secret_keys:
        val = _os.environ.get(key, "")
        if val and val in sanitized:
            sanitized = sanitized.replace(val, _mask_secret(val))
    return sanitized


def _get_configured_model() -> str:
    """Get the configured model from config, fallback to gemini-2.0-flash / openrouter."""
    import os

    # Auto-detect model based on available API keys
    _key_model_map = [
        ("OPENROUTER_API_KEY", "openrouter/free"),
        ("OPENAI_API_KEY", "gpt-4o"),
        ("GEMINI_API_KEY", "gemini-2.0-flash"),
        ("ANTHROPIC_API_KEY", "claude-sonnet-4-20250514"),
    ]
    for env_key, default_model in _key_model_map:
        if os.environ.get(env_key):
            # Try config first, fall back to key-matched default
            try:
                from sago.config.loader import get_config

                config = get_config()
                default_prov = getattr(config.llm_providers, "default", "gemini")
                providers = getattr(config.llm_providers, "providers", {})
                if default_prov in providers and getattr(providers[default_prov], "model", None):
                    configured_model = providers[default_prov].model
                    # Only use configured model if its provider matches an available key
                    configured_key_env = getattr(providers[default_prov], "api_key_env", "")
                    if configured_key_env and os.environ.get(configured_key_env):
                        return configured_model
            except Exception as e:
                log_exception(e, "Loading config for model selection")
            return default_model
    return "openrouter/free"


@click.group()
@click.version_option(version=__version__, prog_name="sago")
def cli() -> None:
    """Sago - Sophisticated Multi-Agent Orchestration System.

    A CrewAI-based system with infinite tools, cross-platform support,
    and a master orchestrator named Sago.
    """
    pass


@cli.result_callback()
@click.pass_context
def cli_result_callback(ctx: click.Context, result: Any, **kwargs: Any) -> Any:
    """Log CLI command completion."""
    cmd_name = ctx.invoked_subcommand or ctx.info_name
    logger.debug("CLI command '%s' completed", cmd_name)
    return result


@cli.command()
@click.argument("task")
@click.option("--agent", "-a", default=None, help="Specific agent to use")
@click.option(
    "--chain",
    "-c",
    default=None,
    help="Comma-separated agent chain (e.g. python-pro,code-reviewer)",
)
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode with agent selection")
@click.option(
    "--detach",
    "-d",
    is_flag=True,
    help="Run task in detached background mode (safe to close terminal)",
)
def run(task: str, agent: str | None, chain: str | None, interactive: bool, detach: bool) -> None:
    """Execute a task using Sago agents.

    Examples:
        sago run "Write a Python web scraper"
        sago run "Run integration tests" --detach
        sago run "Debug this error" --agent debugger
        sago run "Build a REST API" --chain system-architect,fullstack-dev,code-reviewer
    """
    import os
    import subprocess
    import sys
    import time

    from sago.database import init
    from sago.engine.simple_executor import execute_agent_task
    from sago.paths import get_sago_home

    logger.info(
        "CLI 'run' invoked: task_len=%d, agent=%s, chain=%s, detach=%s",
        len(task),
        agent,
        chain,
        detach,
    )
    init()

    agent_name = agent or "python-engineer"

    if detach:
        sago_home = get_sago_home()
        logs_dir = sago_home / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        task_id = f"task_{int(time.time())}_{os.getpid()}"
        log_file = logs_dir / f"{task_id}.log"

        logger.info("Submitting detached task: task_id=%s, agent=%s", task_id, agent_name)

        # Launch detached worker in background
        cmd = [
            sys.executable,
            "-m",
            "sago.main",
            "run",
            task,
            "--agent",
            agent_name,
        ]
        with open(log_file, "w") as out_f:
            subprocess.Popen(
                cmd,
                stdout=out_f,
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
                start_new_session=True,
            )

        console.print(
            Panel(
                f"[bold green]✓ Task started in detached background mode![/]\n\n"
                f"[bold]Task ID:[/] [cyan]{task_id}[/]\n"
                f"[bold]Agent:[/]   [yellow]{agent_name}[/]\n"
                f"[bold]Log:[/]     [dim]{log_file}[/]\n\n"
                f"[green]You can safely close this terminal tab now.[/]\n\n"
                f"[dim]• Check status:[/]  [bold]sago status[/]\n"
                f"[dim]• Reattach & tail:[/] [bold cyan]sago attach {task_id}[/bold cyan]",
                title="[bold]Sago Detached Worker[/]",
                border_style="green",
            )
        )
        return

    console.print(
        Panel.fit(
            f"[bold green]Sago Agent System[/]\n"
            f"[dim]Task: {task[:80]}{'...' if len(task) > 80 else ''}[/]",
            border_style="green",
        )
    )

    # Get API key from environment
    api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
    if not api_key:
        console.print("[red]Error: No API key found. Set OPENROUTER_API_KEY or OPENAI_API_KEY[/]")
        return

    console.print(f"[green]Using agent: {agent_name}[/]\n")

    from sago.engine.prompt_enhancer import enhance_prompt

    enhancement = enhance_prompt(
        task=task,
        agent_role=agent_name,
        cwd=os.getcwd(),
    )
    if enhancement.was_modified:
        console.print(
            Panel(
                f"[bold cyan]✨ Prompt Automatically Enhanced with Intent & Scope[/bold cyan]\n\n"
                f"[bold]Synthesized Objective:[/] [white]{enhancement.intent_summary}[/white]\n"
                f"[dim]Key Additions:[/] [green]{' • '.join(enhancement.improvements)}[/green]",
                title="[bold]Sago Prompt Enhancer[/]",
                border_style="cyan",
            )
        )

    result = execute_agent_task(
        task=task,
        agent_role=agent_name.replace("-", " ").title(),
        api_key=api_key,
        model=_get_configured_model(),
        max_tokens=4096,
        max_iterations=8,
    )

    # Display result
    if isinstance(result, dict):
        output = result.get("output", "No output")
        tool_calls = result.get("tool_calls", [])
        files = result.get("files_created", [])
        logger.info(
            "Task completed: agent=%s, output_len=%d, tool_calls=%d, files=%d",
            agent_name,
            len(output),
            len(tool_calls),
            len(files),
        )

        if tool_calls:
            console.print("\n[bold]Tool calls:[/]")
            for tc in tool_calls:
                console.print(f"  [cyan]{tc['tool']}[/]: {tc.get('result', '')[:100]}")

        if files:
            console.print(f"\n[green]Files created:[/] {', '.join(files)}")

        console.print(
            Panel(
                output,
                title="[bold]Result[/]",
                border_style="blue",
            )
        )
    else:
        console.print(
            Panel(
                str(result),
                title="[bold]Result[/]",
                border_style="blue",
            )
        )


@cli.command("help")
@click.argument("command_name", required=False, default=None)
@click.pass_context
def help_cmd(ctx: click.Context, command_name: str | None) -> None:
    """Show dynamic, formatted help and usage guides for SAGO commands.

    Examples:
      sago help                # Overview of all commands & system capabilities
      sago help run            # Detailed guide for 'run' command
      sago help tools          # Detailed guide for 'tools' command
      sago help agents         # Detailed guide for 'agents' command
      sago help pr             # Detailed guide for 'pr' command group
    """
    import difflib

    from sago.agents.registry import list_agents
    from sago.plugins.base import get_plugin_manager
    from sago.skills.registry import list_skills
    from sago.tools.registry import get_total_tools_count

    root_cli = ctx.find_root().command
    if not isinstance(root_cli, click.Group):
        console.print(ctx.get_help())
        return

    # If no command_name provided, display the categorized master dashboard
    if not command_name:
        total_agents = len(list_agents())
        total_tools = get_total_tools_count()
        total_skills = len(list_skills())
        try:
            total_plugins = len(get_plugin_manager().list_plugins())
        except Exception as e:
            log_exception(e, "Listing plugins for help dashboard")
            total_plugins = 0

        console.print(
            Panel.fit(
                f"[bold cyan]SAGO Multi-Agent Orchestration — Command Reference[/]\n"
                f"[dim]Version: v{__version__}  |  Model: {_get_configured_model()}  |  "
                f"Agents: {total_agents}  |  Tools: {total_tools}  |  Skills: {total_skills}  |  Plugins: {total_plugins}[/]",
                border_style="cyan",
            )
        )

        categories = {
            "🚀 Agent Execution & Workflows": [
                (
                    "run",
                    "Execute a task using specialist agents or custom agent chains (--detach supported)",
                ),
                ("smart", "Autonomous agent selection with streaming & effort-level reasoning"),
                (
                    "chain",
                    "Sequential agent pipeline execution (e.g. architect -> dev -> reviewer)",
                ),
                (
                    "workflow",
                    "LangGraph stateful planning & execution workflow with adaptive loops",
                ),
                ("workflow-create", "Interactive creation of multi-step structured workflows"),
                ("workflow-run", "Execute a saved stateful workflow by ID"),
                ("workflow-add-step", "Add an agent or tool step to a workflow"),
                ("workflows", "List all configured workflows and execution status"),
            ],
            "💬 Interactive & Runtime Interfaces": [
                ("tui", "Interactive Textual full-terminal UI with live streaming & autocomplete"),
                ("chat", "Quick conversational interface with master Sago orchestrator"),
                ("attach", "Attach to and stream running detached tasks or TUI sessions"),
                ("serve", "Start Sago daemon background server for remote execution"),
                ("stop", "Stop running Sago daemon background server"),
                ("daemon-status", "Inspect active Sago daemon PID and status"),
                ("remote", "Dispatch and execute tasks on a remote Sago daemon instance"),
            ],
            "🔍 Codebase Intelligence & VCS": [
                ("search", "Natural language semantic & BM25 hybrid codebase search"),
                ("map", "Generate compact AST symbol outline map across repository"),
                (
                    "project-graph",
                    "Deep architecture diagrams, process pipelines & data model ER graphs",
                ),
                ("graph", "Alias for project-graph with curated architecture visualization"),
                (
                    "verify",
                    "Self-healing linter, type-check, and automated test suite verification",
                ),
                ("pr", "Automated feature branch and verified Pull Request creation workflow"),
                ("parse", "Convert documents, PDFs, Excel sheets, and web files to Markdown"),
            ],
            "🗂️ Dynamic Registries & State": [
                (
                    "tools",
                    "Dynamically explore, search, and inspect all available tools & parameters",
                ),
                ("agents", "Explore specialist engineering agents across domain categories"),
                ("info", "Inspect detailed role, skills, tools, and handoffs for an agent"),
                ("skills", "List built-in capabilities and custom workspace skills"),
                ("plugins", "List installed third-party plugins and lifecycle hooks"),
                ("sessions", "List historical interactive sessions with message & tool metrics"),
                ("history", "View full message history and tool trace logs for a session"),
                (
                    "checkpoint",
                    "Create and restore atomic workspace snapshots for safe refactoring",
                ),
            ],
            "⚙️ Configuration & Diagnostics": [
                ("status", "Comprehensive live system health, active model, tools, and DB status"),
                ("doctor", "Full diagnostic check of Python runtime, DB, API keys, and ports"),
                ("init", "Initialize Sago in current directory with tailored project config"),
                ("setup", "Interactive setup wizard for LLM providers and workspace preferences"),
                ("onboard", "Seamless first-time onboarding wizard"),
                ("clean", "Garbage collect stale caches, backups, logs, and empty DB sessions"),
                (
                    "logs",
                    "View, filter, and manage Sago log files with dashboard and smart cleanup",
                ),
                ("usage", "Inspect token consumption, API costs, and cache hit rates"),
                ("telemetry", "Export traces and metrics (OpenTelemetry, Prometheus, JSON, HTML)"),
                ("hook", "Manage Git pre-commit hooks for automatic syntax and symbol indexing"),
                ("update", "Check for updates and auto-upgrade SAGO via uv/pip"),
                ("help", "Display this dynamic guide or detailed help for any specific command"),
            ],
        }

        for cat_title, cmd_list in categories.items():
            table = Table(
                title=f"[bold]{cat_title}[/bold]",
                show_header=True,
                header_style="bold cyan",
                border_style="dim",
            )
            table.add_column("Command", style="bold yellow", width=22)
            table.add_column("Description", style="white")

            for cmd_name, fallback_desc in cmd_list:
                cmd_obj = root_cli.commands.get(cmd_name)
                desc = fallback_desc
                if cmd_obj:
                    doc = (cmd_obj.help or cmd_obj.short_help or "").strip()
                    if doc:
                        desc = doc.splitlines()[0]
                table.add_row(f"sago {cmd_name}", desc)

            console.print(table)
            console.print("")

        console.print(
            "[bold cyan]Need details on a specific command?[/bold cyan] Run [bold white]sago help <command>[/bold white]  "
            "[dim](e.g. 'sago help run', 'sago help tools', 'sago help agents')[/dim]\n"
        )
        return

    # If command_name is provided, find and display its dynamic help
    cmd_name = command_name.strip()
    cmd_obj = root_cli.commands.get(cmd_name)

    if not cmd_obj:
        # Check sub-groups like "pr create" or "hook install"
        parts = cmd_name.split()
        if len(parts) > 1 and parts[0] in root_cli.commands:
            group = root_cli.commands[parts[0]]
            if isinstance(group, click.Group) and parts[1] in group.commands:
                cmd_obj = group.commands[parts[1]]

    if not cmd_obj:
        # Fuzzy match suggestions
        all_cmds = list(root_cli.commands.keys())
        matches = difflib.get_close_matches(cmd_name, all_cmds, n=3, cutoff=0.4)
        console.print(f"[bold red]Command not found:[/] '{cmd_name}'")
        if matches:
            console.print(
                f"[yellow]Did you mean:[/] {', '.join(f'[bold cyan]sago {m}[/bold cyan]' for m in matches)}"
            )
        console.print("[dim]Run 'sago help' to see all available commands.[/]\n")
        return

    # Render rich help for cmd_obj
    console.print(
        Panel.fit(
            f"[bold cyan]SAGO Command:[/] [bold yellow]sago {cmd_name}[/bold yellow]",
            border_style="cyan",
        )
    )

    doc = (cmd_obj.help or cmd_obj.short_help or "No description available.").strip()
    console.print(f"\n[bold]Description:[/]\n{doc}\n")

    # Options and arguments
    if hasattr(cmd_obj, "params") and cmd_obj.params:
        p_table = Table(
            title="[bold]Options & Arguments[/bold]", show_header=True, header_style="bold cyan"
        )
        p_table.add_column("Option / Argument", style="bold yellow")
        p_table.add_column("Type", style="dim")
        p_table.add_column("Default", style="green")
        p_table.add_column("Description", style="white")

        for param in cmd_obj.params:
            names = ", ".join(param.opts or [param.name])
            ptype = param.type.name if hasattr(param.type, "name") else str(param.type)
            default_val = str(param.default) if param.default is not None else "[dim]none[/dim]"
            if getattr(param, "is_flag", False):
                default_val = f"flag ({param.default})"
            pdesc = param.help if hasattr(param, "help") and param.help else ""
            p_table.add_row(names, ptype, default_val, pdesc or "-")

        console.print(p_table)

    if isinstance(cmd_obj, click.Group) and cmd_obj.commands:
        sub_table = Table(
            title="[bold]Subcommands[/bold]", show_header=True, header_style="bold cyan"
        )
        sub_table.add_column("Subcommand", style="bold yellow")
        sub_table.add_column("Description", style="white")
        for sc_name, sc_obj in cmd_obj.commands.items():
            sc_desc = (
                (sc_obj.short_help or sc_obj.help or "").splitlines()[0]
                if (sc_obj.help or sc_obj.short_help)
                else ""
            )
            sub_table.add_row(f"sago {cmd_name} {sc_name}", sc_desc)
        console.print("\n", sub_table)

    console.print(f"\n[dim]Run 'sago {cmd_name} --help' for standard Click help output.[/]\n")


@cli.command()
@click.argument("query", required=False, default=None)
@click.option("--all", "show_all", is_flag=True, help="List all agents unconditionally")
def agents(query: str | None = None, show_all: bool = False) -> None:
    """List agent categories or filter agents by category/name.

    Examples:
      sago agents                     # Show all categories
      sago agents database            # List agents in database category
      sago agents security            # List agents in security category
      sago agents python              # Search for agents matching 'python'
      sago agents --all               # List all available agents
    """
    from sago.agents.registry import get_agents_by_category, list_categories

    categories = list_categories()
    total_agents = sum(len(v) for v in categories.values())
    logger.debug("Agents listed: total=%d, categories=%d", total_agents, len(categories))

    # Case 1: No query and not --all -> Show Category Overview
    if not query and not show_all:
        console.print(
            Panel.fit(
                f"[bold cyan]Sago Specialist Agent Categories[/]  [dim]({total_agents} agents across {len(categories)} domains)[/]",
                border_style="cyan",
            )
        )
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Category / Domain", style="bold yellow")
        table.add_column("Count", justify="right", style="green")
        table.add_column("Example Specialist Agents", style="dim")

        for cat, agent_list in sorted(categories.items()):
            sample = ", ".join(a.name for a in agent_list[:4])
            if len(agent_list) > 4:
                sample += f", ... (+{len(agent_list) - 4} more)"
            table.add_row(cat, str(len(agent_list)), sample)

        console.print(table)
        console.print(
            "\n[dim]To view agents in a category, run:[/] [bold cyan]sago agents <category_or_search>[/]"
        )
        console.print(
            "[dim]Example:[/] [bold]sago agents database[/]  or  [bold]sago agents python[/]\n"
        )
        return

    # Case 2: Filtered by query or --all
    if show_all:
        matched_agents = [a for group in categories.values() for a in group]
        header_title = f"All Specialist Agents ({len(matched_agents)})"
    else:
        matched_agents = get_agents_by_category(query)
        header_title = f"Specialist Agents matching '{query}' ({len(matched_agents)})"

    if not matched_agents:
        console.print(f"[yellow]No agents found matching '{query}'.[/]")
        console.print("[dim]Run 'sago agents' to see all available categories.[/]")
        return

    console.print(Panel.fit(f"[bold]{header_title}[/]", border_style="blue"))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Category", style="yellow")
    table.add_column("Role")
    table.add_column("Key Tools", style="dim")
    table.add_column("Handoff To", style="dim")

    for a in matched_agents:
        tools_str = ", ".join(a.tools[:3]) + (f" (+{len(a.tools) - 3})" if len(a.tools) > 3 else "")
        handoff_str = ", ".join(a.handoff_to[:3]) if a.handoff_to else "None"
        table.add_row(a.name, a.category, a.role, tools_str, handoff_str)

    console.print(table)
    console.print(
        f"\n[dim]Total: {len(matched_agents)} agents shown. Use 'sago info <name>' for details.[/]\n"
    )


@cli.command()
@click.argument("agent_name")
def info(agent_name: str) -> None:
    """Show detailed info about a specific agent."""
    import difflib

    from sago.agents.registry import get_agent, get_handoff_targets, list_agents

    agent = get_agent(agent_name)
    if agent is None:
        console.print(f"[bold red]Agent not found:[/] '{agent_name}'")
        all_agents = [a["name"] for a in list_agents()]
        matches = difflib.get_close_matches(agent_name, all_agents, n=3, cutoff=0.4)
        if matches:
            console.print(
                f"[yellow]Did you mean:[/] {', '.join(f'[bold cyan]{m}[/bold cyan]' for m in matches)}"
            )
        console.print("Use 'sago agents' to see available agents.\n")
        return

    console.print(
        Panel.fit(
            f"[bold]{agent.codename}[/]\n[dim]{agent.role}[/]",
            border_style="blue",
        )
    )

    console.print(f"\n[bold]Description:[/]\n{agent.description}")
    console.print(f"\n[bold]Category:[/]\n{agent.category}")
    console.print(f"\n[bold]Skills:[/]\n{', '.join(agent.skills)}")
    console.print(f"\n[bold]Tools:[/]\n{', '.join(agent.tools)}")
    console.print(f"\n[bold]Max Iterations:[/] {agent.max_iterations}")
    console.print(f"\n[bold]Temperature:[/] {agent.temperature}")

    handoff = get_handoff_targets(agent_name)
    if handoff:
        console.print("\n[bold]Can Hand Off To:[/]")
        for h in handoff:
            console.print(f"  - {h.name} ({h.codename})")


@cli.command()
def status() -> None:
    """Show Sago system status and active resource metrics."""
    from sago.agents.registry import list_agents
    from sago.config.loader import get_config
    from sago.database import Session
    from sago.mcp.manager import get_mcp_manager
    from sago.paths import get_db_path, get_sago_home
    from sago.plugins.base import get_plugin_manager
    from sago.skills.loader import SkillLoader
    from sago.skills.registry import list_skills
    from sago.tools.registry import get_total_tools_count
    from sago.tools.registry import list_categories as list_tool_categories

    config = get_config()
    db_path = get_db_path()
    sago_home = get_sago_home()

    console.print(
        Panel.fit(
            f"[bold cyan]Sago System Status[/]  [dim](v{__version__})[/]",
            border_style="cyan",
        )
    )

    # Core Directories & DB
    console.print(f"[bold]Home:[/]     {sago_home}")
    console.print(f"[bold]Database:[/] {db_path}")

    if db_path.exists():
        try:
            session = Session()
            sessions = session.list_all(limit=100)
            active_count = sum(1 for s in sessions if s.get("status") == "active")
            console.print(f"[bold]Sessions:[/] {len(sessions)} stored ({active_count} active)")
            session.close()
        except Exception as e:
            console.print(f"[bold]Sessions:[/] Error reading database: {e}")
    else:
        console.print("[bold]Database:[/] [yellow]Not initialized[/]")

    # LLM & Orchestration
    console.print(f"\n[bold]Default Provider:[/] [cyan]{config.llm_providers.default}[/cyan]")
    console.print(f"[bold]Default Model:[/]    [green]{_get_configured_model()}[/green]")
    console.print(f"[bold]Orchestrator:[/]     [yellow]{config.orchestrator.name}[/yellow]")

    # Dynamic Registries Counts
    agents_list = list_agents()
    tools_count = get_total_tools_count()
    tool_cats = len(list_tool_categories())
    builtin_skills = list_skills()
    custom_skills = SkillLoader.discover_skills()
    total_skills = len(builtin_skills) + len(custom_skills)

    pm = get_plugin_manager()
    plugins = pm.list_plugins()
    mcp_mgr = get_mcp_manager()
    mcp_servers = mcp_mgr.list_servers()

    console.print(
        f"\n[bold]Specialist Agents:[/] [bold green]{len(agents_list)}[/bold green] available across 22 domains"
    )
    console.print(
        f"[bold]Tool Registry:[/]     [bold green]{tools_count}[/bold green] dynamic tools across {tool_cats} categories"
    )
    console.print(
        f"[bold]Skills Registry:[/]   [bold green]{total_skills}[/bold green] skills ({len(builtin_skills)} built-in, {len(custom_skills)} custom)"
    )
    console.print(
        f"[bold]Plugins:[/]           [bold green]{len(plugins)}[/bold green] external plugins loaded"
    )
    console.print(
        f"[bold]MCP Servers:[/]       [bold green]{len(mcp_servers)}[/bold green] servers configured\n"
    )


@cli.command()
@click.argument("query", required=False, default=None)
@click.option("--all", "show_all", is_flag=True, help="List all tools unconditionally in a table")
@click.option("--category", "-c", default=None, help="Filter tools by specific category")
@click.option("--json-out", is_flag=True, help="Output tools in raw JSON format")
@click.option("--reload", "-r", is_flag=True, help="Force reload tools from disk & plugins")
def tools(
    query: str | None,
    show_all: bool,
    category: str | None,
    json_out: bool,
    reload: bool,
) -> None:
    """Explore, search, and inspect all available SAGO tools dynamically.

    Examples:
      sago tools                       # Show categories overview & tool counts
      sago tools coding                # List tools in coding category
      sago tools git                   # Search for tools related to 'git'
      sago tools read_file             # Inspect specific tool arguments & schema
      sago tools --all                 # List all tools in a table
      sago tools --category file       # Filter by category
      sago tools --json-out            # Machine-readable JSON export
    """
    import json

    from sago.tools.registry import (
        discover_tools,
        get_tool,
        list_categories,
        list_tools,
    )

    if reload:
        discover_tools(force_reload=True)

    # JSON export
    if json_out:
        all_tools = discover_tools(force_reload=reload)
        out = {k: v.to_dict() for k, v in all_tools.items()}
        console.print(json.dumps(out, indent=2))
        return

    # Check if querying a specific single tool by exact name
    if query:
        single_tool = get_tool(query.strip())
        if single_tool:
            console.print(
                Panel.fit(
                    f"[bold cyan]Tool:[/] [bold yellow]{single_tool.name}[/bold yellow]  "
                    f"[dim]Category: {single_tool.category} | Source: {single_tool.source}[/dim]",
                    border_style="cyan",
                )
            )
            console.print(f"\n[bold]Description:[/]\n{single_tool.description}\n")
            console.print(f"[bold]Implementation Module:[/] [dim]{single_tool.module_path}[/dim]\n")

            if single_tool.args_schema:
                table = Table(
                    title="[bold]Tool Arguments & Parameters[/bold]",
                    show_header=True,
                    header_style="bold cyan",
                )
                table.add_column("Parameter", style="bold yellow")
                table.add_column("Type", style="dim")
                table.add_column("Required", style="green")
                table.add_column("Default")
                table.add_column("Description")

                for pname, pinfo in single_tool.args_schema.items():
                    req_str = (
                        "[bold red]YES[/bold red]" if pinfo.get("required") else "[dim]no[/dim]"
                    )
                    def_str = (
                        str(pinfo.get("default"))
                        if pinfo.get("default") is not None
                        else "[dim]none[/dim]"
                    )
                    table.add_row(
                        pname,
                        pinfo.get("type", "str"),
                        req_str,
                        def_str,
                        pinfo.get("description", "-"),
                    )
                console.print(table)
            else:
                console.print(
                    "[dim]No structured argument schema required (takes standard keyword args).[/dim]"
                )
            console.print("")
            return

    categories = list_categories()
    total_tools = sum(len(v) for v in categories.values())

    # Case 1: Category overview when no query and not --all and not --category
    if not query and not show_all and not category:
        console.print(
            Panel.fit(
                f"[bold cyan]Sago Dynamic Tools Registry[/]  [dim]({total_tools} tools across {len(categories)} categories)[/]",
                border_style="cyan",
            )
        )

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Category / Domain", style="bold yellow", width=18)
        table.add_column("Count", justify="right", style="green", width=8)
        table.add_column("Discovered Tools", style="white")

        for cat, tool_list in sorted(categories.items()):
            sample = ", ".join(t.name for t in tool_list[:5])
            if len(tool_list) > 5:
                sample += f", ... (+{len(tool_list) - 5} more)"
            table.add_row(cat, str(len(tool_list)), sample)

        console.print(table)
        console.print(
            "\n[dim]To view tools in a category or search by name:[/] [bold cyan]sago tools <category_or_search>[/bold cyan]"
        )
        console.print(
            "[dim]To inspect parameters of a specific tool:[/]   [bold cyan]sago tools <tool_name>[/bold cyan]"
        )
        console.print(
            "[dim]To list every tool with full descriptions:[/]      [bold cyan]sago tools --all[/bold cyan]\n"
        )
        return

    # Case 2: Filtered search or --all or --category
    filter_cat = category
    matched_tools = list_tools(category=filter_cat, query=query)

    if not matched_tools:
        console.print(f"[yellow]No tools found matching query '{query or filter_cat}'.[/yellow]")
        console.print("[dim]Run 'sago tools' to see all available categories.[/]\n")
        return

    header_title = f"Discovered Tools ({len(matched_tools)})"
    if query:
        header_title += f" matching '{query}'"
    if filter_cat:
        header_title += f" in category '{filter_cat}'"

    console.print(Panel.fit(f"[bold]{header_title}[/]", border_style="cyan"))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Tool Name", style="bold cyan", min_width=20)
    table.add_column("Category", style="yellow", min_width=12)
    table.add_column("Description", style="white")
    table.add_column("Source", style="dim")

    for t in matched_tools:
        table.add_row(t.name, t.category, t.description, t.source)

    console.print(table)
    console.print(
        f"\n[dim]Total: {len(matched_tools)} tools shown. Use 'sago tools <tool_name>' for parameter details.[/]\n"
    )


@cli.command()
@click.option("--limit", "-l", default=20, help="Number of sessions to list")
@click.option("--clean/--no-clean", default=True, help="Auto-clean empty and useless sessions")
def sessions(limit: int, clean: bool) -> None:
    """List recent sessions with message and tool execution stats."""
    from sago.database import MessageStore, Session, ToolUsageStore, init_db

    init_db()
    session = Session()
    if clean:
        session.cleanup_useless_sessions()
    sessions_list = session.list_all(limit=limit)

    if not sessions_list:
        console.print("[dim]No active sessions found in database ~/.sago/data/sago.db.[/]")
        return

    console.print(Panel.fit("[bold cyan]Recent SAGO Sessions[/]", border_style="cyan"))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Session ID", style="cyan", max_width=14)
    table.add_column("Title / Prompt", max_width=36)
    table.add_column("Msgs", justify="right", style="green")
    table.add_column("Tools", justify="right", style="yellow")
    table.add_column("Created", style="dim")
    table.add_column("Status")

    for s in sessions_list:
        sid = s["id"]
        try:
            ms = MessageStore(sid)
            msg_count = ms.count()
        except Exception as e:
            log_exception(e, "Counting messages for session")
            msg_count = 0
        try:
            tus = ToolUsageStore(sid)
            tool_count = len(tus.get_all())
        except Exception as e:
            log_exception(e, "Counting tool usage for session")
            tool_count = 0

        status_str = s.get("status", "active")
        status_styled = (
            "[bold green]active[/bold green]"
            if status_str == "active"
            else (
                "[cyan]detached[/cyan]" if status_str == "detached" else f"[dim]{status_str}[/dim]"
            )
        )

        table.add_row(
            sid[:12],
            (s.get("title") or "Untitled")[:35],
            str(msg_count),
            str(tool_count),
            s["created_at"][:16].replace("T", " "),
            status_styled,
        )

    console.print(table)
    console.print("\n[dim]To view history:  sago history <session_id>[/dim]")
    console.print("[dim]To resume in TUI: sago tui --resume <session_id>[/dim]\n")


@cli.command()
@click.argument("session_id")
def history(session_id: str) -> None:
    """Show message history and tool executions for a session."""
    from sago.database import MessageStore, Session, init_db

    init_db()

    target_sid = session_id
    session_title = "Untitled"
    matched = Session().find_by_prefix(session_id)
    if matched:
        target_sid = matched["id"]
        session_title = matched.get("title") or "Untitled"

    msg_store = MessageStore(target_sid)
    messages = msg_store.get_history(limit=100)

    if not messages:
        console.print(f"[dim]No messages found for session {session_id} in ~/.sago/data/sago.db[/]")
        return

    console.print(
        Panel.fit(
            f"[bold]Session History: {target_sid[:12]}[/] [dim]({session_title})[/]",
            border_style="blue",
        )
    )

    for msg in messages:
        role = msg["role"]
        agent = msg.get("agent_name", "")
        content = msg["content"]

        if role == "user":
            console.print("\n[bold blue]User:[/]")
        elif role == "assistant":
            console.print(f"\n[bold green]{agent or 'Sago'}:[/]")
        else:
            console.print(f"\n[bold]{role}:[/]")

        console.print(content[:500])
        if len(content) > 500:
            console.print("[dim]...[/]")


@cli.command()
@click.option("--name", "-n", default=None, help="Project name")
@click.option("--ssh/--no-ssh", default=False, help="Enable SSH tools")
def init(name: str | None, ssh: bool) -> None:
    """Initialize Sago in the current directory.

    Creates a config.sago.json file that lets you customize agents,
    tools, permissions, and prompts for this project.

    Examples:
        sago init
        sago init --name my-project
        sago init --ssh
    """
    from sago.agents.loader import load_all_profiles
    from sago.config.project_config import (
        create_config_file,
        detect_project_frameworks,
        detect_project_languages,
    )

    project_path = Path.cwd()

    console.print(
        Panel.fit(
            "[bold blue]Sago Project Initialization[/]",
            border_style="blue",
        )
    )

    # Detect project info
    languages = detect_project_languages(project_path)
    frameworks = detect_project_frameworks(project_path)

    console.print(f"\n[bold]Project:[/] {project_path.name}")
    if languages:
        console.print(f"[bold]Languages:[/] {', '.join(languages)}")
    if frameworks:
        console.print(f"[bold]Frameworks:[/] {', '.join(frameworks)}")

    # Check for existing config
    config_path = project_path / "config.sago.json"
    if config_path.exists():
        console.print("[yellow]config.sago.json already exists![/]")
        if not click.confirm("Overwrite?"):
            console.print("[dim]Cancelled.[/]")
            return

    # Create config
    config_file = create_config_file(
        project_path=project_path,
        project_name=name or project_path.name,
        languages=languages,
        frameworks=frameworks,
        enable_all_agents=True,
        enable_ssh=ssh,
    )

    # Show what was created
    profiles = load_all_profiles()
    console.print(f"\n[green]Created: {config_file.name}[/]")
    console.print(f"\n[bold]Configured {len(profiles)} agents:[/]")

    for agent_name in sorted(profiles.keys()):
        profile = profiles[agent_name]
        console.print(f"  [cyan]{agent_name}[/] - {profile.role}")

    console.print("\n[bold]Customize by editing config.sago.json:[/]")
    console.print("  - Enable/disable agents")
    console.print("  - Override system prompts")
    console.print("  - Add/remove tools per agent")
    console.print("  - Configure permissions")
    console.print("  - Set LLM provider preferences")

    console.print("\n[bold]Usage:[/]")
    console.print('  sago run "your task"          # Auto-orchestrate')
    console.print('  sago run "task" --agent X     # Use specific agent')
    console.print("  sago agents                   # List all agents")


def _run_interactive_setup() -> None:
    """Core interactive setup wizard for Sago."""
    import os
    from pathlib import Path

    import yaml
    from rich.prompt import Confirm, Prompt

    logger.info("Setup wizard started")

    console.print(
        Panel.fit(
            "[bold cyan]✨ Welcome to SAGO — Intelligent Multi-Agent Orchestration[/]\n"
            "[dim]Let's configure your workspace for seamless local & distributed agent execution.[/]",
            border_style="cyan",
        )
    )

    sago_home = Path.home() / ".sago"
    sago_home.mkdir(parents=True, exist_ok=True)
    for sub in ("logs", "sessions", "cache", "data", "cache/hybrid_index"):
        (sago_home / sub).mkdir(parents=True, exist_ok=True)

    # 1. Select LLM provider
    console.print("\n[bold]1. Choose your Primary LLM Provider:[/]")
    console.print("  [cyan]1.[/] Google Gemini [dim](Fast & recommended default)[/]")
    console.print("  [cyan]2.[/] OpenAI [dim](GPT-4o / o1 / o3-mini)[/]")
    console.print("  [cyan]3.[/] Anthropic Claude [dim](Claude 3.7 Sonnet / Haiku)[/]")
    console.print("  [cyan]4.[/] OpenRouter [dim](Unified API for 100+ models)[/]")
    console.print("  [cyan]5.[/] Ollama [dim](100% Private local offline LLM)[/]")

    choice = Prompt.ask("Select provider", choices=["1", "2", "3", "4", "5"], default="1")
    providers_map = {
        "1": ("gemini", "GEMINI_API_KEY", "gemini-2.0-flash"),
        "2": ("openai", "OPENAI_API_KEY", "gpt-4o"),
        "3": ("claude", "ANTHROPIC_API_KEY", "claude-sonnet-4-20250514"),
        "4": ("openrouter", "OPENROUTER_API_KEY", "anthropic/claude-sonnet-4"),
        "5": ("ollama", None, "llama3.1"),
    }
    provider, api_key_env, default_model = providers_map[choice]

    logger.info("Setup wizard: provider selected=%s", provider)

    # 2. Get API key if needed
    saved_key: str | None = None
    if api_key_env:
        current_env = os.environ.get(api_key_env, "")
        prompt_msg = f"Enter {api_key_env}" + (
            f" [dim](found in env: {_mask_secret(current_env)})[/]" if current_env else ""
        )
        entered_key = Prompt.ask(prompt_msg, default=current_env)
        if entered_key:
            saved_key = entered_key
            os.environ[api_key_env] = entered_key
            console.print(f"  [green]✓[/] {api_key_env} registered.")

    # 3. Model selection
    selected_model = Prompt.ask("Default Model", default=default_model)

    # 4. Save persistent user config to ~/.sago/config.yaml
    config_file = sago_home / "config.yaml"
    user_config: dict[str, Any] = {}
    if config_file.exists():
        try:
            user_config = yaml.safe_load(config_file.read_text()) or {}
        except Exception as e:
            log_exception(e, "Reading existing user config YAML")
            user_config = {}

    user_config.setdefault("llm_providers", {})
    user_config["llm_providers"]["default"] = provider
    user_config["llm_providers"].setdefault("providers", {})
    user_config["llm_providers"]["providers"][provider] = {
        "enabled": True,
        "model": selected_model,
    }
    if saved_key and api_key_env:
        user_config["llm_providers"]["providers"][provider]["api_key_env"] = api_key_env

    config_file.write_text(yaml.dump(user_config, default_flow_style=False))
    console.print(f"  [green]✓[/] Configuration saved to [bold]{config_file}[/]")

    # 5. Initialize SQLite Database
    from sago.database import init

    init()
    console.print("  [green]✓[/] SQLite database & state storage initialized.")

    # 6. Ask for Git Hooks installation if inside git repo
    if (Path.cwd() / ".git").exists() and (Path.cwd() / "scripts" / "install-hooks.sh").exists():
        if Confirm.ask(
            "\nInstall Git pre-commit & pre-push quality hooks for this repo?", default=True
        ):
            import subprocess

            try:
                subprocess.run(
                    ["bash", "./scripts/install-hooks.sh"], check=True, capture_output=True
                )
                console.print("  [green]✓[/] Git hooks installed successfully.")
            except Exception as e:
                console.print(
                    f"  [yellow]Notice:[/] Could not install git hooks automatically ({e})."
                )

    # Onboarding summary card
    console.print(
        Panel(
            f"[bold green]Setup Complete & Ready to Build![/]\n\n"
            f"[bold]Active Provider:[/] [cyan]{provider}[/] ([bold]{selected_model}[/])\n"
            f"[bold]Config Path:[/]     [dim]{config_file}[/]\n\n"
            f"[bold]Recommended Next Steps:[/]\n"
            f"  • [cyan]sago run 'your task'[/]       Auto-orchestrate any software task\n"
            f"  • [cyan]sago tui[/]                    Launch interactive full-screen TUI terminal\n"
            f"  • [cyan]sago smart 'review PR'[/]      Execute smart auto-delegating task\n"
            f"  • [cyan]sago doctor[/]                 Verify system health, keys, and network ports\n"
            f"  • [cyan]sago agents[/]                 Explore 339 specialized engineering agents",
            title="[bold blue]🚀 Quickstart Guide[/]",
            border_style="green",
        )
    )


@cli.command()
def setup() -> None:
    """Interactive setup wizard for Sago."""
    _run_interactive_setup()


@cli.command()
def onboard() -> None:
    """Seamless interactive onboarding wizard for new Sago setups."""
    _run_interactive_setup()


@cli.command()
def doctor() -> None:
    """Check system health, API keys, database, network ports, and tool dependencies."""
    import os
    import socket
    import sys
    from pathlib import Path

    from rich.table import Table

    table = Table(title="🏥 Sago System Health Check", border_style="cyan", show_header=True)
    table.add_column("Subsystem", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    table.add_row("Python Runtime", "[green]✓ PASS[/]", f"Python {py_ver}")

    # 2. Config & Directories
    sago_home = Path.home() / ".sago"
    if sago_home.exists():
        table.add_row("User Directory", "[green]✓ PASS[/]", f"{sago_home} (Writable)")
    else:
        table.add_row(
            "User Directory", "[yellow]! WARN[/]", f"{sago_home} missing. Run 'sago setup'."
        )

    # 3. Database
    from sago.database import get_db

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            table.add_row("SQLite Database", "[green]✓ PASS[/]", f"{len(tables)} tables active")
    except Exception as exc:
        table.add_row("SQLite Database", "[red]✗ FAIL[/]", str(exc))

    # 4. LLM API Keys
    keys = {
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
        "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY"),
    }
    configured_keys = [k for k, v in keys.items() if v]
    if configured_keys:
        table.add_row("LLM API Keys", "[green]✓ PASS[/]", f"Active: {', '.join(configured_keys)}")
    else:
        table.add_row(
            "LLM API Keys",
            "[yellow]! NONE[/]",
            "No API keys found in environment. Set GEMINI_API_KEY or run 'sago setup'.",
        )

    # 5. Ports availability
    for name, port in [("Daemon Port", 7654), ("Mesh P2P Port", 7655)]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(0.5)
            res = s.connect_ex(("127.0.0.1", port))
            if res == 0:
                table.add_row(name, "[green]● ACTIVE[/]", f"Port {port} in use / service running")
            else:
                table.add_row(name, "[dim]○ READY[/]", f"Port {port} free for daemon/mesh")
        except Exception as e:
            log_exception(e, f"Checking port {port} availability")
            table.add_row(name, "[dim]○ READY[/]", f"Port {port} ready")
        finally:
            s.close()

    # 6. Agents & Tools Registries
    from sago.agents.registry import list_agents
    from sago.mcp.manager import get_mcp_manager
    from sago.plugins.base import get_plugin_manager
    from sago.skills.loader import SkillLoader
    from sago.skills.registry import list_skills
    from sago.tools.registry import get_total_tools_count
    from sago.tools.registry import list_categories as list_tool_categories

    agents_count = len(list_agents())
    table.add_row(
        "Specialist Agents",
        "[green]✓ PASS[/]",
        f"{agents_count} agent profiles active across 22 domains",
    )

    tools_count = get_total_tools_count()
    tool_cats = len(list_tool_categories())
    table.add_row(
        "Dynamic Tools",
        "[green]✓ PASS[/]",
        f"{tools_count} tools discovered across {tool_cats} categories",
    )

    skills_count = len(list_skills()) + len(SkillLoader.discover_skills())
    table.add_row(
        "Skills Registry", "[green]✓ PASS[/]", f"{skills_count} built-in & workspace skills ready"
    )

    pm = get_plugin_manager()
    plugins = pm.list_plugins()
    table.add_row(
        "Plugin Extensions",
        "[green]✓ PASS[/]",
        f"{len(plugins)} external plugins loaded"
        if plugins
        else "0 plugins (ready for extensions)",
    )

    mcp_mgr = get_mcp_manager()
    mcp_servers = mcp_mgr.list_servers()
    table.add_row(
        "MCP Protocol",
        "[green]✓ PASS[/]",
        f"{len(mcp_servers)} MCP servers configured"
        if mcp_servers
        else "0 MCP servers (ready for integration)",
    )

    console.print(table)
    console.print(
        "\n[dim]Run [bold]sago onboard[/] to reconfigure providers or workspace settings.[/]\n"
    )


@cli.command()
@click.option("--check", is_flag=True, help="Check for updates without installing")
@click.option("--pre", is_flag=True, help="Allow pre-release versions")
def update(check: bool, pre: bool) -> None:
    """Auto-detect package manager (uv/pip) and update SAGO to the latest version.

    Examples:
        sago update          # Upgrade SAGO in-place
        sago update --check  # Check current vs latest PyPI version
    """
    import json
    import shutil
    import subprocess
    import sys
    import urllib.request

    console.print(
        Panel.fit(
            f"[bold cyan]🚀 SAGO Package Updater (Current: v{__version__})[/]",
            border_style="cyan",
        )
    )

    # 1. Fetch latest version from PyPI
    latest_version = None
    package_name = "sago-agent"
    try:
        req = urllib.request.Request(
            f"https://pypi.org/pypi/{package_name}/json",
            headers={"User-Agent": f"sago-cli/{__version__}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            latest_version = data.get("info", {}).get("version")
    except Exception as e:
        log_exception(e, "Fetching latest version from PyPI")
        latest_version = None

    if latest_version:
        console.print(f"  • Current Installed Version: [bold]{__version__}[/]")
        console.print(f"  • Latest PyPI Version:      [bold green]{latest_version}[/]")
        if latest_version == __version__ and not pre:
            logger.info("Update check: already up to date (v%s)", __version__)
            console.print("\n[green]✓ SAGO is already up to date![/]\n")
            return
        else:
            logger.info(
                "Update check: update available current=%s latest=%s", __version__, latest_version
            )
    else:
        logger.warning("Update check: could not fetch latest version from PyPI")
        console.print(f"  • Current Installed Version: [bold]{__version__}[/]")
        console.print("  • [yellow]Note:[/] Checking PyPI for updates...")

    if check:
        return

    # 2. Detect package manager and installation method
    has_uv = bool(shutil.which("uv"))
    has_pipx = bool(shutil.which("pipx"))

    # Check if installed via `uv tool`
    is_uv_tool = False
    if has_uv:
        try:
            res = subprocess.run(["uv", "tool", "list"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and "sago-agent" in res.stdout:
                is_uv_tool = True
        except Exception as e:
            log_exception(e, "Checking uv tool installation status")
            is_uv_tool = False

    # Check if installed via `pipx`
    is_pipx = False
    if not is_uv_tool and has_pipx:
        try:
            res = subprocess.run(["pipx", "list"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and "sago-agent" in res.stdout:
                is_pipx = True
        except Exception as e:
            log_exception(e, "Checking pipx installation status")
            is_pipx = False

    update_cmd = []
    if is_uv_tool:
        console.print(
            "\n[dim]⚡ Detected global installation via [bold cyan]uv tool[/bold cyan][/dim]"
        )
        update_cmd = ["uv", "tool", "upgrade", package_name]
    elif is_pipx:
        console.print(
            "\n[dim]📦 Detected global installation via [bold cyan]pipx[/bold cyan][/dim]"
        )
        update_cmd = ["pipx", "upgrade", package_name]
    elif has_uv:
        console.print("\n[dim]⚡ Detected package manager: [bold cyan]uv[/bold cyan][/dim]")
        update_cmd = ["uv", "pip", "install", "--upgrade", package_name]
        if sys.prefix == sys.base_prefix:
            update_cmd.append("--system")
        if pre:
            update_cmd.append("--prerelease=allow")
    else:
        console.print("\n[dim]📦 Detected package manager: [bold cyan]pip[/bold cyan][/dim]")
        update_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", package_name]
        if pre:
            update_cmd.append("--pre")

    console.print(f"[bold]Executing upgrade command:[/] `{' '.join(update_cmd)}`\n")
    try:
        with console.status(
            f"[bold cyan]Fetching and installing latest {package_name}...[/bold cyan]",
            spinner="dots",
        ):
            result = subprocess.run(update_cmd, capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            console.print(
                "[bold green]✓ SAGO has been successfully updated to the latest version![/bold green]\n"
            )
            if result.stdout.strip():
                tail_out = "\n".join(result.stdout.strip().splitlines()[-6:])
                console.print(f"[dim]{tail_out}[/dim]\n")
        else:
            console.print(
                f"[bold red]✗ Update failed with exit code {result.returncode}:[/bold red]"
            )
            if result.stderr.strip():
                console.print(f"[red]{result.stderr.strip()}[/red]\n")
            else:
                console.print(f"[dim]{result.stdout.strip()}[/dim]\n")
    except Exception as exc:
        console.print(f"[bold red]✗ Failed to execute update:[/] {exc}\n")


@cli.command()
@click.argument("task")
@click.option(
    "--effort",
    "-e",
    type=click.Choice(["minimal", "low", "medium", "high", "max"], case_sensitive=False),
    default="medium",
    help="Effort level: minimal/low/medium/high/max",
)
@click.option("--thinking/--no-thinking", default=False, help="Show thinking traces")
def smart(task: str, effort: str, thinking: bool) -> None:
    """Smart task execution with auto-delegation and streaming.

    Automatically analyzes the task, selects the best agent,
    and executes with streaming output and thinking traces.

    Examples:
        sago smart "Fix the authentication bug"
        sago smart "Write a REST API" --effort high
        sago smart "Review this code" --thinking
    """
    import os

    from sago.agents.registry import get_agent, list_agents
    from sago.engine.simple_executor import execute_agent_task

    logger.info("CLI 'smart' invoked: task_len=%d, effort=%s", len(task), effort)

    api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
    if not api_key:
        console.print("[red]Error: No API key found. Set OPENROUTER_API_KEY or OPENAI_API_KEY[/]")
        return

    # First: Ask the AI which agent to use
    agents = list_agents()
    agent_list_str = "\n".join(
        [
            f"- {a['name']}: {a.get('role', '')} | Skills: {', '.join(a.get('skills', [])[:5])}"
            for a in agents[:50]
        ]
    )

    agent_name = None
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

        router_response = client.chat.completions.create(
            model=_get_configured_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a task router. Given a task, select the EXACT BEST agent name from the list.\n"
                        "Reply with ONLY the exact agent name, nothing else. No quotes, no explanation.\n"
                        "If the task mentions Java, use java-engineer. If Python, use python-engineer.\n\n"
                        f"Available agents:\n{agent_list_str}"
                    ),
                },
                {"role": "user", "content": f"Task: {task}"},
            ],
            max_tokens=50,
        )

        agent_name = router_response.choices[0].message.content
        if not agent_name and getattr(router_response.choices[0].message, "reasoning", None):
            for a in agents:
                if a["name"] in router_response.choices[0].message.reasoning:
                    agent_name = a["name"]
                    break
    except Exception as e:
        log_exception(e, "Routing task to best agent via LLM")
        agent_name = None
    if agent_name:
        agent_name = agent_name.strip().strip('"').strip("'")
    else:
        agent_name = "python-engineer"

    # Validate agent exists, fallback to python-engineer
    agent_def = get_agent(agent_name)
    if not agent_def:
        # Try partial match
        for a in agents:
            if agent_name.lower() in a["name"].lower() or a["name"].lower() in agent_name.lower():
                agent_name = a["name"]
                agent_def = get_agent(agent_name)
                break

    if not agent_def:
        agent_name = "python-engineer"
        agent_def = get_agent(agent_name)

    agent_role = agent_def.role if agent_def else agent_name
    logger.info("Smart command: selected agent=%s", agent_name)

    console.print(
        Panel.fit(
            f"[bold green]Smart Execution[/]\n"
            f"[dim]Agent: {agent_name} ({agent_role}) | Effort: {effort}[/]\n"
            f"[dim]Task: {task[:60]}{'...' if len(task) > 60 else ''}[/]",
            border_style="green",
        )
    )

    from sago.engine.prompt_enhancer import enhance_prompt

    enhancement = enhance_prompt(
        task=task,
        agent_role=agent_name,
        cwd=os.getcwd(),
    )
    if enhancement.was_modified:
        console.print(
            Panel(
                f"[bold cyan]✨ Prompt Automatically Enhanced with Intent & Scope[/bold cyan]\n\n"
                f"[bold]Synthesized Goal:[/] [white]{enhancement.intent_summary}[/white]\n"
                f"[dim]Key Additions:[/] [green]{' • '.join(enhancement.improvements)}[/green]",
                title="[bold]Sago Prompt Enhancer[/]",
                border_style="cyan",
            )
        )

    with console.status(f"[bold green]Agent {agent_name} is working...[/]"):
        result = execute_agent_task(
            task=task,
            agent_role=agent_role,
            api_key=api_key,
            model=_get_configured_model(),
            max_tokens=2048,
            max_iterations=5,
        )

    # Display result
    if isinstance(result, dict):
        output = result.get("output", "No output")
        tool_calls = result.get("tool_calls", [])
        iterations = result.get("iterations", 0)

        if tool_calls:
            console.print("\n[bold]Tool calls:[/]")
            for tc in tool_calls:
                console.print(f"  [cyan]{tc.get('tool', '')}[/]: {tc.get('result', '')[:100]}")

        console.print(
            Panel(
                output,
                title=f"[bold]{agent_name}[/]",
                border_style="blue",
            )
        )
        console.print(f"[dim]Completed in {iterations} iterations[/]")
    else:
        console.print(Panel(str(result), title="[bold]Result[/]", border_style="blue"))


@cli.command()
@click.argument("task")
@click.option("--chain", "-c", required=True, help="Comma-separated agent chain")
@click.option("--effort", "-e", default="medium", help="Effort level")
def chain(task: str, chain: str, effort: str) -> None:
    """Execute task through an agent chain.

    Each agent processes the output of the previous one.

    Examples:
        sago chain "Build a web app" --chain system-architect,fullstack-dev,code-reviewer
        sago chain "Fix security issue" --chain security-engineer,debugger,code-reviewer
    """
    import os

    from sago.engine.production import ProductionEngine
    from sago.engine.prompt_enhancer import enhance_prompt

    engine = ProductionEngine()
    agent_list = [a.strip() for a in chain.split(",")]

    logger.info("CLI 'chain' invoked: task_len=%d, chain=%s", len(task), agent_list)

    enhancement = enhance_prompt(
        task=task,
        agent_role=agent_list[0] if agent_list else "chain",
        cwd=os.getcwd(),
    )
    if enhancement.was_modified:
        console.print(
            Panel(
                f"[bold cyan]✨ Pipeline Prompt Enhanced[/bold cyan]\n\n"
                f"[bold]Target Goal:[/] [white]{enhancement.intent_summary}[/white]\n"
                f"[dim]Key Additions:[/] [green]{' • '.join(enhancement.improvements)}[/green]",
                title="[bold]Sago Chain Prompt Enhancer[/]",
                border_style="cyan",
            )
        )

    console.print(
        Panel.fit(
            f"[bold green]Agent Chain[/]\n[dim]{' -> '.join(agent_list)}[/]",
            border_style="green",
        )
    )

    result = engine.run_chain(task, agent_list, effort=effort)

    if result.get("success"):
        console.print("\n[green]Chain completed successfully![/]")
    else:
        console.print(f"\n[red]Chain failed: {result.get('error', 'Unknown error')}[/]")

    engine.shutdown()


@cli.command()
def workflows() -> None:
    """List all workflows."""
    from sago.paths import get_sago_home
    from sago.workflow.engine import WorkflowEngine

    engine = WorkflowEngine(persist_dir=get_sago_home() / "workflows")
    workflows_list = engine.list_workflows()

    if not workflows_list:
        console.print("[dim]No workflows found. Use 'sago workflow-create' to create one.[/]")
        return

    console.print(Panel.fit("[bold]Workflows[/]", border_style="blue"))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan", max_width=12)
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Steps")
    table.add_column("Created")

    for w in workflows_list:
        table.add_row(
            w["id"][:12],
            w["name"][:40],
            w["status"],
            w.get("progress", "0/0"),
            str(w.get("created_at", ""))[:19],
        )

    console.print(table)


@cli.command()
@click.argument("name")
@click.option("--description", "-d", default="", help="Workflow description")
@click.option(
    "--trigger", "-t", default="manual", help="Trigger type: manual/schedule/event/ticket"
)
def workflow_create(name: str, description: str, trigger: str) -> None:
    """Create a new workflow interactively."""
    from sago.paths import get_sago_home
    from sago.workflow.engine import TriggerType, WorkflowEngine

    engine = WorkflowEngine(persist_dir=get_sago_home() / "workflows")

    trigger_map = {
        "manual": TriggerType.MANUAL,
        "schedule": TriggerType.SCHEDULE,
        "event": TriggerType.EVENT,
        "ticket": TriggerType.TICKET,
    }

    workflow = engine.create_workflow(
        name=name,
        description=description,
        trigger=trigger_map.get(trigger, TriggerType.MANUAL),
    )

    console.print(f"[green]Created workflow: {workflow.name}[/]")
    console.print(f"ID: {workflow.id}")
    console.print("\nAdd steps with:")
    console.print(f"  sago workflow-add-step {workflow.id}")


@cli.command()
@click.argument("workflow_id")
@click.option("--name", "-n", required=True, help="Step name")
@click.option("--type", "-t", "step_type", required=True, help="Step type: agent_call/tool_call")
@click.option("--agent", "-a", default=None, help="Agent name (for agent_call)")
@click.option("--tool", default=None, help="Tool name (for tool_call)")
@click.option("--task", required=True, help="Task description or command")
def workflow_add_step(
    workflow_id: str,
    name: str,
    step_type: str,
    agent: str | None,
    tool: str | None,
    task: str,
) -> None:
    """Add a step to a workflow."""
    from sago.paths import get_sago_home
    from sago.workflow.engine import WorkflowEngine

    engine = WorkflowEngine(persist_dir=get_sago_home() / "workflows")

    config = {"task": task}
    if agent:
        config["agent"] = agent
    if tool:
        config["tool"] = tool

    step = engine.add_step(
        workflow_id,
        name,
        step_type,
        config,
    )

    if step:
        console.print(f"[green]Added step: {name}[/]")
    else:
        console.print("[red]Failed to add step. Check workflow ID.[/]")


@cli.command()
@click.argument("workflow_id")
def workflow_run(workflow_id: str) -> None:
    """Execute a workflow."""
    from sago.paths import get_sago_home
    from sago.workflow.engine import WorkflowEngine

    engine = WorkflowEngine(persist_dir=get_sago_home() / "workflows")

    console.print(f"[green]Running workflow {workflow_id[:12]}...[/]\n")

    result = engine.execute_workflow(workflow_id)

    if "error" in result:
        console.print(f"[red]Workflow failed: {result['error']}[/]")
    else:
        console.print("[green]Workflow completed![/]")
        console.print(f"Status: {result.get('status')}")
        console.print(f"Progress: {result.get('progress')}")


@cli.command()
def usage() -> None:
    """Show token usage and cache statistics."""
    from sago.cache.intelligent import get_cache
    from sago.tracking.token_tracker import get_token_tracker

    tracker = get_token_tracker(persist=False)
    cache = get_cache(persist=False)

    console.print(Panel.fit("[bold]Usage Statistics[/]", border_style="blue"))

    # Token usage
    summary = tracker.get_summary()
    console.print("\n[bold]Token Usage:[/]")
    console.print(f"  Total Requests: {summary.total_requests}")
    console.print(f"  Total Tokens: {summary.total_tokens:,}")
    console.print(f"  Input Tokens: {summary.total_input_tokens:,}")
    console.print(f"  Output Tokens: {summary.total_output_tokens:,}")
    console.print(f"  Total Cost: ${summary.total_cost_usd:.6f}")
    console.print(f"  Avg Latency: {summary.avg_latency_ms:.1f}ms")

    if summary.by_provider:
        console.print("\n[bold]By Provider:[/]")
        for provider, stats in summary.by_provider.items():
            console.print(f"  {provider}: {stats['requests']} requests, {stats['tokens']:,} tokens")

    # Cache stats
    cache_stats = cache.get_stats_dict()
    console.print("\n[bold]Cache Statistics:[/]")
    console.print(f"  Hits: {cache_stats['hits']}")
    console.print(f"  Misses: {cache_stats['misses']}")
    console.print(f"  Hit Rate: {cache_stats['hit_rate_percent']}%")
    console.print(f"  Entries: {cache_stats['total_entries']}")
    console.print(f"  Size: {cache_stats['total_size_kb']} KB")
    console.print(f"  Evictions: {cache_stats['evictions']}")


@cli.command()
@click.argument("message", required=False, default=None)
def chat(message: str | None) -> None:
    """Interactive chat with Sago. Pass a message or run interactively."""

    from sago.llm.tui_providers import resolve_active_llm_config

    console.print(
        Panel.fit(
            "[bold green]Sago Chat[/]\n[dim]Type 'exit' to quit, 'help' for commands[/]",
            border_style="green",
        )
    )

    resolved = resolve_active_llm_config()
    api_key = resolved["api_key"]
    if not api_key:
        console.print(
            "[red]Error: No API key. Set OPENROUTER_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, or ANTHROPIC_API_KEY[/]"
        )
        return

    provider = resolved["provider"]
    model = resolved["model"]
    base_url = resolved["base_url"]
    console.print(f"[dim]Using {provider}/{model}[/]\n")

    logger.info("Chat session starting: provider=%s, model=%s", provider, model)

    # Build client and conversation history
    history: list[dict] = []
    system_prompt = _CHAT_SYSTEM_PROMPT

    def _send_to_llm(user_msg: str) -> str:
        """Send a message to the LLM and return the response text."""
        if provider == "google":
            return _chat_gemini(api_key, model, system_prompt, history, user_msg)
        else:
            return _chat_openai_compatible(
                provider, model, api_key, base_url, system_prompt, history, user_msg
            )

    # If a message was passed as argument, handle single-shot then enter interactive
    if message:
        # Check for special commands
        if message.strip().lower() in ("exit", "quit"):
            return
        if message.strip().lower() == "help":
            _print_chat_help()
            return

        console.print(f"[cyan]You:[/] {message}")
        with console.status("[dim]Thinking...[/]"):
            response = _send_to_llm(message)
        console.print(f"\n[green]Sago:[/] {response}\n")
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response})
        # Truncate history to prevent unbounded memory usage
        if len(history) > _CHAT_HISTORY_MAX_SIZE:
            history = history[-_CHAT_HISTORY_MAX_SIZE:]

    # Interactive loop
    from rich.prompt import Prompt as _Prompt

    while True:
        try:
            user_input = _Prompt.ask("[cyan]You[/]")
        except (KeyboardInterrupt, EOFError):
            logger.info("Chat session interrupted: messages=%d", len(history) // 2)
            console.print("\n[dim]Bye![/]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            logger.info("Chat session ending: messages=%d", len(history) // 2)
            console.print("[dim]Bye![/]")
            break
        if user_input.lower() == "help":
            _print_chat_help()
            continue

        with console.status("[dim]Thinking...[/]"):
            try:
                response = _send_to_llm(user_input)
            except Exception as e:
                console.print(f"\n[red]Error: {_sanitize_error_message(str(e))}[/]\n")
                continue

        console.print(f"\n[green]Sago:[/] {response}\n")
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        # Truncate history to prevent unbounded memory usage
        if len(history) > _CHAT_HISTORY_MAX_SIZE:
            history = history[-_CHAT_HISTORY_MAX_SIZE:]


def _print_chat_help() -> None:
    console.print(
        Panel(
            "[bold]Chat Commands[/]\n"
            "- Type naturally to chat\n"
            "- [cyan]help[/] — Show this help\n"
            "- [cyan]exit[/] or [cyan]quit[/] — Exit chat\n",
            border_style="dim",
        )
    )


def _chat_gemini(
    api_key: str,
    model: str,
    system_prompt: str,
    history: list[dict],
    user_msg: str,
) -> str:
    """Single-turn call to Gemini using native SDK with rate limit retry."""
    import time

    from google import genai as google_genai
    from google.genai import types as google_types

    logger.debug(
        "Gemini call: model=%s, history_len=%d, prompt_len=%d", model, len(history), len(user_msg)
    )

    client = google_genai.Client(api_key=api_key)

    contents = []
    for msg in history:
        role = msg["role"]
        c = msg.get("content", "")
        if role == "user":
            contents.append(google_types.Content(role="user", parts=[google_types.Part(text=c)]))
        elif role == "assistant":
            contents.append(google_types.Content(role="model", parts=[google_types.Part(text=c)]))
    contents.append(google_types.Content(role="user", parts=[google_types.Part(text=user_msg)]))

    config = google_types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=2048,
        temperature=0.7,
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            resp_text = response.text or ""
            logger.debug(
                "Gemini response: attempt=%d, response_len=%d, model=%s",
                attempt,
                len(resp_text),
                model,
            )
            return resp_text
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "429" in err_str or "rate" in err_str or "quota" in err_str
            if is_rate_limit and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "Gemini rate limited on attempt %d/%d, retrying in %ds",
                    attempt + 1,
                    max_retries,
                    wait,
                )
                console.print(f"[yellow]Rate limited. Retrying in {wait}s...[/yellow]")
                time.sleep(wait)
                continue
            logger.error("Gemini call failed after %d attempts: %s", attempt + 1, type(e).__name__)
            raise


def _chat_openai_compatible(
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None,
    system_prompt: str,
    history: list[dict],
    user_msg: str,
) -> str:
    """Single-turn call to OpenAI-compatible API with rate limit retry."""
    import time

    from openai import OpenAI, RateLimitError

    logger.debug(
        "OpenAI-compatible call: provider=%s, model=%s, history_len=%d, prompt_len=%d",
        provider,
        model,
        len(history),
        len(user_msg),
    )

    if provider == "openrouter":
        base_url = base_url or "https://openrouter.ai/api/v1"
    elif provider == "openai":
        base_url = base_url or "https://api.openai.com/v1"

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_msg})

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
            )
            resp_text = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            logger.debug(
                "OpenAI-compatible response: attempt=%d, response_len=%d, model=%s, "
                "prompt_tokens=%s, completion_tokens=%s",
                attempt,
                len(resp_text),
                model,
                getattr(usage, "prompt_tokens", None) if usage else None,
                getattr(usage, "completion_tokens", None) if usage else None,
            )
            return resp_text
        except RateLimitError:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "OpenAI-compatible rate limited on attempt %d/%d, retrying in %ds",
                    attempt + 1,
                    max_retries,
                    wait,
                )
                console.print(f"[yellow]Rate limited. Retrying in {wait}s...[/yellow]")
                time.sleep(wait)
                continue
            logger.error("OpenAI-compatible rate limit exceeded after %d attempts", attempt + 1)
            raise
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "429" in err_str or "rate" in err_str or "quota" in err_str
            if is_rate_limit and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "OpenAI-compatible rate limited (via exception) on attempt %d/%d, "
                    "retrying in %ds",
                    attempt + 1,
                    max_retries,
                    wait,
                )
                console.print(f"[yellow]Rate limited. Retrying in {wait}s...[/yellow]")
                time.sleep(wait)
                continue
            logger.error(
                "OpenAI-compatible call failed after %d attempts: %s", attempt + 1, type(e).__name__
            )
            raise


@cli.command()
@click.option("--resume", "-r", default=None, help="Resume a previous session by ID (prefix)")
def tui(resume: str | None) -> None:
    """Launch the interactive Textual TUI.

    Features:
        - Slash commands (/help, /agents, /sessions, etc.)
        - @ file/folder attachments
        - Syntax highlighting
        - Streaming responses
        - Session management
        - Autocomplete suggestions

    Examples:
        sago tui
        sago tui --resume a62c0922
        sago tui -r a62c0922
    """
    from sago.tui.app import SagoApp

    app = SagoApp()
    if resume:
        app._pending_resume = resume
    app.run()
    if hasattr(app, "print_exit_summary"):
        app.print_exit_summary()


@cli.command("attach")
@click.argument("target", required=False)
def attach_cmd(target: str | None) -> None:
    """Attach to a running detached session or background task log.

    Examples:
        sago attach                  # List and choose active sessions / tasks
        sago attach a62c0922         # Reattach to TUI session
        sago attach task_1700000000  # Stream detached task log
    """
    import os
    import time

    from sago.paths import get_sago_home
    from sago.tui.app import SagoApp

    sago_home = get_sago_home()
    logs_dir = sago_home / "logs"

    # If no target, list available sessions and background tasks
    if not target:
        from sago.database import Session, init_db

        init_db()
        s = Session()
        sessions = s.list_all(limit=10)
        s.close()

        table = Table(title="[bold green]Available Detached Sessions & Tasks[/]")
        table.add_column("Type", style="cyan")
        table.add_column("ID", style="yellow")
        table.add_column("Title / Info", style="white")
        table.add_column("Status", style="green")

        if sessions:
            for ses in sessions:
                table.add_row(
                    "Session",
                    ses["id"][:8],
                    ses.get("title", "Session")[:35],
                    ses.get("status", "open"),
                )

        if logs_dir.exists():
            log_files = sorted(logs_dir.glob("*.log"), key=os.path.getmtime, reverse=True)[:5]
            for lf in log_files:
                table.add_row("Task Log", lf.stem, f"Log: {lf.name}", "background")

        console.print(table)
        console.print("\n[dim]To attach, run:[/] [bold cyan]sago attach <id>[/bold cyan]\n")
        return

    # Check if target is a background task log
    log_candidates = [
        logs_dir / f"{target}.log",
        logs_dir / f"task_{target}.log",
    ]
    matched_log = next((p for p in log_candidates if p.exists()), None)

    if matched_log:
        console.print(f"[bold green]Streaming detached task log:[/] {matched_log}")
        console.print("[dim]Press Ctrl+C to detach without killing the background job...[/]\n")
        try:
            with open(matched_log) as f:
                # Read existing content
                content = f.read()
                if content:
                    console.print(content, end="")
                # Tail new content
                while True:
                    line = f.readline()
                    if line:
                        console.print(line, end="")
                    else:
                        time.sleep(0.5)
        except KeyboardInterrupt:
            console.print("\n\n[yellow]✓ Detached from log. Task continues in background.[/]")
            return

    # Otherwise, attach to TUI session
    app = SagoApp()
    app._pending_resume = target
    app.run()
    if hasattr(app, "print_exit_summary"):
        app.print_exit_summary()


@cli.command()
@click.option("--host", "-h", default="0.0.0.0", help="Bind host (0.0.0.0 for all interfaces)")
@click.option("--port", "-p", default=7654, help="Port number")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground")
def serve(host: str, port: int, foreground: bool) -> None:
    """Start Sago daemon server.

    Runs Sago as a background service for remote task execution
    and peer communication.

    Examples:
        sago serve                          # Default 0.0.0.0:7654
        sago serve --host 127.0.0.1         # Localhost only
        sago serve --port 9000              # Custom port
        sago serve --foreground             # Run in foreground
    """
    from sago.server.daemon import get_daemon

    daemon = get_daemon(host=host, port=port)

    if daemon.is_running():
        console.print(f"[yellow]Daemon already running (PID: {daemon.get_pid()})[/]")
        return

    console.print(f"[green]Starting Sago daemon on {host}:{port}...[/]")
    daemon.start(foreground=foreground)


@cli.command()
def stop() -> None:
    """Stop Sago daemon server."""
    from sago.server.daemon import get_daemon

    daemon = get_daemon()

    if not daemon.is_running():
        console.print("[yellow]Daemon not running[/]")
        return

    console.print("[green]Stopping daemon...[/]")
    daemon.stop()
    console.print("[green]Daemon stopped[/]")


@cli.command()
def daemon_status() -> None:
    """Show Sago daemon status."""
    from sago.server.daemon import get_daemon

    daemon = get_daemon()

    if daemon.is_running():
        console.print(f"[green]{daemon.status()}[/]")
    else:
        console.print("[yellow]Daemon not running[/]")


@cli.command()
@click.argument("task")
@click.option("--agent", "-a", default=None, help="Specific agent")
@click.option("--host", "-h", default="127.0.0.1", help="Daemon host")
@click.option("--port", "-p", default=7654, help="Daemon port")
def remote(task: str, agent: str | None, host: str, port: int) -> None:
    """Execute task on daemon server.

    Examples:
        sago remote "fix the bug"
        sago remote "review code" --agent code-reviewer
        sago remote "task" --host 192.168.1.100
    """
    from sago.server.daemon import get_client

    client = get_client(host=host, port=port)

    if not client.ping():
        console.print("[red]Daemon not running. Start with: sago serve[/]")
        return

    console.print(f"[green]Executing on daemon: {task[:60]}...[/]")
    result = client.execute(task, agent)

    if result.get("status") == "completed":
        console.print(
            Panel(
                result.get("result", ""),
                title="[bold]Result[/]",
                border_style="blue",
            )
        )
    else:
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/]")


@cli.command()
@click.argument("task")
@click.option("--agent", "-a", default="Sago Orchestrator", help="Agent name")
@click.option("--iterations", "-i", default=8, help="Max iterations")
@click.option("--stream", "-s", is_flag=True, help="Stream updates")
def workflow(task: str, agent: str, iterations: int, stream: bool) -> None:
    """Execute complex task using LangGraph stateful workflow.

    Uses stateful graph execution with planning, tool calling,
    and adaptive iteration for complex multi-step tasks.

    Examples:
        sago workflow "Build a REST API with auth and tests"
        sago workflow "Refactor this codebase" --iterations 12
        sago workflow "Debug the memory leak" --stream
    """
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
    if not api_key:
        console.print("[red]Error: No API key. Set OPENROUTER_API_KEY[/]")
        return

    from sago.workflow.langgraph_engine import SagoWorkflowEngine

    engine = SagoWorkflowEngine(api_key=api_key, model=_get_configured_model())
    logger.info(
        "CLI 'workflow' invoked: task_len=%d, agent=%s, iterations=%d, stream=%s",
        len(task),
        agent,
        iterations,
        stream,
    )

    console.print(
        Panel.fit(
            f"[bold green]LangGraph Workflow[/]\n"
            f"[dim]Task: {task[:60]}{'...' if len(task) > 60 else ''}[/]\n"
            f"[dim]Agent: {agent} | Max Iterations: {iterations}[/]",
            border_style="green",
        )
    )

    def on_update(event: str, data: Any) -> None:
        if event == "thinking":
            console.print(f"  [dim]{data}[/]")

    if stream:
        result = engine.run_streaming(task, agent, iterations, on_update=on_update)
    else:
        with console.status("[bold green]Executing workflow...[/]"):
            result = engine.run(task, agent, iterations)

    if result.tool_calls:
        console.print("\n[bold]Tool calls:[/]")
        for tc in result.tool_calls:
            status = "[green]✓[/]" if tc.get("success", True) else "[red]✗[/]"
            console.print(f"  {status} [cyan]{tc['tool']}[/]: {tc.get('result', '')[:100]}")

    if result.files_created:
        console.print(f"\n[green]Files created:[/] {', '.join(result.files_created)}")

    console.print(
        Panel(
            result.output,
            title="[bold]Result[/]",
            border_style="blue",
        )
    )

    console.print(
        f"[dim]Iterations: {result.iterations} | Tokens: {result.tokens['input']} in / {result.tokens['output']} out | Time: {result.elapsed:.1f}s[/]"
    )


@cli.command("map")
@click.option("--dir", "-d", default=".", help="Directory to map")
@click.option("--query", "-q", default=None, help="Filter by file path or symbol name")
@click.option("--max-files", "-m", default=200, help="Max files to include")
def repo_map_cmd(dir: str, query: str | None, max_files: int) -> None:
    """Generate a compact AST symbol outline map across the repository."""
    from sago.memory.symbol_graph import SymbolGraph

    root_path = Path(dir).resolve()
    console.print(f"[bold green]Generating Symbol Repo Map for:[/] {root_path}")
    graph = SymbolGraph(root_dir=root_path)
    rmap = graph.generate_repo_map(max_files=max_files, filter_query=query)
    console.print(Panel(rmap, title="[bold]Symbol Map[/]", border_style="cyan"))


@cli.command("project-graph")
@click.option("--dir", "-d", default=".", help="Directory to graph")
@click.option(
    "--view",
    "-v",
    type=click.Choice(["dashboard", "arch", "process", "er", "tree", "mermaid", "json", "llm"]),
    default="dashboard",
    help="Graph output view: dashboard (curated), arch (box diagram), process (pipeline), er (data models), tree, mermaid, json, llm",
)
@click.option("--focus", default=None, help="Focus filter (e.g. database, auth, file name)")
@click.option("--max-files", "-m", default=400, help="Max files to include")
def project_graph_cmd(dir: str, view: str, focus: str | None, max_files: int) -> None:
    """Generate deep architecture diagram, process execution map, and data models graph."""
    from sago.memory.project_graph import ProjectGraph

    root_path = Path(dir).resolve()
    console.print(f"[bold green]Building Project & Architecture Graph for:[/] {root_path}")
    pg = ProjectGraph(root_dir=root_path)
    pg.build_graph(max_files=max_files)

    if view == "arch":
        console.print(
            Panel(
                pg.to_architecture_diagram(),
                title="[bold]System Architecture Map[/]",
                border_style="cyan",
            )
        )
    elif view == "process":
        console.print(
            Panel(
                pg.to_process_map(),
                title="[bold]Execution & Process Pipeline[/]",
                border_style="yellow",
            )
        )
    elif view == "er":
        console.print(
            Panel(
                pg.to_er_diagram(),
                title="[bold]Entity Relationship & Data Models[/]",
                border_style="magenta",
            )
        )
    elif view == "tree":
        console.print(
            Panel(
                pg.to_ascii_tree(), title="[bold]Project & Data Graph Tree[/]", border_style="blue"
            )
        )
    elif view == "mermaid":
        console.print(pg.to_mermaid(focus_filter=focus))
    elif view == "json":
        import json

        console.print(json.dumps(pg.to_dict(), indent=2))
    elif view == "llm":
        console.print(
            Panel(
                pg.to_llm_context(), title="[bold]Project Topology Context[/]", border_style="green"
            )
        )
    else:
        # Curated Dashboard
        console.print(pg.to_curated_dashboard(focus_filter=focus))


@cli.command("graph")
@click.option("--dir", "-d", default=".", help="Directory to graph")
@click.option(
    "--view",
    "-v",
    type=click.Choice(["dashboard", "arch", "process", "er", "tree", "mermaid", "json", "llm"]),
    default="dashboard",
    help="Graph output view",
)
@click.option("--focus", default=None, help="Focus filter")
@click.option("--max-files", "-m", default=400, help="Max files to include")
def graph_alias_cmd(dir: str, view: str, focus: str | None, max_files: int) -> None:
    """Alias for project-graph."""
    project_graph_cmd.callback(dir=dir, view=view, focus=focus, max_files=max_files)


@cli.command("verify")
@click.option("--dir", "-d", default=".", help="Project directory to verify")
def verify_cmd(dir: str) -> None:
    """Run automated multi-language linters, type checks, and test suites."""
    from sago.engine.verifier import ProjectVerifier

    root_path = Path(dir).resolve()
    console.print(f"[bold green]Running Self-Healing Verification Suite on:[/] {root_path}")
    verifier = ProjectVerifier(root_dir=root_path)
    report = verifier.verify_project()

    if report.passed:
        console.print(
            Panel("[bold green]✓ ALL CHECKS PASSED[/]\n" + report.summary, border_style="green")
        )
    else:
        console.print(
            Panel(
                report.to_prompt_feedback(),
                title="[bold red]Verification Failed[/]",
                border_style="red",
            )
        )


@cli.command("skills")
@click.option("--filter", "-f", default="", help="Filter skills by name or keyword")
def skills_cmd(filter: str) -> None:
    """List all available built-in and custom workspace skills."""
    from sago.skills.loader import SkillLoader
    from sago.skills.registry import list_skills

    builtin = list_skills()
    custom = SkillLoader.discover_skills()

    console.print(f"[bold]Available Skills ({len(builtin) + len(custom)} total):[/bold]\n")

    if custom:
        console.print("[bold cyan]Workspace & Custom Skills:[/bold cyan]")
        for name, sk in sorted(custom.items()):
            if (
                filter
                and filter.lower() not in name.lower()
                and filter.lower() not in sk.description.lower()
            ):
                continue
            tools_str = f" [dim](tools: {', '.join(sk.tools)})[/dim]" if sk.tools else ""
            console.print(f"  • [bold yellow]{name:<18}[/bold yellow] {sk.description}{tools_str}")
        console.print("")

    console.print("[bold cyan]Built-in Capabilities:[/bold cyan]")
    for sk in builtin:
        name = sk.get("name", "")
        desc = sk.get("description", "")
        tools = sk.get("tools", [])
        if filter and filter.lower() not in name.lower() and filter.lower() not in desc.lower():
            continue
        tools_str = f" [dim](tools: {', '.join(tools[:4])})[/dim]" if tools else ""
        console.print(f"  • [bold green]{name:<18}[/bold green] {desc}{tools_str}")


@cli.command("plugins")
def plugins_cmd() -> None:
    """List installed SAGO third-party plugins and lifecycle extensions."""
    from sago.plugins.base import get_plugin_manager

    pm = get_plugin_manager()
    plugins = pm.list_plugins()

    if not plugins:
        console.print(
            "[dim]No external plugins loaded. Place Python plugins in .sago/plugins/ or ~/.sago/plugins/[/dim]"
        )
        return

    console.print(f"[bold]Installed Plugins ({len(plugins)}):[/bold]\n")
    for p in plugins:
        status = "[green]ENABLED[/green]" if p.enabled else "[dim]DISABLED[/dim]"
        console.print(
            f"  • [bold cyan]{p.name}[/bold cyan] v{p.version} ({p.author}) - {status}\n    {p.description}"
        )


@cli.command("checkpoint")
@click.argument(
    "action", default="list", type=click.Choice(["create", "list", "restore", "prune", "clean"])
)
@click.argument("target", required=False)
def checkpoint_cmd(action: str, target: str | None) -> None:
    """Manage atomic snapshots and rollbacks for large refactorings (create, list, restore, prune)."""
    from sago.engine.checkpoint import CheckpointManager

    mgr = CheckpointManager()
    if action == "create":
        desc = target or "Manual CLI checkpoint"
        meta = mgr.create_checkpoint(description=desc)
        console.print(
            f"[bold green]✓ Checkpoint created:[/bold green] [bold cyan]{meta.checkpoint_id}[/bold cyan] ({len(meta.file_paths)} files) — {desc}"
        )
    elif action == "list":
        checkpoints = mgr.list_checkpoints()
        if not checkpoints:
            console.print("[dim]No checkpoints saved in .sago/checkpoints/[/dim]")
            return
        console.print(f"[bold]Available Workspace Snapshots ({len(checkpoints)}):[/bold]\n")
        for c in checkpoints:
            import datetime

            dt_str = datetime.datetime.fromtimestamp(c.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            console.print(
                f"  • [bold cyan]{c.checkpoint_id}[/bold cyan] [dim]({dt_str})[/dim]\n    {c.description} [dim]({len(c.file_paths)} files)[/dim]"
            )
    elif action == "restore":
        if not target:
            console.print(
                "[bold red]Error:[/bold red] Please specify checkpoint ID to restore. (e.g. `sago checkpoint restore chk_1234`)"
            )
            return
        res = mgr.restore_checkpoint(target)
        if res.get("success"):
            console.print(
                f"[bold green]✓ Successfully restored {res['restored_count']} files from snapshot {target}![/bold green]"
            )
        else:
            console.print(f"[bold red]Failed to restore:[/bold red] {res.get('error')}")
    elif action in ("prune", "clean"):
        keep = 3
        if target and target.isdigit():
            keep = int(target)
        deleted = mgr.prune_checkpoints(keep_latest=keep)
        console.print(
            f"[bold green]✓ Checkpoints pruned:[/] Removed {len(deleted)} old snapshots (retained newest {keep})."
        )


@cli.command("clean")
@click.option(
    "--all",
    "clean_all",
    is_flag=True,
    default=False,
    help="Clean all caches, backups, checkpoints, logs, and empty DB sessions (Default)",
)
@click.option("--cache", is_flag=True, help="Purge hybrid index & AST graph caches")
@click.option("--backups", is_flag=True, help="Purge stale file edit backups (~/.sago/backups)")
@click.option(
    "--checkpoints", is_flag=True, help="Purge older workspace snapshots (.sago/checkpoints)"
)
@click.option(
    "--plans", is_flag=True, help="Purge completed/stale task plans (~/.sago/task_plans.json)"
)
@click.option("--db", is_flag=True, help="Clean empty/stale sessions and vacuum SQLite database")
@click.option("--logs", is_flag=True, help="Clean / truncate old and oversized log files")
@click.option("--days", type=float, default=None, help="Purge items older than N days")
@click.option(
    "--keep-checkpoints",
    type=int,
    default=3,
    help="Number of newest checkpoints to retain (default: 3)",
)
@click.option(
    "--keep-backups",
    type=int,
    default=1,
    help="Number of newest session backups to retain (default: 1)",
)
@click.option(
    "--keep-sessions",
    type=int,
    default=10,
    help="Number of newest DB sessions to retain (default: 10)",
)
@click.option("--dry-run", is_flag=True, help="Show what would be cleaned without deleting")
@click.option("--force", "-f", is_flag=True, help="Perform cleanup without confirmation prompts")
def clean_cmd(
    clean_all: bool,
    cache: bool,
    backups: bool,
    checkpoints: bool,
    plans: bool,
    db: bool,
    logs: bool,
    days: float | None,
    keep_checkpoints: int,
    keep_backups: int,
    keep_sessions: int,
    dry_run: bool,
    force: bool,
) -> None:
    """Safely clean stale caches, backups, checkpoints, task plans, logs, and DB sessions."""
    from sago.cleanup import run_cleanup

    # Default to cleaning everything if no specific target is selected or --all is used
    if not (cache or backups or checkpoints or plans or db or logs):
        clean_all = True

    c_cache = clean_all or cache
    c_backup = clean_all or backups
    c_chkpt = clean_all or checkpoints
    c_plans = clean_all or plans
    c_db = clean_all or db
    c_logs = clean_all or logs

    if dry_run:
        console.print(
            "[bold yellow]Running in dry-run mode (no files will be deleted)...[/bold yellow]\n"
        )

    results = run_cleanup(
        clean_cache=c_cache,
        clean_backup=c_backup,
        clean_chkpt=c_chkpt,
        clean_plan=c_plans,
        clean_db=c_db,
        clean_log=c_logs,
        keep_checkpoints=keep_checkpoints,
        keep_recent_backups=keep_backups,
        keep_recent_sessions=keep_sessions,
        max_age_days=days,
        dry_run=dry_run,
    )

    table = Table(
        title="Sago Garbage Collection & Cleanup Summary",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Target Category", style="bold white", min_width=30)
    table.add_column("Scanned", justify="right")
    table.add_column("Purged / Cleaned", justify="right", style="green")
    table.add_column("Space Reclaimed", justify="right", style="bold green")
    table.add_column("Details", style="dim")

    total_scanned = 0
    total_deleted = 0
    total_reclaimed = 0

    for r in results:
        total_scanned += r.items_scanned
        total_deleted += r.items_deleted
        total_reclaimed += r.bytes_reclaimed
        detail_msg = (
            "; ".join(r.details)
            if r.details
            else ("OK" if not r.error else f"[red]{r.error}[/red]")
        )
        table.add_row(
            r.category,
            str(r.items_scanned),
            str(r.items_deleted),
            r.human_bytes,
            detail_msg,
        )

    console.print(table)

    if total_reclaimed < 1024 * 1024:
        rec_str = f"{total_reclaimed / 1024:.1f} KB"
    elif total_reclaimed < 1024 * 1024 * 1024:
        rec_str = f"{total_reclaimed / (1024 * 1024):.2f} MB"
    else:
        rec_str = f"{total_reclaimed / (1024 * 1024 * 1024):.2f} GB"

    if dry_run:
        console.print(
            f"\n[bold yellow]Dry-run complete:[/] Found {total_deleted} items ({rec_str}) eligible for cleanup."
        )
    else:
        console.print(
            f"\n[bold green]✓ Cleanup complete:[/] Purged {total_deleted} items and reclaimed [bold cyan]{rec_str}[/bold cyan] disk space."
        )


# ---------------------------------------------------------------------------
# sago logs — Interactive log viewer & manager
# ---------------------------------------------------------------------------


@cli.group(invoke_without_command=True)
@click.pass_context
@click.option("--errors", "errors_only", is_flag=True, help="Show only ERROR+ log lines")
@click.option("--session", "-s", default=None, help="Filter by session ID")
@click.option("--module", "-m", default=None, help="Filter by module name (partial match)")
@click.option(
    "--level",
    "-l",
    default=None,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    help="Filter by exact log level",
)
@click.option("--search", "-q", default=None, help="Full-text search in log messages")
@click.option(
    "--since", default=None, help="Show logs since (e.g. '1h', '30m', '7d', '2w', or ISO date)"
)
@click.option("--limit", "-n", default=100, help="Max lines to display (default: 100)")
@click.option("--tail", "-f", is_flag=True, help="Follow logs in real-time (tail -f)")
def logs(
    ctx: click.Context,
    errors_only: bool,
    session: str | None,
    module: str | None,
    level: str | None,
    search: str | None,
    since: str | None,
    limit: int,
    tail: bool,
) -> None:
    """View, filter, and manage Sago log files.

    Examples:
        sago logs                    # Show last 100 log lines
        sago logs --errors           # Show only errors
        sago logs --session abc123   # Filter by session
        sago logs --since 1h         # Logs from last hour
        sago logs --module sago.config
        sago logs --search "timeout" # Full-text search
        sago logs --tail             # Follow in real-time
        sago logs stats              # Show statistics dashboard
        sago logs level              # Show current log level
        sago logs level --set debug  # Change log level
        sago logs sessions           # List session IDs
        sago logs clean              # Smart cleanup wizard
        sago logs export output.txt  # Export filtered logs
    """
    from sago.log_manager import LogManager
    from sago.log_viewer import display_logs, follow_logs

    if ctx.invoked_subcommand is not None:
        return

    manager = LogManager()

    if tail:
        follow_logs(manager)
        return

    display_logs(
        manager,
        level=level,
        session_id=session,
        module=module,
        search=search,
        since=since,
        limit=limit,
        errors_only=errors_only,
    )


@logs.command("stats")
@click.option(
    "--quick", "-q", is_flag=True, help="Quick mode — file metadata only (no line parsing)"
)
def logs_stats(quick: bool) -> None:
    """Show log statistics dashboard with charts and top errors."""
    from sago.log_manager import LogManager
    from sago.log_viewer import display_stats

    manager = LogManager()
    display_stats(manager, quick=quick)


@logs.command("sessions")
def logs_sessions() -> None:
    """List all session IDs found in log files."""
    from sago.log_manager import LogManager
    from sago.log_viewer import display_sessions

    manager = LogManager()
    display_sessions(manager)


@logs.command("level")
@click.option(
    "--set",
    "set_level",
    default=None,
    type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
    help="Set the log level (saved to settings.json)",
)
def logs_level(set_level: str | None) -> None:
    """View or change the current log level.

    Without --set, shows the current level.
    With --set, saves the new level to ~/.sago/settings.json and applies immediately.

    Examples:
        sago logs level              # Show current level
        sago logs level --set debug  # Enable debug logging
        sago logs level --set error  # Only log errors
    """
    from rich.text import Text

    from sago.logging_config import get_log_level, set_log_level

    if set_level:
        set_log_level(set_level)
        level_name = set_level.upper()
        level_style = {
            "DEBUG": "dim",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
        }.get(level_name, "white")
        console.print(
            Text("Log level set to ", style="bold green")
            + Text(level_name, style=level_style)
            + Text(" (saved to ~/.sago/settings.json)", style="dim")
        )
    else:
        current = get_log_level().upper()
        level_style = {
            "DEBUG": "dim",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
        }.get(current, "white")
        console.print(Text("Current log level: ", style="bold") + Text(current, style=level_style))
        console.print(
            Text("  Change with: ", style="dim")
            + Text("sago logs level --set <level>", style="cyan")
        )


@logs.command("clean")
@click.option("--max-size", default=100.0, help="Max total log directory size in MB (default: 100)")
@click.option("--max-age", default=None, type=float, help="Delete logs older than N days")
@click.option(
    "--max-file",
    default=5.0,
    help="Max individual log file size in MB before truncation (default: 5)",
)
@click.option(
    "--keep",
    default=0,
    type=int,
    help="Number of rotated log files to keep (default: 0 = delete all)",
)
@click.option("--dry-run", is_flag=True, help="Show what would be cleaned without deleting")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def logs_clean(
    max_size: float, max_age: float | None, max_file: float, keep: int, dry_run: bool, force: bool
) -> None:
    """Smart log cleanup — deletes rotated backups, truncates large files, enforces budget.

    By default, deletes all rotated log files and truncates active logs over 5MB.
    Use --keep N to retain N rotated backups.
    Use --max-file N to set the truncation threshold in MB.
    Use --max-age N to also delete files older than N days.
    """
    from sago.log_manager import LogManager

    manager = LogManager()
    stats = manager.get_stats(quick=True)

    console.print(f"[dim]Current logs: {stats.total_files} files, {stats.size_human}[/dim]")

    if not force and not dry_run:
        if not click.confirm("Proceed with cleanup?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    deleted, reclaimed = manager.prune(
        max_total_mb=max_size,
        max_age_days=max_age,
        keep_rotated=keep,
        max_file_mb=max_file,
        dry_run=dry_run,
    )

    if reclaimed < 1024 * 1024:
        rec_str = f"{reclaimed / 1024:.1f} KB"
    else:
        rec_str = f"{reclaimed / (1024 * 1024):.2f} MB"

    prefix = "[yellow]DRY RUN:[/yellow] " if dry_run else ""
    console.print(
        f"{prefix}[bold green]✓ Log cleanup:[/] Deleted {deleted} files, reclaimed [bold cyan]{rec_str}[/bold cyan]"
    )


@logs.command("export")
@click.argument("output_path")
@click.option("--errors", "errors_only", is_flag=True, help="Export only ERROR+ lines")
@click.option("--session", "-s", default=None, help="Filter by session ID")
@click.option("--module", "-m", default=None, help="Filter by module name")
@click.option("--since", default=None, help="Export logs since (e.g. '7d', '2025-01-15')")
def logs_export(
    output_path: str, errors_only: bool, session: str | None, module: str | None, since: str | None
) -> None:
    """Export filtered logs to a file."""
    from sago.log_manager import LogManager
    from sago.log_viewer import export_logs

    manager = LogManager()
    export_logs(
        manager,
        output_path,
        session_id=session,
        module=module,
        since=since,
        errors_only=errors_only,
    )


# ---------------------------------------------------------------------------
# sago search
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("query")
@click.option("--limit", "-l", default=6, help="Maximum search results to display")
@click.option("--json-out", is_flag=True, help="Output in raw JSON format")
def search(query: str, limit: int, json_out: bool) -> None:
    """Natural language semantic & BM25 hybrid codebase search.

    Example:
        sago search "Where are database models defined?"
        sago search "JWT authentication handler" --limit 10
    """
    import json

    from sago.memory.hybrid_indexer import get_hybrid_code_indexer

    indexer = get_hybrid_code_indexer()
    results = indexer.search(query=query, limit=limit)

    if json_out:
        console.print(json.dumps([r.to_dict() for r in results], indent=2))
        return

    if not results:
        console.print(f"[yellow]No matching code snippets found for: '{query}'[/yellow]")
        return

    console.print(f"[bold cyan]Hybrid Code Search Results ({len(results)} matches):[/bold cyan]\n")
    for i, r in enumerate(results, 1):
        chunk = r.chunk
        title = f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
        if chunk.name:
            title += f" ({chunk.chunk_type} {chunk.name})"
        console.print(
            Panel(
                f"```{chunk.language}\n{chunk.content[:500]}\n```",
                title=f"#{i} {title}",
                subtitle=f"Score: {r.combined_score:.2f} | BM25: {r.bm25_score:.2f} | Dense Vec: {r.semantic_score:.2f}",
                border_style="cyan",
            )
        )


@cli.command()
@click.option(
    "--export",
    "-e",
    type=click.Choice(["otel", "prometheus", "json", "md"], case_sensitive=False),
    default="otel",
    help="Export telemetry format",
)
@click.option("--output", "-o", default=None, help="Output destination file")
def telemetry(export: str, output: str | None) -> None:
    """Export developer execution telemetry and OpenTelemetry/Prometheus metrics.

    Example:
        sago telemetry --export otel --output traces.json
        sago telemetry --export prometheus --output metrics.prom
    """
    import json

    from sago.tracking.dev_tracer import get_dev_tracer
    from sago.tracking.otel_exporter import OTelExporter, PrometheusExporter

    tracer = get_dev_tracer()
    events = tracer.get_events()

    if export == "otel":
        payload = OTelExporter().export_traces(events)
        out_file = Path(output or "sago_otel_traces.json").resolve()
        out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print(
            f"[bold green]✓ OpenTelemetry traces exported to:[/bold green] [cyan]{out_file}[/cyan]"
        )
    elif export == "prometheus":
        text = PrometheusExporter().export_metrics(events)
        out_file = Path(output or "sago_metrics.prom").resolve()
        out_file.write_text(text, encoding="utf-8")
        console.print(
            f"[bold green]✓ Prometheus metrics exported to:[/bold green] [cyan]{out_file}[/cyan]"
        )
    elif export in ("html", "report"):
        from sago.utils.report_generator import generate_html_report

        session_data = {
            "task": "SAGO Session Export",
            "model": "Orchestrated Swarm",
            "elapsed": 1.0,
            "success": True,
            "tool_calls": events,
            "output": f"Exported {len(events)} trace events.",
        }
        html = generate_html_report(session_data, events)
        out_file = Path(output or "sago_report.html").resolve()
        out_file.write_text(html, encoding="utf-8")
        console.print(
            f"[bold green]✓ Interactive HTML report exported to:[/bold green] [cyan]{out_file}[/cyan]"
        )
    else:
        success, res = tracer.export_traces(file_path=output, format=export)
        if success:
            console.print(f"[bold green]✓ Traces exported to:[/bold green] [cyan]{res}[/cyan]")
        else:
            console.print(f"[bold red]Export failed:[/bold red] {res}")


@cli.group("hook")
def hook_group() -> None:
    """Manage SAGO git hooks for pre-commit verification and AST indexing."""
    pass


@hook_group.command("install")
@click.option("--repo", default=".", help="Path to git repository")
def hook_install(repo: str) -> None:
    """Install SAGO pre-commit hook in git repository."""
    repo_path = Path(repo).resolve()
    hooks_dir = repo_path / ".git" / "hooks"
    if not hooks_dir.exists():
        console.print(f"[bold red]✗ Not a git repository:[/bold red] {repo_path}")
        return

    hook_script = hooks_dir / "pre-commit"
    hook_content = """#!/usr/bin/env bash
# SAGO Auto Pre-Commit Hook
sago hook run
"""
    hook_script.write_text(hook_content, encoding="utf-8")
    hook_script.chmod(0o755)
    console.print(
        f"[bold green]✓ Installed SAGO pre-commit hook into:[/bold green] [cyan]{hook_script}[/cyan]"
    )


@hook_group.command("run")
@click.option("--dir", "target_dir", default=".", help="Directory to verify")
def hook_run(target_dir: str) -> None:
    """Run SAGO pre-commit checks (syntax, types, symbol indexing)."""
    import sys

    from sago.engine.verifier import get_project_verifier

    console.print("[cyan]🔍 SAGO Pre-Commit Verification starting...[/cyan]")
    verifier = get_project_verifier(root_dir=target_dir)
    report = verifier.verify_project()

    all_passed = report.passed
    console.print(f"  Status: {'[green]✓ PASS[/green]' if all_passed else '[red]✗ FAIL[/red]'}")
    for issue in report.issues:
        console.print(
            f"    [red]✗ {issue.rule}[/red] {issue.file_path}:{issue.line} - {issue.message}"
        )

    if all_passed:
        console.print("[bold green]✓ All pre-commit checks passed![/bold green]")
    else:
        console.print("[bold red]✗ Pre-commit checks failed.[/bold red]")
        sys.exit(1)


@cli.group("pr")
def pr_group() -> None:
    """Manage Git branches and automated Pull Request creation."""
    pass


@pr_group.command("create")
@click.argument("title")
@click.option("--body", "-b", default="", help="PR description body")
@click.option("--branch", default="", help="Target branch name")
@click.option("--target", default="main", help="Base target branch to merge into")
@click.option("--draft", is_flag=True, help="Create as a draft PR")
@click.option("--dir", "target_dir", default=".", help="Directory to run git PR in")
def pr_create(
    title: str, body: str, branch: str, target: str, draft: bool, target_dir: str
) -> None:
    """Create a verified feature branch and Pull Request.

    Example:
        sago pr create "Add JWT authentication system"
    """
    from sago.tools.vcs.pr_workflow import create_pr_workflow

    console.print(f"[cyan]🚀 Creating Pull Request: [bold]{title}[/bold]...[/cyan]")
    res = create_pr_workflow(
        title=title,
        body=body,
        branch=branch,
        target_branch=target,
        draft=draft,
        cwd=target_dir,
    )
    if res["success"]:
        console.print(f"[bold green]✓ {res['message']}[/bold green]")
        if res.get("pr_markdown"):
            from rich.markdown import Markdown

            console.print("\n", Markdown(res["pr_markdown"]))
    else:
        console.print(f"[bold red]✗ PR creation failed:[/bold red] {res.get('error')}")


@cli.command("parse")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Save parsed Markdown to file")
def parse_cmd(file_path: str, output: str | None) -> None:
    """Parse documents, PDFs, spreadsheets, and web files to Markdown via MarkItDown.

    Example:
        sago parse documentation.pdf
        sago parse financial_report.xlsx -o report.md
    """
    from rich.markdown import Markdown

    from sago.utils.markitdown_converter import convert_file_to_markdown, is_markitdown_available

    path = Path(file_path)
    success, content = convert_file_to_markdown(path)
    if not success:
        avail_msg = (
            ""
            if is_markitdown_available()
            else "\nTip: Run `pip install markitdown` for full Microsoft Office & PDF parsing support."
        )
        console.print(f"[bold red]Parse error:[/] {content}{avail_msg}")
        return

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        console.print(
            f"[bold green]✓ Converted {path.name} to Markdown:[/] [cyan]{out_path}[/cyan] ({len(content):,} chars)"
        )
    else:
        console.print(Markdown(content))


def main() -> None:
    """Main entry point."""
    from sago.paths import ensure_sago_dirs

    ensure_sago_dirs()
    logger.info("Sago v%s starting", __version__)
    cli()
    logger.debug("Sago CLI exited")


if __name__ == "__main__":
    main()
