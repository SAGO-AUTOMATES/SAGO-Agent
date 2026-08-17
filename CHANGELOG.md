# Changelog

All notable changes to the SAGO project are documented in this file.

## [0.1.11] - 2026-08-17

### Fixed
- **`sago chat` Rate Limit on Gemini (`sago/engine/simple_executor.py`)**:
  - Chat tasks now skip tool definitions when calling the LLM. Previously ~30 tools were sent even for simple greetings, hitting Google's tool-use rate quotas.
- **`sago chat` Multi-Turn Interactive Mode (`sago/main.py`)**:
  - Rewrote `sago chat` from single-shot to interactive: maintains conversation history across turns, supports `exit`/`quit`/`help`.
  - Works with both Google Gemini (native SDK) and OpenAI-compatible providers.
  - `sago chat "hello"` now sends the message then drops into an interactive loop; `sago chat` starts interactive directly.
- **Auto-Fallback to Available LLM Provider (`sago/llm/tui_providers.py`, `sago/main.py`)**:
  - When the configured default provider (e.g. `gemini`) has no API key set, the system now automatically falls back to a provider that has a valid key (checks `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` in order).
  - `_get_configured_model()` now selects a model matching the available API key instead of always using the config default.
  - `sago chat` now uses `resolve_active_llm_config()` for proper provider/model resolution.
  - `resolve_active_llm_config` reads `load_setting("model")` from `~/.sago/settings.json` (TUI settings).
- **TUI Rich Markup Crash (`sago/tui/helpers.py`)**:
  - `_add_system_message` now uses `Text.from_markup(_escape(content))` to safely render content while preventing LLM hallucinations like `[c8caa51e]` from being interpreted as Rich style tags.
  - `_render_markdown()` escapes ALL LLM content with `rich.markup.escape()` BEFORE converting markdown to Rich markup, preventing `MissingStyle` crashes.
  - `_add_plan_card()` escapes `plan_text` before rendering with `markup=True`.
  - `_add_tool_call()` escapes tool argument keys and values to prevent markup injection.
- **TokenUsage Deserialization Crash (`sago/tracking/token_tracker.py`)**:
  - `to_dict()` included `total_tokens` (a computed property), but `TokenUsage.__init__()` doesn't accept it, causing `TypeError` on `_load()`.
  - Fixed by filtering data to only valid dataclass field names before construction.
- **PeerInfo Data Loss on Deserialization (`sago/peers/manager.py`)**:
  - `to_dict()` was missing `ssh_key`, `sago_path`, `python_version`, `last_seen` fields, losing data on round-trip.
  - All fields now serialized and deserialized correctly.
- **MemoryEntry Missing Fields (`sago/memory/rag.py`)**:
  - `to_dict()` was missing `user_id` and `last_accessed` fields. Both now included.
- **Silent Error Swallowing (`sago/cache/intelligent.py`, `sago/memory/rag.py`, `sago/peers/manager.py`)**:
  - Replaced bare `except Exception: pass` blocks with `logger.warning()` for visibility into load failures.
- **Config Model Mismatch (`sago/config/sago.yaml`, `sago/config/llm_providers.yaml`)**:
  - Updated default Gemini model from `gemini-2.0-flash` to `gemini-2.5-flash` to match TUI settings.

## [0.1.10] - 2026-08-16

### Added (Hidden Dev Mode, Auto Session Title, Collapsible Enhancement & Highlights Summary)
- **Intelligent One-Liner Session Title Synthesis (`sago/engine/prompt_enhancer.py`)**:
  - Automatically synthesizes concise, high-impact session titles based on the user's initial objective and intent (e.g. `Fix authentication token refresh bug in auth.py`, `Explore codebase module topology`, `General greeting & capabilities inquiry`).
  - Persisted directly to SQLite session database, `chat_export.md`, `trace.md`, `/sessions` list, and terminal summary banners.
- **Clean Inline Collapsible Prompt Enhancement (`sago/tui/helpers.py`)**:
  - Rendered directly inside the exchange turn box as a sleek collapsible card with clean typography and minimal emoji clutter, maintaining clear visual hierarchy with user prompt, tool executions, and assistant responses.
