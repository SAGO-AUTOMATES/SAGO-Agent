# SAGO-Agent: Production Migration Plan v1.0.0

## Document Overview

**Project:** SAGO-Agent (Sophisticated Multi-Agent Orchestration System)
**Current Version:** 0.1.13
**Target Version:** 1.0.0 (production-grade release)
**Primary Goal:** Evolve from CLI/TUI-only application to a production-grade, multi-interface platform with server-side execution, WebSocket real-time capabilities, and HTTP API — **while preserving 100% of existing features**.

---

## Migration Philosophy

**Evolution, Not Revolution:**

> SAGO-Agent evolves, it does not restart. Every existing workflow, agent, tool, debug hook, and LLM interaction pattern continues working exactly as before. New API/WebSocket paths produce identical results to native TUI/CLI paths. The client is a thin interface; all intelligence, file analysis, tool execution, and LLM calls happen server-side.

### Core Guarantees

| Guarantee | Description |
|-----------|-------------|
| **Zero Feature Loss** | All 150+ features preserved across both execution paths |
| **100% Backward Compatibility** | Default mode: `native`; existing TUI/CLI works unchanged |
| **Opt-In API Mode** | API/WebSocket mode requires explicit config change |
| **Hot-Reload Robustness** | Config changes without server restart |
| **Emergency Rollback** | Instant revert to native mode via config |
| **Server-Side Security** | Client never sees project files, API keys, or internal code |

---

## Architecture: Server-Side Only Execution

### Why Server-Side Only

| Concern | Client-Side Risk | Server-Side Solution |
|---------|------------------|----------------------|
| **Security** | Files/API keys exposed to user terminal | All data protected on server |
| **Sensitive Data** | User inspects all project source | Only results shown, never raw code |
| **LLM Key Exposure** | API keys leak in tool outputs | Keys NEVER leave server environment |
| **Tool Tampering** | User modifies tool arguments | Server validates ALL arguments before execution |
| **Audit/Compliance** | Hard to track actions | Full audit trail on server (who, what, when) |
| **Performance** | Limited by client hardware | Server uses full resources (planned scaling) |
| **Code Security** | User reverse-engineers algorithms | Internal logic never exposed |

### The Golden Rule

> The client never sees project files, source code, API keys, or internal algorithms. It only sees structured results, status updates, and rich formatting for display.

---

## System Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                    CLIENT INTERFACE LAYER (THIN)                   │
│  ┌─────────────────┐  ┌──────────────────────────────────────┐   │
│  │   Textual TUI   │  │              Web Frontend              │   │
│  │ (sago/tui/)     │  │ (future: React, Flutter, etc.)         │   │
│  └─────┬───────────┘  └───────┬───────────────────────────────┘   │
│        │                      │                                    │
│   sends│◄─────────────────────│ API request / WS message            │
│        │  command + metadata  │ (task_id, agent, params)           │
│        ▼                      ▼                                    │
│   result│◄─────────────────────│ structured result (NO raw code)    │
│  displays│                     │ displays                           │
│  ✅ UI   │                     │ ✅ UI                              │
└────────────┘                    └──────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────┐
│                 EXECUTION SERVER LAYER (ALL INTELLIGENCE)          │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  sago/                                                      │  │
│  │  ├── api/server.py       │ FastAPI + WebSocket server        │  │
│  │  ├── engine/             │ Unified executor, simple_executor │  │
│  │  ├── agents/             │ 339 specialist agents + registry  │  │
│  │  ├── tools/              │ 70+ production tools + registry   │  │
│  │  ├── llm/                │ Provider registry, routing, cache  │  │
│  │  ├── permissions.py      │ Risk-based approval system        │  │
│  │  ├── database.py         │ SQLite + WAL + connection pooling │  │
│  │  ├── config/             │ config.yaml + feature flags       │  │
│  │  ├── tracking/           │ Token tracking, cost analytics    │  │
│  │  ├── engine/hallucination_verifier.py │ 9-stage verification │  │
│  │  └── ...                 │ All other sago modules            │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  receives: task description, agent name, safe params only          │
│  sends: structured results (NO raw files, NO keys, NO prompts)    │
└────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────┐
│                OPERATIONS & INFRASTRUCTURE (server-only)           │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  ~/.sago/                                                    │  │
│  │  ├── data/sago.db          │ SQLite database (WAL mode)      │  │
│  │  ├── cache/                │ Hybrid BM25 + dense vector cache│  │
│  │  ├── backups/              │ File edit backups (server-only) │  │
│  │  ├── permissions.json      │ Tool permission state           │  │
│  │  ├── sessions/             │ Session data (JSON/Markdown)    │  │
│  │  ├── config.yaml           │ Global config (mode, flags)     │  │
│  │  ├── logs/                 │ Daily-rotated logs              │  │
│  │  └── checkpoints/          │ SHA-256 snapshots of files      │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  All state, persistence, and intelligence lives HERE               │
│  Client has NO persistent state beyond current session UI          │
└────────────────────────────────────────────────────────────────────┘
```

---

## What Client NEVER Sees (Security Boundary)

| Data Type | Reason | Client Gets |
|-----------|--------|-------------|
| **Project source files** (`*.py`, `*.js`, `*.ts`) | IP protection, security | Filenames only, maybe formatted snippets |
| **API keys** (`OPENAI_API_KEY`, etc.) | Never leak under any circumstances | Never — server uses its own keys |
| **LLM prompts** | Prompt engineering IP | Only output, never the prompt sent |
| **Internal algorithms** | Trade secrets | Results only |
| **Tool argument details** beyond what's needed | Attack surface reduction | Sanitized summaries |
| **Database contents** | Full state exposure | Query results only |
| **Project graph data** | Architecture IP | Diagrams/charts only |
| **Token costs per file** | Billing details not user concern | Session total only |
| **Error stack traces** | Internal debugging info | Sanitized user-friendly messages |
| **Permission state** | Security audit trail | Allow/block status only |

### What Client DOES See (Safe Summaries)

| Data Type | Format |
|-----------|--------|
| **File names** | `["db.py", "config.yaml", "main.py"]` |
| **Code snippets** | Max 3 lines, heavily truncated, with "..." |
| **Tool results** | Formatted output, success/failure status |
| **Task output** | Natural language summary, key results |
| **Tool calls** | `{"tool": "read_file", "args": {...}, "result": "..."}` |
| **Token usage** | `{"input": 150, "output": 85}` per session |
| **Agent names** | `python-engineer`, `security-engineer`, etc |
| **Category names** | `Engineering Dev`, `Data Intelligence`, etc |
| **Progress** | `42% complete`, `iteration 3/8` |
| **Errors** | User-friendly messages, no internal details |

---

## API Protocol: Server-Side Only

### WebSocket Message Flow

```
CLIENT (TUI/Web)                          SERVER (sago/)                          CLIENT (TUI/Web)
│                                                                     │
│ 1. {type: "execute", task: "Fix bug",  │──────────────────────────────────────────────▶│
│    agent: "python-engineer"}           │  WebSocket connection - server-side only    │
│                                                                     │
│ 2. Server processes:                                              │
│    • Validates agent exists                                       │
│    • Validates permissions                                        │
│    • Loads project context (server-side only)                     │
│    • Executes via unified_executor.py                             │
│    • Runs hallucination verification (server-side)                │
│    • Records to DB (server-side)                                  │
│    • Streams results back via WS                                  │
│                                                                     │
│ 3. {type: "tool_call", tool: "read_file",│──────────────────────────────────────────────▶│
│    args: {file_path: "sago/database.py"}}│  server chooses what to send              │
│                                                                     │
│ 4. {type: "token", delta: "def fix(",  │──────────────────────────────────────────────▶│
│    accumulated: "def fix("})              │  token-by-token streaming                 │
│                                                                     │
│ 5. {type: "tool_result", tool: "read_file",│──────────────────────────────────────────────▶│
│    success: true, result: "..."}          │  formatted result, no raw code dumps      │
│                                                                     │
│ 6. {type: "complete", output: "...",   │──────────────────────────────────────────────▶│
│    files: ["sago/database.py"],         │  structured result, safe formatting       │
│    tokens: {...}}                         │                                           │
│                                                                     │
│ 7. {type: "error", message: "Not found"}│──────────────────────────────────────────────▶│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### REST API Endpoint Flow

