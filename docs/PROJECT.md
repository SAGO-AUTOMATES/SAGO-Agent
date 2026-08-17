# Sago - Project Architecture

> Production-grade multi-agent orchestration system with 339 agents, 70 production tools, parallel execution, feedback loops, and multi-LLM support.

## Overview

Sago is an advanced multi-agent operating system that orchestrates 339 specialized AI agents to handle complex software engineering workflows. It features dynamic task delegation, parallel agent execution, feedback loops, built-in Vector DB / RAG memory, self-healing verification, and a modern Textual TUI.

For detailed execution diagrams and architectural flowcharts, see **[Technical Flows & Architecture (docs/FLOWS.md)](FLOWS.md)**.

## Directory Structure

```
sago/
├── sago/                          # Main package
│   ├── __init__.py               # Package init
│   ├── main.py                   # CLI entry point (click)
│   ├── database.py               # SQLite persistence
│   ├── paths.py                  # Cross-platform paths
│   ├── learning.py               # Cross-session learning store
│   │
│   ├── agents/                   # Agent system
│   │   ├── __init__.py
│   │   ├── base.py               # AgentConfig model
│   │   ├── registry.py           # Agent loading & registry
│   │   ├── loader.py             # Dynamic profile loader
│   │   ├── spawner.py            # CrewAI agent execution
│   │   └── profiles/             # 339 agent profiles (.py)
│   │       ├── python_engineer.py
│   │       ├── security_engineer.py
│   │       ├── fullstack_engineer.py
│   │       └── ... (339 total)
│   │
│   ├── tools/                    # Tool system (70 production tools)
│   │   ├── __init__.py
│   │   ├── base.py               # BaseTool with helpers
│   │   ├── file/                 # File operations
│   │   │   ├── read_file.py
│   │   │   ├── write_file.py
│   │   │   ├── edit_file.py
│   │   │   ├── glob_files.py
│   │   │   ├── grep_content.py
│   │   │   ├── file_ops.py       # move/copy/delete
│   │   │   ├── directory_scanner.py  # Smart scanning
│   │   │   ├── agent_delegator.py    # Smart routing
│   │   │   ├── data_processor.py
│   │   │   ├── database_query.py
│   │   │   ├── hash_checksum.py
│   │   │   ├── archive.py
│   │   │   ├── pdf_reader.py
│   │   │   ├── regex_tester.py
│   │   │   └── diff_tool.py
│   │   ├── shell/                # Shell operations
│   │   │   ├── execute.py
│   │   │   └── background.py
│   │   ├── ssh/                  # SSH operations
│   │   │   ├── ssh_connect.py
│   │   │   ├── ssh_command.py
│   │   │   └── ssh_transfer.py
│   │   ├── session/              # Session tools
│   │   │   ├── session_manager.py
│   │   │   └── clipboard.py
│   │   ├── coding/               # Code analysis
│   │   │   ├── hybrid_search_tool.py # Hybrid BM25 & dense vector search
│   │   │   ├── project_graph_tool.py # Topology architecture & flow map
│   │   │   ├── checkpoint_tool.py    # Atomic snapshots & 1-click restore
│   │   │   ├── code_analyzer.py
│   │   │   ├── linter.py
│   │   │   ├── formatter.py
│   │   │   ├── test_runner.py
│   │   │   ├── debugger.py
│   │   │   ├── log_analyzer.py
│   │   │   └── text_summarizer.py
│   │   ├── network/              # Network tools
│   │   │   ├── http_client.py
│   │   │   ├── web_crawler.py
│   │   │   ├── dns_lookup.py
│   │   │   ├── port_scan.py
│   │   │   └── config_manager.py
│   │   ├── admin/                # Admin tools
│   │   │   ├── software_install.py
│   │   │   ├── permission_manager.py
│   │   │   ├── sudo_executor.py
│   │   │   └── prompt_generator.py
│   │   └── system/               # System tools
│   │       ├── os_detector.py
│   │       ├── process_manager.py
│   │       ├── env_manager.py
│   │       ├── git_ops.py
│   │       ├── docker_ops.py
│   │       ├── cron_schedule.py
│   │       ├── screenshot.py
│   │       └── env_info.py
│   │
│   ├── llm/                      # LLM providers
│   │   ├── __init__.py
│   │   ├── base.py               # BaseLLMProvider
│   │   ├── factory.py            # LLMFactory
│   │   ├── mock.py               # MockLLMProvider for offline CI testing
│   │   ├── gemini.py             # Google Gemini
│   │   ├── openai_provider.py    # OpenAI GPT
│   │   ├── claude.py             # Anthropic Claude
│   │   ├── openrouter.py         # OpenRouter
│   │   └── ollama.py             # Local Ollama
│   │
│   ├── engine/                   # Execution engine
│   │   ├── __init__.py
│   │   ├── context_assembler.py  # Multi-tiered context builder & prompt generator
│   │   ├── intent_classifier.py  # Micro-LLM & LRU semantic intent detection
│   │   ├── simple_executor.py    # Streaming ReAct loop & context compaction
│   │   ├── checkpoint.py         # Atomic workspace snapshot & rollback
│   │   ├── project_synthesizer.py # Multi-file topological synthesis
│   │   ├── verifier.py           # Self-healing verification flywheel & daemon
│   │   └── unified.py            # Unified router
│   │
│   ├── errors/                   # Error handling & recovery
│   │   ├── __init__.py
│   │   ├── exceptions.py         # Typed exception hierarchy
│   │   └── handler.py            # Recovery manager & fallback tools
│   │
│   ├── mcp/                      # Model Context Protocol
│   │   ├── __init__.py
│   │   ├── server.py             # MCP Server exposing tools
│   │   └── client.py             # MCP Client for remote tool consumption
│   │
│   ├── tracking/                 # Telemetry & tracing
│   │   ├── __init__.py
│   │   ├── dev_tracer.py         # Real-time function & latency tracer
│   │   └── otel_exporter.py      # OpenTelemetry JSON & Prometheus export
│   │
│   ├── plugins/                  # Extensible plugin system
│   │   ├── __init__.py
│   │   └── base.py               # BasePlugin & PluginManager (lifecycle hooks)
│   │
│   ├── skills/                   # Skills system
│   │   ├── __init__.py
│   │   ├── registry.py           # Pre-built skills registry
│   │   └── loader.py             # Custom markdown SKILL.md loader
│   │
│   ├── memory/                   # Memory systems & code graphs
│   │   ├── __init__.py
│   │   ├── hybrid_indexer.py     # BM25 + dense sub-token vector indexer
│   │   ├── project_graph.py      # Dynamic architecture, process & ER maps
│   │   ├── compaction.py         # 3-tier Hierarchical Memory Pyramid
│   │   ├── symbol_graph.py       # Compact AST repository outline map
│   │   ├── symbol_index.py       # SQLite FTS5 symbol index
│   │   ├── rag.py                # RAGMemory
│   │   └── profiles.py           # UserProfileManager
│   │
│   ├── orchestrator/             # Orchestration
│   │   ├── __init__.py
│   │   ├── engine.py             # SagoOrchestrator
│   │   └── delegator.py          # Recursion & cycle guards
│   │
│   └── tui/                      # Modular Terminal User Interface
│   │   ├── app.py                # Core SagoApp & event composition
│   │   ├── styles.py             # Layout CSS, responsive tokens & 11 themes
│   │   ├── orchestrator.py       # AgentOrchestrationMixin (delegation, chain, parallel)
│   │   ├── processor.py          # MessageProcessorMixin (LLM streaming, tools & retry)
│   │   ├── commands.py           # CommandHandlers mixin
│   │   ├── helpers.py            # UIHelpers & card renderers
│   │   ├── models.py             # Constants, themes, & command registry
│   │   ├── trace_viewer.py       # Modal trace & payload viewer
│   │   └── widgets/              # Textual dashboard, spinners & cards
│   │
│   ├── tools/                    # Tool system (70 tools)
│   │   ├── file/
│   │   │   ├── resilient_editor.py # 3-tier fuzzy & normalized matching
│   │   │   ├── multi_replace_file.py # Atomic multi-chunk replace
│   │   │   └── ...
│   │   ├── coding/
│   │   │   ├── repo_map_tool.py  # AST symbol mapper
│   │   │   ├── ast_grep.py       # Structural code search
│   │   │   ├── git_blame.py      # Author provenance & line history
│   │   │   └── ...
│   │   ├── security/
│   │   │   └── secret_scanner.py # Credential & API token scanner
│   │   ├── web/
│   │   │   └── search.py         # Web documentation search
│   │   └── ...
│
├── docs/                         # Documentation
│   ├── PROJECT.md                # This file
│   ├── AGENTS.md                 # Agent documentation
│   ├── TOOLS.md                  # Tool documentation
│   ├── BUILD.md                  # Build & dev commands
│   ├── COMMANDS.md               # CLI & TUI commands
│   ├── MCP.md                    # MCP server docs
│   └── ERRORS.md                 # Error handling docs
│
├── pyproject.toml                # Project config (hatchling)
├── README.md                     # Main readme
└── config.sago.json              # Project config (generated)
```