- **Structured Execution Trace Reports (`sago/tracking/dev_tracer.py`)**:
  - Replaced heavy unformatted JSON dumps in `trace.md` with structured Markdown summaries, latency metrics, and collapsible `<details><summary>View Raw Payload</summary>` inspection blocks.
- **Robust Typo-Tolerant Greeting & Capability Resolution (`sago/engine/intent_classifier.py`, `sago/engine/prompt_enhancer.py`)**:
  - Fast-paths conversational greetings (`hellos`, `heya`, `howdy`), capability questions (`what can you do`, `wehta can yiu do`, `skills`), and small talk into lightweight chat context without dumping 30,000-character project instruction files or triggering code synthesis.
- **Post-Exit Session Highlights Summary Banner (`sago/tui/app.py`, `sago/main.py`)**:
  - Displays comprehensive session statistics (Session ID, One-Liner Title, Total Queries, Messages, Tool Calls breakdown, In/Out Tokens, Specialist Agents, Resume command, and Dev Mode artifact paths) cleanly to the terminal upon exit or detach.
- **Hidden Developer Mode Configuration (`~/.sago/`)**:
  - Configurable via `~/.sago/config.json`, `~/.sago/settings.json`, `~/.sago/config.yaml`, or environment variable `SAGO_DEV_MODE=1` / `SAGO_DEV_MODE=true`.
  - When enabled, TUI and CLI start with Developer Mode active by default; `F2` live trace inspection and deep telemetry are immediately available.
- **TUI Home Screen Dev Mode Green Dot Indicator**:
  - Prominent visual badge (`● Dev Mode ON ─ F2 Dev Traces Active`) displayed directly below the SAGO logo on the welcome home screen.
- **Automatic Project-Specific Session Artifact Export on Exit**:
  - Automatically exports full session artifacts to `.sago/data/<session_id>/`:
    - `chat_export.md`: Complete Markdown formatted transcript with all user, assistant, agent messages, and tool outputs.
    - `trace.md`: Formatted execution trace with Mermaid interaction graph, call hierarchy, and latency breakdown.
    - `trace.json`: Full machine-readable event stream and graph nodes/edges.
  - Informs the user on exit with resume instructions: `sago tui --resume <session_id>` along with paths to all generated artifacts.
- **Dynamic Multi-Factor Specialist Agent Resolution (`sago/agents/registry.py`)**:
  - Eliminated hardcoded generic agent defaults; dynamically resolves the optimal specialist from 340+ built-in profiles (e.g. Next.js $\rightarrow$ `nextjs-engineer`, Spring Boot $\rightarrow$ `spring-boot-engineer`, Azure $\rightarrow$ `azure-engineer`, Rust $\rightarrow$ `rust-engineer`, Go $\rightarrow$ `go-engineer`, Terraform $\rightarrow$ `terraform-engineer`, etc.) based on keywords, referenced file extensions (`.tsx`, `.java`, `.rs`, `.go`, `.tf`), and workspace project context.

## [0.1.9] - 2026-08-16

### Added (Dynamic Registry & Intelligent Transparent Prompt Enhancement)
- **Dynamic Tool Registry (`sago/tools/registry.py`)**:
  - Replaced hardcoded tool dictionaries with live dynamic discovery across all 69+ tools and 13 categories (`coding`, `file`, `system`, `network`, `shell`, `ssh`, `database`, `session`, `security`, `admin`, `interactive`, `web`, `vcs`).
  - Dynamic discovery for third-party plugins and bridged Model Context Protocol (MCP) tools.
  - Interactive parameter and argument schema extraction for `sago tools <tool_name>`.
- **Dynamic Help System (`sago help`)**:
  - Categorized CLI dashboard showing live agent counts, dynamic tool counts, skills, plugins, and active models.
  - Subcommand parameter inspection with fuzzy matching suggestions for mistyped commands.
- **Intelligent Context-Adaptive Prompt Enhancer (`sago/engine/prompt_enhancer.py`)**:
  - Automatically synthesizes core objectives, detects workspace targets/files, and injects acceptance criteria and domain constraints without requiring users to write "perfect prompts".
  - **Comprehensive Real-World Trigger Coverage**: Handles bug troubleshooting (`why is this not working`, `it crashes`, `500 error`), architecture/codebase exploration (`projects`, `project structure`, `how does X work`), performance optimization (`this feels slow`, `memory leak`), code cleanup (`clean this up`), DevOps (`how do I run this`, `dockerize`), and QA testing (`pytest`).
  - **Zero-Token Local Overhead**: Completely local, deterministic, and fast-path cached; internal enhancer logs and metadata never pollute the main LLM payload.
