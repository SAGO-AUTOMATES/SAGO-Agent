# SAGO Architecture

This document describes the high-level architecture of SAGO, a Python multi-agent
orchestration system with a Textual TUI, an auto-discovered tool system, a memory
pyramid, and an orchestration engine.

All references below point to real modules in the `sago/` package and the
`agents/` directory. Paths are given so you can jump straight to the source.

## Component overview (textual diagram)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              USER (terminal)                               │
└───────────────────────────────┬──────────────────────────────────────────┘
                                 │ types a message / runs a command
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  TUI  (sago/tui)                                                          │
│  app.py · commands.py · processor.py · orchestrator.py · styles.py ·       │
│  helpers.py · models.py · trace_viewer.py · smart_input.py · widgets/     │
│  - Textual App: renders chat, agent dashboard, background task manager     │
│  - CommandHandlers parse /command input and route to subsystems           │
│  - MessageProcessorMixin handles LLM streaming & tool execution loop       │
│  - AgentOrchestrationMixin manages delegation, chains & parallel execution │
└───────────────────────────────┬──────────────────────────────────────────┘
                                 │ user message + effort level + profile
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Orchestrator / Delegator  (sago/orchestrator)                            │
│  delegator.py (TaskDelegator, TaskType, TaskComplexity, TaskPlan)         │
│  engine.py     (loads agent profiles, maps a plan -> agent execution)     │
│  - Classifies the task (CODE_WRITE, DEBUG, SECURITY, ...)                  │
│  - Picks a primary + supporting agents and an execution chain             │
└───────────────────────────────┬──────────────────────────────────────────┘
                                 │ TaskPlan + agent profile(s)
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Engine / Executor  (sago/engine)                                         │
│  simple_executor.py  (native function-calling loop, _discover_tools)       │
│  unified.py · production.py · intent_classifier.py · verifier.py · ...    │
│  hallucination_verifier.py (9-stage response verification pipeline)        │
│  - Builds OpenAI-style tool schemas from BaseTool.args_model              │
│  - Runs the LLM loop, calls tools, handles permission/timeout/errors      │
│  - Detects and sanitizes hallucinated content in responses                │
└───────┬───────────────────────────┬───────────────────────────┬──────────┘
        │ tool call                  │ profile/skills           │ errors
        ▼                            ▼                           ▼
