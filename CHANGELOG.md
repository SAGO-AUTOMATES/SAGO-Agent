# Changelog

All notable changes to the SAGO project are documented in this file.

## [0.1.14] - 2026-08-26 (Unreleased — summary waste & dev default fixes)

### Fixed
- **Summary waste on “so what was the sumamry?” (2e6cdf4e-ea4):** Previously re-ran full tool loops (`grep`, `execute_shell`) and gave generic README summary, wasting tokens. Now:
  - `sago/tui/processor.py` detects summary intent via spec regex `r"\b(summar|what was done|what did you do)\b"` (+ typo-tolerant `sumamry`/`summar*` fallbacks) and short-circuits **before** tool discovery — 0 new tool calls.
  - Builds categorized summary **by agent** from `self.messages` + `ToolUsageStore.get_all()` + `DevTracer.get_recent_traces()` + cached `PROJECT_ANALYSIS.md` / `Session.get_full_export()` (per-agent tools, output, cost, output file). Single LLM call with `tool_choice: none` and injected Reference Context, not a tool loop; falls back to deterministic `_build_local_summary_markdown()` if LLM unavailable. Heavy `context_assembler.assemble()` also short-circuits RAG/BM25/symbol search for summary intents.
  - `sago/sessions/manager.py` adds `get_summary_by_agent()` / `is_summary_intent()` helpers reusing `Session.get_full_export()` so fresh sessions also do 0 re-analysis.
- **Auto Summary Card by agent:** `sago/tui/helpers.py` adds `_add_summary_by_agent_card()` (`Collapsible(title="● Summary — by agent", collapsed=False)`) with per-agent sections (tools `✓/✗` + args, output preview, token cost, output file `PROJECT_ANALYSIS.md` cached). `sago/tui/orchestrator.py` auto-mounts it after **chain** (20/20 + HandoffFlow), **delegate**, **parallel**, and **orchestrate** completions so user sees summary without asking.
- **Systematic thinking → tool order & per-agent headers:** All flows (`processor` normal + `orchestrator` chain/parallel/delegate/orchestrate) now share `set_execution_callbacks(on_tool/on_tool_result/on_thinking with agent_name)` → `ExchangeTurnCard.mount_sequential()` (seq_id, inserts `before=.exchange-response` in call order) so `thinking1 → tool1 → thinking2 → tool2 …` is deterministic, not bulk at end. Titles are now `● {agent} — Technical Reasoning` and `● OK Tool: read_file by @agent`. `DevTracer.record_thinking` dedups only same `source` + same `[:300]` within 5s (not global 120s), preserving architect vs python-engineer distinction. DB `messages.metadata.thinking_blocks[{seq, agent, text, timestamp}]` + `tool_usage.created_at` are sorted on reload (`commands._load_session` / `_switch_session`) via `mount_sequential`, so `sago tui --resume 2e6cdf4e-ea4` shows 3 thinking cards in same positions and `Inspector 19 events 6 LLM 3 thinking`.
- **Docs caps & updates:** `docs/tui_chat_structure.md` → `docs/TUI_CHAT_STRUCTURE.md` (caps, canonical) rewritten with systematic pipeline §20, per-agent headers §12, DB persistence/reload §8/§20, Inspector §16, auto Summary — by agent §15, uniform chain/parallel/delegate handling table §20d. `docs/DEVELOPER_MODE.md`, `docs/ARCHITECTURE.md`, `docs/COMMANDS.md`, `README.md` updated to mention dev default ON, systematic order, zero-tool summary.
- **Dev mode default ON until beta:** `sago/config/sago.yaml` `settings.dev_mode: true # TODO: flip to false at 1.0` (was `false`), `sago/config/loader.py` `SettingsConfig.dev_mode: True` + `init_user_config` `dev_mode: True` (both TODO), `sago/tui/app.py` `developer_mode: True # TODO: flip to false at 1.0`. Fresh `rm -rf ~/.sago/data && sago tui` shows Inspector (`F2`) without `/dev on`; `is_dev_mode_enabled()` now returns true on clean install.

