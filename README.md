# SAGO-Agent

> **Production-grade multi-agent orchestration system** — 339 specialist agents, 45 tools, multi-LLM support, streaming, parallel execution, feedback loops, workflows, TUI with dashboard, and built-in security.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What is Sago?

Sago is a **production-grade multi-agent orchestration system** built for real-world software engineering tasks. It goes beyond simple code generation — it autonomously delegates work to **339 specialist agents**, uses **45 production tools**, streams responses token-by-token, runs agents in parallel, manages sessions, enforces permissions, and runs workflows.

### Key Capabilities

| Feature | Description |
|---------|-------------|
| **339 Specialist Agents** | Agents across 22 categories (engineering, security, data, cloud, compliance, etc.) |
| **45 Production Tools** | File ops, shell, networking, SSH, coding, Docker, and more |
| **Parallel Agent Execution** | Run multiple agents simultaneously on the same task |
| **Feedback Loops** | Agents can request clarification from previous agents in a chain |
| **Recursion Protection** | Depth tracking, cycle detection, and visited-agent guards |
| **Structured Handoffs** | Typed context passing between agents with history tracking |
| **AI-Powered Routing** | `sago smart` asks the LLM to pick the best agent for any task |
| **Token-by-Token Streaming** | Real-time streaming with usage tracking via OpenAI streaming API |
| **Permission System** | Risk-based tool permissions (safe/low/medium/high/critical) with approval workflow |
| **Session Persistence** | SQLite database + JSON file save/load with full state preservation |
| **Workflow Engine** | Stateful multi-step workflows with dependencies, retries, and pausing |
| **TUI Interface** | Rich terminal UI with agent dashboard, autocomplete, collapsible tool calls, and command history |
| **Multi-LLM Support** | OpenRouter, OpenAI, Gemini, Claude, Ollama |
| **Token Cost Tracking** | Per-model pricing with cache hit/miss analytics |
| **Security Audit** | Path traversal protection, input validation, sensitive data filtering |

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/SAGO-AUTOMATES/SAGO-Agent.git
cd SAGO-Agent

# Install dependencies
pip install -e .

# Set your API key
export OPENROUTER_API_KEY="your-key-here"

# Launch the TUI
sago tui

