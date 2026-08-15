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

### Core & Autonomous Coding

| Command | Description |
|---------|-------------|
| `/help` | Show categorized command reference |
| `/project_graph [view] [path]` | Generate architecture, process, data, and dependency views (`dashboard`, `arch`, `process`, `er`, `flow`, `tree`, `mermaid`, `json`), or an AI analysis (`llm`, `ai`, `review`, `analysis`, `summary`) |
| `/graph` | Alias for `/project_graph` |
| `/copy [code\|all]` | Copy the last assistant response, its last code block, or the full chat history to the clipboard |
| `/clip [code\|all]` | Alias for `/copy` |
| `/map [query]` | Generate compact AST symbol repo map |
| `/verify` | Run automated linters, type checks, and test suites |
| `/plan` | Show current multi-step task execution plan |
| `/todos` | Show all tasks in plan |
| `/todo <id>` | Show details of a specific todo item |
| `/done <id>` | Mark a todo item as completed |
| `/retry` | Retry last user prompt |
| `/continue` | Resume an interrupted task from previous execution state without wasting tokens |
| `/compact` | Semantic context compression (prunes verbose tool outputs) |
| `/reset` | Reset active session |
| `/detach` | Cleanly detach from session while keeping background tasks running (safe to close terminal) |
| `/buttons [on\|off\|toggle]` | Toggle or configure bottom quick action buttons bar |
| `/show` | Make bottom action buttons bar visible |
| `/hide` | Hide bottom button bar for a clean, power-user experience |
| `/version` | Show Sago version info |
| `/exit` | Save session and quit |

### Multi-Agent Swarm & Mention Triggers

| Command / Trigger | Description |
|---|---|
| `@<agent>` | Mention and invoke a specialist agent anywhere in your prompt (triggers live agent autocompletion popup) |
| `@delegate <agent>` / `/delegate <agent> <task>` | Delegate task to a specialist with dynamic model and provider inheritance |
| `@chain <a1,a2>` / `/chain <a1,a2> <task>` | Chain multiple agents sequentially |
| `/agents [filter]` | List and filter all 339 specialist agents |
| `/agent <name>` | Set current active agent |
| `/parallel <a1,a2> <task>` | Run agents in parallel on the same task |
| `/orchestrate <task>` | Auto-delegate subtasks to specialists |
| `/handoff` | Show handoff targets for current agent |
| `#<file>` | Mention and autocomplete local repository files |
| `~<file>` | Mention and autocomplete user home directory files |

### Model & Runtime

| Command | Description |
|---------|-------------|
| `/model` | Show LLM Models Manager |
| `/model <name>` | Switch active model (fuzzy match) |
| `/model <provider> <name>` | Set active provider and model |
| `/model refresh` | Refresh model list from OpenRouter |
| `/model add <name>` | Add a custom model ID |
| `/model remove <name>` | Remove a custom model |
| `/provider` | Show or change active provider |
| `/effort <level>` | Set reasoning effort (`low`, `medium`, `high`, `max`) |
| `/cost` | Display token usage and cost analytics |
| `/dashboard` | Toggle live agent dashboard sidebar (`Ctrl+D`) |
| `/tasks` | Show running background tasks (`Ctrl+T`) |
| `/cancel <id\|all>` | Cancel running background task (`Ctrl+C`) |

### Developer Diagnostics & Telemetry

| Command | Description |
|---------|-------------|
| `/developer [on\|off\|toggle]` | Toggle Developer Mode (`/dev [on\|off\|toggle]`) |
| `/dev logs` | Stream real-time function execution and LLM trace logs |
| `/dev traces` | Inspect function latency and execution durations |
| `/dev export [file]` | Export deep traces and payloads to JSON (`.json`) or Markdown (`.md`) |
| `/dev clear` | Clear the developer trace telemetry buffer |

### Themes & UI Controls

| Command | Description |
|---------|-------------|
| `/theme <name>` | Switch color theme (11 themes available: `obsidian`, `nord`, `dracula`, `monokai`, `tokyo-night`, `solarized-dark`, `cyberpunk`, `catppuccin-mocha`, `gruvbox-dark`, `rose-pine`, `light`) |
| `/themes` | List all available color themes with active status indicator |
| `/collapse [all\|expand]` | Collapse or expand all conversational turns and tool cards |

### Version Control, Checkpoints & Rollbacks

| Command | Description |
|---------|-------------|
| `/checkpoint create [desc]` | Create an atomic point-in-time workspace snapshot |
| `/checkpoint list` | List available workspace checkpoints |
| `/checkpoint restore <id>` | Instantly restore workspace to a previous checkpoint |
| `/git` | Show git status |
| `/diff [file]` | View diff of modified files |
| `/commit <message>` | Commit changes to git |
| `/changes` | Show session file modification log |
| `/undo` | Roll back the last file change |

### Sessions & Security

| Command | Description |
|---------|-------------|
| `/sessions` | List all saved sessions |
| `/session <id>` | Switch to a specific session |
| `/save [name]` | Save current session context |
| `/load <id>` | Load a saved session |
| `/export` | Export session conversation to Markdown |
| `/yolo` | Toggle YOLO mode (auto-approve all tool calls globally) |
| `/permissions` | Show tool permissions (`/permissions [blocked|allowed]`) |
| `/allow <tool>` | Unblock or auto-approve a tool |
| `/block <tool>` | Block a tool |

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