### Changed
- `README.md` Key Capabilities + Documentation table now lists `TUI_CHAT_STRUCTURE.md`, `DEVELOPER_MODE.md` (default ON), `ARCHITECTURE.md` (systematic order + summary).
- `docs/COMMANDS.md` `/dev` row notes default ON until 1.0; `/summary` row documents natural-language short-circuit.
- `docs/ARCHITECTURE.md` adds § Systematic Thinking → Tool Order and § Summary — By Agent, and notes `context_assembler`/`processor`/`sessions/manager` summary short-circuit.

### Validation
- `ruff check` clean (other than pre-existing `google.genai` missing in CI)
- `pytest tests/unit/test_tui_turn_container.py` — `test_tui_developer_mode` updated to expect default ON where applicable, reload order preserved
- Manual: summary query `so what was the sumamry ?` creates 1 LLM event, 0 `TOOL_DISPATCH` events (DevTracer delta), no new `grep_content`/`execute_shell`; fresh session `developer_mode == True`

## [0.1.13] - 2026-08-23

### Fixed
- **TUI crash on tool output containing `[`/markup-like text** (`MarkupError` killed layout
  mid-task): all dynamic content mounted into `markup=True` widgets (spinner text, enhanced
  prompt cards, orchestrate plan/step lines, approval bar) is now escaped or rendered with
  markup disabled.
- **Orchestration died instantly with false `Cycle detected: X -> X`** for every step:
  - recursion guard is now passed explicitly through chain (sequential + parallel) and
    orchestration flows instead of thread-local lookup (thread idents get recycled across
    commands, inheriting stale guard state)
  - removed the orchestrator's redundant raw-name `guard.exit()` that mismatched aliased
    agent names (`code-reviewer` -> `reviewer`) and left permanent residue
  - `RecursionGuard.exit()` removes by value; genuine A->A self-recursion is still blocked
- **Turn cards stretched to fill the viewport / clipped assistant answers**: Textual's
  `Vertical` default `height: 1fr` overridden with `height: auto` for exchange cards;
  plan-widget step list (`#plan-steps`) sized by content so steps actually render
- **`/chain` mangled tasks**: only `->` is an arrow separator now (bare `>` survives);
  agent words validated against the registry instead of a `-in-word` heuristic
- **Chains aborted on prose false-positives**: `_is_error_result` now reacts only to hard
  failure markers ("no errors found" no longer kills a chain)
- **`/provider gemini` set model to garbage `gemini/free`**: `/provider` now validates names,
  lists providers with API-key status, seeds the provider default model
- **Plan steps trimmed mid-word** (`task[:60]`): full task text renders with wrapping
- **Silent loss of orchestration summary** when the turn card was missing: falls back to
  `#messages` with a warning log
- **Nondeterministic hallucinated-agent mapping** in orchestration plans: fuzzy match is
  now sorted + longest-overlap scoring
- **Reasoning-model tool payload (test-only `stealth/ox-alpha`)**: auto-filters 73→10 essential tools to avoid empty `tool_calls` (`sago/engine/simple_executor.py:1998`) — verified with live complex tasks (not default model)
- **Multi-language syntax guard**: `sago/tools/file/resilient_editor.py:168` now guards `.py/.js/.ts/.go/.rs/.java/.rb/.php/.sh/.c/.cpp` via native checkers with auto-rollback

### Added
- **Provider registry** (`sago/llm/registry.py`) — single source of truth for provider
  metadata (aliases like gemini/google & claude/anthropic, env keys, default models, base
  URLs, billing links, fallback order). Adding a new AI provider is ONE declarative
  `register_provider(ProviderSpec(...))` call; unknown providers now fail loudly instead of
  silently routing to OpenRouter. TUI key resolution, `/model`, `/provider`, autocomplete,
  secret masking and error hints all read from it.
- **`review_changes` tool** (`sago/tools/vcs/review.py`): review-ready context for
  `working_tree`, `staged`, `commit <ref>`, `branch vs base`, and GitHub PR diffs via
  `gh pr diff`. Auto-discovered by the tool registry.
