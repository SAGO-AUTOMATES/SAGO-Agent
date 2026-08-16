"""Smart Suggestions Engine for SAGO TUI — Fuzzy search, Git-aware files, dynamic subcommands."""

from __future__ import annotations

import difflib
import os
import subprocess
import time
from pathlib import Path
from typing import Any

# In-memory cache for git modified files
_GIT_CACHE: dict[str, tuple[float, set[str]]] = {}


def fuzzy_score(query: str, target: str) -> float:
    """Compute fuzzy match score between query and target.

    Higher score means better match. Returns 0.0 if not matched.
    """
    if not query:
        return 1.0

    q = query.lower()
    t = target.lower()

    # 1. Exact match
    if q == t:
        return 100.0

    # 2. Prefix match
    if t.startswith(q):
        return 80.0 + (len(q) / max(len(t), 1)) * 10.0

    # 3. Substring match
    if q in t:
        idx = t.find(q)
        pos_bonus = max(0.0, 10.0 - idx)
        return 60.0 + pos_bonus

    # 4. Subsequence match (e.g. 'pythn' matches 'python-engineer')
    t_idx = 0
    matched_chars = 0
    for char in q:
        found_idx = t.find(char, t_idx)
        if found_idx == -1:
            break
        matched_chars += 1
        t_idx = found_idx + 1

    if matched_chars == len(q):
        return 40.0 + (len(q) / max(len(t), 1)) * 10.0

    # 5. Approximate ratio match
    ratio = difflib.SequenceMatcher(None, q, t).ratio()
    if ratio >= 0.60:
        return 20.0 + ratio * 20.0

    return 0.0


def get_git_modified_files(cwd: Path) -> set[str]:
    """Fetch set of currently modified, staged, or untracked file relative paths."""
    key = str(cwd.resolve())
    now = time.time()
    if key in _GIT_CACHE:
        ts, cached = _GIT_CACHE[key]
        if now - ts < 3.0:
            return cached

    modified: set[str] = set()
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line = line.strip()
                if len(line) >= 4:
                    rel_path = line[3:].strip().strip('"')
                    modified.add(rel_path)
                    # Also add filename
                    modified.add(Path(rel_path).name)
    except Exception:
        pass

    _GIT_CACHE[key] = (now, modified)
    return modified


