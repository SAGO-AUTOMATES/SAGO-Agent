"""TUI Constants - Models, effort levels, and command definitions."""

from __future__ import annotations

import json

from sago.paths import get_sago_home

COMMANDS = {
    "/help": "Show all commands",
    "/agents": "List agents (or /agents <filter>)",
    "/agent": "Set current agent (/agent <name>)",
    "/delegate": "Delegate task to specialist (/delegate <agent> <task>)",
    "/chain": "Chain agents (/chain <agent1,agent2> <task>)",
    "/orchestrate": "Multi-agent orchestration (auto-delegates to specialists)",
    "/clear": "Clear chat",
    "/status": "System status",
    "/export": "Export to markdown",
    "/sessions": "List sessions",
    "/session": "Switch session (/session <id>)",
    "/history": "Chat history",
    "/model": "Model: /model, /model <name>, /model add, /model remove, /model refresh",
    "/provider": "Change provider",
    "/effort": "Set effort: low/medium/high/max",
    "/cost": "Token usage and costs",
    "/compact": "Summarize and compress context",
    "/retry": "Retry last message",
    "/reset": "Reset session",
    "/save": "Save session (/save [name])",
    "/load": "Load session (/load <id>)",
    "/git": "Git status",
    "/diff": "Show diff (/diff [file])",
    "/commit": "Commit (/commit <message>)",
    "/approve": "Approve pending action",
    "/deny": "Deny pending action",
    "/yolo": "Toggle YOLO mode (auto-approve all tools)",
    "/version": "Version info",
    "/undo": "Undo last file change",
    "/changes": "Show file changes",
    "/permissions": "Show tool permissions (/permissions [blocked|allowed])",
    "/allow": "Allow a tool (/allow <tool_name>)",
    "/block": "Block a tool (/block <tool_name>)",
    "/plan": "Show current task plan",
    "/todo": "Show todo (/todo <id>)",
    "/todos": "Show all todos",
    "/done": "Mark todo done (/done <id>)",
    "/ask": "Ask user for input (/ask <question>)",
    "/exit": "Save session and exit",
    "/resume": "List sessions to resume",
    "/parallel": "Run agents in parallel (/parallel <agent1,agent2> <task>)",
    "/dashboard": "Toggle agent dashboard sidebar",
    "/tasks": "Show background tasks",
    "/cancel": "Cancel a task (/cancel <task-id|all>)",
    "/handoff": "Show handoff graph for current chain",
    "/agents-color": "List agents with their colors",
    "/summary": "Toggle summary display after each task",
    "/map": "Generate compact symbol repo map (/map [query])",
    "/verify": "Run multi-language linters, type checks, and tests (/verify)",
    "/skills": "List available skills (/skills [filter] or /skill <name>)",
    "/plugins": "List installed third-party plugins (/plugins)",
}

BUILTIN_MODELS = [
    "openrouter/free",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-4-turbo",
    "anthropic/claude-3-5-sonnet",
    "anthropic/claude-3-haiku",
    "anthropic/claude-3-opus",
    "google/gemini-2.0-flash-001",
    "google/gemini-2.0-flash-lite",
    "google/gemini-pro",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-405b-instruct",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-coder",
    "deepseek/deepseek-r1",
    "mistralai/mistral-large-latest",
    "mistralai/mixtral-8x7b-instruct",
    "qwen/qwen-2.5-72b-instruct",
    "qwen/qwen-2.5-coder-32b-instruct",
    "cohere/command-r-plus",
    "perplexity/sonar-pro",
]

BUILTIN_COSTS = {
    "openrouter/free": {"input": 0, "output": 0},
    "openrouter/deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
    "openrouter/meta-llama/llama-3.1-70b-instruct": {"input": 0.52, "output": 0.75},
    "openrouter/qwen/qwen-2.5-72b-instruct": {"input": 0.35, "output": 0.4},
    "openrouter/google/gemini-2.0-flash-001": {"input": 0.075, "output": 0.3},
}

# Keep as dict for backward compat (used in status display)
MODEL_COSTS = BUILTIN_COSTS