- **Approval transparency**: the orchestration approval bar lists exactly which agents will
  run which tasks before you press Y/N.
- ~30 previously hidden-but-working commands (`/plan`, `/retry`, `/continue`, `/pr`,
  `/commit`, `/sessions`, `/handoff`, `/dashboard`, `/cancel`, `/copy`, ...) added to
  `/help` and autocomplete.

### Changed
- Tool-call collapsibles inside turn cards use compact spacing (no more blank-line
  marathons during long agent runs)
- `tools.yaml`: corrected stale `git_ops` module path/class; registered `review_changes`

## [0.1.12] - 2026-08-20

### Added
- **Dependency auto-installer** (`sago/tools/ensure_dep.py`):
  - Platform detection: OS, distro (Ubuntu/Debian/CentOS/RHEL/Fedora/Alpine/Arch/Amazon/OpenSUSE/SLES/Rocky/Alma/Gentoo/NixOS/Void), arch, libc, WSL, containers
  - Distro version detection from `/etc/os-release`
  - Package manager detection: apt, dnf, yum, apk, pacman, brew, winget, choco, scoop, nix, xbps, portage, zypper
  - System info: Python version, CPU count, total memory (Linux/macOS/Windows)
  - Per-binary auto-installers with OS-specific logic
  - Smart binary lookup: checks ~/.local/bin, ~/.cargo/bin, ~/.nvm/*/bin, ~/go/bin, etc. before installing
- **Kubernetes tool** (`k8s_ops`): kubectl wrapper with k3s auto-install (lightweight, ~50MB)
- **Browser automation tool** (`browser`): Headless browser via Playwright with auto-install
- **Code sandbox tool** (`code_sandbox`): Isolated Python/JS/Bash execution with auto-install
- **Configuration system improvements**:
  - Auto-creates `~/.sago/config/` with default YAML files on first run
  - Auto-creates `~/.sago/settings.json` with sensible defaults
  - Supports `~/.sago/config/` directory with individual YAML files
  - Complete config documentation in `docs/CONFIGURATION.md`
- **Docker tool improvements**: Fixed shell injection, explicit `list[str]` args, auto-install Docker Engine
- **Git tool improvements**: Merged system/vcs into unified tool with 22 operations, always `shell=False`
- **Web fetch improvements**: HTML-to-text conversion, content-type filtering, 10MB max size
- **Web search improvements**: Serper API support, in-memory TTL cache, 3-engine fallback

### Changed
- `ensure_dep.py` added as centralized dependency management utility
- `docker_ops` now uses explicit argument lists instead of string interpolation
- `git_operations` expanded from 6 to 22 operations with same safety guarantees
- `k8s_ops` prefers k3s over standalone kubectl on Linux
- `ensure_sago_dirs()` now creates all directories including backups/, cache/, prompts/
- Tool count: 70 → 72

### Fixed
- Docker shell injection vulnerability (args were interpolated into shell commands)
- Git operations tool overlap (merged system/vcs into single tool)
- Web search missing Serper API support
- Web fetch returning raw HTML instead of clean text
- Config loading now checks `~/.sago/config/` directory for user overrides
- Removed junk file `settings.jsonu` from default directory structure

## [0.1.11] - 2026-08-19

### Added
- **Centralized logging** (`sago/logging_config.py`): daily file rotation to `~/.sago/logs/sago.log`, 7 days retention, DEBUG in file + INFO on console
- **Comprehensive logging across 30+ modules**: database, LLM calls, orchestrator, TUI processor, tools, sessions, permissions, config, memory, workflows, agents, peers, token tracking
- `log_exception()` utility for consistent error logging
- Rate limit retry with exponential backoff for chat (Gemini + OpenAI)
- API key masking in error messages (`_mask_secret()`, `_sanitize_error_message()`)
- Chat history size limit (50 messages) to prevent memory growth
- Version fallback in `sago/version.py` fixed (0.1.7 -> 0.1.11)

### Fixed
- **TUI Session Resume Card Rendering (`sago/tui/commands.py`)**:
  - Fixed ExchangeTurnCard responses rendering outside the card boundary when loading/resuming a session.
  - Response container (`_response_container`) is created asynchronously during `compose()` and was not available immediately after `mount()`. Now uses `call_after_refresh` to defer response mounting until the DOM is ready.
  - Both `_load_session` and `_switch_session` now use the two-phase mount pattern (mount cards first, then mount responses after compose).
- **TUI Session Resume CSS Class Consistency (`sago/tui/commands.py`)**:
  - Agent tags and markdown bodies now use `exchange-assistant` class during session load, matching normal operation styling.
- **TUI Session Resume Welcome Screen (`sago/tui/commands.py`)**:
  - `_load_session` and `_switch_session` now call `_hide_welcome_screen()` before mounting messages.
- **TUI Session Resume Title Restore (`sago/tui/commands.py`)**:
  - Session title is now restored from database when loading/resuming a session.
- **TUI Active Exchange Card After Load (`sago/tui/commands.py`)**:
  - `_active_exchange_card` is now set to the last card after session load, so new messages render inside a proper exchange card.
- **TUI Tool Usage Placement on Session Load (`sago/tui/commands.py`)**:
  - Tool usage calls are now matched to the correct exchange card by comparing `created_at` timestamps, instead of being dumped into a single summary on the last card.
- **TUI Empty Session on Resume (`sago/tui/app.py`)**:
  - `_init_session` now skips creating a new session when `--resume` flag is passed, preventing orphaned empty sessions.
- **TUI Session Flag Initialization (`sago/tui/app.py`)**:
  - `_loading_session`, `_active_exchange_card`, `_message_store`, and `current_session_title` are now initialized in `on_mount` for reliable session state management.
- **Temp file resource leaks** in `hallucination_verifier.py` (12 sections, all use `try/finally` with guaranteed `os.unlink()`)
- **Markup escaping inconsistency** in TUI markdown rendering (`_render_markdown_rich()` now escapes before rendering)
- **Silent `except: pass` patterns** replaced with proper logging (~50+ blocks across 9 files)
- **CodeNode.to_dict()** now includes all fields (docstring, defaults, is_classmethod, etc.)
- **Duplicate pattern definitions** consolidated in hallucination verifier
- **Click `resultcallback`** deprecated API fixed to `result_callback`
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

### Added
- **Shared Hallucination Verifier Module (`sago/engine/hallucination_verifier.py`)**:
  - 9-stage verification pipeline used by all execution paths (simple_executor, unified streaming, orchestrator, production).
  - Fabrication phrase detection with 80+ patterns and tool-category cross-referencing.
  - Hedging/subtle claim detection catches "this should work", "trust me", "no breaking changes" without tool evidence.
  - Claim vs tool-history verification cross-references read, write, search, analyze, execute claims against actual tool calls.
  - Tool result integrity checking via SHA-256 hashing detects plugin tampering.
  - Confidence scoring (0-100) based on tool usage, fabrication signals, hedging claims, and code validity.
  - Response sanitization strips hallucinated sentences when confidence is low.
  - `verify_response()` convenience function and `ResponseVerifier` singleton.
- **Extended Language Support**:
  - Brace matching for 15 languages: Python, JavaScript, TypeScript/TSX, Go, Rust, Java, C, C++, C#, Ruby, PHP, Kotlin, Swift, Scala, Dart.
  - External syntax checkers for 12 languages: `py_compile`, `gofmt`, `rustfmt`, `node --check`, `npx tsc`, `javac`, `gcc -fsyntax-only`, `bash -n`, `ruby -c`, `php -l`, `ktlint`, `swiftc -parse`, `scalac`, `dotnet script`.
- **TUI Hallucination Sanitization (`sago/tui/processor.py`)**:
  - Streaming path now runs shared verifier and sanitizes responses before display.
  - No-tool content path also runs verifier for fabrication detection.
- **Streaming Path Verification (`sago/engine/unified.py`)**:
  - `stream()` method now runs hallucination verification on final response.
- **Tool Result Integrity (`sago/engine/hallucination_verifier.py`, `sago/engine/simple_executor.py`)**:
  - `ToolResultIntegrity` class records original tool results and detects plugin modifications.
  - Wired into simple_executor after plugin hook_tool_result.
- **Lightweight "query" Intent Type (`sago/engine/intent_classifier.py`)**:
  - New `query` task type for quick information lookups ("what's in this file", "where is X defined", "explain this function").
  - Routes simple file/concept questions to a lightweight prompt that reads ONLY the specific file and gives a brief answer.
  - Prevents aggressive multi-file analysis for simple questions.
- **Complexity Assessment (`sago/engine/intent_classifier.py`, `sago/engine/prompt_enhancer.py`)**:
  - Intent classifier now returns `complexity` field (simple/medium/complex) for all classifications.
  - Prompt enhancer skips enhancement for truly simple queries (greetings, single words, basic math).
  - Complex tasks get structured multi-step workflows; simple tasks get minimal overhead.
- **Multi-Language Code Block Validation (`sago/engine/simple_executor.py`)**:
  - `_detect_code_hallucinations` now validates JS/TS/Go/Rust code blocks for syntax (not just Python).

### Changed
- **Expanded Fabrication Phrases (`sago/engine/simple_executor.py`)**:
  - Added 15+ hedging/subtle claim phrases to inline fabrication detection.
  - Now detects "this should work", "trust me", "rest assured", "I'm confident" without tools.
- **Expanded Anti-Hallucination Constraints (`sago/engine/prompt_enhancer.py`)**:
  - 16 constraints (up from 12) including hedging phrase detection.
- **Stronger Anti-Hallucination Prompts (`sago/engine/simple_executor.py`)**:
  - All prompts now include "COMPLEXITY CALIBRATION" section to prevent overthinking.
  - Added prohibition on overclaiming ("production-ready", "fully tested") without tool evidence.
  - Analyze prompt now says "read the ONE file that defines X" instead of "inspect ALL relevant files thoroughly".
- **Expanded Fabrication Detection (`sago/engine/simple_executor.py`)**:
  - 18 fabrication phrase patterns detect common LLM lies ("I've verified", "tests pass", etc.).
  - Hallucinated symbol detection flags function/class names not found in tool results.
  - Overconfidence detection flags strong claims without any tool usage.
- **Enhanced Claim Verification (`sago/engine/simple_executor.py`)**:
  - 8 claim categories checked: read, write, test, fix, analyze, execute, search, file paths.
  - Analyze claims now require read/search tools specifically (not just any tool).
- **Improved Confidence Scoring (`sago/engine/simple_executor.py`)**:
  - Factors in tool diversity, excessive fabrication, and response length appropriateness.
  - Heavy penalty for 3+ fabrication signals.
- **String/Comment-Aware AST Brace Counting (`sago/tools/coding/ast_editor.py`)**:
  - `_estimate_end_line` now skips braces inside string literals, single-line comments, and block comments.
- **Prompt Enhancer Anti-Hallucination (`sago/engine/prompt_enhancer.py`)**:
  - 10 anti-hallucination constraints (up from 6).
  - Universal acceptance criteria: "never claim verification without running actual tools".
- **TUI Verification Display (`sago/tui/processor.py`)**:
  - Shows actual issue details and tool call count instead of generic "minor issues".
- **Lightweight Query Routing (`sago/tui/processor.py`, `sago/engine/simple_executor.py`)**:
  - Query and chat tasks skip heavy context assembly, skill injection, and learning store.
- **Updated Documentation**:
  - README.md: Added hallucination detection section, updated language support.
  - ARCHITECTURE.md: Added hallucination_verifier.py to engine layer.
  - PROJECT.md: Added hallucination_verifier.py and prompt_enhancer.py to file tree.
  - FLOWS.md: 6-layer safety matrix (was 5), added hallucination detection layer.
  - ERRORS.md: Added hallucination warning categories and issue types.
  - CONTRIBUTING.md: Added hallucination prevention test suite reference.

### Tests
- 100+ unit tests passing.
- New test classes: `TestQueryIntentRouting`, `TestFabricationPhrasePatterns`, `TestStringAwareBraceCounting`, `TestIntentClassifierComplexity`.

## [0.1.10] - 2026-08-16

### Added (Hidden Dev Mode, Auto Session Title, Collapsible Enhancement & Highlights Summary)
- **Intelligent One-Liner Session Title Synthesis (`sago/engine/prompt_enhancer.py`)**:
  - Automatically synthesizes concise, high-impact session titles based on the user's initial objective and intent.
- **Clean Inline Collapsible Prompt Enhancement (`sago/tui/helpers.py`)**:
  - Rendered directly inside the exchange turn box as a sleek collapsible card.
- **Structured Execution Trace Reports (`sago/tracking/dev_tracer.py`)**:
  - Replaced heavy unformatted JSON dumps with structured Markdown summaries.
- **Post-Exit Session Highlights Summary Banner (`sago/tui/app.py`, `sago/main.py`)**:
  - Displays comprehensive session statistics to the terminal upon exit or detach.
- **Hidden Developer Mode Configuration (`~/.sago/`)**:
  - Configurable via `~/.sago/config.json`, `~/.sago/settings.json`, `~/.sago/config.yaml`, or environment variable `SAGO_DEV_MODE=1`.
- **Dynamic Multi-Factor Specialist Agent Resolution (`sago/agents/registry.py`)**:
  - Dynamically resolves the optimal specialist from 340+ built-in profiles.

## [0.1.9] - 2026-08-16

### Added (Dynamic Registry & Intelligent Transparent Prompt Enhancement)
- **Dynamic Tool Registry (`sago/tools/registry.py`)**:
  - Replaced hardcoded tool dictionaries with live dynamic discovery across all 69+ tools and 13 categories.
- **Intelligent Context-Adaptive Prompt Enhancer (`sago/engine/prompt_enhancer.py`)**:
  - Automatically synthesizes core objectives, detects workspace targets/files, and injects acceptance criteria.
- **Transparent TUI Prompt Enhancement Cards (`sago/tui/helpers.py`)**:
  - Mounted directly in active exchange turns in the Textual TUI.

### Fixed (Critical Bugs)
- **RAG Context Layer Completely Broken** (`sago/engine/context_assembler.py`):
  - Fixed `getattr(r, "file_path")` to use `r.chunk.file_path`.
- **Thread Safety in Project Graph** (`sago/memory/project_graph.py`):
  - Merge loop now wrapped in `with self._lock:` for thread-safe parallel access.
- **Dead Code in Symbol Index** (`sago/memory/symbol_index.py`):
  - Removed unreachable code after `finally: conn.close()` block.

## [0.1.7] - 2026-08-16

### Added
- **SQLite Checkpoint Store & Multi-Project Snapshot Tracking**.
- **Automated MCP Server Manager & Dynamic Tool Bridge (`/mcp`)**.
- **Comprehensive Garbage Collection & Cleanup System (`sago clean`)**.
- **Database Session Garbage Collection & Physical Defragmentation**.
- **Deep Recursive Fuzzy File Autocomplete & Context Injection (`#<file>`)**.

## [0.1.6] - 2026-08-15

### Added
- **Modular TUI Architecture Decomposition**.
- **Autonomous Task Continuity (`/continue` command)**.
- **SQLite Database Persistence & Enhanced CLI History**.
- **TUI Progressive Live Streaming for Parallel Agents**.
- **Interactive Onboarding Wizard & System Diagnostics**.

## [0.1.5] - 2026-08-14

### Added
- **Sub-Agent & Delegation Dynamic Model/Provider Inheritance**.
- **Instant `@` Agent Autocompletion & Delegation Auto-Suggest**.
- **Copy to Clipboard (`/copy`, `/clip`, `📋 Copy Code` button)**.

## [0.1.3] - 2026-08-14

### Added
- **Hybrid BM25 + Dense Semantic Vector Search (`/search` & `sago search`)**.
- **Continuous Background Linting & Self-Healing Diagnostics**.
- **OpenTelemetry & Prometheus Telemetry Exporters**.
- **Smart Project & Data Graph (`/project_graph` & `sago project-graph`)**.
- **Detach Mode & Background Job Management**.