```
CLIENT                        SERVER
│                           │
│ POST /execute {task, agent}│
│────────────────────────────▶│
│                           │ 1. Validate inputs
│                           │ 2. Check permissions
│                           │ 3. Execute via unified
│                           │ 4. Verify hallucinations
│                           │ 5. Record to DB
│                           │ 6. Return structured result
│  ◄─────────────────────────│
│                           │
│ GET /status/{task_id}      │
│────────────────────────────▶│
│                           │ 1. Query DB for status
│                           │ 2. Return formatted
│  ◄─────────────────────────│
│                           │
│ WS /ws/{task_id}           │
│────────────────────────────▶│ (persistent connection)
│                           │ 1. Accept connection
│                           │ 2. Stream messages
│                           │ 3. On disconnect, gracefully handle
│  ◄─────────────────────────│
```

### Safe Parameter Passing

**Client NEVER sends:**
- File paths that exist on their machine
- Raw code snippets for analysis
- LLM model names or API key details
- Tool argument values that could expose project internals

**Client SENDS (safe metadata only):**
- Task description (text only)
- Agent name (from known list)
- High-level preferences (effort level, model preference if any)
- Session ID (for resuming)
- Command type (execute, cancel, status, etc.)

**Server resolves everything internally:**
- Which files to read (based on task, not client input)
- Which tools to use (based on agent + task)
- LLM model selection (from configured provider)
- Permission checks (based on `~/.sago/permissions.json`)
- Project context detection (from config, not client-supplied paths)

---

## Server-Side Execution Flow

### Client Request (Minimal)

```python
# TUI sends via WebSocket or API:
{
    "type": "execute",
    "task": "Fix the authentication bug in sago/database.py",
    "agent": "python-engineer",
    "effort": "high",
    "session_id": "session_abc123",
}
```

### Server Processing

```python
# server-side (sago/api/server.py)
async def execute_task(task, agent_name, effort, session_id):
    # 1. Resolve agent from registry (server-side)
    agent = await get_agent(agent_name)  # From sago.agents.registry

    # 2. Detect project context SERVER-SIDE (NO client file paths needed)
    project_ctx = await detect_project_context(cwd="sago/")

    # 3. Load agent profile (server-side)
    profile = await load_agent_profile(agent.name)

    # 4. Build prompt with project context (server-side only)
    prompt = build_prompt(
        task=task, agent_role=agent.role, project_ctx=project_ctx, profile=profile
    )

    # 5. Execute with tool calling (server-side)
    result = await unified.execute(
        task=task,
        agent_name=agent.name,
        system_prompt=prompt,
        max_tokens=calculate_max_tokens(effort),
        max_iterations=get_max_iterations(agent, effort),
        on_tool_call=lambda name, args: broadcast_tool_call(name, args),
        on_thinking=lambda msg: broadcast_thinking(msg),
    )

    # 6. Run hallucination verification (server-side)
    verified = await verify_hallucinations(result.content, tool_history)

    # 7. Record to database (server-side)
    await record_task_session(session_id, task, agent.name, result, tool_history)

    # 8. Return structured result (NO raw project files)
    return {
        "output": verified.cleaned_content,
        "tool_calls": format_tool_calls(result.tool_history),
        "files_created": [f.name for f in result.files_created],
        "tokens": result.tokens,
        "iterations": result.iterations,
        "confidence": verified.confidence,
    }
```