- **Selective Context Assembly for Conversational Queries (`sago/engine/context_assembler.py`)**:
  - For casual chat, weather questions, greetings, and general explanations, heavy repository scans, Git status diffs, AST symbol maps, RAG chunks, and `.sago/instructions.md` dumps are automatically omitted.
- **Transparent TUI Prompt Enhancement Cards (`sago/tui/helpers.py`)**:
  - Mounted directly in active exchange turns in the Textual TUI (`/delegate`, `/chain`, and chat), displaying synthesized goals, detected files, verification criteria, and the exact injected prompt.
- **Developer Telemetry Integration (`sago/tracking/dev_tracer.py`)**:
  - Emits `PROMPT_ENHANCED` trace events exportable to OpenTelemetry, Prometheus, JSON, and Markdown formats.

### Fixed (Critical Bugs)
- **RAG Context Layer Completely Broken** (`sago/engine/context_assembler.py:202-208`):
  - `getattr(r, "file_path")` always returned `""` because `HybridSearchResult` stores data in `r.chunk`, not directly on `r`.
  - Fixed to use `r.chunk.file_path` and `r.chunk.content`. The entire RAG code snippet injection pipeline is now functional.
- **Thread Safety in Project Graph** (`sago/memory/project_graph.py:260`):
  - `self._lock` was declared but never acquired. Concurrent `build_graph()` calls corrupted shared `self.edges` and `self.nodes` dicts.
  - Merge loop now wrapped in `with self._lock:` for thread-safe parallel access.
- **Dead Code in Symbol Index** (`sago/memory/symbol_index.py:275-293`):
  - Unreachable code after `finally: conn.close()` block referenced closed variables.
  - Removed dead code; function now returns cleanly.

### Enhanced (Language Support)
- **20 Languages Now Supported** (was 6):
  - Added Ruby (`.rb`), PHP (`.php`), Kotlin (`.kt`), Scala (`.scala`), Swift (`.swift`), C# (`.cs`), Dart (`.dart`), Elixir (`.ex`, `.exs`), Lua (`.lua`) regex parsers in `symbol_graph.py`.
  - Added all new extensions to `project_graph.py` candidate discovery, language detection, and file scanning.
- **Java Parser Added** (`sago/memory/project_graph.py`):
  - New `_parse_java_local()` method extracts `import` edges, class/interface/enum symbols, and method definitions with `@*Mapping` endpoint detection (Spring Boot).
- **C++ Parser Added** (`sago/memory/project_graph.py`):
  - New `_parse_cpp_local()` method extracts `#include` edges, namespace/class/struct symbols, and function definitions.
- **Go Import Edge Parsing** (`sago/memory/project_graph.py`):
  - `_parse_go_rust_local()` now extracts `import` block and single-line `import` statements, creating edges to `module:` nodes.
- **Rust Import Edge Parsing** (`sago/memory/project_graph.py`):
  - `_parse_go_rust_local()` now extracts `use` statements, creating edges to `module:` nodes.
- **JS/TS Import Resolution** (`sago/memory/project_graph.py`):
  - Relative imports (`./utils`, `../lib`) now resolve to actual `file:` nodes when the target file exists.
  - External package imports store only the package root name (e.g., `module:react`).

### Enhanced (Python AST Parser)
- **Nested Class Support** (`sago/memory/symbol_graph.py`):
  - Recursive extraction of nested classes via `_extract_class()` helper.
- **Type Annotations in Signatures** (`sago/memory/symbol_graph.py`):
  - Signatures now show `x: int, y: str = "hello"` instead of just `x, y`.
- **Decorator Distinction** (`sago/memory/symbol_graph.py`):
  - `@property`, `@staticmethod`, `@classmethod` now have distinct `symbol_type` values instead of generic `"method"`.
- **Dataclass Field Extraction** (`sago/memory/symbol_graph.py`):
  - `@dataclass` class fields (annotated assignments) extracted as `"field"` child symbols.

