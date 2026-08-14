"""Sago - Multi-Agent Orchestration System.

Main entry point for the Sago application.
"""

from __future__ import annotations

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

console = Console()


def _get_configured_model() -> str:
    """Get the configured model from config, fallback to openrouter/free."""
    try:
        from sago.config.loader import get_config

        config = get_config()
        return config.llm.model or "openrouter/free"
    except Exception:
        return "openrouter/free"


@click.group()
@click.version_option(version="0.1.1", prog_name="sago")
def cli() -> None:
    """Sago - Sophisticated Multi-Agent Orchestration System.

    A CrewAI-based system with infinite tools, cross-platform support,
    and a master orchestrator named Sago.
    """
    pass


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

    init()

    agent_name = agent or "python-engineer"

    if detach:
        sago_home = get_sago_home()
        logs_dir = sago_home / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        task_id = f"task_{int(time.time())}_{os.getpid()}"
        log_file = logs_dir / f"{task_id}.log"

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
      sago agents --all               # List all 339 agents
    """
    from sago.agents.registry import get_agents_by_category, list_categories

    categories = list_categories()
    total_agents = sum(len(v) for v in categories.values())

    # Case 1: No query and not --all -> Show Category Overview
    if not query and not show_all:
        console.print(
            Panel.fit(
                f"[bold]Sago Specialist Agent Categories[/]  [dim]({total_agents} agents across {len(categories)} domains)[/]",
                border_style="blue",
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
    from sago.agents.registry import get_agent, get_handoff_targets

    agent = get_agent(agent_name)
    if agent is None:
        console.print(f"[red]Agent not found: {agent_name}[/]")
        console.print("Use 'sago agents' to see available agents.")
        return

    console.print(
        Panel.fit(
            f"[bold]{agent.codename}[/]\n[dim]{agent.role}[/]",
            border_style="blue",
        )
    )

    console.print(f"\n[bold]Description:[/]\n{agent.description}")
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
    """Show Sago system status."""
    from sago.config.loader import get_config
    from sago.database import Session
    from sago.paths import get_db_path, get_sago_home

    config = get_config()

    console.print(
        Panel.fit(
            "[bold]Sago System Status[/]",
            border_style="blue",
        )
    )

    console.print("\n[bold]Version:[/] 0.1.1")
    console.print(f"[bold]Home:[/] {get_sago_home()}")
    console.print(f"[bold]Database:[/] {get_db_path()}")

    # Check if DB exists
    if get_db_path().exists():
        session = Session()
        sessions = session.list_all(limit=10)
        console.print(f"[bold]Sessions:[/] {len(sessions)} stored")
    else:
        console.print("[bold]Database:[/] Not initialized")

    console.print(f"\n[bold]Default LLM:[/] {config.llm_providers.default}")
    console.print(f"[bold]Orchestrator:[/] {config.orchestrator.name}")

    # Enabled agents
    from sago.agents.registry import list_agents

    agents_list = list_agents()
    console.print(f"[bold]Agents:[/] {len(agents_list)} available")


@cli.command()
def tools() -> None:
    """List all available tools."""
    from sago.config.loader import get_config

    get_config()

    console.print(
        Panel.fit(
            "[bold]Sago Tools Registry[/]",
            border_style="blue",
        )
    )

    tool_categories = {
        "File Operations": [
            "read_file",
            "write_file",
            "edit_file",
            "glob_files",
            "grep_content",
            "file_operations",
        ],
        "Shell": ["execute_shell", "background_process"],
        "SSH": ["ssh_connect", "ssh_command", "ssh_transfer"],
        "Session": ["session_manager", "clipboard"],
        "Coding": [
            "code_analyzer",
            "linter",
            "formatter",
            "test_runner",
            "debugger",
            "log_analyzer",
        ],
        "Network": ["http_client", "dns_lookup", "port_scan", "network_config"],
        "Admin": ["software_install", "permission_manager", "sudo_executor", "prompt_generator"],
        "System": ["os_detector", "process_manager", "env_manager"],
    }

    for category, tool_list in tool_categories.items():
        console.print(f"\n[bold]{category}:[/]")
        for tool in tool_list:
            console.print(f"  - {tool}")


@cli.command()
def sessions() -> None:
    """List recent sessions."""
    from sago.database import Session

    session = Session()
    sessions_list = session.list_all(limit=20)

    if not sessions_list:
        console.print("[dim]No sessions found.[/]")
        return

    console.print(Panel.fit("[bold]Recent Sessions[/]", border_style="blue"))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan", max_width=12)
    table.add_column("Title")
    table.add_column("Created")
    table.add_column("Status")

    for s in sessions_list:
        table.add_row(
            s["id"][:12],
            (s.get("title") or "Untitled")[:50],
            s["created_at"][:19],
            s.get("status", "active"),
        )

    console.print(table)


@cli.command()
@click.argument("session_id")
def history(session_id: str) -> None:
    """Show message history for a session."""
    from sago.database import MessageStore

    msg_store = MessageStore(session_id)
    messages = msg_store.get_history(limit=50)

    if not messages:
        console.print(f"[dim]No messages found for session {session_id}[/]")
        return

    console.print(
        Panel.fit(
            f"[bold]Session History: {session_id[:12]}[/]",
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


@cli.command()
def setup() -> None:
    """Interactive setup wizard for Sago."""
    from rich.prompt import Prompt

    console.print(
        Panel.fit(
            "[bold blue]Sago Setup Wizard[/]\n[dim]Configure your multi-agent system[/]",
            border_style="blue",
        )
    )

    # Select LLM provider
    console.print("\n[bold]Select LLM Provider:[/]")
    console.print("  1. Gemini (Google)")
    console.print("  2. OpenAI (GPT)")
    console.print("  3. Claude (Anthropic)")
    console.print("  4. OpenRouter")
    console.print("  5. Ollama (Local)")

    choice = Prompt.ask("Choice", default="1")
    providers = {"1": "gemini", "2": "openai", "3": "claude", "4": "openrouter", "5": "ollama"}
    provider = providers.get(choice, "gemini")

    # Get API key
    api_key_env = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }.get(provider)

    if api_key_env:
        import os

        key = Prompt.ask(f"Enter {api_key_env} (or press Enter to skip)")
        if key:
            os.environ[api_key_env] = key
            console.print(f"[green]Set {api_key_env}[/]")

    # Initialize database
    from sago.database import init

    init()
    console.print("[green]Database initialized.[/]")

    console.print("\n[green]Setup complete![/]")
    console.print("Run [bold]sago run 'your task'[/] to get started.")
    console.print("Run [bold]sago agents[/] to see available agents.")


@cli.command()
@click.argument("task")
@click.option("--effort", "-e", default="medium", help="Effort level: minimal/low/medium/high/max")
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

    from openai import OpenAI

    from sago.agents.registry import get_agent, list_agents
    from sago.engine.simple_executor import execute_agent_task

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
    # Some models put response in reasoning field
    if not agent_name and router_response.choices[0].message.reasoning:
        # Extract agent name from reasoning
        for a in agents:
            if a["name"] in router_response.choices[0].message.reasoning:
                agent_name = a["name"]
                break
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

    console.print(
        Panel.fit(
            f"[bold green]Smart Execution[/]\n"
            f"[dim]Agent: {agent_name} ({agent_role}) | Effort: {effort}[/]\n"
            f"[dim]Task: {task[:60]}{'...' if len(task) > 60 else ''}[/]",
            border_style="green",
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
    from sago.engine.production import ProductionEngine

    engine = ProductionEngine()
    agent_list = [a.strip() for a in chain.split(",")]

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
@click.argument("message")
def chat(message: str) -> None:
    """Interactive chat with Sago."""
    import os

    from sago.engine.simple_executor import execute_agent_task

    console.print(
        Panel.fit(
            "[bold green]Sago Chat[/]\n[dim]Type 'exit' to quit, 'help' for commands[/]",
            border_style="green",
        )
    )

    api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
    if not api_key:
        console.print("[red]Error: No API key. Set OPENROUTER_API_KEY[/]")
        return

    session_id = str(__import__("uuid").uuid4())[:12]
    console.print(f"[dim]Session: {session_id}[/]\n")

    result = execute_agent_task(
        task=message,
        agent_role="Sago Orchestrator",
        api_key=api_key,
        model=_get_configured_model(),
        max_tokens=2048,
        max_iterations=3,
    )

    output = result.get("output", "No response")
    console.print(f"\n[green]Sago:[/] {output}")


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
    type=click.Choice(["dashboard", "arch", "process", "tree", "mermaid", "json", "llm"]),
    default="dashboard",
    help="Graph output view: dashboard (curated), arch (box diagram), process (pipeline), tree, mermaid, json, llm",
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
    type=click.Choice(["dashboard", "arch", "process", "tree", "mermaid", "json", "llm"]),
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
@click.argument("action", default="list", type=click.Choice(["create", "list", "restore"]))
@click.argument("target", required=False)
def checkpoint_cmd(action: str, target: str | None) -> None:
    """Manage atomic snapshots and rollbacks for large refactorings (create, list, restore)."""
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


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