### What Client Receives (Safe Formatting)

```json
{
    "output": "Successfully fixed the authentication bug.\n\n## Changes Made\n- Fixed JWT token validation in `sago/auth.py`\n- Added error handling for expired tokens\n\n## Confidence: 95/100",
    "tool_calls": [
        {
            "tool": "read_file",
            "args": {"file_path": "sago/auth.py"},
            "result": "// [safe summary - first 20 lines only]\n... (truncated for safety)"
        }
    ],
    "files_created": [],
    "tokens": {"input": 2450, "output": 180},
    "iterations": 3,
    "confidence": 95
}
```

---

## Feature Preservation Matrix

| # | Feature | Native Path | API/WS Path | Status |
|---|---------|-------------|-------------|--------|
| **1** | 339 Specialist Agents | `sago/agents/registry.py` direct import | Same registry, WS `GET /agents` | PRESERVED |
| **2** | 70+ Production Tools | `sago/tools/registry.py` `_discover_tools()` | Same discovery, WS `tool_call` messages | PRESERVED |
| **3** | Simple Executor | `sago/engine/simple_executor.py` native function calling | Via `unified.py` same execution | PRESERVED |
| **4** | Unified Executor | `sago/engine/unified.py` simple/CrewAI/LangGraph | IDENTICAL — this is the bridge | PRESERVED |
| **5** | Agent Chains `/chain` | `sago/main.py` click `execute_agent_task` | WS `execute` same chain logic | PRESERVED |
| **6** | Parallel Agents `/parallel` | `sago/main.py` ThreadPoolExecutor | WS supports parallel task submission | PRESERVED |
| **7** | Prompt Enhancement | `sago/main.py` `enhance_prompt()` | Same function called from API | PRESERVED |
| **8** | Hallucination Verification | `sago/engine/hallucination_verifier.py` 9-stage pipeline | Same verifier, API returns `cleaned_content` | PRESERVED |
| **9** | Permission System | `sago/permissions.py` 5-risk-level approval | Same checks, API validates before tool dispatch | PRESERVED |
| **10** | Checkpoint/Undo | `/checkpoint create/restore/undo` | API `/checkpoint` endpoints | PRESERVED |
| **11** | Session Persistence | SQLite `~/.sago/data/sago.db` + JSON exports | API uses same DB, WS syncs state | PRESERVED |
| **12** | Developer Mode `/dev` | `sago/main.py` Inspector, traces, OTel | API adds `/dev/export otel` endpoint | PRESERVED |
| **13** | Token Cost Tracking | `sago/tracking/token_tracker.py` | Same tracker, API POST `/usage` | PRESERVED |
| **14** | MCP Server | `sago/mcp/server.py` 70+ tools | API coexists, MCP routes unchanged | PRESERVED |
| **15** | TCP Daemon | `sago/server/daemon.py` | kept running, WS adds concurrent layer | PRESERVED |
| **16** | TUI All Commands | 50+ `/commands` in `sago/tui/app.py` | API mode TUI calls same endpoints | PRESERVED |
| **17** | LLM Provider Routing | `sago/llm/registry.py` Gemini/OpenAI/Claude/Ollama | Same `_get_configured_model()` logic | PRESERVED |
| **18** | Effort Levels low/medium/high/max | Task type detection token/iteration caps | Same caps in API execution | PRESERVED |
| **19** | Smart Project Map `/map` | `sago/map.py` AST symbol graph | API `POST /map` endpoint | PRESERVED |
| **20** | Project Graph `/graph` | `sago/project_graph.py` Mermaid diagrams | API `POST /graph` endpoint | PRESERVED |
| **21** | Self-Healing Verification `/verify` | Continuous background linting/tests | API `POST /verify` endpoint | PRESERVED |
| **22** | PR Creation Workflow `/pr create` | Automated Git branch/PR | API `POST /pr/create` endpoint | PRESERVED |
| **23** | Skills Registry `/skills` | `sago/skills/registry.py` built-in + workspace | Same, API `GET /skills` | PRESERVED |
| **24** | Onboarding Wizard | `sago setup` interactive wizard | API does not replace, supplements | PRESERVED |
| **25** | First-Time Setup | `sago onboard` provider/model/config | Same flow, API available after | PRESERVED |
| **26** | Intent Classification | `sago/engine/intent_classifier.py` micro-LLM | Same classifier, API uses it | PRESERVED |
| **27** | Context Assembly | `sago/engine/context_assembler.py` project context | Same, API includes context in prompts | PRESERVED |
| **28** | Subagent Isolation | `sago/agents/subagent_isolation.py` budgets/whitelists | Same, API respects budgets | PRESERVED |
| **29** | Iteration Budgets | max_iterations per agent/task | Same, API respects max_iterations param | PRESERVED |
| **30** | Tool Result Integrity | SHA-256 fingerprinting, 3x failure cap | API records hashes same way | PRESERVED |
| **31** | Memory Pyramid | 4-tier hierarchical compaction | API records metrics, WS streams progress | PRESERVED |
| **32** | BM25 + Dense Search | `sago/hybrid_indexer.py` semantic + BM25 | API `POST /search` endpoint | PRESERVED |
| **33** | File Operations 57+ tools | `sago/tools/file/` read/write/glob/grep | Same tools dispatched via API WS | PRESERVED |
| **34** | Shell Execution | `execute_shell` subprocess with timeout | API validates permissions first, then runs | PRESERVED |
| **35** | SSH Operations | `ssh_connect`/`ssh_command`/`ssh_transfer` | Same, API checks permission before connect | PRESERVED |
| **36** | Docker Operations | `docker_ops` ps/build/run/compose | API `POST /docker` endpoint | PRESERVED |
| **37** | Git Operations | `git_ops` status/log/diff/commit/push | API `POST /git` endpoint | PRESERVED |
| **38** | Web Crawling | `web_crawler` extract content | API `POST /crawl` endpoint | PRESERVED |
| **39** | HTTP Client | `http_client` GET/POST/PUT/DELETE | API `POST /http` endpoint | PRESERVED |
| **40** | Database Tools | `database/` query/schema/migration | API `POST /database` endpoint | PRESERVED |
| **41** | Code Analyzer | `code_analyzer` complexity/issues | API `POST /code-analyze` endpoint | PRESERVED |
| **42** | Linter/Formatter | `linter`/`formatter` ruff/black | API `POST /lint` `/format` endpoints | PRESERVED |
| **43** | Test Runner | `test_runner` pytest integration | API `POST /test-run` endpoint | PRESERVED |
| **44** | Debugger | `debugger` breakpoints/AST analysis | API `POST /debug` endpoint | PRESERVED |
| **45** | Log Analyzer | `log_analyzer` log file analysis | API `POST /log-analyze` endpoint | PRESERVED |
| **46** | Text Summarizer | `text_summarizer` summarize text | API `POST /summarize` endpoint | PRESERVED |
| **47** | Permission Manager | `/permissions` `/allow` `/block` | API `GET/POST /permissions` endpoints | PRESERVED |
| **48** | Session Manager | `/save` `/load` `/sessions` `/export` | API `GET/POST /sessions` endpoints | PRESERVED |
| **49** | Clipboard | `clipboard` tool system clipboard | API `POST /clipboard` endpoint | PRESERVED |
| **50** | Prompt Generator | `prompt_generator` tool | API `POST /prompt` endpoint | PRESERVED |
| **51** | Agent Handoffs | `/delegate` `/chain` `/parallel` | Same handoff logic, WS includes handoff data | PRESERVED |
| **52** | Recursion Guard | `is_spawn_allowed()` in registry.py | Same guard, API calls it | PRESERVED |
| **53** | Agent Spawning | `@` mentions `/delegate` commands | WS preserves agent inheritance | PRESERVED |
| **54** | Model Inheritance | Child agents inherit parent LLM/config | API passes same config through | PRESERVED |
| **55** | Fallback Chains | Provider fallback Gemini to OpenAI to Claude to Ollama | Same, API uses `fallback_order()` | PRESERVED |
| **56** | Temperature Tuning | Per-category: security=0.2, language=0.3, etc | API respects temperature param | PRESERVED |
| **57** | Max Iterations | Per-agent: 15 default, domain-aware tuning | API `max_iterations` param | PRESERVED |
| **58** | Chat Structure | `docs/TUI_CHAT_STRUCTURE.md` thinking then tool order | API messages follow same structure | PRESERVED |
| **59** | Thinking Blocks DB | `thinking_blocks[].seq` + `tool_usage.created_at` | API writes same DB schema | PRESERVED |
| **60** | Inspector F2 | TUI developer mode | API `/dev traces` `/dev logs` endpoints | PRESERVED |
| **61** | Telemetry Export | `/dev export otel` `/dev export prometheus` | API same endpoints | PRESERVED |
| **62** | Caching Layer | `sago/cache/intelligent.py` content-hash cache | API uses same cache keys | PRESERVED |
| **63** | Garbage Collection | `sago/cleanup.py` purge caches/backups/checkpoints | API `sago clean` endpoints | PRESERVED |
| **64** | Cleanup Commands | `/clean` `/clean cache` `/checkpoint prune` | API `POST /clean` endpoints | PRESERVED |
| **65** | Agent Categories | `sago agents` 22 categories listing | API `GET /agents/categories` | PRESERVED |
| **66** | Agent Info | `/info <agent>` detailed role/tools/handoffs | API `GET /agents/{name}` | PRESERVED |
| **67** | Fuzzy Agent Search | `sago agents <query>` category/name/role match | API `GET /agents/search` | PRESERVED |
| **68** | Skill Filtering | `/skills [--filter X]` | API `GET /skills?filter=X` | PRESERVED |
| **69** | Plugin System | `sago/plugins/` 3rd party hooks | API coexists, same plugin manager | PRESERVED |
| **70** | Hook System | Git pre-commit/pre-push hooks | API respects same hooks | PRESERVED |
| **71** | Environment Detection | `sago doctor` Python/DB/keys/ports | API health endpoint mirrors this | PRESERVED |
| **72** | Port Checking | Daemon ports 7654/7655 | API uses different ports, no conflict | PRESERVED |
| **73** | Configuration Persistence | `~/.sago/config.yaml` + `config.sago.json` | API reads/writes same files | PRESERVED |
| **74** | Sensitive Data Filtering | API keys never exposed in tool output | Same, API redacts same patterns | PRESERVED |
| **75** | Path Traversal Protection | Tool path validation | API validates same way | PRESERVED |
| **76** | Command Injection Protection | Shell command validation | API validates same patterns | PRESERVED |
| **77** | Input Validation | Empty/None handling, special chars | API Pydantic models + validation | PRESERVED |
| **78** | Error Message Sanitization | `_sanitize_error_message()` in main.py | Same function, API uses it | PRESERVED |
| **79** | Timeout Configurations | Various tool timeouts (60s, 120s, etc) | API respects same timeouts | PRESERVED |
| **80** | Connection Pooling | DB connection pooling in `database.py` | Same pool, API uses context manager | PRESERVED |
| **81** | WAL Mode | SQLite WAL for concurrent reads | API uses same connection management | PRESERVED |
| **82** | Foreign Key Constraints | DB schema with CASCADE/SET NULL | API uses same SQLAlchemy-like patterns | PRESERVED |
| **83** | Batch Commits | High-frequency operations | API batches where possible | PRESERVED |
| **84** | Thread-Local Connections | `_connections: dict[int, sqlite3.Connection]` | API per-thread or connection pooling | PRESERVED |
| **85** | Audit Logging | All tool calls, agent decisions logged | API logs same structured data | PRESERVED |
| **86** | Usage Tracking | `sago usage` token costs/cache hits | API `GET /usage` endpoint | PRESERVED |
| **87** | Per-Model Cost Breakdown | 9 models with pricing | API `GET /cost` endpoint | PRESERVED |
| **88** | Session-Level Tracking | Per-session token/storage tracking | API tracks per-task, aggregates | PRESERVED |
| **89** | Cumulative Tracking | Cumulative across sessions | API accumulates same way | PRESERVED |
| **90** | Daily Log Rotation | `~/.sago/logs/sago.log` 7-day retention | API does not affect, keeps separate | PRESERVED |
| **91** | TUI Screens/States | All TUI screens (project overview, agent dashboard) | API mode TUI renders same UI | PRESERVED |
| **92** | Agent Dashboard | `/dashboard` `Ctrl+D` sidebar | WS streams same data to TUI | PRESERVED |
| **93** | Task Tracker | `/tasks` `Ctrl+T` background tasks | WS same functionality | PRESERVED |
| **94** | Cancel Operations | `/cancel <id|all>` `Ctrl+C` | WS `cancel` message kills task | PRESERVED |
| **95** | Handoff Targets | `/handoff` show targets | API same handoff data | PRESERVED |
| **96** | Effort Level Setting | `/effort <level>` low/medium/high/max | API `max_iterations`/`max_tokens` param | PRESERVED |
| **97** | Cost Display | `/cost` token usage/costs | API `GET /cost` endpoint | PRESERVED |
| **98** | Save/Load Session | `/save [name]` `/load <name>` | API `POST/GET /sessions` | PRESERVED |
| **99** | Context Compact | `/compact` summarize old turns | API same functionality | PRESERVED |
| **100** | Git Status | `/git` status output | API `GET /git` endpoint | PRESERVED |
| **101** | Diff Viewer | `/diff [file]` show diff | API `POST /diff` endpoint | PRESERVED |
| **102** | Commit Command | `/commit <msg>` commit changes | API `POST /commit` endpoint | PRESERVED |
| **103** | Telemetry Flow Graphs | `/graph process` `/graph arch` etc | API `POST /graph` with different views | PRESERVED |
| **104** | AI Architecture Analysis | `/graph ai` `sago project-graph --view llm` | Same, API endpoint | PRESERVED |
| **105** | Recursive File Mentions `#file` | Fuzzy indexing with Git prioritization | API same search capabilities | PRESERVED |
| **106** | Detach/Attach Mode | `sago run --detach` `/detach` `/attach <id>` | API supports detach mode, WS for reattach | PRESERVED |
| **107** | Background Workers | Daemon startup/stop/status | API `POST /daemon` endpoints | PRESERVED |
| **108** | Remote Execution | `sago remote` dispatch tasks | API same remote patterns | PRESERVED |
| **109** | OpenTelemetry Export | Traces to JSON/Prometheus metrics | API `GET /telemetry/otel`/`/prometheus` | PRESERVED |
| **110** | TUI Regressive Flows | All `/tui_regressive_user_flows` tests | API mode passes same tests | PRESERVED |
| **111** | TUI Session Resume | `/load <name>` resumes TUI session | API WS preserves session state | PRESERVED |
| **112** | TUI Multiline Paste | `Shift+Enter` newline support | API same input handling | PRESERVED |
| **113** | TUI Turn Container | Card-based turn display | API WS streams same card data | PRESERVED |
| **114** | TUI Workspace Option | `-w`/`--path` workspace routing | API same `-w` parameter | PRESERVED |
| **115** | TUI Smart Suggest | Autocomplete in input | API same suggestion logic | PRESERVED |
| **116** | TUI Agent Delegation | `@agent` mentions `/delegate` | API same delegation flow | PRESERVED |
| **117** | TUI Smart Input | `sago/tui/smart_input.py` | API mode uses same parser | PRESERVED |
| **118** | TUI Helpers | `sago/tui/helpers.py` agent-tagged messages | API same message format | PRESERVED |
| **119** | TUI Widgets | AgentDashboard/AgentSpinner/HandoffFlow | API WS renders same widgets | PRESERVED |
| **120** | TUI Agent List | `/agents [category]` | API same, TUI displays | PRESERVED |
| **121** | TUI Skills List | `/skills [filter]` | API same | PRESERVED |
| **122** | TUI Plugin List | `/plugins` | API same | PRESERVED |
| **123** | TUI Permission View | `/permissions` | API same | PRESERVED |
| **124** | TUI Allow/Block | `/allow <tool>` `/block <tool>` | API same | PRESERVED |
| **125** | TUI Developer Mode | `/dev on` `/dev logs` `/dev traces` | API same endpoints, TUI displays | PRESERVED |
| **126** | TUI Session Export | `/export` JSON/Markdown | API `GET /sessions/export` | PRESERVED |

