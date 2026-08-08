# Sago - Production-Grade Multi-Agent Orchestration System

> **The most advanced AI agent orchestration platform.** More capable than Claude Code, Antigravity Codex, and traditional coding assistants.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What is Sago?

Sago is a **production-grade multi-agent orchestration system** with:

- **339 Specialist Agents** across 22 categories
- **45+ Production Tools** for every task
- **Dynamic Task Delegation** with intelligent routing
- **Streaming Responses** with thinking traces
- **Multi-Session Parallel Execution**
- **Temporal Workflows** for stateful automation
- **Token Usage Tracking** with cost estimation
- **Intelligent Caching** with hit/miss analytics
- **Cross-Platform Support** (Linux, macOS, Windows)

## Quick Start

```bash
# Install
pip install sago

# Initialize in your project
cd your-project
sago init

# Launch interactive TUI
sago tui

# Or run tasks directly
sago smart "Fix the authentication bug"
sago run "Build a REST API" --agent python-engineer
```

## Commands

### Interactive TUI

| Command | Description |
|---------|-------------|
| `sago tui` | **Launch interactive TUI** with slash commands, @ attachments, syntax highlighting |
| `/help` | Show available commands |
| `/agents` | List available agents |
| `/sessions` | List active sessions |
| `/attach <path>` | Attach a file or folder |
| `/effort <level>` | Set effort level |
| `/compact` | Compact session context |
| `/provider <name>` | Switch LLM provider |
| `/model <name>` | Switch model |

### Core Execution

| Command | Description |
|---------|-------------|
| `sago smart "task"` | **Smart execution** with auto-delegation, streaming, thinking |
| `sago run "task"` | Execute task with auto-orchestration |
| `sago run "task" --agent X` | Use specific agent |
| `sago run "task" --chain X,Y,Z` | Agent chain execution |
| `sago chain "task" --chain X,Y` | Sequential agent chain |
| `sago chat "message"` | Interactive chat |

### Agent Management

| Command | Description |
|---------|-------------|
| `sago agents` | List all 339 agents |
| `sago info <agent>` | Agent details and capabilities |
| `sago init` | Initialize project config |
| `sago setup` | Interactive setup wizard |

### Workflows (Temporal)

| Command | Description |
|---------|-------------|
| `sago workflows` | List all workflows |
| `sago workflow-create "name"` | Create new workflow |
| `sago workflow-add-step <id>` | Add step to workflow |
| `sago workflow-run <id>` | Execute workflow |

### Monitoring

| Command | Description |
|---------|-------------|
| `sago usage` | Token usage and cache stats |
| `sago status` | System status |
| `sago sessions` | List sessions |
| `sago history <id>` | Session history |

## 339 Agents Across 22 Categories

| Category | Count | Examples |
|----------|-------|----------|
| specialized-engineering | 71 | security-engineer, devsecops-engineer, blockchain-engineer |
| engineering-dev | 52 | full-stack-engineer, backend-engineer, mobile-engineer |
| language-specific | 35 | python-engineer, rust-engineer, go-engineer |
| data-intelligence | 34 | data-engineer, ml-engineer, ai-engineer |
| infrastructure-ops | 23 | devops, kubernetes-engineer, terraform-engineer |
| database-specialists | 16 | postgresql-engineer, mongodb-engineer, redis-engineer |
| compliance-legal-finance | 16 | gdpr-engineer, soc2-engineer, hipaa-engineer |
| planning-oversight | 13 | technical-debt-manager, risk-manager, capacity-planner |
| design-architecture | 12 | solutions-architect, enterprise-architect, security-architect |
| testing-quality | 11 | qa-engineer, penetration-tester, performance-engineer |
| orchestration | 10 | engineering-manager, scrum-master, technical-program-manager |
| content-communication | 10 | technical-writer, documentation-updater, tech-translator |
| cloud-infra-architecture | 9 | aws-engineer, gcp-engineer, azure-engineer |
| system-extensibility | 6 | agent-builder, prompt-engineer, skill-creator |
| frontend-frameworks | 5 | react-engineer, vue-engineer, angular-engineer |
| business-revenue | 5 | developer-advocate, sales-engineer, marketing-engineer |
| people-culture | 3 | technical-recruiter, training-specialist |
| executive | 3 | cto, vp-engineering, ceo |
| cloud-providers | 2 | cloudflare-engineer, oracle-cloud-engineer |
| business-analysis | 2 | business-analyst, data-analyst |
| it-support | 1 | it-support-engineer |
| game-development | 1 | game-engineer |

## 45+ Production Tools

### File Operations
- `read_file`, `write_file`, `edit_file`, `glob_files`, `grep_content`
- `file_operations` (move, copy, delete, rename)
- `data_processor` (JSON/YAML parse, validate, format, query, merge)
- `hash_checksum` (md5, sha1, sha256)
- `archive` (zip, tar, tar.gz)
- `pdf_reader` (extract text from PDFs)
- `database_query` (SQLite SQL queries)
- `regex_tester` (test/debug regex)
- `diff_tool` (compare files/text)

### Shell & System
- `execute_shell`, `background_process`
- `git_ops` (status, log, diff, commit, push)
- `docker_ops` (ps, build, run, compose)
- `cron_schedule` (manage scheduled tasks)
- `screenshot` (capture screenshots)
- `env_info` (system, disk, memory, network info)

### Network
- `http_client` (API requests)
- `web_crawler` (crawl websites, extract content)
- `dns_lookup`, `port_scan`, `network_config`

### SSH
- `ssh_connect`, `ssh_command`, `ssh_transfer`

