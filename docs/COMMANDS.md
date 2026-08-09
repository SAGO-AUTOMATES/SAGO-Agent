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
```

### `sago tui`
Launch interactive TUI.

```bash
sago tui
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

| Command | Alias | Description |
|---------|-------|-------------|
| `/help` | `/h` | Show all commands |
| `/version` | — | Show version |
| `/exit` | `/q`, `/quit` | Quit |

### Agents

| Command | Alias | Description |
|---------|-------|-------------|
| `/agents` | `/a` | List all agents grouped by category |
| `/agents <filter>` | `/a <filter>` | Filter agents by name/skill |

### Chat

| Command | Alias | Description |
|---------|-------|-------------|
| `/clear` | `/c` | Clear chat |
| `/history` | — | Show recent messages |
| `/retry` | — | Retry last message |
| `/compact` | — | Summarize context |
| `/reset` | — | Reset session |

### Model & Provider

| Command | Description |
|---------|-------------|
| `/model` | Show current model |
| `/model <name>` | Change model |
| `/provider` | Show available providers |
| `/provider <name>` | Change provider |
| `/effort <level>` | Set effort: low/medium/high |

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
| `/chain <agents>` | Chain agents for task |

### Permissions

| Command | Description |
|---------|-------------|
| `/permissions` | Show all tool permissions |
| `/permissions blocked` | Show blocked tools |
| `/permissions allowed` | Show allowed tools |
| `/allow <tool>` | Unblock a tool |
| `/block <tool>` | Block a tool |

### Multi-Agent

| Command | Description |
|---------|-------------|
| `/agent <name>` | Set current agent |
| `/delegate <agent> <task>` | Delegate task to specialist |
| `/chain <a1,a2> <task>` | Chain agents sequentially |
| `/orchestrate <task>` | Auto-delegate to specialists |

### Git

| Command | Description |
|---------|-------------|
| `/git` | Git status |
| `/diff [file]` | Show diff |
| `/commit <msg>` | Commit changes |
| `/approve` | Approve pending action |
| `/deny` | Deny pending action |

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
| `Escape` | Dismiss suggestions / Quit |

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
```
