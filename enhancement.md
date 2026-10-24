# SAGO Enhancement Plan (Non-Breaking)

**Status:** Draft for review  
**Principle:** Enhancements only. No breaking changes to existing TUI, commands, tools, sessions, or user workflows. Every change must be additive, feature-flagged where risky, and covered by regression tests.

---

## 0. Ground Rules (MUST FOLLOW)

1. **No breaking changes.** Existing CLI commands, TUI screens, tool names, config keys, session file formats, and public APIs remain valid. Add new capabilities alongside; deprecate only with a migration path.
2. **Feature flags.** Any behavior change that could alter output (parsing, routing, verification, streaming) must be gated by a config flag defaulting to the *current* behavior, so users opt in.
3. **Backward compatibility.** Session JSON, settings JSON, and YAML configs from prior versions must still load (extend schemas, never remove fields).
4. **Additive tooling.** New tools get new names; existing tool schemas only gain optional fields. Never rename or remove a tool without a compatibility shim.
5. **Tests before merge.** Each enhancement ships with unit + (where applicable) integration tests; coverage floor must not drop.
6. **No event-loop blocking.** New work that touches the TUI must be async or offloaded; never call blocking subprocess/file IO on the UI thread.
7. **Observability first.** New paths emit traces/metrics consistent with `DevTracer`/OTel.
8. **Rollback.** Every phase must be revertible via config flag or git revert without data migration.

---

## 1. Why SAGO Responses Are Less Reliable Than Reference Agents

### 1.1 Parsing & code intelligence gaps
- **Regex-only for non-Python languages.** `symbol_graph.extract_generic_symbols` and `hybrid_indexer._chunk_file` use line-anchored regex with fixed 30-60 line windows. Modern syntax (arrow functions, generics, decorators, nested classes) is missed or mis-bounded, so retrieved context is wrong or incomplete.
- **Duplicate Python chunks.** `codebase_indexer._chunk_python` uses `ast.walk`, which descends into nested nodes, emitting methods both as class children and standalone functions. This inflates context and confuses the model.
- **No call-graph or scope resolution.** Symbols are keyed by `sym:{file}#{name}` with no qualified names or caller/callee edges, so "who calls X" cannot be answered accurately.
- **Hash-vector "embeddings"** are character n-gram hashes, not semantic. Retrieval quality plateaus on paraphrased queries.
- **Result:** The model receives approximate, duplicated, sometimes incorrect code context, which directly causes hallucinated or incomplete answers.

### 1.2 Tool runtime gaps
- **Fragile schema conversion.** `_pydantic_field_to_schema` mishandles `Literal`, `Union`, `Optional`, enums, defaults, and nested models. The LLM can be given a wrong or lossy argument schema, leading to malformed tool calls.
- **No standard output truncation/spill.** Large tool results can overflow the context window; only some tools truncate individually.
- **No uniform timeout.** A hanging tool (or compiler) blocks the loop and the TUI.
- **Permission boundaries are implicit** and bypassed in YOLO mode, risking unsafe execution.
- **All tools sent every call.** ~80+ schemas per request waste tokens and dilute tool selection accuracy.
- **Skills are static prompt text**, not lazy, validated, permission-gated resources.
- **Result:** Tool calls fail or return oversized/untrusted output, forcing the model to guess.

### 1.3 Verification gaps
- **Regex-heuristic grounding only.** The verifier checks phrase patterns and file-path existence, but not whether referenced **symbols** exist. A claim about a nonexistent function can pass.
- **No pre-execution validation.** Tool args (e.g., stale `old_string`) are not checked before execution.
- **No diff validation.** Edits are not verified against the original file content before write.
- **No multi-pass self-correction.** The verifier sanitizes once and returns; it never feeds issues back to the model for correction.
- **Heavy sync compiler subprocesses** on the hot path add latency and can freeze the UI.
- **Over-flagging.** With empty `tool_history` (orchestrator path), legitimate content may be stripped; confidence scoring is uncalibrated.
- **Result:** Either unverified claims slip through, or valid content is stripped, reducing trust and completeness.

### 1.4 Streaming & responsiveness gaps
- **No true token streaming.** The executor uses blocking `chat.completions.create`; `StreamingResponse` is a manual accumulator.
- **Blocking IO on the event loop.** Subprocess calls, index builds, and compiler checks can freeze the Textual UI.
- **No early cancellation** in the main executor path.
- **Result:** Slower perceived responsiveness and frozen UI under load.

