# Sago - Commands Reference

## CLI Commands

### `sago smart`
AI-powered agent routing.

```bash
sago smart "Fix the auth bug"
sago smart "Create a React component" --effort high
```

### `sago run`
Execute with specific agent.

```bash
sago run "task" --agent python-engineer
sago run "task" --chain python-engineer,code-reviewer
```

### `sago tui`
Launch interactive TUI.

```bash
sago tui
sago tui --resume abc123  # Resume a session
```

### `sago agents`
List all 339 agents.

### `sago status`
System status.

### `sago tools`
List all tools.

---

## TUI Commands

### General

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/version` | Show version |
| `/exit` | Save session and quit |

### Agents

| Command | Description |
|---------|-------------|
| `/agents [filter]` | List all agents, optionally filtered |
| `/agent <name>` | Set current agent |
| `/agents-color` | List agents with their assigned colors |

### Chat

| Command | Description |
|---------|-------------|
| `/clear` | Clear chat |
| `/history` | Show recent messages |
| `/retry` | Retry last message |
| `/compact` | Summarize context |
| `/reset` | Reset session |

### Model & Provider

| Command | Description |
|---------|-------------|
| `/model` | Show current model |
| `/model <provider> <name>` | Change provider and model |
| `/model refresh` | Refresh model list from OpenRouter |
| `/model add <name>` | Add a custom model |
| `/model remove <name>` | Remove a custom model |
| `/effort <level>` | Set effort: low/medium/high/max |

### Sessions

| Command | Description |
|---------|-------------|
| `/sessions` | List recent sessions |
| `/session <id>` | Switch session |
| `/save [name]` | Save context |
| `/load <name>` | Load context |
| `/export` | Export to markdown |

### Monitoring

| Command | Description |
|---------|-------------|
| `/status` | System status with agent count |
| `/cost` | Token usage and cost |

### Permissions

| Command | Description |
|---------|-------------|
| `/permissions` | Show all tool permissions |
| `/permissions blocked` | Show blocked tools |
| `/permissions allowed` | Show allowed tools |
| `/allow <tool>` | Unblock a tool |
| `/block <tool>` | Block a tool |
| `/yolo` | Toggle YOLO mode (auto-approve all tools) |

### Multi-Agent

| Command | Shortcut | Description |
|---------|----------|-------------|
| `/delegate <agent> <task>` | — | Delegate task to specialist |
| `/chain <a1,a2> <task>` | — | Chain agents sequentially |
| `/parallel <a1,a2> <task>` | — | Run agents in parallel on same task |
| `/orchestrate <task>` | — | Auto-delegate to specialists |
| `/handoff` | — | Show handoff targets for current agent |

### Dashboard & Tasks

| Command | Shortcut | Description |
|---------|----------|-------------|
| `/dashboard` | `Ctrl+D` | Toggle agent dashboard sidebar |
| `/tasks` | `Ctrl+T` | Show background tasks |
| `/cancel <id\|all>` | `Ctrl+C` | Cancel running task(s) |

### Git

| Command | Description |
|---------|-------------|
| `/git` | Git status |
| `/diff [file]` | Show diff |
| `/commit <msg>` | Commit changes |
| `/approve` | Approve pending action |
| `/deny` | Deny pending action |

### Undo & Changes

| Command | Description |
|---------|-------------|
| `/undo` | Undo last file change |
| `/changes` | Show all file changes this session |

### Autocomplete

| Trigger | Shows |
|---------|-------|
| `/` | Command suggestions |
| `@` | Agent list |
| `#` | Files in current directory |

Press Escape to dismiss suggestions.

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Q` | Quit |
| `Ctrl+L` | Clear chat |
| `Ctrl+D` | Toggle dashboard |
| `Ctrl+T` | Show tasks |
| `Ctrl+C` | Cancel task |
| `Escape` | Dismiss suggestions |
| `Y` | Approve pending action |
| `N` | Deny pending action |

---

## Provider Setup

```bash
export OPENROUTER_API_KEY="sk-or-..."
sago smart "task"
```

## Available Models

- `openrouter/free` (default)
- `openrouter/auto`
- `anthropic/claude-3.5-sonnet`
- `openai/gpt-4o`
- `openai/gpt-4o-mini`
- `google/gemini-2.0-flash`
- `meta-llama/llama-3.1-70b-instruct`
- `mistralai/mistral-7b-instruct:free`

## Examples

```bash
sago smart "Fix the authentication bug"
sago smart "Create a Java calculator"
sago tui
# In TUI:
/a engineer     # Filter agents
/model gpt      # Change model
/sessions       # List sessions
/parallel python-engineer,code-reviewer "Build a REST API with auth"
/dashboard      # Toggle agent dashboard
```