---

## Phase-Based Migration Roadmap

### Phase 0: Foundation and Setup (Week 1)

**NO CHANGES TO EXISTING CODE**

| Task | Detail | Deliverable |
|------|--------|-------------|
| 0.1 | Create `sago/api/` directory completely separate from `sago/` | `sago/api/__init__.py` |
| 0.2 | Install new dependencies: `fastapi`, `uvicorn` | `pip install fastapi uvicorn` |
| 0.3 | Add API optional deps to `pyproject.toml` under `[project.optional-deps]` | New `api = ["fastapi", "uvicorn"]` entry |
| 0.4 | DO NOT MODIFY any existing `sago/` files | Zero existing code changed |
| 0.5 | Create `sago/api/config.py` that reads `config.yaml` and returns mode setting | Config system reads mode |
| 0.6 | Create baseline git tag: `git tag v0.1.13-before-api` | Release marker |

---

### Phase 1: API Server Skeleton (Week 2)

**PROTO ONLY — safe endpoints only**

| Task | Detail | Feature Preservation |
|------|--------|---------------------|
| 1.1 | Create `sago/api/server.py` with bare FastAPI app | No endpoints yet, just app init |
| 1.2 | Add health endpoint only: `GET /health` returns `{"status": "ok"}` | No feature impact |
| 1.3 | Add config read endpoint: `GET /config` returns mode from `config.yaml` | Uses existing config system |
| 1.4 | Test: `curl http://localhost:8000/health` must work | Existing flow unchanged |
| 1.5 | Test: `curl http://localhost:8000/config` returns mode | New but non-intrusive |