### 1.5 Orchestration gaps
- **Keyword-only routing** ignores most of the 340+ profiles and is brittle to phrasing.
- **Static chains** with no dynamic replanning.
- **Process-global singletons** (indexers, registries, learning store) cause cross-session/cross-agent contamination.
- **No formal message bus** for inter-agent handoffs; context passing is implicit.
- **Result:** Wrong agent selection, stale shared state, and inconsistent multi-agent outcomes.

---

## 2. Enhancement Roadmap (Non-Breaking, Additive)

Each item is additive and gated by a config flag defaulting to current behavior.

### Phase 0 — Stabilization (no behavior change)
- **E0.1** Make `mypy` a required CI gate; fix errors incrementally behind the gate (start `tools/`, `memory/`).
- **E0.2** Flip `dev_mode` default to `false` (opt-in only).
- **E0.3** Add uniform tool timeout wrapper + standard output truncation/spill (new modules, no existing tool changes).
- **E0.4** Make permission checks mandatory in `BaseTool.run` behind a `permissions.strict` flag (default off initially).

### Phase 1 — Code Intelligence (additive)
- **E1.1** Add tree-sitter parsers for JS/TS (then Go/Rust/Java/C++) behind `code_intel.parser` flag; keep regex as fallback.
- **E1.2** Fix Python chunk duplication (explicit traversal) behind `code_intel.dedup_chunks` flag.
- **E1.3** Add call-graph + qualified symbol IDs as a new index layer (does not replace existing).
- **E1.4** Add LSP backend as optional precision provider (`lsp.enabled`).
- **E1.5** Add real embeddings behind existing `HybridCodeIndexer` interface (`embeddings.provider`).
- **E1.6** Unify indexers behind a `CodeIntelligenceService` facade (old APIs delegate).
- **E1.7** Token-accurate repo-map budgeting (`tiktoken`) with fallback to char estimate.

### Phase 2 — Tool Runtime (additive)
- **E2.1** Use Pydantic `model_json_schema()` for tool schemas; keep legacy converter as fallback behind flag.
- **E2.2** Add task-aware tool subset selection (`tool_search.enabled`) without removing full schema path.
- **E2.3** Safe discovery mode: allow-listed roots, no implicit execution (`discovery.safe_mode`).
- **E2.4** Verified edit gate (read→derive→verify) as an optional edit backend.
- **E2.5** Lazy, validated, permission-gated skill loader (new `skill` tool variant, old skills unchanged).

### Phase 3 — Verification (additive)
- **E3.1** Pre-execution arg validation against repo state (new validator, opt-in).
- **E3.2** Post-execution AST/type checks on modified files (opt-in).
- **E3.3** Multi-pass self-correction loop (configurable max iterations, default 1 = current).
- **E3.4** Symbol-existence grounding in verifier (uses new symbol index).
- **E3.5** Async, cached compiler checks (move off hot path).
- **E3.6** Calibrate confidence scoring with eval set (advisory only).

### Phase 4 — Streaming (additive)
- **E4.1** True async token streaming behind `streaming.mode` flag (default legacy).
- **E4.2** Offload blocking IO to pools; never block UI thread.
- **E4.3** Early cancellation propagation.
- **E4.4** Virtualized history rendering (opt-in UI mode).
- **E4.5** Budget-aware effort levels.

### Phase 5 — Orchestration (additive)
- **E5.1** Semantic routing behind `orchestration.router` flag (default keyword).
- **E5.2** Dynamic replanning (opt-in).
- **E5.3** Planner→coder→verifier role loop (opt-in chain).
- **E5.4** Scoped registries (session-scoped instances; global remains default).
- **E5.5** Structured message bus (opt-in IPC).
- **E5.6** Retrieval-aware per-agent context assembly.
- **E5.7** Async-first concurrency.

### Phase 6 — Quality & Ops
- **E6.1** Raise coverage floor to 70%+ with integration tests.
- **E6.2** Add eval harness for hallucination and tool-use benchmarks.
- **E6.3** Architecture decision records for parser/schema/orchestration.

---

## 3. Compatibility & Rollback

- All new behavior is behind flags defaulting to current behavior.
- No session/settings schema removals; only additive fields.
- Tool names and schemas only gain optional fields.
- Each phase ships with tests; rollback is a config flip or revert.
- Migration notes required for any user-visible change.

---

## 4. Success Metrics

- Hallucination eval pass rate improvement (target +20%).
- Tool-call success rate (malformed args) improvement.
- p95 TUI responsiveness under load (no >200ms stalls).
- Retrieval precision@5 on code queries.
- Agent routing accuracy on benchmark tasks.

---

*This document is additive to the existing architecture; nothing here removes current functionality.*