## Core Components

### 1. Agent System (`sago/agents/`)

**Registry** loads 339 agent profiles from `.py` files. Each profile defines:
- `name`, `codename`, `role`, `description`
- `system_prompt` - Detailed instructions
- `skills` - What the agent can do
- `tools` - Which tools it can use
- `handoff_to` - Other agents it can delegate to
- `model_preference` - Preferred LLM
- `max_iterations`, `temperature`

**Spawner** executes agents using CrewAI framework with:
- **Feedback Loops**: Agents can request feedback from other agents
- **RecursionGuard**: Prevents infinite loops (depth/visit/cycle limits)
- **HandoffContext**: Structured context passing between agents
- **Error Propagation**: Breaks on failure instead of propagating error strings

**Handoff System** (`agents/handoff.py`) provides structured context passing:
- `HandoffContext`: Manages originator, contexts, and results
- `RecursionGuard`: Depth limit (5), visit limit (15), cycle detection
- `FeedbackRequest`: Agent-to-agent feedback requests

### 2. Tool System (`sago/tools/`)

70 tools across 13 categories:
- **File** (15): read, write, edit, glob, grep, scan, analyze
- **Shell** (2): execute, background
- **SSH** (3): connect, command, transfer
- **Session** (2): manager, clipboard
- **Coding** (7): analyzer, linter, formatter, test, debug, logs, summarize
- **Network** (5): http, crawl, dns, port, config
- **Database** (3): query, schema, migration
- **Security** (2): secret_scanner, permission_manager
- **Web** (3): search, crawler, screenshot
- **Interactive** (2): ask_question, confirm
- **VCS** (2): git_ops, git_operations
- **Admin** (4): install, permissions, sudo, prompts
- **System** (8): os, process, env, git, docker, cron, screenshot, info