**Deliverable:** API server starts, two safe endpoints, nothing broken.

---

### Phase 2: Execution Bridge (Week 3)

**THE CORE — this preserves all 150+ features through a single call**

| Task | Detail | Feature Preservation |
|------|--------|---------------------|
| 2.1 | Import and reuse `UnifiedExecutor` from `sago.engine.unified` | CRITICAL: Same executor, same logic |
| 2.2 | Implement `POST /execute` that calls `unified.execute()` identically to TUI | ALL 150+ features preserved through this single call |
| 2.3 | Implement WebSocket `/ws/{task_id}` that uses same execution flow | WS messages mirror TUI output exactly |
| 2.4 | Add `on_tool_call` callback that sends `tool_call` WS message | Mirrors TUI tool display exactly |
| 2.5 | Add `on_thinking` callback that sends `thinking` WS message | Mirrors TUI thinking display exactly |
| 2.6 | Add streaming `token` messages for token-by-token delivery | Same as TUI streaming behavior |
| 2.7 | Add `complete` message with full result object | Same fields as TUI result display |
| 2.8 | Add `error` message mirroring TUI error display | Same error formatting |

**Test:**
```bash
# Native TUI execution (existing)
sago run "Fix the bug"  # Works as before

# API execution (new, same result)
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -d '{"task": "Fix the bug", "agent": "python-engineer"}'
```