def rank_agents_fuzzy(agents: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Rank agents using fuzzy scoring across name, category, and description."""
    if not query:
        featured = [
            "sago-orchestrator",
            "python-engineer",
            "frontend-engineer",
            "backend-engineer",
            "fullstack-developer",
            "debugger",
            "architect",
            "devops-engineer",
            "reviewer",
            "qa-engineer",
            "security-engineer",
            "database-engineer",
        ]
        featured_set = set(featured)
        top = [a for a in agents if a["name"] in featured_set]
        top.sort(key=lambda a: featured.index(a["name"]) if a["name"] in featured else 999)
        rest = [a for a in agents if a["name"] not in featured_set]
        return top + rest

    scored: list[tuple[float, dict[str, Any]]] = []
    for a in agents:
        name = a.get("name", "")
        cat = a.get("category", "")
        desc = a.get("description", "")

        s_name = fuzzy_score(query, name) * 3.0
        s_cat = fuzzy_score(query, cat) * 1.5
        s_desc = fuzzy_score(query, desc) * 1.0

        best_score = max(s_name, s_cat, s_desc)
        if best_score > 0:
            scored.append((best_score, a))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored]


# In-memory cache for workspace file trees: root_path -> (timestamp, list of (rel_path, is_dir, size_bytes))
_WORKSPACE_FILES_CACHE: dict[str, tuple[float, list[tuple[str, bool, int]]]] = {}


def get_workspace_files(root: Path, max_files: int = 3000) -> list[tuple[str, bool, int]]:
    """Scan and cache workspace files recursively, skipping build and cache directories."""
    key = str(root.resolve())
    now = time.time()
    if key in _WORKSPACE_FILES_CACHE:
        ts, cached = _WORKSPACE_FILES_CACHE[key]
        if now - ts < 4.0:
            return cached

    ignore_dirs = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".ruff_cache",
        ".mypy_cache",
        ".pytest_cache",
        ".next",
        "dist",
        "build",
        "target",
        ".cache",
        "vendor",
        ".sago",
    }
    results: list[tuple[str, bool, int]] = []

    try:
        for cur_root, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            rel_root = Path(cur_root).relative_to(root)

            for d in sorted(dirs):
                rel_d = str(rel_root / d) if str(rel_root) != "." else d
                results.append((rel_d + "/", True, 0))
                if len(results) >= max_files:
                    break

            for f in sorted(files):
                if f.startswith(".") or f.endswith(
                    (".pyc", ".min.js", ".map", ".lock", ".png", ".jpg", ".ico")
                ):
                    continue
                rel_f = str(rel_root / f) if str(rel_root) != "." else f
                full_p = Path(cur_root) / f
                try:
                    size = full_p.stat().st_size
                except Exception:
                    size = 0
                results.append((rel_f, False, size))
                if len(results) >= max_files:
                    break

            if len(results) >= max_files:
                break
    except Exception:
        pass

    _WORKSPACE_FILES_CACHE[key] = (now, results)
    return results


def rank_files_smart(
    prefix: str,
    base_dir: Path | None = None,
    home: bool = False,
) -> tuple[list[str], list[str]]:
    """Return smart recursive fuzzy ranked file suggestions prioritizing Git modified files."""
    if home:
        root = Path.home()
        search_q = prefix
        if "/" in prefix:
            last_slash = prefix.rfind("/")
            dir_part = prefix[:last_slash]
            search_q = prefix[last_slash + 1 :]
            root = Path.home() / dir_part

        if not root.exists() or not root.is_dir():
            return [], []

        scored_entries: list[tuple[float, str, str]] = []
        try:
            for p in root.iterdir():
                name = p.name
                if name.startswith(".") and not search_q.startswith("."):
                    continue
                score = fuzzy_score(search_q, name)
                if search_q and score == 0:
                    continue
                is_dir = p.is_dir()
                rel_name = name + "/" if is_dir else name
                tag = "[blue][dir][/blue]  " if is_dir else "[cyan][file][/cyan] "
                display = f"{tag}[bold]{rel_name}[/bold]"
                val = f"~{rel_name}"
                scored_entries.append((score, display, val))
        except Exception:
            return [], []
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored_entries[:15]], [x[2] for x in scored_entries[:15]]

    # Workspace recursive search
    root = base_dir or Path.cwd()
    if not root.exists() or not root.is_dir():
        return [], []

    git_modified = get_git_modified_files(root)
    workspace_entries = get_workspace_files(root)
    search_q = prefix.strip()

    scored_entries = []
    for rel_path, is_dir, size_bytes in workspace_entries:
        basename = rel_path.rstrip("/").split("/")[-1]

        # Score across filename and full relative path
        score_base = fuzzy_score(search_q, basename)
        score_full = fuzzy_score(search_q, rel_path) * 0.9
        score = max(score_base, score_full)

        if search_q and score == 0:
            continue

        is_mod = (
            rel_path in git_modified
            or basename in git_modified
            or rel_path.rstrip("/") in git_modified
        )

        # Mod bonus & directory rank
        if is_mod:
            score += 60.0
        if is_dir:
            score += 5.0

        # Human-readable size
        if not is_dir and size_bytes > 0:
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            size_str = ""

        if is_mod:
            display_tag = "[yellow][mod][/yellow] "
        elif is_dir:
            display_tag = "[blue][dir][/blue]  "
        else:
            display_tag = "[cyan][file][/cyan] "

        size_display = f" [dim]({size_str})[/dim]" if size_str else ""
        display = f"{display_tag}[bold]{rel_path:<28}[/bold]{size_display}"
        val = f"#{rel_path}"
        scored_entries.append((score, is_mod, display, val))

    scored_entries.sort(key=lambda x: (x[0], x[1]), reverse=True)
    items = [x[2] for x in scored_entries[:18]]
    values = [x[3] for x in scored_entries[:18]]
    return items, values


def get_subcommand_completions(raw: str) -> tuple[list[str], list[str]] | None:
    """Dynamic parameter completions for common slash commands."""
    r = raw.strip()
    parts = r.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    # /plan subcommands
    if cmd == "/plan":
        items = []
        values = []
        if not arg or arg == "<task>":
            items.append(
                "[bold cyan]<task>    [/bold cyan] [dim]Create implementation plan for review before making changes[/dim]"
            )
            values.append("/plan <task>")
            items.append(
                "[bold cyan]status    [/bold cyan] [dim]View current active plan progress and task items[/dim]"
            )
            values.append("/plan status")
        else:
            items.append(
                f"[bold cyan]plan      [/bold cyan] [dim]Generate implementation plan for '{arg}'[/dim]"
            )
            values.append(f"/plan {arg}")
        return items, values

    # /graph subcommands
    if cmd in ("/graph", "/project_graph"):
        graph_opts = {
            "summary": "Executive codebase summary & hub dependencies (Default)",
            "arch": "System architecture layered box diagram",
            "process": "Execution lifecycle & processing pipeline",
            "models": "Entity-Relationship (ER) schemas & data models",
            "flow": "Component dependency and data flow diagram",
            "mermaid": "Export diagram as Mermaid flowchart",
            "json": "Export raw dependency graph in JSON",
        }
        matches = (
            [k for k in graph_opts if fuzzy_score(arg, k) > 0] if arg else list(graph_opts.keys())
        )
        items = [
            f"[bold magenta]{k:<10}[/bold magenta] [dim]{graph_opts[k]}[/dim]" for k in matches
        ]
        values = [f"/graph {k}" for k in matches]
        return items, values

    # /map subcommands
    if cmd == "/map":
        map_opts = {
            "": "Generate full repository symbol outline",
            "models": "Filter symbols related to models & schemas",
            "tools": "Filter symbols related to tools & agents",
            "routes": "Filter API routes & endpoints",
        }
        items = []
        values = []
        if not arg:
            items.append(
                "[bold cyan]all       [/bold cyan] [dim]Generate full repository AST symbol outline[/dim]"
            )
            values.append("/map")
            for k, desc in list(map_opts.items())[1:]:
                items.append(f"[bold cyan]{k:<10}[/bold cyan] [dim]{desc}[/dim]")
                values.append(f"/map {k}")
        else:
            items.append(
                f"[bold cyan]{arg:<10}[/bold cyan] [dim]Filter repo symbol map by '{arg}'[/dim]"
            )
            values.append(f"/map {arg}")
        return items, values

    # /perms subcommands
    if cmd in ("/perms", "/permissions", "/allow", "/block"):
        perms_opts = {
            "list": "List all allowed and blocked tools",
            "allow": "Allow a tool to run without prompt (/perms allow <tool>)",
            "block": "Block a tool completely (/perms block <tool>)",
            "reset": "Reset all tool permissions to default",
        }
        matches = (
            [k for k in perms_opts if fuzzy_score(arg, k) > 0] if arg else list(perms_opts.keys())
        )
        items = [f"[bold yellow]{k:<10}[/bold yellow] [dim]{perms_opts[k]}[/dim]" for k in matches]
        values = [f"/perms {k}" for k in matches]
        return items, values

    # /todo subcommands
    if cmd in ("/todo", "/todos", "/done"):
        todo_opts = {
            "list": "Show all current task items",
            "done": "Mark a task item complete (/todo done <id>)",
            "clear": "Clear finished items",
        }
        matches = (
            [k for k in todo_opts if fuzzy_score(arg, k) > 0] if arg else list(todo_opts.keys())
        )
        items = [f"[bold green]{k:<10}[/bold green] [dim]{todo_opts[k]}[/dim]" for k in matches]
        values = [f"/todo {k}" for k in matches]
        return items, values

    # /buttons subcommands
    if cmd in ("/buttons", "/bar"):
        btn_opts = {
            "toggle": "Toggle action button bar visibility",
            "on": "Always show action button bar",
            "off": "Hide action button bar for maximal chat space",
        }
        matches = [k for k in btn_opts if fuzzy_score(arg, k) > 0] if arg else list(btn_opts.keys())
        items = [f"[bold blue]{k:<10}[/bold blue] [dim]{btn_opts[k]}[/dim]" for k in matches]
        values = [f"/buttons {k}" for k in matches]
        return items, values

    # /tasks subcommands
    if cmd in ("/tasks", "/cancel"):
        task_opts = {
            "list": "View all active and finished background jobs",
            "cancel": "Cancel a running task (/tasks cancel <id>)",
            "cancel all": "Cancel all running background tasks",
        }
        matches = (
            [k for k in task_opts if fuzzy_score(arg, k) > 0] if arg else list(task_opts.keys())
        )
        items = [f"[bold red]{k:<12}[/bold red] [dim]{task_opts[k]}[/dim]" for k in matches]
        values = [f"/tasks {k}" for k in matches]
        return items, values

    # /mcp subcommands
    if cmd == "/mcp":
        mcp_opts = {
            "list": "List configured MCP servers and bridged tools",
            "reload": "Reload MCP configuration files and reconnect",
            "test": "Test connection to a specific MCP server (/mcp test <name>)",
        }
        matches = [k for k in mcp_opts if fuzzy_score(arg, k) > 0] if arg else list(mcp_opts.keys())
        items = [f"[bold cyan]{k:<12}[/bold cyan] [dim]{mcp_opts[k]}[/dim]" for k in matches]
        values = [f"/mcp {k}" for k in matches]
        return items, values

    # /skill and /skills subcommands
    if cmd in ("/skill", "/skills"):
        skill_opts = {
            "list": "List all built-in and workspace custom skills",
            "reload": "Reload custom skills from .sago/skills/ and ~/.sago/skills/",
        }
        matches = (
            [k for k in skill_opts if fuzzy_score(arg, k) > 0] if arg else list(skill_opts.keys())
        )
        items = [f"[bold green]{k:<12}[/bold green] [dim]{skill_opts[k]}[/dim]" for k in matches]
        values = [f"/skill {k}" for k in matches]
        return items, values

    # /agent subcommands & list
    if cmd in ("/agent", "/agents"):
        if arg == "list" or not arg:
            items = [
                "[bold magenta]list      [/bold magenta] [dim]List all 300+ specialist agents by domain[/dim]"
            ]
            values = ["/agent list"]
            try:
                from sago.agents.registry import list_agents

                agents = list_agents()
                for a in rank_agents_fuzzy(agents, arg if arg != "list" else "")[:12]:
                    items.append(
                        f"[bold magenta]@{a['name']:<22}[/bold magenta] [dim]{a.get('description', '')[:38]}[/dim]"
                    )
                    values.append(f"/agent {a['name']}")
            except Exception:
                pass
            return items, values

    # /git subcommands
    if cmd == "/git":
        git_cmds = {
            "status": "Show working tree status",
            "diff": "Show changes between commits or work tree",
            "log": "Show commit logs",
            "commit": "Record changes to repository",
            "branch": "List or manage branches",
            "checkout": "Switch branches or restore files",
            "push": "Update remote refs",
            "pull": "Fetch and integrate with remote",
        }
        matches = [k for k in git_cmds if fuzzy_score(arg, k) > 0] if arg else list(git_cmds.keys())
        items = [f"[bold cyan]{k:<12}[/bold cyan] [dim]{git_cmds[k]}[/dim]" for k in matches]
        values = [f"/git {k}" for k in matches]
        return items, values

    # /pr subcommands
    if cmd == "/pr":
        pr_opts = {
            "create": "Automate feature branch, verification, and Pull Request creation",
            "--draft": "Create pull request as draft",
            "--branch": "Specify target feature branch name",
            "--target": "Specify target base branch (default: main)",
        }
        matches = [k for k in pr_opts if fuzzy_score(arg, k) > 0] if arg else list(pr_opts.keys())
        items = [f"[bold cyan]{k:<12}[/bold cyan] [dim]{pr_opts[k]}[/dim]" for k in matches]
        values = [f"/pr {k}" for k in matches]
        return items, values

    # /sessions subcommands and existing session IDs
    if cmd in ("/sessions", "/session"):
        session_opts = {
            "list": "List all active and stored sessions",
            "save": "Save current session state",
            "load": "Load session from file (/session load <file>)",
            "reset": "Reset current conversation context",
            "export": "Export session transcript to Markdown",
        }
        items = []
        values = []

        # 1. Fetch available sessions from DB so users never have to type raw IDs
        try:
            from sago.database import Session, init_db

            init_db()
            s = Session()
            sessions = s.list_all(limit=10)
            s.close()
            for ses in sessions:
                sid = ses.get("id", "")
                title = ses.get("title") or "Untitled Session"
                t_short = sid[:8]
                score = (
                    fuzzy_score(arg, t_short)
                    or fuzzy_score(arg, title)
                    or (1.0 if not arg else 0.0)
                )
                if score > 0:
                    items.append(
                        f"[bold cyan]{t_short:<10}[/bold cyan] [white]{title[:32]}[/white]"
                    )
                    values.append(f"/session {t_short}")
        except Exception:
            pass

        # 2. Add subcommand options
        for k, desc in session_opts.items():
            if not arg or fuzzy_score(arg, k) > 0:
                items.append(f"[bold blue]{k:<10}[/bold blue] [dim]{desc}[/dim]")
                values.append(f"/session {k}")

        return items, values

    # /checkpoint subcommands and existing checkpoint IDs
    if cmd == "/checkpoint":
        items = []
        values = []

        # 1. Base actions
        cp_opts = {
            "create": "Create an atomic point-in-time workspace snapshot",
            "list": "List available workspace checkpoints",
            "prune": "Prune old checkpoints retaining latest 3",
        }
        for k, desc in cp_opts.items():
            if not arg or fuzzy_score(arg, k) > 0:
                items.append(f"[bold blue]{k:<10}[/bold blue] [dim]{desc}[/dim]")
                values.append(f"/checkpoint {k}")

        # 2. Add existing checkpoints for instant 1-click restore
        try:
            from sago.engine.checkpoint import get_checkpoint_manager

            mgr = get_checkpoint_manager()
            cps = mgr.list_checkpoints(limit=10)
            for cp in cps:
                cid = cp.checkpoint_id
                desc = cp.description or "Manual Snapshot"
                score = fuzzy_score(arg, cid) or fuzzy_score(arg, desc) or (1.0 if not arg else 0.0)
                if score > 0:
                    items.append(
                        f"[bold cyan]restore {cid}[/bold cyan] [dim]{desc[:26]} ({len(cp.file_paths)} files)[/dim]"
                    )
                    values.append(f"/checkpoint restore {cid}")
        except Exception:
            pass

        return items, values

    # /chain workflows and agent sequence auto-completions
    if cmd == "/chain":
        chain_workflows = {
            "architect -> python-engineer -> test-engineer": "Plan architecture, implement in Python, run tests",
            "frontend-engineer,backend-engineer -> test-engineer": "Full-stack feature build with unit & e2e tests",
            "database-engineer -> backend-engineer": "Database schema design, migration & API routing",
            "security-engineer,penetration-engineer": "Security audit, AST check & vulnerability scan",
            "devops-engineer,docker-engineer -> sre-engineer": "Containerization, Dockerfile & CI/CD deployment",
        }
        items = []
        values = []

        for seq, desc in chain_workflows.items():
            if not arg or fuzzy_score(arg, seq) > 0 or fuzzy_score(arg, desc) > 0:
                items.append(f"[bold cyan]{seq:<50}[/bold cyan] [dim]{desc}[/dim]")
                values.append(f"/chain {seq} ")

        # If user is typing an agent name in the chain, provide agent matches
        last_token = arg.split("->")[-1].split(",")[-1].strip() if arg else ""
        if last_token:
            try:
                from sago.agents.registry import list_agents

                agents = list_agents()
            except Exception:
                agents = []
            for a in rank_agents_fuzzy(agents, last_token)[:6]:
                aname = a["name"]
                prefix_part = arg[: arg.rfind(last_token)]
                items.append(
                    f"[bold magenta]+{aname:<24}[/bold magenta] [dim]{a.get('description', '')[:35]}[/dim]"
                )
                values.append(f"/chain {prefix_part}{aname} -> ")

        return items, values

    # /delegate specialist agent selection
    if cmd == "/delegate":
        items = []
        values = []
        try:
            from sago.agents.registry import list_agents

            agents = list_agents()
        except Exception:
            agents = []
        ranked = rank_agents_fuzzy(agents, arg)
        for a in ranked[:12]:
            aname = a["name"]
            desc = a.get("description", "")
            items.append(f"[bold magenta]@{aname:<22}[/bold magenta] [dim]{desc[:40]}[/dim]")
            values.append(f"/delegate {aname} ")
        return items, values

    # /model completions with descriptions
    if cmd == "/model":
        models_catalog = {
            "openrouter/free": "OpenRouter Free tier (Auto-routed fast free models)",
            "anthropic/claude-3.7-sonnet": "Claude 3.7 Sonnet (Hybrid thinking & deep reasoning)",
            "openai/gpt-4o": "OpenAI GPT-4o (High-speed multimodal coding)",
            "openai/o3-mini": "OpenAI o3-mini (Advanced reasoning model)",
            "google/gemini-2.5-pro": "Google Gemini 2.5 Pro (Large context window & code intelligence)",
            "google/gemini-2.5-flash": "Google Gemini 2.5 Flash (Ultra-fast low-latency code execution)",
            "ollama/deepseek-r1:latest": "Local Ollama DeepSeek R1 (100% private local reasoning)",
            "ollama/llama3.3:latest": "Local Ollama Llama 3.3 (Local open weights model)",
        }
        items = []
        values = []
        for m, desc in models_catalog.items():
            if not arg or fuzzy_score(arg, m) > 0 or fuzzy_score(arg, desc) > 0:
                items.append(f"[bold cyan]{m:<32}[/bold cyan] [dim]{desc}[/dim]")
                values.append(f"/model {m}")
        return items, values

    # /provider completions
    if cmd == "/provider":
        providers_catalog = {
            "openrouter": "OpenRouter multi-model gateway (Default)",
            "openai": "Direct OpenAI API (GPT-4o, o3-mini)",
            "gemini": "Google Gemini API (Gemini 2.5 Pro / Flash)",
            "anthropic": "Anthropic Claude API (Claude 3.7 Sonnet)",
            "ollama": "Local Ollama instance (localhost:11434)",
        }
        items = []
        values = []
        for p, desc in providers_catalog.items():
            if not arg or fuzzy_score(arg, p) > 0 or fuzzy_score(arg, desc) > 0:
                items.append(f"[bold blue]{p:<14}[/bold blue] [dim]{desc}[/dim]")
                values.append(f"/provider {p}")
        return items, values

    return None
