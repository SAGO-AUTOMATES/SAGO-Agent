# Sago - Commands Reference

## CLI Commands

### Core Execution

#### `sago smart`
Smart task execution with AI-powered agent routing.

```bash
sago smart "task description"
sago smart "Create a React component" --effort high
```

The AI analyzes your task and automatically selects the best agent from 339 available agents.

---

#### `sago run`
Execute task with specific agent.

```bash
sago run "task" --agent python-engineer
sago run "task" --agent java-engineer
```

---

#### `sago tui`
Launch clean interactive TUI.

```bash
sago tui
```

---

### Agent Management

#### `sago agents`
List all available agents.

```bash
sago agents
sago agents --category security
```

---

#### `sago info`
Show agent details.

```bash
sago info python-engineer
```

---

### Project Setup

#### `sago init`
Initialize Sago in current directory.

```bash
sago init
```

Creates `config.sago.json` for per-project customization.

---

### Monitoring

#### `sago status`
Show system status.

```bash
sago status
```

---

#### `sago tools`
List all available tools.

```bash
sago tools
sago tools --category file
```

---

## TUI Commands

### Launch
```bash
sago tui
```

### Slash Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `/help` | `/h` | Show help |
| `/agents` | `/a` | List agents |
| `/clear` | `/c` | Clear chat |
| `/status` | `/s` | System status |
| `/export` | `/e` | Export session to markdown |
| `/exit` | `/q` | Quit |

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Q` | Quit |
| `Ctrl+L` | Clear chat |

---

## Provider Setup

### OpenRouter (Recommended)
```bash
export OPENROUTER_API_KEY="sk-or-..."
sago smart "task"
```

### Gemini
```bash
export GEMINI_API_KEY="AIza..."
sago smart "task" --provider gemini
```

### OpenAI
```bash
export OPENAI_API_KEY="sk-..."
sago smart "task" --provider openai
```

### Ollama (Local)
```bash
ollama serve
ollama pull llama3.1
sago smart "task" --provider ollama --model llama3.1
```

---

## Examples

### Quick Task
```bash
sago smart "Fix the authentication bug"
```

### Java Project
```bash
sago smart "Create a Java calculator with add, subtract, multiply, divide"
```

### React Frontend
```bash
sago smart "Create a React login form with validation"
```

### Initialize Project
```bash
cd my-project
sago init
sago smart "Add user authentication"
```