**Deliverable:** API execution produces bit-for-bit identical results to native TUI.

---

### Phase 3: State and Task Tracking (Week 4)

| Task | Detail | Feature Preservation |
|------|--------|---------------------|
| 3.1 | Extend `sago/database.py` `init_db()` to add `task_executions` table | Uses same DB connection pool, same patterns |
| 3.2 | Track task status in DB from both native and API paths | Recovery: If API crashes, native still has state in DB |
| 3.3 | Add task progress tracking (0-100%) | Same progress display in TUI |
| 3.4 | Add error message storage | Same error logs visible via `/logs` |
| 3.5 | Ensure checkpoint integration still works | `/checkpoint` commands unchanged |

**SQL Migration (backward compatible):**
```sql
CREATE TABLE IF NOT EXISTS task_executions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    current_agent TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    output TEXT,
    token_count INTEGER DEFAULT 0,
    iteration_count INTEGER DEFAULT 0,
    error_message TEXT,
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
```

---

### Phase 4: Authentication (Week 5)

**OPTIONAL BUT SAFE — no auth by default**

| Task | Detail | Feature Preservation |
|------|--------|---------------------|
| 4.1 | Add API key validation only for `/execute` | Default: no auth required (same as current TUI) |
| 4.2 | Validate against existing env keys: `GEMINI_API_KEY`, etc | Uses same `sago/llm/registry.py` |
| 4.3 | Add `Authorization: Bearer <key>` header support | New capability, opt-in |
| 4.4 | Default: no auth so existing TUI/CLI works unchanged | Zero breakage |

---

### Phase 5: TUI API Integration (Week 6)

| Task | Detail | Feature Preservation |
|------|--------|---------------------|
| 5.1 | Add `execution_mode` to `config.yaml` with default `"native"` | Default: native mode, no TUI changes needed |
| 5.2 | Create `sago/api/client.py` with httpx-based execution | Fallback: if API fails, use native functions |
| 5.3 | Modify TUI `app.py` to read `execution_mode` config | Conditional: API mode only if user changes config |
| 5.4 | Add `/mode` TUI command: `/mode native` `/mode api` | User choice, preserves existing behavior |
| 5.5 | Add `/ws-status` TUI command | Shows current connection status |
| 5.6 | Backward compatibility tests: All existing TUI tests must pass | GATE: PR merged only if 100% pass |

**TUI Config Entry:**
```yaml
execution:
  mode: "native"  # Default - no TUI changes needed
  ws_url: "ws://localhost:8000"  # only used if mode: "api"
```

---

### Phase 6: Hot-Reload and Config Watching (Week 7)

| Task | Detail | Feature Preservation |
|------|--------|---------------------|
| 6.1 | Add filesystem watcher on `config.yaml` | No restart needed when mode changes |
| 6.2 | TUI auto-reloads when config changes (SIGHUP or `/reload`) | Seamless transition |
| 6.3 | API server rereads config on config change | Zero downtime |
| 6.4 | Add `/reload` TUI command | Hot-reload without restart |
| 6.5 | Ensure all config changes are backward compatible | Existing settings still work |

**Hot-Reload Flow:**
```
1. User changes config.yaml: execution.mode: "api"
2. TUI receives SIGHUP or /reload command
3. TUI reads new config, switches to API mode
4. All ongoing tasks continue (state preserved in DB)
5. New tasks use API path
6. Old native tasks unaffected
```

---

### Phase 7: Exhaustive Testing and Parity (Weeks 8-9)