# Or run tasks from CLI
sago smart "Fix the authentication bug"
sago run "Build a REST API" --agent python-engineer
```

---

## Installation

### From Source (Recommended)

```bash
git clone https://github.com/SAGO-AUTOMATES/SAGO-Agent.git
cd SAGO-Agent
pip install -e .
```

### Using uv (Faster)

```bash
git clone https://github.com/SAGO-AUTOMATES/SAGO-Agent.git
cd SAGO-Agent
uv pip install -e .
```

### Dependencies

- Python 3.11+
- openai (for LLM calls)
- textual (for TUI)
- pydantic (for data validation)

Optional:
- crewai (for CrewAI orchestration path)
- langgraph (for LangGraph workflow engine)
- anthropic (for Claude provider)
- google-generativeai (for Gemini provider)

---

## CLI Commands

### Core Execution

| Command | Description |
|---------|-------------|
| `sago smart "task"` | **AI-powered execution** — LLM selects best agent, streams response |
| `sago run "task"` | Execute task with auto-orchestration |
| `sago run "task" --agent X` | Use specific agent |
| `sago run "task" --chain X,Y,Z` | Sequential agent chain |
| `sago run "task" --effort high` | Control execution depth (low/medium/high/max) |

### Interactive TUI

| Command | Shortcut | Description |
|---------|----------|-------------|
| `sago tui` | — | Launch interactive terminal UI |
| `/help` | — | Show all commands |
| `/agents [filter]` | — | List/search 339 agents |
| `/agent <name>` | — | Set current agent |
| `/delegate <agent> <task>` | — | Delegate to specialist |
| `/chain <a1,a2> <task>` | — | Chain agents sequentially |
| `/parallel <a1,a2> <task>` | — | Run agents in parallel on same task |
| `/orchestrate <task>` | — | Auto-delegate to specialists |
| `/dashboard` | `Ctrl+D` | Toggle agent dashboard sidebar |
| `/tasks` | `Ctrl+T` | Show background tasks |
| `/cancel <id\|all>` | `Ctrl+C` | Cancel running task(s) |
| `/handoff` | — | Show handoff targets for current agent |
| `/effort <level>` | — | Set effort: low/medium/high/max |
| `/cost` | — | Token usage and costs |
| `/save [name]` | — | Save session to file |
| `/load <name>` | — | Load session from file |
| `/compact` | — | Summarize context |
| `/permissions` | — | Show tool permissions |
| `/allow <tool>` | — | Allow a tool |
| `/block <tool>` | — | Block a tool |
| `/git` | — | Git status |
| `/diff [file]` | — | Show diff |
| `/commit <msg>` | — | Commit changes |

### Workflows

| Command | Description |
|---------|-------------|
| `sago workflows` | List all workflows |
| `sago workflow-create "name"` | Create new workflow |
| `sago workflow-add-step <id>` | Add step to workflow |
| `sago workflow-run <id>` | Execute workflow |

### System

| Command | Description |
|---------|-------------|
| `sago status` | System status |
| `sago agents` | List all agents |
| `sago info <agent>` | Agent details |
| `sago init` | Initialize project |
| `sago daemon start` | Start background server |
| `sago daemon stop` | Stop server |

---

## 339 Agents Across 22 Categories

| Category | Count | Examples |
|----------|-------|----------|
| Specialized Engineering | 71 | security-engineer, devsecops-engineer, blockchain-engineer |
| Engineering Dev | 52 | full-stack-engineer, backend-engineer, mobile-engineer |
| Language Specific | 35 | python-engineer, rust-engineer, go-engineer |
| Data Intelligence | 34 | data-engineer, ml-engineer, ai-engineer |
| Infrastructure Ops | 23 | devops, kubernetes-engineer, terraform-engineer |
| Database Specialists | 16 | postgresql-engineer, mongodb-engineer, redis-engineer |
| Compliance Legal Finance | 16 | gdpr-engineer, soc2-engineer, hipaa-engineer |
| Planning Oversight | 13 | technical-debt-manager, risk-manager, capacity-planner |
| Design Architecture | 12 | solutions-architect, enterprise-architect, security-architect |
| Testing Quality | 11 | qa-engineer, penetration-tester, performance-engineer |
| Orchestration | 10 | engineering-manager, scrum-master, technical-program-manager |
| Content Communication | 10 | technical-writer, documentation-updater, tech-translator |
| Cloud Infra Architecture | 9 | aws-engineer, gcp-engineer, azure-engineer |
| System Extensibility | 6 | agent-builder, prompt-engineer, skill-creator |
| Frontend Frameworks | 5 | react-engineer, vue-engineer, angular-engineer |
| Business Revenue | 5 | developer-advocate, sales-engineer, marketing-engineer |
| People Culture | 3 | technical-recruiter, training-specialist |
| Executive | 3 | cto, vp-engineering, ceo |
| Cloud Providers | 2 | cloudflare-engineer, oracle-cloud-engineer |
| Business Analysis | 2 | business-analyst, data-analyst |
| IT Support | 1 | it-support-engineer |
| Game Development | 1 | game-engineer |

---

## 45 Production Tools

### File Operations
- `read_file` — Read file contents
- `write_file` — Write files with auto-directory creation
- `glob_files` — Pattern-based file search
- `grep_content` — Regex content search
- `file_operations` — Move, copy, delete, rename, mkdir, list
- `archive` — Create/extract zip, tar, tar.gz, tar.bz2
- `hash_checksum` — MD5, SHA1, SHA256, SHA512
- `diff_tool` — Compare files/text
- `regex_tester` — Test/debug regular expressions
- `pdf_reader` — Extract text from PDFs
- `data_processor` — JSON/YAML parse, validate, format, query, merge

### Shell & System
- `execute_shell` — Run shell commands
- `background_process` — Run commands in background
- `process_manager` — List/kill processes
- `env_info` — System, disk, memory, network info
- `env_manager` — Environment variable management
- `os_detector` — Detect operating system
- `cron_schedule` — Manage scheduled tasks
- `screenshot` — Capture screenshots

### Network
- `http_client` — API requests (GET, POST, PUT, DELETE)
- `web_crawler` — Crawl websites, extract content
- `dns_lookup` — DNS resolution
- `port_scan` — Scan ports
- `network_config` — Network configuration info

### SSH
- `ssh_connect` — SSH connections
- `ssh_command` — Execute remote commands
- `ssh_transfer` — File transfer via SCP/SFTP

### Coding
- `code_analyzer` — Code structure, complexity, issues
- `linter` — Code linting
- `formatter` — Code formatting
- `test_runner` — Run tests
- `debugger` — Debug with breakpoints, AST analysis
- `log_analyzer` — Analyze log files
- `text_summarizer` — Summarize text

### DevOps
- `docker_ops` — Docker ps, build, run, compose
- `git_ops` — Git status, log, diff, commit, push

### Session & Other
- `session_manager` — Session management
- `clipboard` — Clipboard operations
- `prompt_generator` — Generate prompts
- `permission_manager` — Manage permissions
- `spawn_agent` — Delegate to specialist agents

---

## Permission System

Sago includes a **risk-based permission system** that controls which tools can be executed.

### Risk Levels

| Level | Tools | Default |
|-------|-------|---------|
| **Safe** | read_file, glob_files, env_info, os_detector | Auto-approved |
| **Low** | write_file, edit_file, file_operations | Auto-approved |
| **Medium** | execute_shell, background_process, docker_ops | Requires approval |
| **High** | ssh_connect, ssh_command, sudo_executor | Requires approval |
| **Critical** | spawn_agent | Requires approval |

### Managing Permissions

```bash
# View all tool permissions
/permissions