### 3. LLM Providers (`sago/llm/`)

5 providers with unified interface:
- **Gemini**: gemini-2.0-flash, gemini-2.0-pro
- **OpenAI**: gpt-4o, gpt-4o-mini
- **Claude**: claude-3-5-sonnet, claude-3-5-haiku
- **OpenRouter**: Multiple models
- **Ollama**: Local models (llama3.1, codellama, etc.)

### 4. Memory System (`sago/memory/`)

- **RAGMemory**: Retrieval-augmented generation with search
- **SessionCompactor**: Compacts long conversations
- **InputSummarizer**: Summarizes long inputs
- **UserProfileManager**: Persistent user preferences

### 5. Workflow System (`sago/workflow/`)

Temporal-style workflows with:
- Stateful execution
- Pause/resume/cancel
- Retry with backoff
- Built-in templates (ticket, review, deploy, incident)

### 6. MCP Server (`sago/mcp/`)

Model Context Protocol support for:
- Tool exposure via MCP
- External tool integration
- Server/client architecture

### 7. TUI System (`sago/tui/`)

Modern Textual-based terminal UI with:
- **AgentDashboard**: Real-time agent status with spinner, color coding
- **HandoffFlow**: Visual handoff tracking between agents
- **OrchestrationPlanWidget**: Orchestration plan display
- **BackgroundTaskManager**: Parallel task tracking
- **Parallel Execution**: `/parallel` command with ThreadPoolExecutor
- **Agent Colors**: 12-color palette, deterministic per agent
- **Feedback Loops**: Agent-to-agent feedback requests
- **RecursionGuard**: Prevents infinite delegation loops

## Data Flow

```
User Input
    ↓
Smart Input Processor (summarize, extract keywords)
    ↓
TUI / CLI
    ↓
Production Engine
    ├── Task Delegator (classify, route)
    ├── Agent Spawner (CrewAI execution)
    ├── Tool Execution (70 tools)
    ├── LLM Provider (streaming)
    └── Cache (hit/miss)
    ↓
Response (streaming, collapsible panels)
    ↓
Session Manager (persistence)
    ↓
Token Tracker (cost estimation)
```

## Configuration

### Environment Variables
```bash
GEMINI_API_KEY=...        # Google Gemini
OPENAI_API_KEY=...        # OpenAI
ANTHROPIC_API_KEY=...     # Claude
OPENROUTER_API_KEY=...    # OpenRouter
```

### Project Config (`config.sago.json`)
```json
{
  "agents": {
    "python-engineer": {
      "enabled": true,
      "system_prompt_override": "...",
      "temperature": 0.8
    }
  },
  "permissions": {
    "allow_shell": true,
    "allow_ssh": false
  }
}
```

## Key Features

1. **Smart Delegation**: Auto-routes tasks based on language, file type, keywords
2. **Parallel Execution**: ThreadPoolExecutor for concurrent agent tasks
3. **Feedback Loops**: Agent-to-agent feedback requests with structured handoffs
4. **Recursion Protection**: Depth limit (5), visit limit (15), cycle detection
5. **Input Summarization**: Long inputs (>500 words) auto-summarized
6. **Collapsible UI**: Thinking blocks, tool usage, errors in panels
7. **Agent Dashboard**: Real-time agent status with spinner and color coding
8. **Token Tracking**: Cost estimation per provider
9. **Intelligent Caching**: Content-based dedup, TTL, LRU
10. **Session Persistence**: SQLite + JSON summaries
11. **Multi-Language**: Python, JS, TS, Java, Go, Rust, etc.
12. **MCP Support**: External tool integration
13. **Error Recovery**: Automatic retry, fallback agents
14. **Streaming**: Real-time response with thinking traces