| Task | Detail | Verification |
|------|--------|-------------|
| 7.1 | Write parity tests: Same task, native vs API, compare results | MUST PASS before merge |
| 7.2 | Write state recovery tests: Crash API, resume with native | State must be recoverable |
| 7.3 | Write tool parity tests: 57+ tools via both paths | All tools work via API |
| 7.4 | Write agent parity tests: 339 agents via both paths | All agents accessible |
| 7.5 | Write hallucination verification parity | Same false positive/negative rates |
| 7.6 | Write permission parity tests: Both paths respect permissions | Same approval workflows |
| 7.7 | Write session persistence parity | Same DB, same export/import |
| 7.8 | Write developer mode parity | Same `/dev` functionality |
| 7.9 | Write workflow parity tests | Same chain/parallel/workflow behavior |
| 7.10 | Load testing: 10+ concurrent WS connections | No degradation |

**Parity Test Template:**
```python
@pytest.mark.asyncio
async def test_task_execution_parity(async_client):
    """Test that API and native execution produce identical results."""
    task = "Create a simple Python function that adds two numbers"

    # Native execution
    native_result = await execute_natively(task)

    # API execution
    resp = await async_client.post("/execute", json={"task": task, "agent": "python-engineer"})
    api_result = resp.json()

    # Compare key fields
    assert native_result["output"] == api_result["output"]
    assert native_result["tool_calls"] == api_result["tool_calls"]
    assert native_result["files_created"] == api_result["files_created"]
    assert native_result["iterations"] == api_result["iterations"]
```

---

### Phase 8: Documentation and Onboarding (Week 10)

| Task | Detail |
|------|--------|
| 8.1 | Update `README.md` with "API mode" section, clearly marked as opt-in |
| 8.2 | Create `docs/API_MIGRATION_GUIDE.md` with feature preservation matrix |
| 8.3 | Create `docs/HOT_RELOAD_GUIDE.md` for developers |
| 8.4 | Update `CONTRIBUTING.md` with "API mode development guidelines" |
| 8.5 | Ensure all existing docs still apply to native mode |
| 8.6 | Add migration checklist to this document |

---

### Phase 9: Gradual Rollout (Week 11+)

| Milestone | Criteria |
|-----------|----------|
| 9.1 | `v0.1.14` released: "API mode beta — opt-in only" |
| 9.2 | Default: `execution.mode: "native"` in config.yaml |
| 9.3 | All existing tests pass with native mode only |
| 9.4 | Users can opt-in: change config to `mode: "api"` |
| 9.5 | Feedback collected, bugs fixed |
| 9.6 | `v0.2.0`: Make API mode default for new installs |
| 9.7 | Keep native mode as legacy/fallback indefinitely |
| 9.8 | `v1.0.0`: "Production release" with both modes documented |

**Rollout Guardrails:**
```
NO feature removed from native mode until API mode has 100% parity
NO breaking changes without 2-week notice
ALL PRs must include parity test results
Rollback plan documented for each phase
```

---

## Critical Parity Guarantees

### Guarantee 1: Identical Execution Results

```
Task: "Fix the authentication bug in sago/auth.py"
Agent: python-engineer

Native TUI output EXACTLY matches API/WebSocket output:
- Same output text
- Same tool calls (name, args, results)
- Same files created
- Same iteration count
- Same token usage
- Same hallucination verification result
- Same permission approval flow
```

### Guarantee 2: Identical State Management

```
Database state after task completion:
- Same session entries in SQLite
- Same task records
- Same tool usage logs
- Same checkpoint snapshots
- Same session export format (JSON/Markdown)
- Same log files written

Recovery: If API server crashes mid-task,
native TUI can resume from same DB state.
```

### Guarantee 3: Identical Permission System

```
Tool execution approval flow:
- Safe tools: auto-approved (both paths)
- Low tools: auto-approved (both paths)
- Medium tools: require approval (both paths show same modal)
- High tools: require approval (both paths same)
- Critical tools: require approval (both paths same)
- Blocked tools: blocked in both paths

Approval state: Same ~/.sago/permissions.json read by both paths.
```

### Guarantee 4: Identical Developer Tools

```
/dev mode features (both paths):
- /dev on — Inspector enabled
- /dev logs — Live function execution logs
- /dev traces — OTel trace export
- /dev export otel — JSON traces
- /dev export prometheus — Metrics format
- Microsecond latency diagnostics
- LLM payload inspection
- All still work in API mode via same endpoints
```

### Guarantee 5: Identical Session Persistence

```
Session save/load (both paths):
- Save to ~/.sago/data/sago.db (SQLite)
- Export to JSON or Markdown
- List sessions via /sessions
- Load session via /load <name>
- Compact context via /compact
- All work identically regardless of execution path

Cross-path: Task started via API, resumed in TUI, or vice versa.
State preserved throughout.
```

### Guarantee 6: Identical Agent System

```
Agent features (both paths):
- 339 agents across 22 categories
- Agent info via /info <name>
- Agent listing via sago agents
- Skill filtering via /skills [filter]
- Handoff targets via /handoff
- Model inheritance preserved
- Temperature per domain preserved
- Max iterations per agent preserved
- All 70+ tools available to all agents
```

### Guarantee 7: Identical Hallucination Prevention

```
Verification pipeline (both paths):
- 9-stage fabrication phrase detection
- Claim vs tool-history cross-referencing
- Hedging/subtle claim detection
- Multi-language code syntax validation
- External syntax checking (py_compile, gofmt, etc.)
- Tool result integrity (SHA-256 hashing)
- Confidence scoring (0-100)
- Response sanitization (strip unverified claims)

Confidence scores: Same LLM output, same verification result.
```

### Guarantee 8: Identical Checkpoint/Undo