### Enhanced (Architecture & Classification)
- **Multi-Signal Architecture Classification** (`sago/memory/project_graph.py`):
  - Replaced naive substring matching with priority cascade: directory name (strongest) → path substring (fallback).
  - Eliminates false positives like `utils/api_helper.py` → "Presentation".
- **Expanded Endpoint Detection** (`sago/memory/project_graph.py`):
  - Added `@blueprint.route`, `@api_view`, `@api.route`, `.route(`, `.api_route(`, `@controller`, `@action` for Flask/Django/Express/FastAPI.
- **Data Model False Positive Reduction** (`sago/memory/project_graph.py`):
  - Changed from `"model" in name.lower()` to exact suffix matching: `*Model`, `*Schema`, `*DTO`, `*Entity`, `*Record`, `*Table`.

### Enhanced (Search & Index)
- **FTS5 Query Sanitizer Fixed** (`sago/memory/symbol_index.py`):
  - Preserves dotted names: `os.path.join` → searches `os* AND path* AND join*` instead of stripping dots.
- **Symbol Index Update Cooldown** (`sago/memory/symbol_index.py`):
  - `update_index()` now has 30-second cooldown instead of running on every `get_ranked_repo_map()` call.
- **Hybrid Indexer Thread Safety** (`sago/memory/hybrid_indexer.py`):
  - Global singleton now protected by `threading.Lock()`.
- **Smart Zero-Match Fallback** (`sago/memory/hybrid_indexer.py`):
  - Zero-match fallback now uses stratified sampling (max 20 per chunk type) instead of scanning all chunks.

### Enhanced (Monorepo Support)
- **Workspace Detection** (`sago/memory/project_graph.py`):
  - Detects npm/yarn/pnpm workspaces (`package.json`), Cargo workspaces (`Cargo.toml [workspace]`), Nx/Turbo/Lerna configs, and pyproject.toml workspaces.
  - `build_graph()` scans all workspace roots in parallel.

### Enhanced (Token Budget & Overflow)
- **Token Budget System** (`sago/engine/context_assembler.py`):
  - New `_TokenBudget` class with priority-based truncation (12K token default limit).
  - Prevents context overflow by truncating sections by priority.
- **Mermaid ID Collision Prevention** (`sago/memory/project_graph.py`):
  - Counter suffix prevents ID collisions when different paths produce the same sanitized ID.
- **Quote Escaping in Mermaid** (`sago/memory/project_graph.py`):
  - Labels with `"` now escaped to `'` to prevent Mermaid syntax errors.
- **Overflow Indicators** (`sago/memory/project_graph.py`):
  - All truncated renderers now show "... and N more" indicators (ER diagram, flowchart, ASCII tree, LLM blueprint).

## [0.1.7] - 2026-08-16

- **SQLite Checkpoint Store & Multi-Project Snapshot Tracking**:
  - Checkpoints are now indexed and stored directly in SQLite (`~/.sago/data/sago.db`) with `checkpoints` table and `CheckpointStore`.
  - Added support for cross-project / external path snapshotting and restoration preserving original absolute paths.
  - Added proactive pre-modification workspace auto-snapshot notifications in TUI.
- **Automated MCP Server Manager & Dynamic Tool Bridge (`/mcp`)**:
  - Added `sago.mcp.manager.MCPManager` to discover standard Claude/Anthropic format `mcpServers` configs across `~/.sago/mcp_servers.json`, `.sago/mcp_servers.json`, and `mcp.json`.
  - Dynamically bridges remote MCP tools into native Sago `BaseTool` instances with Pydantic argument schemas so agents can call external MCP tools autonomously.
  - Added `/mcp [list|test|reload]` and `/skills [query|reload]` commands.
- **Extensibility & Authoring Documentation (`docs/SKILLS_AND_PLUGINS.md`)**:
  - Comprehensive guide covering `SKILL.md` authoring, Python `BasePlugin` lifecycle hooks, and MCP server configuration.
- **Deduplicated & Streamlined TUI Slash Command Suite**:
  - Consolidated 50+ scattered commands into 4 clean, focused categories: Core & Workflow, Agent Orchestration, Code Intelligence & VCS, and Settings & Runtime.
  - Merged single-action commands into clean subcommands: `/perms [list|allow|block|reset]`, `/todo [list|done]`, `/session [list|save|load|reset]`, `/tasks [list|cancel]`, `/buttons [toggle|on|off]`, and `/graph [arch|process|models|flow|summary]`.
  - Updated `/help` command reference and interactive shortcuts modal (`F1` / `?`).
