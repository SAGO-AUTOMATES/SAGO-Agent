# Sago Configuration Guide

## Overview

Sago uses multiple configuration files with different purposes. Here's the hierarchy:

```
~/.sago/
├── config/                    # YAML configs (detailed system configuration)
│   ├── sago.yaml             # Main config (orchestrator, settings, routing)
│   ├── agents.yaml           # Agent definitions and capabilities
│   ├── tools.yaml            # Tool registry and permissions
│   └── llm_providers.yaml    # LLM provider settings
├── settings.json             # Quick user preferences (JSON)
└── ...                       # Other data files
```

## Config File Differences

### `settings.json` — Quick User Preferences

**Purpose:** Simple key-value store for frequently changed user preferences.

**Format:** JSON

**When to use:** Quick toggles like model selection, yolo mode, dev mode.

**Example:**
```json
{
  "model": "gemini-2.5-flash",
  "provider": "google",
  "yolo": true,
  "dev_mode": false,
  "log_level": "info"
}
```

**Available keys:**
| Key | Type | Description |
|-----|------|-------------|
| `model` | string | Default LLM model (e.g., "gemini-2.5-flash", "gpt-4o") |
| `provider` | string | Default provider ("google", "openai", "anthropic", "openrouter", "ollama") |
| `agent` | string | Default agent to use |
| `yolo` | bool | Skip permission prompts (dangerous in production) |
| `dev_mode` | bool | Enable developer features |
| `log_level` | string | "debug", "info", "warning", "error" |
| `show_summary` | bool | Show task summary after completion |
| `show_action_bar` | bool | Show action bar in TUI |
| `effort` | string | "low", "medium", "high" — controls agent effort level |

---

### `config/sago.yaml` — Main System Configuration

**Purpose:** Core system settings, orchestrator config, routing rules.

**Format:** YAML

**When to use:** Changing system behavior, agent defaults, timeouts, directories.

**Sections:**

```yaml
# Project metadata
project:
  name: "sago"
  version: "0.1.12"

# Orchestrator settings
orchestrator:
  name: "Sago"
  model: "gemini-2.5-flash"
  max_iterations: 25
  verbose: true
  memory: true
  planning: true

# Global settings
settings:
  auto_detect_os: true
  preferred_shell: null  # null = auto-detect
  max_concurrent_tools: 5
  tool_timeout_seconds: 300
  retry_on_failure: true
  max_retries: 3
  log_level: "INFO"
  log_to_file: true
  log_directory: "~/.sago/logs"
  session_persistence: true
  session_directory: "~/.sago/sessions"

# Enabled agents
agents:
  enabled:
    - sago
    - coder
    - debugger
    - architect
    - devops
    - reviewer
    - researcher
    - planner

# Tool categories
tools:
  categories:
    file: true
    shell: true
    ssh: true
    coding: true
    network: true
    admin: true
    system: true

# Task routing triggers
routing:
  triggers:
    coder:
      - "write code"
      - "implement"
      - "create function"
    debugger:
      - "debug"
      - "fix bug"
      - "error"
    # ... more agents
```

---

### `config/agents.yaml` — Agent Definitions

**Purpose:** Define each agent's role, capabilities, tools, and personality.

**Format:** YAML

**When to use:** Adding new agents, modifying agent behavior, changing agent tools.

**Structure:**

```yaml
agents:
  agent_name:
    name: "Display Name"
    role: "Role Title"
    description: >
      What this agent does.
    goal: "Primary objective"
    backstory: >
      Background story for the agent.
    tools:
      - tool_name_1
      - tool_name_2
    model: null  # null = use default from sago.yaml
    max_iterations: 15
    verbose: true
    allow_delegation: false
    priority: 2
```

---

### `config/tools.yaml` — Tool Registry

**Purpose:** Define all available tools, their metadata, and permissions.

**Format:** YAML

**When to use:** Adding new tools, modifying tool permissions, changing tool categories.

**Structure:**

```yaml
tools:
  tool_name:
    name: "Display Name"
    category: "file|shell|ssh|coding|network|admin|system|vcs|web"
    description: "What this tool does"
    module: "sago.tools.category.module_name"
    class_name: "ClassName"
    permissions:
      - read
      - write
      - edit
      - execute
```

---

### `config/llm_providers.yaml` — LLM Provider Settings

**Purpose:** Configure LLM providers, models, API keys, and parameters.

**Format:** YAML

**When to use:** Adding new providers, changing models, adjusting parameters.

**Structure:**

```yaml
llm_providers:
  default: "gemini"

  providers:
    gemini:
      enabled: true
      api_key_env: "GEMINI_API_KEY"  # Environment variable name
      model: "gemini-2.5-flash"
      max_tokens: 8192
      temperature: 0.7

    openai:
      enabled: true
      api_key_env: "OPENAI_API_KEY"
      model: "gpt-4o"
      max_tokens: 4096
      temperature: 0.7

    ollama:
      enabled: false
      base_url: "http://localhost:11434"
      model: "llama3.1"
```

---

## Priority Order

Settings are loaded in this order (later overrides earlier):

1. **Package defaults** (`sago/config/*.yaml`) — Built-in defaults
2. **User global** (`~/.sago/config/*.yaml` or `~/.sago/config.yaml`) — Your overrides
3. **Project overrides** (`.sago.yaml` in project root) — Project-specific

For `settings.json`:
1. **Global** (`~/.sago/settings.json`)
2. **Project** (`.sago/settings.json` in project root)

---

## Common Tasks

### Change default model

**Option A: Quick (settings.json)**
```bash
sago set model gpt-4o
```

**Option B: Full config (sago.yaml)**
```yaml
# ~/.sago/config/sago.yaml
orchestrator:
  model: "gpt-4o"
```

### Enable YOLO mode (skip prompts)

```bash
sago set yolo true
```

Or edit `~/.sago/settings.json`:
```json
{
  "yolo": true
}
```

### Add a new agent

Edit `~/.sago/config/agents.yaml`:
```yaml
agents:
  my_agent:
    name: "My Agent"
    role: "Specialist"
    description: "Does something specific"
    goal: "Complete the task"
    backstory: "Background info"
    tools:
      - read_file
      - write_file
    model: null
    max_iterations: 10
```

### Change log level

**Quick:**
```bash
sago set log_level debug
```

**Full:**
Edit `~/.sago/config/sago.yaml`:
```yaml
settings:
  log_level: "DEBUG"
```

---

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| `settings.json` | `~/.sago/settings.json` | Quick user preferences |
| `sago.yaml` | `~/.sago/config/sago.yaml` | Main system config |
| `agents.yaml` | `~/.sago/config/agents.yaml` | Agent definitions |
| `tools.yaml` | `~/.sago/config/tools.yaml` | Tool registry |
| `llm_providers.yaml` | `~/.sago/config/llm_providers.yaml` | LLM providers |
| `.sago.yaml` | `<project>/.sago.yaml` | Project overrides |
| `.sago/settings.json` | `<project>/.sago/settings.json` | Project settings |

---

## Auto-Initialization

On first run, Sago automatically:
1. Creates `~/.sago/` directory structure
2. Copies default configs to `~/.sago/config/`
3. Creates empty `settings.json` if missing

To force reinitialize (reset to defaults):
```python
from sago.config.loader import init_user_config

init_user_config(force=True)
```