```
Checkpoint system (both paths):
- /checkpoint create "message" — creates snapshot
- /checkpoint list — lists available checkpoints
- /checkpoint restore chk_id — restores workspace
- /undo — revert latest assistant turn
- SHA-256 hashes of touched files
- All checkpoint files in ~/.sago/checkpoints/

API path: Same checkpoint manager, same file locations.
```

---

## Emergency Rollback Procedures

### If API Mode Breaks Something Critical

**Step 1: Disable API Mode (Quickest)**
```bash
# Edit config.yaml — instant effect
cat > config.yaml << 'EOF'
execution:
  mode: "native"
EOF
```

**Step 2: Restart TUI**
```bash
# TUI reads config on start, switches back to native instantly
sago tui
```

**Step 2 Alternative: Environment Variable**
```bash
# Override config at runtime
SAGO_EXECUTION_MODE=native sago tui
```

**Step 3: Kill API Server**
```bash
pkill -f "uvicorn sago.api.server"
```

**Step 4: Verify Native Mode**
```bash
sago tui  # Should work exactly as before
sago run "test task"  # Should work exactly as before
```

---

## Pre-Merge Checklist

Before merging any API-related changes, ALL must pass:

```
Git tag created: v0.1.13-before-api
All existing TUI tests pass: uv run pytest tests/tui/ -x
All existing unit tests pass: uv run pytest tests/unit/ -x
All existing integration tests pass: uv run pytest tests/integration/ -x
All existing security tests pass: uv run pytest tests/security/ -x
Feature parity: Sample task run via API, compare results to native
State recovery: Kill API server, resume task via native, verify state
Permission system: Verify both paths respect same permissions.json
Hallucination verification: Same results on sample hallucinated content
Checkpoint system: Create/restore via both paths produce same workspace
Session persistence: Save/load via both paths produce same data
Developer mode: /dev features work via both paths
Hot-reload: Switch config from native to api, TUI auto-reloads
No existing functionality removed or changed
All 126 features from preservation matrix verified
Documentation updated: README, contributing, API guide
Rollback procedures tested and documented
Feature flags default to "native" mode
API is truly opt-in (no default-on for existing users)
```

---

## File Structure Changes

### New Files to Create

```
sago/
├── api/
│   ├── __init__.py
│   ├── server.py           # Main FastAPI app + WebSocket
│   ├── client.py           # TUI API client (httpx)
│   ├── protocols.py        # WS message types definition
│   ├── models.py           # Pydantic request/response models
│   ├── config.py           # Read config.yaml execution mode
│   └── middleware.py       # Auth, rate limiting, CORS
├── config.yaml             # Updated with execution.mode setting
```

### Modified Files

```
sago/tui/app.py             # Conditional native/API mode switching
sago/tui/smart_input.py     # API-aware input handling
sago/tui/helpers.py         # Mode detection support
sago/main.py                # --api flag support
sago/database.py            # Extended task_executions table
sago/config/loader.py       # Read execution_mode config
pyproject.toml              # Add API optional dependencies
```

### Files That Remain UNCHANGED

```
sago/engine/unified.py       # THE BRIDGE — transport agnostic, already perfect
sago/engine/simple_executor.py  # Core execution logic — unchanged
sago/agents/registry.py      # Agent loading — unchanged
sago/tools/registry.py       # Tool discovery — unchanged
sago/llm/                    # All LLM providers — unchanged
sago/permissions.py          # Permission system — unchanged
sago/engine/hallucination_verifier.py  # Verification — unchanged
sago/mcp/                    # MCP server — unchanged
sago/server/daemon.py        # TCP daemon — unchanged
```

---

## Configuration Reference

### config.yaml (full example)

```yaml
# Execution mode — the single source of truth
execution:
  mode: "native"           # "native" (default) or "api"
  auto_fallback: true      # Fallback to native if API fails
  hot_reload: true         # Watch config for changes

  # API mode settings (only used when mode: "api")
  ws_url: "ws://localhost:8000"
  api_base_url: "http://localhost:8000"
  api_key: ""              # Optional API key for auth

  # Feature flags
  enable_websocket: true
  enable_rest_api: true
  enable_native_tui: true
  config_watch_interval: 5000  # ms

# Existing settings (unchanged)
llm_providers:
  default: gemini
  providers:
    gemini:
      enabled: true
      model: gemini-2.0-flash
```

### Environment Variable Overrides

```bash
# Override execution mode at runtime (takes precedence over config.yaml)
SAGO_EXECUTION_MODE=native sago tui

# Override API URL
SAGO_API_BASE_URL=http://localhost:8000 sago tui

# Override WebSocket URL
SAGO_WS_URL=ws://localhost:8000 sago tui
```

---

## Docker Deployment (Phase 8+)

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv pip install -e . --system

# Copy source
COPY sago/ ./sago/
COPY api/ ./api/

# Expose ports
EXPOSE 8000 7654 7655

# Run API server
CMD ["uvicorn", "sago.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: "3.8"
services:
  sago-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - SAGO_EXECUTION_MODE=api
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
    volumes:
      - sago-data:/root/.sago
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  sago-data:
```

---

## Success Metrics

| Metric | Target (v1.0.0) |
|--------|-----------------|
| API uptime | 99.9% |
| WS connection stability | 95%+ connections last 5min+ |
| Task execution parity | Native and API produce identical results (95%+ match) |
| API response time | 2s for simple tasks, 10s for complex |
| Concurrent users | 10+ simultaneous API+WS connections |
| Test coverage | 80%+ of new code |
| Documentation | All endpoints documented, TUI updated |
| Deployment | Docker image built, one-command deploy works |
| Existing tests | 100% pass rate (645+ tests) |
| Feature preservation | All 126 features verified preserved |

---

*Migration Plan v1.0.0. Guarantee: Zero feature loss, 100% backward compatibility, or full rollback.*