MODELS_FILE = get_sago_home() / "models.json"
MODELS_CACHE_MAX_AGE = 86400  # 24 hours


def _load_models_data() -> dict:
    """Load custom models and costs from disk."""
    if MODELS_FILE.exists():
        try:
            return json.loads(MODELS_FILE.read_text())
        except Exception:
            pass
    return {"custom": [], "fetched": [], "costs": {}, "fetched_at": 0}


def _save_models_data(data: dict) -> None:
    """Persist custom models and costs to disk."""
    MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODELS_FILE.write_text(json.dumps(data, indent=2))


def get_all_models() -> list[str]:
    """Return merged list: builtin + custom + fetched, no duplicates."""
    data = _load_models_data()
    seen: set[str] = set()
    result: list[str] = []
    for m in BUILTIN_MODELS + data.get("custom", []) + data.get("fetched", []):
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


def get_model_costs() -> dict[str, dict]:
    """Return merged cost table: builtin + custom/fetched costs."""
    data = _load_models_data()
    costs = dict(BUILTIN_COSTS)
    costs.update(data.get("costs", {}))
    return costs


def add_custom_model(model_id: str) -> str:
    """Add a custom model. Returns status message."""
    data = _load_models_data()
    all_existing = set(BUILTIN_MODELS + data.get("custom", []) + data.get("fetched", []))
    if model_id in all_existing:
        return f"Already exists: {model_id}"
    data.setdefault("custom", []).append(model_id)
    _save_models_data(data)
    return f"Added: {model_id}"


def remove_custom_model(model_id: str) -> str:
    """Remove a custom or fetched model. Returns status message."""
    data = _load_models_data()
    for key in ("custom", "fetched"):
        lst = data.get(key, [])
        if model_id in lst:
            lst.remove(model_id)
            data[key] = lst
            _save_models_data(data)
            return f"Removed: {model_id}"
    return f"Not found: {model_id}"


def refresh_models_from_openrouter(api_key: str) -> str:
    """Fetch latest models from OpenRouter, store free + cheap ones."""
    import time
    import urllib.request

    if not api_key:
        return "No API key. Set OPENROUTER_API_KEY."

    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data_raw = json.loads(resp.read())
    except Exception as e:
        return f"Fetch failed: {e}"

    models = data_raw.get("data", [])
    if not models:
        return "No models returned from OpenRouter"

    data = _load_models_data()
    fetched: list[str] = []
    costs: dict[str, dict] = {}

    for m in models:
        mid = m.get("id", "")
        if not mid:
            continue
        fetched.append(mid)
        pricing = m.get("pricing", {})
        prompt_price = float(pricing.get("prompt", 0) or 0)
        completion_price = float(pricing.get("completion", 0) or 0)
        costs[mid] = {
            "input": prompt_price * 1_000_000,
            "output": completion_price * 1_000_000,
        }

    data["fetched"] = fetched
    data["costs"] = costs
    data["fetched_at"] = int(time.time())
    _save_models_data(data)

    free_count = sum(1 for m in fetched if ":free" in m)
    return (
        f"Fetched {len(fetched)} models from OpenRouter ({free_count} free)\nUse /model to see all"
    )


def auto_refresh_if_stale(api_key: str) -> str | None:
    """Auto-refresh models if cache is >24h old. Returns message or None."""
    import time

    data = _load_models_data()
    fetched_at = data.get("fetched_at", 0)
    if fetched_at and (time.time() - fetched_at) < MODELS_CACHE_MAX_AGE:
        return None  # Cache is fresh
    if not api_key:
        return None  # Can't refresh without key
    return refresh_models_from_openrouter(api_key)


EFFORT_LEVELS = {
    "low": {"max_iterations": 8, "max_tokens": 16384, "desc": "Quick answers, minimal tool use"},
    "medium": {"max_iterations": 20, "max_tokens": 50000, "desc": "Balanced approach"},
    "high": {"max_iterations": 35, "max_tokens": 50000, "desc": "Thorough analysis, complex tasks"},
    "max": {
        "max_iterations": 50,
        "max_tokens": 50000,
        "desc": "Maximum depth, full context utilization",
    },
}