- **Strict Monospace Column Alignment & Zero Emoji Breakage**:
  - Eliminated variable-width emoji glyphs from autocompletion menus and shortcut sheets.
  - Standardized fixed-width monospace column padding (`{key:<12}`) for razor-sharp rendering across all terminal emulators and fonts.
- **Deep Recursive Fuzzy File Autocomplete & Context Injection (`#<file>`)**:
  - Upgraded `rank_files_smart` with recursive workspace file tree indexing and fast in-memory TTL caching.
  - Prioritizes Git-modified files (`[mod]`) and displays human-readable file sizes (`53 KB`).
  - Automatically resolves referenced file paths recursively and injects their code content directly into the LLM prompt context.
- **Structured AST Repo Map & Automated Topology Priming**:
  - Implemented `generate_clean_tui_map` in `SymbolGraph` to render structured Markdown cards with line counts and query filtering (`/map [query]`).
  - Injected topological project graph summaries into `ContextAssembler` when queries touch architecture, dependencies, or data models.
- **Comprehensive Garbage Collection & Cleanup System (`sago clean`)**:
  - Implemented `sago.cleanup` module to safely purge stale, unneeded, and regenerable files across `~/.sago` and project `.sago` directories.
  - Added `sago clean` CLI command (defaulting to `--all`) with rich summary reporting of scanned items, deleted files, and bytes of disk space reclaimed.
  - Supports fine-grained CLI flags: `--cache`, `--backups`, `--checkpoints`, `--db`, `--logs`, `--days <N>`, `--keep-checkpoints <N>`, `--keep-backups <N>`, and `--dry-run`.
- **Database Session Garbage Collection & Physical Defragmentation**:
  - Automatically identifies and purges empty sessions (0 messages or blank whitespace) and noise-only sessions from `~/.sago/data/sago.db`.
  - Removes orphaned foreign key records and executes SQLite `VACUUM` and `PRAGMA optimize` to reclaim physical disk blocks.
- **Subsystem Auto-Retention Policies**:
  - **`ChangeTracker`**: Automatically caps session backup files to 50 files per session and auto-prunes older session backup folders beyond the 10 most recent sessions.
  - **`CheckpointManager`**: Added `prune_checkpoints()` method and automatic retention capping (retains newest 20 snapshots upon creation).
- **TUI Maintenance Commands**:
  - Added `/checkpoint prune [keep]` and `sago checkpoint prune` to easily trim older workspace snapshots.

## [0.1.6] - 2026-08-15

- **Modular TUI Architecture Decomposition**:
  - Refactored monolithic `sago/tui/app.py` into dedicated, cohesive mixins: `sago/tui/styles.py` (layout CSS & 11 themes), `sago/tui/orchestrator.py` (agent delegation, chaining, routing & parallel execution), `sago/tui/processor.py` (LLM streaming, token budgeting, tool execution loop & test-fix verification), and `sago/tui/commands.py`.
- **Autonomous Task Continuity (`/continue` command)**:
  - Added the `/continue` command across TUI models, commands, and app routers to resume interrupted tasks from the exact previous execution state after hitting rate limits (`429`) or network timeouts without token waste or repeating completed steps.
- **SQLite Database Persistence & Enhanced CLI History**:
  - Fixed immediate message writes and flushes into `~/.sago/data/sago.db` in `_save_message`.
  - Added automatic session title tagging from the user's initial prompt.
  - Enhanced `sago sessions` CLI output with message counts, tool counts, and formatted status indicators.
  - Enabled short prefix matching for session IDs in `sago history <session_id>` (e.g. `sago history 85ccb9d7`).
- **TUI Quick Action Bar Visibility Controls**:
  - Added `/show`, `/hide`, and `/buttons [on|off|toggle]` commands to hide or show the bottom action buttons for a clean, power-user terminal experience with settings persistence.
- **Sub-Millisecond Inverted Index & Disk Caching for Hybrid Search**:
  - `HybridCodeIndexer` now builds an in-memory inverted term index and caches AST tokenized chunks and statistics to disk (`~/.sago/cache/hybrid_index/`).
  - Search term frequency lookup changed from $O(\text{tokens})$ linear scan to $O(1)$ dictionary lookups, accelerating query speeds to sub-millisecond range.
  - Lifted the default indexing limit from 2,000 to 50,000 files for seamless large codebase scale.
