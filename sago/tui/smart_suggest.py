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


def rank_files_smart(
    prefix: str,
    base_dir: Path | None = None,
    home: bool = False,
) -> tuple[list[str], list[str]]:
    """Return smart ranked file suggestions prioritizing Git modified files."""
    if home:
        root = Path.home()
        search_q = prefix
    elif "/" in prefix:
        last_slash = prefix.rfind("/")
        dir_part = prefix[:last_slash]
        search_q = prefix[last_slash + 1 :]
        root = (
            (base_dir or Path.cwd()) / dir_part if not os.path.isabs(dir_part) else Path(dir_part)
        )
    else:
        root = base_dir or Path.cwd()
        search_q = prefix

    if not root.exists() or not root.is_dir():
        return [], []

    git_modified = get_git_modified_files(root)

    scored_entries: list[tuple[float, bool, str, str]] = []
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
            is_mod = name in git_modified or str(p) in git_modified

            # Git modified bonus
            if is_mod:
                score += 50.0

            # Directory sorting
            if is_dir:
                score += 10.0

            display_tag = (
                "[yellow]● mod[/yellow] "
                if is_mod
                else ("[blue]📁[/blue] " if is_dir else "[cyan]📄[/cyan] ")
            )
            display = f"{display_tag}[bold]{rel_name}[/bold]"
            val = f"~{rel_name}" if home else f"#{rel_name}"
            scored_entries.append((score, is_mod, display, val))
    except Exception:
        return [], []

    scored_entries.sort(key=lambda x: x[0], reverse=True)
    items = [x[2] for x in scored_entries]
    values = [x[3] for x in scored_entries]
    return items, values


def get_subcommand_completions(raw: str) -> tuple[list[str], list[str]] | None:
    """Dynamic parameter completions for common slash commands."""
    r = raw.strip()
    parts = r.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

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
        items = [f"[bold cyan]● {k:<10}[/bold cyan] [dim]{git_cmds[k]}[/dim]" for k in matches]
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
        items = [f"[bold cyan]● {k:<12}[/bold cyan] [dim]{pr_opts[k]}[/dim]" for k in matches]
        values = [f"/pr {k}" for k in matches]
        return items, values

    # /sessions subcommands and existing session IDs
    if cmd in ("/sessions", "/session"):
        session_opts = {
            "list": "List all active and stored sessions",
            "clean": "Prune empty or abandoned sessions",
            "save": "Save current session state",
            "load": "Load session from file (/load <file>)",
            "export": "Export session transcript (/export <file>)",
        }
        items: list[str] = []
        values: list[str] = []

        # 1. Fetch available sessions from DB so users never have to type raw IDs
        try:
            from sago.database import Session, init_db

            init_db()
            s = Session()
            sessions = s.list_all(limit=15)
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
                    items.append(f"[bold cyan]● {t_short}[/bold cyan] [white]{title[:32]}[/white]")
                    values.append(f"/session {t_short}")
        except Exception:
            pass

        # 2. Add subcommand options
        for k, desc in session_opts.items():
            if not arg or fuzzy_score(arg, k) > 0:
                items.append(f"[bold blue]⚡ {k:<10}[/bold blue] [dim]{desc}[/dim]")
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
                items.append(f"[bold blue]⚡ {k:<10}[/bold blue] [dim]{desc}[/dim]")
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
                        f"[bold cyan]● restore {cid}[/bold cyan] [dim]{desc[:26]} ({len(cp.file_paths)} files)[/dim]"
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
                items.append(f"[bold cyan]● {seq}[/bold cyan]\n  [dim]{desc}[/dim]")
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
                    f"[bold magenta]⚡ +{aname}[/bold magenta] [dim]{a.get('description', '')[:35]}[/dim]"
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
            items.append(f"[bold magenta]● @{aname:<20}[/bold magenta] [dim]{desc[:40]}[/dim]")
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
                items.append(f"[bold cyan]● {m:<32}[/bold cyan] [dim]{desc}[/dim]")
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
                items.append(f"[bold blue]⚡ {p:<14}[/bold blue] [dim]{desc}[/dim]")
                values.append(f"/provider {p}")
        return items, values

    return None
