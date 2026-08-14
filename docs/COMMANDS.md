# Sago - Commands Reference

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
sago run "task" --chain system-architect,backend-engineer,code-reviewer
```

### `sago map`
Generate an AST-parsed compact symbol repository map (classes, methods, signatures) across 1,000+ files.

```bash
sago map
sago map --dir ./src --query UserService --max-files 100
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
List and search all 339 specialist agents.

### `sago status`
Show system and connection status.

---

## TUI Commands

### Core & Autonomous Coding

| Command | Description |
|---------|-------------|
| `/help` | Show categorized command reference |
| `/map [query]` | Generate compact AST symbol repo map |
| `/verify` | Run automated linters, type checks, and test suites |
| `/plan` | Show current multi-step task execution plan |
| `/todos` | Show all tasks in plan |
| `/todo <id>` | Show details of a specific todo item |
| `/done <id>` | Mark a todo item as completed |
| `/compact` | Semantic context compression (prunes verbose tool outputs) |
| `/reset` | Reset active session |
| `/version` | Show Sago version info |
| `/exit` | Save session and quit |

### Multi-Agent Swarm

| Command | Description |
|---------|-------------|
| `/agents [filter]` | List and filter all 339 specialist agents |
| `/agent <name>` | Set current active agent |
| `/delegate <agent> <task>` | Delegate task to a specialist |
| `/chain <a1,a2> <task>` | Chain agents sequentially |
| `/parallel <a1,a2> <task>` | Run agents in parallel on the same task |
| `/orchestrate <task>` | Auto-delegate subtasks to specialists |
| `/handoff` | Show handoff targets for current agent |

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

### Version Control & Rollbacks

| Command | Description |
|---------|-------------|
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
| `PageUp` / `Shift+Up` | Scroll messages pane up |
| `PageDown` / `Shift+Down` | Scroll messages pane down |
| `Ctrl+D` | Toggle agent dashboard sidebar |
| `Ctrl+T` | Show background tasks |
| `Ctrl+C` | Cancel current task |
| `Up` / `Down` | Navigate command history / autocomplete suggestions |
| `Tab` / `Enter` | Accept autocomplete suggestion |
| `Escape` | Close autocomplete suggestions |