### Coding
- `code_analyzer`, `linter`, `formatter`, `test_runner`
- `debugger`, `log_analyzer`, `text_summarizer`

### Session
- `session_manager`, `clipboard`

## Dynamic Task Delegation

Sago automatically analyzes tasks and selects the best agent:

```bash
# Auto-delegates based on task content
sago smart "Fix the SQL injection vulnerability"
# -> Routes to security-engineer

sago smart "Write unit tests for the API"
# -> Routes to qa-engineer

sago smart "Deploy to Kubernetes"
# -> Routes to kubernetes-engineer
```

### Effort Levels

Control execution depth:

| Level | Description | Use Case |
|-------|-------------|----------|
| `minimal` | Quick fix | Typos, formatting |
| `low` | Simple task | Basic changes |
| `medium` | Standard | Most tasks |
| `high` | Complex | Architecture, security |
| `max` | Expert | Critical systems |

```bash
sago smart "Refactor authentication module" --effort high
```

### Thinking Traces

See the agent's reasoning process:

```bash
sago smart "Debug the race condition" --thinking
```

## Temporal Workflows

Create stateful, multi-step automation:

### Ticket Processing

```bash
# Create a workflow
sago workflow-create "Process Ticket" --trigger ticket

# Add steps
sago workflow-add-step <id> --name "Analyze" --type agent_call --agent business-analyst --task "Analyze ticket requirements"
sago workflow-add-step <id> --name "Implement" --type agent_call --agent developer --task "Implement the fix"
sago workflow-add-step <id> --name "Review" --type agent_call --agent code-reviewer --task "Review the implementation"

# Execute
sago workflow-run <id>
```

### Built-in Templates

- **Ticket Processor**: Auto-analyze, classify, and respond to tickets
- **Code Review Pipeline**: Fetch PR, analyze, security check, summarize
- **Deployment Pipeline**: Pre-checks, build, deploy, verify
- **Incident Response**: Triage, root cause, fix, verify, post-mortem

## Token Usage & Cost Tracking

```bash
sago usage
```

Output:
```
Token Usage:
  Total Requests: 142
  Total Tokens: 1,234,567
  Total Cost: $0.045678
  Avg Latency: 1,234ms

By Provider:
  gemini: 100 requests, 890,123 tokens
  openai: 42 requests, 344,444 tokens

Cache Statistics:
  Hits: 89
  Misses: 53
  Hit Rate: 62.68%
  Entries: 234
  Size: 1.23 MB
```

## Intelligent Caching

Sago caches LLM responses for efficiency:

- **Content-based deduplication**
- **TTL-based expiration**
- **LRU eviction**
- **Hit/miss tracking**
- **Persistent storage**

## Input Summarization & Compaction

### Smart Input Handling

When prompts exceed 500 words, Sago automatically:

1. Extracts key points, errors, and code references
2. Summarizes the input while preserving context
3. Reduces token usage for cost efficiency

```bash
# Long inputs are auto-summarized
sago smart "Here's a long bug report with stack traces, code blocks, and detailed reproduction steps..."
# -> Input summarized, key points extracted, tokens saved
```

### Session Compaction

For long conversations, Sago compacts context:

```bash
# In TUI, compact session context
/compact

# Automatic compaction when context exceeds limits
# - Preserves recent messages
# - Summarizes older messages
# - Extracts decisions and action items
```

### Compaction Features

- **Automatic**: Triggers when context exceeds token limits
- **Selective**: Preserves recent messages, summarizes older ones
- **Intelligent**: Extracts decisions, action items, and key points
- **Configurable**: Adjustable token limits per session

## Project Configuration

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

## Multi-Session Parallel Execution

Run multiple tasks concurrently:

```python
from sago.engine.production import ProductionEngine

engine = ProductionEngine()

# Run tasks in parallel
results = engine.run_parallel([
    {"task": "Write unit tests", "agent": "qa-engineer"},
    {"task": "Update documentation", "agent": "technical-writer"},
    {"task": "Review code", "agent": "code-reviewer"},
])
```

## Architecture

```
sago/
├── agents/           # 339 agent profiles
│   ├── profiles/     # One .py per agent
│   ├── registry.py   # Agent loading
│   └── spawner.py    # Agent execution
├── tools/            # 45+ tools
│   ├── file/         # File operations
│   ├── shell/        # Shell commands
│   ├── network/      # HTTP, DNS, crawling
│   ├── coding/       # Code analysis
│   └── system/       # Git, Docker, etc.
├── engine/           # Production engine
├── streaming/        # Response streaming
├── sessions/         # Session management
├── workflow/         # Temporal workflows
├── cache/            # Intelligent caching
├── tracking/         # Token usage tracking
├── memory/           # RAG memory & compaction
│   ├── rag.py        # RAG memory with search
│   ├── profiles.py   # User profiles & workspaces
│   └── compaction.py # Input summarization & session compaction
├── tui/              # Textual TUI
│   └── app.py        # Interactive interface with slash commands
├── llm/              # LLM providers
└── config/           # Configuration
```

## LLM Providers

| Provider | Models | API Key |
|----------|--------|---------|
| Gemini | gemini-2.0-flash, gemini-1.5-pro | `GEMINI_API_KEY` |
| OpenAI | gpt-4o, gpt-4o-mini | `OPENAI_API_KEY` |
| Claude | claude-3-5-sonnet, claude-3-haiku | `ANTHROPIC_API_KEY` |
| OpenRouter | Multiple models | `OPENROUTER_API_KEY` |
| Ollama | Local models | None required |

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Sago** - Because every task deserves the perfect agent.
