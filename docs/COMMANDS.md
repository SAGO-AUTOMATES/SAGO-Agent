# Sago - Commands Reference

## Setup & Diagnostics

### `sago onboard` / `sago setup`
Interactive setup wizard to configure LLM providers, API keys, persistent storage, and workspace directories.

```bash
sago onboard             # Launch interactive onboarding setup wizard
sago setup               # Reconfigure providers and settings
```

### `sago doctor`
Check system health, Python runtime, API keys, SQLite integrity, network ports, and tool dependencies.

```bash
sago doctor              # Run comprehensive subsystem health check
```

### `sago update`
Auto-detect package manager (`uv` or `pip`) and update SAGO to the latest release in-place.

```bash
sago update              # Auto-detect uv/pip and upgrade SAGO
sago update --check      # Check current vs latest PyPI version without installing
```

## CLI Commands

### `sago smart`
AI-powered agent routing and streaming execution.

```bash
sago smart "Fix the auth bug"
sago smart "Create a React component" --effort high
```

### `sago run`
Execute with specific agent or sequential chain.

```bash
sago run "task" --agent python-engineer
sago run "Run long test suite" --detach   # Detach immediately; safe to close terminal tab
sago run "task" --chain system-architect,backend-engineer,code-reviewer
```

### `sago attach`
Attach to a running detached session or stream a background task log.

```bash
sago attach                   # Interactive list of running sessions & background tasks
sago attach a62c0922          # Reattach to TUI session
sago attach task_1700000000   # Live tail background task log
```

### `sago project-graph` / `sago graph`
Generate a deep architecture box diagram, autonomous execution process map, data model schema topology, and file dependency graph across multi-language codebases.

```bash
sago project-graph                           # Curated full architecture dashboard
sago project-graph --view arch               # Layered system architecture box diagram
sago project-graph --view process            # End-to-end execution pipeline & flywheel map
sago project-graph --view er                 # Entity-Relationship & data model diagram
sago project-graph --view flow               # Terminal-native component flow pipeline
sago project-graph --view tree               # Formatted file dependency & symbol tree
sago project-graph --view mermaid            # Visual Mermaid flowchart
sago project-graph --view llm                # AI-generated architectural analysis
sago project-graph --dir ./services --view arch
```

### `sago map`
Generate an AST-parsed compact symbol repository map (classes, methods, signatures) across 1,000+ files.

```bash
sago map
sago map --dir ./src --query UserService --max-files 100
```

### `sago search`
Natural language semantic & BM25 hybrid codebase search across 1,000+ files without external cloud vector DBs.

```bash
sago search "Where are database models defined?"
sago search "JWT authentication handler" --limit 10
sago search "retry logic on network failure" --json-out
```

### `sago telemetry`
Export microsecond execution telemetry into standard OpenTelemetry (`OTEL`) Trace JSON or Prometheus metrics exposition format.

```bash
sago telemetry --export otel --output traces.json
sago telemetry --export prometheus --output metrics.prom
```

### `sago parse`
Parse complex document formats (PDF, DOCX, XLSX, PPTX, HTML, CSV, JSON, XML) to clean, token-efficient Markdown powered by MarkItDown.

```bash
sago parse design_spec.pdf                     # Output parsed Markdown directly to terminal
sago parse data_sheet.xlsx -o sheet.md         # Save parsed table to Markdown file
sago parse architecture.pptx -o slides.md      # Convert slide deck to Markdown
```

### `sago verify`
Run multi-language automated verification (linters, type checks, and test suites) with diagnostic reports.

```bash
sago verify
sago verify --dir .
```

### `sago tui`
Launch interactive Terminal User Interface.

```bash
sago tui
sago tui --resume abc123  # Resume a session
```

### `sago workflow`
Execute complex multi-step tasks using LangGraph stateful engine.

```bash
sago workflow "Build a complete REST API with auth and tests"
```

### `sago agents`
List specialist agent categories or filter agents by category/name.

```bash
sago agents                     # Display category overview and agent counts across all 22 domains
sago agents database            # List all database specialist agents (SQLite, PostgreSQL, MySQL, Redis, etc.)
sago agents security            # List all security and compliance specialist agents
sago agents python              # Search for agents matching 'python'
sago agents --all               # List all 339 specialist agents
```

### `sago skills`
List available skills across workspace and user directories.

```bash
sago skills
sago skills --filter security
```

### `sago plugins`
List loaded custom plugins and active lifecycle hooks.

```bash
sago plugins
```

### `sago status`
Show system and connection status.

---

## TUI Commands

### 1. Core & Workflow

| Command | Description |
|---------|-------------|
| `/help` | Display categorized command reference manual |
| `/?` | Open interactive keyboard shortcuts & quick reference modal (`F1`) |
| `/status` | System health, active provider, model, and session metrics |
| `/clear` | Clear chat message history from terminal screen |
| `/compact` | Trigger immediate hierarchical context compaction |
| `/session [list\|save\|load\|reset]` | Manage sessions (list active, save state, load from disk, or reset) |
| `/export` | Export active conversation transcript to Markdown (`.md`) |
| `/exit` | Save active session state and exit cleanly |

### 2. Multi-Agent Orchestration & Mention Triggers