- **Mesh Task Execution Engine & Port Isolation**:
  - Added receiver-side task execution for `task_request` messages with automatic `task_result` responses in `MeshNetwork`.
  - Moved default UDP mesh port to `7655` (configurable via `SAGO_MESH_PORT`) to eliminate collisions with the TCP daemon on `7654`.
- **In-Process Python Syntax Verification & Queue Batching**:
  - `ProjectVerifier` now performs fast in-process `py_compile` checks, avoiding subprocess spawn overhead on file verification.
  - `ContinuousVerifier` now batches consecutive queued file verification tasks to prevent N+1 linter storms during bulk file modifications.
- **TUI Progressive Live Streaming for Parallel Agents**:
  - Parallel agent execution (`/parallel`) now progressively mounts each agent's individual response card, prompt context, and Rich syntax-highlighted code output in real-time as each worker finishes, without waiting for the full batch.
  - Dynamically updates individual agent badges on the `#parallel-bar` (`⏳ Waiting` $\rightarrow$ `⚡ Running` $\rightarrow$ `✓ Done (Xs)`).
- **Interactive Onboarding Wizard & System Diagnostics**:
  - Added `sago onboard` and enhanced `sago setup` with persistent YAML configuration, directory scaffolding, database initialization, and Git hooks prompts.
  - Added `sago doctor` CLI command for comprehensive environment and subsystem health diagnostics (Python runtime, keys, database, ports, agents).
- **Configurable Subsystems & Execution Limits**:
  - Added schema models and YAML configurations for `search`, `daemon`, `mesh`, and `executor` in `sago.yaml` and `loader.py`.
  - Made context TTL, token compaction thresholds, circular detection limits, and todo auto-completion criteria configurable via YAML and environment variables.
- **Agent Profile Aliases & 100% Valid Handoff Resolution**:
  - Added `AGENT_ALIASES` in `sago/agents/registry.py` mapping legacy names (`system-architect`, `test-runner`, `ui-designer`, etc.) to canonical profiles.
  - 100% of all 1,570 profile handoff targets now cleanly resolve.
  - Fixed `_plan_chain` in `sago/agents/spawner.py` to route to registered agent profile IDs.

### Fixed
- **Security & Injection Prevention**:
  - Sanitized table and index identifiers in SQLite `PRAGMA` queries in `sql_schema.py` and filtered query parameters in `workflow/templates.py`.
  - Changed default daemon server binding from `0.0.0.0` to `127.0.0.1` (`SAGO_DAEMON_HOST`).
  - Passed sudo passwords via subprocess `stdin` to prevent credentials from appearing in process tables.
  - Enforced fail-closed permission checks in `MCPServer.call_tool()`.
- **Thread-Safe Singletons & State Storage**:
  - Added `threading.Lock()` mutex synchronization to error handlers, recovery managers, token trackers, caches, and config loaders.
- **TUI & Workflow Import Safety**:
  - Made `OpenAI` import lazy in `sago/llm/tui_providers.py`, allowing TUI, workflow, and local Ollama execution without crashing when `openai` is not installed.
- **Native Google GenAI SDK Compatibility**:
  - Updated `GeminiProvider` in `sago/llm/gemini.py` to support modern `google.genai` SDK with fallback to `google.generativeai`.

## [0.1.5] - 2026-08-14

### Added
- **Sub-Agent & Delegation Dynamic Model/Provider Inheritance**:
  - `resolve_active_llm_config()` in `sago/llm/tui_providers.py` dynamically resolves the user's active provider (Google, OpenAI, Claude, OpenRouter), selected model, and corresponding API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.).
  - `AgentDelegator` and `SpawnAgentTool` now execute subagents using the parent's active model instead of defaulting back to `openrouter/free`.
- **Instant `@` Agent Autocompletion & Delegation Auto-Suggest**:
  - Typing `@` immediately displays prioritized specialist agents (orchestrator, python-engineer, frontend, backend, debugger, reviewer, etc.) with role descriptions.
  - Added smart autocompletion for `/delegate <agent>`, `@delegate <agent>`, `/chain <agent1,agent2>`, and `@chain <agent1,agent2>`.
  - Selecting a delegation suggestion automatically pre-fills the input field so users can seamlessly append their task.