# View blocked tools only
/permissions blocked

# Allow a tool
/allow execute_shell

# Block a tool
/block sudo_executor
```

### Configuration

Permissions are stored in `~/.sago/permissions.json`:

```json
{
  "auto_approve_safe": true,
  "auto_approve_low": true,
  "require_approval_medium": true,
  "require_approval_high": true,
  "require_approval_critical": true,
  "blocked_tools": ["dangerous_tool"]
}
```

---

## Session Persistence

Sessions are automatically saved to SQLite (`~/.sago/data/sago.db`) and can be exported to JSON.

```bash
# Save current session
/save my-session

# List saved sessions
/sessions

# Load a session
/load my-session

# Export to markdown
/export

# Compact context (summarize old messages)
/compact
```

---

## Token Usage & Cost Tracking

```bash
# In TUI
/cost

# From CLI
sago usage
```

Output includes:
- Total input/output tokens
- Cache hit/miss counts and savings percentage
- Per-model cost breakdown (9 models supported)
- Session-level and cumulative tracking

---

## Workflow Engine

Create stateful, multi-step automations:

```bash
# Create a workflow
sago workflow-create "Deploy Pipeline"

# Add steps with dependencies
sago workflow-add-step <id> --name "Test" --type agent_call --config '{"task": "Run tests"}'
sago workflow-add-step <id> --name "Build" --type tool_call --config '{"tool": "execute_shell", "args": {"command": "make build"}}' --depends-on test-step
sago workflow-add-step <id> --name "Deploy" --type agent_call --config '{"task": "Deploy to production"}' --depends-on build-step

# Execute
sago workflow-run <id>