┌──────────────────────┐  ┌──────────────────────────┐  ┌──────────────────┐
│ Tools (sago/tools)   │  │ Agents/Profiles          │  │ Errors           │
│ base.py BaseTool     │  │ agents/registry.py       │  │ sago/errors      │
│ *_tool.py (auto-     │  │ agents/profiles/*.py     │  │ handler.py       │
│  discovered via      │  │ agents/loader.py         │  │ (severity+retry) │
│  rglob of *.py)      │  │ agents/base.py           │  │                  │
└──────────┬───────────┘  └───────────┬──────────────┘  └──────────────────┘
           │ result                     │ selected profile
           ▼                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Memory  (sago/memory)                                                    │
│  compaction.py (HierarchicalMemoryPyramid, SessionCompactor,              │
│                 InputSummarizer) · rag.py · hybrid_indexer.py ·           │
│  change_tracker.py · project_instructions.py · symbol_index.py           │
└──────────────────────────────────────────────────────────────────────────┘
           ▲
           │ persists turns, deltas, summaries
┌──────────────────────────────────────────────────────────────────────────┐
│  Sessions  (sago/sessions/manager.py)                                     │
│  Multi-session + multi-thread manager (SessionStatus, ThreadStatus).      │
│  Persists/reloads conversation state; restores legacy statuses.          │
└──────────────────────────────────────────────────────────────────────────┘
           ▲
┌──────────────────────────────────────────────────────────────────────────┐
│  Settings / Config  (sago/settings.py · sago/config)                      │
│  settings.py  : global ~/.sago/settings.json + project .sago/settings.json │
│  config/      : sago.yaml, agents.yaml, tools.yaml, llm_providers.yaml    │
│  Paths resolved via sago/paths.py (get_sago_home)                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Message flow: TUI → orchestrator → engine → tool → memory → response

1. **TUI intake** (`sago/tui/app.py`, `sago/tui/commands.py`).
   The Textual `SagoApp` captures user input (free text or a `/command`).
   `CommandHandlers` and `UIHelpers` normalize the message, attach an effort
   level and the active agent profile, then hand the request to the engine.
   Summary queries (`so what was the summary?`, `summarize what you did`, `what was done`) are detected via `processor._is_summary_intent()` regex `r"\b(summar|what was done|what did you do)\b"` (+ typo tolerance `sumamry`) and short-circuited to cached analysis — 0 new tool calls (see § Summary by Agent below).

2. **Orchestration** (`sago/orchestrator/delegator.py`, `sago/orchestrator/engine.py`).
   `TaskDelegator` classifies the message into a `TaskType` (e.g. `CODE_WRITE`,
   `DEBUG`, `SECURITY`, `RESEARCH`) and a `TaskComplexity`, then builds a
   `TaskPlan` selecting a `primary_agent` plus `supporting_agents`, a `chain`,
   and `parallel_groups`. `engine.py` loads the matching profile(s) from
   `agents/registry.py` / `agents/loader.py`. Summary intents bypass orchestration entirely (handled in TUI layer).

3. **Execution loop** (`sago/engine/simple_executor.py`).
   The executor converts each discovered `BaseTool`'s Pydantic `args_model`
   into an OpenAI function-calling schema (see `_build_openai_tools`), injects
   them into the LLM call, and runs the native function-calling loop. When the
   model requests a tool, the executor instantiates the tool class and calls
   `tool.run(...)` (which wraps `_run` with validation + error recovery).
   For summary intents, `context_assembler.assemble()` returns empty context (no BM25/RAG) and executor is not entered — single LLM call with `tool_choice: none` injects cached `PROJECT_ANALYSIS.md` instead.

4. **Tool execution** (`sago/tools/base.py`).
   `BaseTool.run` calls the subclass `_run`, catches exceptions, consults the
   learning store (`sago/learning.py`) for known fixes, records the failure,
   and returns a safe error string instead of crashing. Cross-platform helpers
   like `_run_command`, `_expand_path`, and `_get_temp_dir` live on the base.
   Per-agent headers (`by @agent`) and systematic `mount_sequential` ensure `thinking1 → tool1 → thinking2 → tool2` ordering is preserved across all flows (chain/parallel/delegate/normal).

5. **Memory update** (`sago/memory/compaction.py`, `sago/memory/*.py`).
   After each turn, the conversation is fed to the `HierarchicalMemoryPyramid`
   (`record_turn`) and/or `SessionCompactor`. Tool results, file modifications,
   and decisions are promoted into pyramid tiers so long-range context survives
   compaction (see "Memory pyramid" below). Thinking blocks are stored per-agent with `seq` for reload fidelity.

6. **Session persistence** (`sago/sessions/manager.py`, `sago/database.py`).
   The session manager stores the running conversation, thread state, and
   status. It supports pausing/resuming and migrating legacy status values on
   reload so a session is never left invalid. `MessageStore` persists `thinking_blocks: [{seq, agent, text, timestamp}]` + `tool_usage` with `created_at`; reload restores via `mount_sequential` in seq/timestamp order (see `docs/TUI_CHAT_STRUCTURE.md` §8, §20).

7. **Response render**.
   The final assistant message (and any tool outputs) are streamed back to the
   TUI widgets (`AgentDashboard`, message log, `BackgroundTaskManager`).
   After chain/orchestration/parallel/delegate completion, `helpers._add_summary_by_agent_card()` auto-mounts `Collapsible(title="● Summary — by agent", collapsed=False)` categorized by agent (tools, cost, output file) so user sees summary without asking.

## Tool auto-discovery

Tools are **auto-discovered** at runtime by walking the `sago/tools` package.

- The canonical discovery lives in `sago/tools/registry.py:147` (`discover_tools()`),
  mirrored in `sago/engine/simple_executor.py:484` (`_discover_tools()`). It does `tools_dir.rglob("*.py")`,
  skips files starting with `_` and `base.py`, imports each module as
  `sago.tools.<dotted.path>`, and collects every class that is a `BaseTool`
  subclass with a non-empty `name`.
- The same discovery pattern is mirrored in `sago/workflow/langgraph_engine.py`
  (`_discover_tools`), `sago/tools/crewai_wrappers.py` (`_discover_all_tools`),
  and `sago/mcp/server.py` so every integration stays in sync.
- Discovered classes are keyed by `obj.name` into a `dict[str, type[BaseTool]]`
  and cached behind a lock (`_tool_discovery_lock`).

**How to add a tool:** drop a single module anywhere under `sago/tools/**/`
that defines a `BaseTool` subclass with `name`, `description`, and an
`args_model`. No registration call is needed — the rglob picks it up on the
next import. Place it in the right category subdirectory (e.g. `system/`,
`file/`, `coding/`, `network/`) for organization, though the directory does not
affect discovery.

## Memory pyramid (sago/memory/compaction.py)

`compaction.py` implements a multi-tier structured memory system for ultra-long
conversations and zero-loss token compaction:

- **Base (Working)**: `active_working_turns` — high-fidelity recent message
  turns and active tool calls.
- **Tier 1 (Architectural)**: `architectural_goals`, `architectural_decisions`
  — foundational goals and invariants, promoted when text matches patterns
  like `goal:`, `decided to`, `we will use`.
- **Tier 2 (Delta)**: `modified_files`, `milestone_history` — file modifications
  and milestone markers (`completed`, `done:`, `shipped`).
- **Tier 3 (Semantic Summary)**: `semantic_summary` — an extractive/LLM summary
  of working turns (`distill()` / `_extractive_summarize`).
- **Tier 4 (Deep Distillation)**: `deep_distillation` — a coherent paragraph
  combining tiers 1–3 that survives aggressive compaction.

`HierarchicalMemoryPyramid.assemble_compact_pyramid(max_working_turns=6)`
renders the token-optimized context. `SessionCompactor` wraps this with
`build_context_window` / `compact_with_llm` and falls back to rule-based
summarization (`InputSummarizer`) when no API key is present.

## Session management (sago/sessions/manager.py)

`SessionManager` supports multiple concurrent sessions, each with multiple
parallel threads (`ThreadPoolExecutor`). Key types:

- `SessionStatus`: `IDLE`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`.
- `ThreadStatus`: `PENDING`, `RUNNING`, `WAITING`, `COMPLETED`, `FAILED`,
  `CANCELLED`.

Legacy/unknown status strings are migrated on restore (`_SESSION_STATUS_MIGRATIONS`,
`_THREAD_STATUS_MIGRATIONS`) so old session files never fail to load. Sessions
are the persistence boundary that the orchestrator and executor read/write
between turns.

## Settings & config

- `sago/settings.py` loads a **global** config at `~/.sago/settings.json` and a
  **project** config at `<project>/.sago/settings.json`, merged together. It is
  validated as a JSON object (`SettingsData = RootModel[dict[str, Any]]`) and
  raises `ValueError` on malformed input.
- `sago/config/` holds YAML definitions: `sago.yaml`, `agents.yaml`,
  `tools.yaml`, `llm_providers.yaml`, loaded/validated by `sago/config/loader.py`.
  **v0.1.14:** `sago.yaml` `settings.dev_mode: true # TODO: flip to false at 1.0` — default ON until beta (`loader.py` `SettingsConfig.dev_mode: True`, `app.py` `developer_mode: True`, `loader.init_user_config` `settings.json dev_mode: True`). Fresh install shows Inspector without `/dev on`.
- Home/project paths resolve through `sago/paths.py` (`get_sago_home`).

## Systematic Thinking → Tool Order (v0.1.14)

All TUI flows enforce `thinking1 → tool1 → thinking2 → tool2 …` in execution order via `ExchangeTurnCard.mount_sequential()` (seq-tagged, inserts before `.exchange-response` but respects call order). `on_thinking`/`on_tool_result` callbacks are set per-flow with `agent_name` so headers are per-agent (`● {agent} — Technical Reasoning`, `by @agent`). `DevTracer.record_thinking` dedups only same `source` + same `[:300]` within 5s (no global coalesce), so architect vs python-engineer reasoning stays distinct. Reload reconstructs via `thinking_blocks[].seq` sorted and `tool_usage.created_at` timestamp matching.

## Summary — By Agent (v0.1.14)

Two mechanisms eliminate token waste on “so what was the summary?”:

- **Short-circuit in TUI:** `processor._is_summary_intent()` detects via `r"\b(summar|what was done|what did you do)\b"` (+ typo `sumamry`) and calls `_handle_summary_intent()` — gathers `self.messages` + `ToolUsageStore.get_all()` + `DevTracer.get_recent_traces()` + `PROJECT_ANALYSIS.md`/`Session.get_full_export()`, builds categorized markdown via `_build_local_summary_markdown()` (per-agent tools/output/cost/files) and makes a **single** LLM call with `tool_choice: none` (no tool loop) injecting that context. `context_assembler.assemble()` also short-circuits heavy RAG/BM25 for summary intents.
- **Auto card after orchestration:** `helpers._add_summary_by_agent_card()` mounts `Collapsible(title="● Summary — by agent", collapsed=False)` with per-agent sections after chain/orchestrate/parallel/delegate completes, so user sees summary without asking.

See `docs/TUI_CHAT_STRUCTURE.md` §15 and `docs/COMMANDS.md` `/summary` for details.

## Errors (sago/errors)

`handler.py` provides structured error recovery for tool/agent execution:

- `ErrorSeverity` (StrEnum): `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- `RecoveryStrategy` (StrEnum): `RETRY`, `FALLBACK`, `SKIP`, `ABORT`, `ASK_USER`.
- `ErrorContext` dataclass bundles `tool_name`, the exception, attempt count,
  severity, and traceback.

The executor layer pairs this with the per-tool `run()` error guard so a single
failing tool never aborts the whole agent loop.

## Agents & profiles (agents/)

- `agents/profiles/*.py` ship 340+ specialist agent profiles (e.g.
  `api-engineer.py`, `security-testing-engineer.py`). Each profile is loaded by
  `agents/loader.py` and registered in `agents/registry.py`.
- `agents/base.py` defines the agent model; `agents/handoff.py`,
  `agents/spawner.py`, and `agents/optimizer.py` handle routing, sub-agent
  spawning, and optimization. The orchestrator selects a profile via the
  `TaskPlan` produced by `TaskDelegator`.