- **Distributed Mesh Authentication & Replay Protection**:
  - Cryptographic HMAC-SHA256 signature generation (`MeshMessage.sign()`) and verification (`MeshMessage.verify()`) using `SAGO_MESH_SECRET`.
  - Replay attack mitigation rejecting packets older than 300 seconds.
- **Copy to Clipboard (`/copy`, `/clip`, `📋 Copy Code` button)**:
  - Inline `📋 Copy Code` action button appears beneath every syntax-highlighted code block. Click to copy; button briefly flashes `✓ Copied!` and auto-resets after 2 seconds.
  - `/copy` — copies last assistant response (thinking blocks stripped).
  - `/copy code` / `/copy snippet` — copies last code block from conversation.
  - `/copy all` / `/copy chat` / `/copy history` — copies entire chat history (all roles) as plain text.
  - `/clip` alias also supported.

### Fixed
- **SQLite Multi-Thread Exit Failure (`ProgrammingError`)**:
  - Resolved `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread` by setting `check_same_thread=False` on connection pooling and cleanly handling thread teardown in `close_all_connections()`.
- **Dynamic Version Resolution Across TUI & CLI**:
  - TUI welcome screen, `/version` command, and Click CLI status dynamically resolve the installed package version from `sago.__version__` / `importlib.metadata`.
- **Markup Artifact Rendering (`[bold cyan]` visible as literal text)**:
  - Root cause: user-typed content interpolated into Rich markup strings without escaping. Fixed with `rich.markup.escape()` throughout `ExchangeTurnCard` and `CollapsibleOutputCard` in `sago/tui/helpers.py`.
  - All prompt previews, header titles, and collapsible card titles are now safely escaped before being rendered as Rich markup.
- **Full User Prompt Display in Chat**:
  - `ExchangeTurnCard` now renders the complete user prompt in the card body (`.exchange-user-prompt`), not just a 75-char truncated header snippet. Multi-line inputs fully readable.
- **Jarring Hover Effects Removed**:
  - Removed distracting background/color flashes on `.exchange-prompt-header:hover` and `.card-header:hover`.
  - Scrollbar hover toned down from bright `#58a6ff` to a subtle `#484f58`.
  - Shortcuts dialog close button hover now uses neutral muted tones instead of harsh white.
- **Wired Real LLM Analysis to `/graph ai|review|llm|summary`**:
  - `/graph ai` and `/graph review` now call `generate_with_provider` with the live AST graph context and produce real architectural summaries, not hardcoded strings.
  - Architecture layers (`ProjectGraph.to_architecture_diagram`) rewritten with dynamic multi-layer classification (Presentation, Orchestration, Specialist Agents, Memory/State, Integration/Mesh, Tests).

### Enhanced
- **Packaging & CI / Build Dependencies**:
  - Added `build>=1.2.0` and `twine>=5.0.0` to dev dependencies; verified clean package builds and twine checks.
- **Chat Box Alignment & Theme Consistency**:
  - Added `.exchange-user-prompt` and `.exchange-divider` CSS rules plus per-theme overrides across all 10 themes (Nord, Dracula, Monokai, Tokyo Night, Solarized Dark, Cyberpunk, Catppuccin Mocha, Gruvbox Dark, Rosé Pine, Light).
  - Each theme now explicitly sets proper foreground colors for user prompts, dividers, and assistant responses.

## [0.1.3] - 2026-08-14

### Added
- **Hybrid BM25 + Dense Semantic Vector Search (`/search` & `sago search`)**:
  - Probabilistic BM25 term weighting combined with zero-dependency local 128-dimensional dense vector embeddings.
  - Sub-millisecond natural language search across 1,000+ codebase files.
  - Registered `hybrid_code_search` agent tool in `sago.tools.coding`.
- **Continuous Background Linting & Self-Healing Diagnostics (`ContinuousVerifier`)**:
  - Non-blocking background worker thread validates written/modified files in real time.
  - Generates line-level diagnostic issues and actionable prompt feedback for autonomous self-healing loops.
- **OpenTelemetry & Prometheus Telemetry Exporters (`/dev export otel|prometheus` & `sago telemetry`)**:
  - Standard OTel Trace JSON specification export with microsecond spans, tool execution events, and error codes.
  - Prometheus text exposition format metrics for tool execution counters, token latencies, and event histograms.
