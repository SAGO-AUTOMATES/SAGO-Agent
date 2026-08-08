# Sago - Commands Reference

## CLI Commands

### `sago smart`
AI-powered agent routing. The AI picks the best agent for your task.

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

### Slash Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `/help` | `/h` | Show help |
| `/agents` | `/a` | List agents |
| `/clear` | `/c` | Clear chat |
| `/status` | `/s` | System status |
| `/export` | `/e` | Export to markdown |
| `/sessions` | — | List recent sessions |
| `/session` | — | Switch session |
| `/history` | — | Show chat history |
| `/model` | — | Show current model |
| `/provider` | — | Show current provider |
| `/version` | — | Show version |
| `/exit` | `/q` | Quit |

### Autocomplete

| Trigger | Shows |
|---------|-------|
| `/` | Command suggestions |
| `@` | Agent list |
| `#` | Files in current directory |

Type `/`, `@`, or `#` and see suggestions appear. Press Escape to dismiss.

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

## Examples

```bash
sago smart "Fix the authentication bug"
sago smart "Create a Java calculator"
sago smart "Build a REST API with Flask"
sago tui
```