| Command / Trigger | Description |
|---|---|
| `/agent [name\|list]` | Switch active agent or list all 300+ specialist agents by domain |
| `/delegate <agent> <task>` | Delegate task to a specialist with dynamic model/provider inheritance |
| `/chain <a1,a2> <task>` | Chain multiple specialist agents in sequence (e.g. `architect -> coder -> test`) |
| `/orchestrate <task>` | Automatically orchestrate and dispatch task across specialist team |
| `/parallel <a1: t1, a2: t2>` | Run multiple agents concurrently, each with its own task (or shared task) |
| `/tasks [list\|cancel <id>]` | Manage background tasks (`Ctrl+T` or `/tasks cancel <id>`) |
| `/skills [query\|reload]` | Inspect available built-in and workspace `SKILL.md` workflows |
| `/mcp [list\|test\|reload]` | Manage external Model Context Protocol servers and bridged tools |
| `/plugins` | List active extension plugins and lifecycle hooks |
| `@<agent>` | Mention and route task to specialist agent anywhere in prompt (`@python-engineer`) |
| `#<file>` | Deep recursive workspace file autocomplete and automatic context injection |
| `~<file>` | Autocomplete user home directory file paths |

### 3. Code Intelligence, Map & Version Control

| Command | Description |
|---------|-------------|
| `/graph [summary\|arch\|process\|models\|flow]` | Generate architecture diagrams, process pipelines, data schemas, or flowcharts |
| `/map [query]` | Generate compact AST symbol repository map (classes, functions, signatures) |
| `/verify` | Run multi-language linters, type checks, and test suites |
| `/git [status\|diff\|commit\|log]` | Fast git operations and status inspection |
| `/diff [file]` | View workspace diffs of modified files |
| `/commit <message>` | Stage all changes and commit (asks for confirmation) |
| `/pr [create\|status]` | Pull-request workflow helper (branch + verification + PR draft) |
| `/search <query>` | Hybrid semantic + symbol code search across the workspace |
| `/undo` | Roll back the most recent file change |
| `/checkpoint [create\|list\|restore\|prune]` | Manage atomic point-in-time workspace snapshot rollbacks |

> **Reviewing changes:** ask the agent to "review my current changes / last commit / PR" —
> it uses the `review_changes` tool (`working_tree`, `staged`, `commit`, `branch`, `pr`
> via `gh pr diff`) to pull status, stats, and diffs in one call.

### 4. Settings & Runtime

| Command | Description |
|---------|-------------|
| `/model [name\|add\|remove]` | Switch active model. Any OpenRouter-style `vendor/model` id works (e.g. `stealth/ox-alpha`) — unknown vendor prefixes route via OpenRouter automatically |
| `/provider <name>` | Change LLM backend provider. Bare `/provider` lists providers with key status; unknown names are rejected with the valid list |
| `/effort <level>` | Adjust reasoning effort (`low`, `medium`, `high`, `max`) |
| `/cost` | Display session token usage analytics and spend metrics |
| `/perms [list\|allow\|block\|reset]` | Manage tool execution permissions |
| `/todo [list\|done <id>]` | Task checklist and plan manager |
| `/theme [name]` | Switch between 11 built-in TUI themes (`obsidian`, `nord`, `dracula`, etc.) |
| `/buttons [toggle\|on\|off]` | Toggle bottom quick action buttons bar |
| `/dev [on\|off\|logs\|traces]` | Real-time developer execution tracing and microsecond latency inspection — **default ON until v1.0** (`dev_mode: true # TODO: flip to false at 1.0`); fresh install shows Inspector (`F2`) without `/dev on` · Turn off with `/dev off` |
| `/yolo` | Toggle YOLO mode (auto-approve safe tool executions globally) |

### 5. Session & Utilities

| Command | Description |
|---------|-------------|
| `/sessions` / `/resume` | List saved sessions to switch or resume |
| `/save [name]` · `/load <id>` | Save current session / load a saved one |
| `/history` | Show conversation history for the active session |
| `/retry` · `/continue` | Retry the last failed request / resume an interrupted answer |
| `/plan [edit\|add\|remove]` | Edit a staged orchestration plan before approving it |
| `/handoff` | Show current agent handoff / recursion-guard state |
| `/dashboard` | Toggle the live agent dashboard sidebar |
| `/cancel` | Cancel active generation or background task |
| `/summary` | Toggle exit session summary display · Also: natural-language “so what was the summary?” / “summarize what you did” / “what was done” triggers 0-tool-call cached summary (categorized by agent, reuses `PROJECT_ANALYSIS.md` + `ToolUsageStore` + `DevTracer`, single LLM `tool_choice:none`) — see `docs/TUI_CHAT_STRUCTURE.md` §15 |
| `/copy [code\|all]` · `/clip` | Copy last response (or code blocks) to clipboard |
| `/clean [gc]` | Clean caches and temporary files |
| `/approve` / `/deny` | Approve or deny a pending tool action or plan (`Y`/`N`) |

---

## Keyboard Shortcuts in TUI

| Shortcut | Action |
| :--- | :--- |
| `F1` or `?` | Open interactive Keyboard Shortcuts & Quick Reference Modal |
| `PageUp` / `Shift+Up` | Scroll messages pane page / line up |
| `PageDown` / `Shift+Down` | Scroll messages pane page / line down |
| `Ctrl+Up` / `Ctrl+Down` | Line-by-line smooth viewport scroll |
| `Ctrl+Home` / `Ctrl+End` | Jump to top / bottom of chat messages |
| `Ctrl+D` | Toggle agent dashboard sidebar |
| `Ctrl+T` | Show background tasks |
| `Ctrl+C` | Cancel current task |
| `Ctrl+L` | Clear chat log |
| `Ctrl+Q` | Quit Sago TUI |
| `Up` / `Down` | Navigate command history / autocomplete suggestions |
| `Tab` / `Enter` | Accept autocomplete suggestion |
| `Escape` | Close autocomplete suggestions / dismiss modals |
| `y` / `n` | Approve or Deny permission requests |
| `Click Header` / `/collapse` | Click card/turn header or run `/collapse` to collapse/expand turns and outputs |