- **Hierarchical Memory Pyramids & Zero-Redundancy Handoff Deltas (`HierarchicalMemoryPyramid`)**:
  - 3-tiered context compaction (Architectural Goals $\to$ Working Deltas $\to$ Active Turns).
  - Compact state delta serialization saving ~70% context overhead during multi-agent handoffs.
- **Bottom-Right Collapse Buttons (`CollapsibleOutputCard` & `ExchangeTurnCard`)**:
  - Pinned `[▲ Collapse Message]` and `[▲ Collapse Output]` action buttons on the bottom-right corner of all message turn cards and command outputs.
  - Eliminates the need to scroll back up to the top of long responses or graph reports to collapse them.
- **Terminal-Native Visual Flowchart (`/graph flow` / `/project_graph flow`)**:
  - Structured Unicode component and data flow connection diagram showing active relationships and dependency branches directly inside the terminal.
- **Dedicated Viewport Keyboard Scroll Shortcuts**:
  - `PageUp` / `PageDown`: Fast page scroll.
  - `Shift+Up` / `Shift+Down` & `Ctrl+Up` / `Ctrl+Down`: Line-by-line smooth viewport scroll.
  - `Ctrl+Home` / `Ctrl+End`: Instant jump to top / bottom.

### Enhanced & Performance Optimizations
- **Asynchronous Non-Blocking `/graph` Execution**:
  - Background daemon thread worker (`threading.Thread`) prevents UI freezes and keeps Textual TUI at a fluid 60 FPS.
- **Multi-Threaded Parallel AST Parsing & In-Memory TTL Caching**:
  - `ThreadPoolExecutor` parallelizes parsing across multi-core CPUs, cutting scan latency by 4x–8x.
  - Thread-safe TTL cache delivers sub-millisecond (< 1ms) view switching between `/graph arch`, `/graph er`, `/graph flow`, and `/graph process`.
- **Rich Markdown & Syntax Highlighting**:
  - Formats all code blocks, Markdown headers, and ASCII box diagrams with Monokai syntax highlighting and clean line wraps.
- **Instant Input Focus Restoration**:
  - Automatically restores active typing focus to `#msg-input` immediately upon widget mounting.
- **Smart Project & Data Graph (`/project_graph` & `sago project-graph`)**:
  - Deep multi-language dependency and symbol extraction (Python, TypeScript, JavaScript, Rust, Go, SQL, Java, C/C++).
  - Layered System Architecture Box Diagrams (`/project_graph arch`).
  - Autonomous Process & Execution Flywheel Maps (`/project_graph process`).
  - Core Data Model & Schema extraction (Pydantic, SQLAlchemy, Tortoise, SQL tables).
  - Interactive Mermaid Flowchart export and compact LLM prompt context injection.
  - File dependency topology tree with symbol count badges and imports.
  - Registered `project_graph` agent tool in `sago.tools.coding.project_graph_tool`.
- **Detach Mode & Background Job Management**:
  - `sago run --detach` (`-d`): Spawns tasks into background daemon workers so users can immediately and safely close their terminal tabs.
  - `sago attach [ID]`: Reconnects to detached TUI sessions or streams background task logs in real-time.
  - `/detach` TUI command: Cleanly exits the interface while leaving background tasks and multi-agent operations active.

### Enhanced & Fixed
- **Web Search Multi-Tier Fallback (`sago.tools.web.search`)**:
  - Added DuckDuckGo organic HTML search extraction with automatic fallback to Instant Answers and optional Tavily API.
  - Eliminates empty results on technical documentation and programming queries.
- **Virtual Environment Self-Healing Verifier (`sago.engine.verifier`)**:
  - Added automatic virtual environment detection (`.venv`, `venv`, `uv run`, `poetry run`).
  - Added multi-language verification suite support for TypeScript (`tsc`), Rust (`cargo check`), Go (`go vet`), and Python (`ruff`, `pytest`).
- **Multi-Language AST Symbol Parsing (`sago.memory.symbol_graph`)**:
  - Expanded pattern extractors to support Go structs/interfaces/funcs, Rust structs/enums/traits/impls, and TypeScript interfaces/type aliases.