# Stream execution
sago workflow-run <id> --stream
```

---

## Architecture

```
sago/
├── agents/              # 339 agent profiles
│   ├── profiles/        # One .py per agent with metadata
│   ├── registry.py      # Agent loading and lookup
│   ├── spawner.py       # Agent execution with feedback loops
│   └── handoff.py       # HandoffContext, RecursionGuard, FeedbackRequest
├── tools/               # 45 production tools
│   ├── base.py          # BaseTool with permission checks
│   ├── file/            # File operations (12 tools)
│   ├── shell/           # Shell execution
│   ├── network/         # HTTP, DNS, crawling
│   ├── coding/          # Code analysis, debugging
│   ├── ssh/             # SSH operations
│   ├── system/          # Git, Docker, env
│   └── admin/           # Sudo, permissions
├── engine/              # Execution engines
│   ├── simple_executor.py   # Smart executor with auto-discovery
│   └── unified.py           # Unified executor (simple/crewai/langgraph)
├── permissions.py       # Risk-based permission system
├── workflow/            # Workflow engine
│   ├── engine.py        # Stateful workflows with dependencies
│   └── langgraph_engine.py  # LangGraph integration
├── server/              # TCP daemon server
│   └── daemon.py        # Background daemon with client
├── mcp/                 # Model Context Protocol
│   └── server.py        # MCP server with 45 tools
├── tui/                 # Terminal UI
│   ├── app.py           # Textual TUI with dashboard
│   ├── widgets/         # AgentDashboard, AgentSpinner, HandoffFlow
│   ├── helpers.py       # Agent-tagged message rendering
│   └── smart_input.py   # Input processor
├── llm/                 # LLM providers
│   ├── openai_provider.py
│   ├── openrouter.py
│   ├── gemini.py
│   └── claude.py
├── memory/              # Memory and context
│   ├── rag.py           # RAG memory with search
│   ├── compaction.py    # Session compaction
│   └── profiles.py      # User profiles
├── cache/               # Intelligent caching
│   └── intelligent.py   # Content-hash cache with TTL/LRU
├── tracking/            # Usage tracking
│   └── token_tracker.py # Token counting and cost
├── sessions/            # Session management
│   └── manager.py       # Multi-session with parallel execution
├── errors/              # Error handling
│   └── handler.py       # Recovery with fallback tools
├── database.py          # SQLite persistence
├── paths.py             # Cross-platform paths
├── config/              # Configuration
│   ├── loader.py
│   ├── project_config.py
│   └── sago.yaml
└── main.py              # CLI entry point
```

---

## Quality

Sago includes comprehensive coverage across unit, integration, and security categories.

### Quality Areas

| Category | Coverage |
|----------|----------|
| Unit - Tools | All 45 tools with proper arguments |
| Unit - Permissions | Risk levels, blocking, approval workflow |
| Unit - Agents | Registry, profiles, lookup |
| Integration - Executor | Tool discovery, task detection, extraction |
| Integration - Server | Daemon, client, protocol |
| Integration - Workflow | Engine, steps, dependencies |
| Integration - MCP | Server, tools, creation |
| Security | Path traversal, injection, bypass, validation |

---

## Security

### Path Traversal Protection
- Tools validate file paths before execution
- Blocked paths configurable per project

### Command Injection Protection
- Shell commands validated before execution
- Permission system blocks dangerous operations

### Permission Bypass Prevention
- High/critical risk tools require explicit approval
- Session-isolated approval state
- Blocked tools cannot be executed even with valid credentials

### Input Validation
- Empty/None inputs handled gracefully
- Special characters sanitized
- Error messages don't expose internals

### Sensitive Data Filtering
- API keys never exposed in tool output
- Passwords filtered from system info

---

## LLM Providers

| Provider | Models | API Key | Streaming |
|----------|--------|---------|-----------|
| OpenRouter | Multiple models | `OPENROUTER_API_KEY` | Yes |
| OpenAI | gpt-4o, gpt-4o-mini | `OPENAI_API_KEY` | Yes |
| Gemini | gemini-2.0-flash, gemini-1.5-pro | `GEMINI_API_KEY` | Yes |
| Claude | claude-3-5-sonnet, claude-3-haiku | `ANTHROPIC_API_KEY` | Yes |
| Ollama | Local models | None required | Yes |

### Effort Levels

| Level | Max Tokens | Max Iterations | Use Case |
|-------|-----------|----------------|----------|
| Low | 8,192 | 3 | Quick fixes, typos |
| Medium | 16,384 | 5 | Standard tasks |
| High | 32,768 | 8 | Complex architecture |
| Max | 65,536 | 12 | Critical systems |

---

## Configuration

### Project Config

After `sago init`, edit `config.sago.json`:

```json
{
  "agents": {
    "python-engineer": {
      "enabled": true,
      "system_prompt_override": "Custom prompt...",
      "tools_add": ["web_crawler"],
      "temperature": 0.8
    }
  },
  "permissions": {
    "allow_shell_execute": true,
    "allow_ssh": false,
    "blocked_paths": ["/etc", "/sys"]
  }
}
```

### Global Config

Stored in `~/.sago/`:

```
~/.sago/
├── data/sago.db          # SQLite database
├── permissions.json      # Tool permissions
├── sessions/             # Saved sessions (JSON)
└── config.yaml           # Global configuration
```

---

## CI/CD

GitHub Actions pipeline runs on every push:

1. **Lint** — Ruff code quality
2. **Type Check** — MyPy static analysis
3. **Unit Tests** — Tool, permission, agent tests
4. **Integration Tests** — Executor, server, workflow tests
5. **Security Tests** — Vulnerability checks
6. **Build** — Package build verification

See `.github/workflows/ci.yml` for details.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Make your changes
4. Ensure code quality with linting
5. Submit a pull request

### Development Setup

```bash
git clone https://github.com/SAGO-AUTOMATES/SAGO-Agent.git
cd SAGO-Agent
pip install -e ".[dev]"
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Sago** — Because every task deserves the perfect agent.
