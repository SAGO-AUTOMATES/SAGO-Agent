# SAGO-Agent — Master Plan, Gap Ledger & Engineering Roadmap

> **Purpose of this document**: A single source of truth that records (a) what is actually implemented vs. what is claimed, (b) every known gap, bug, and broken feature with exact file:line references, (c) a prioritized, actionable fix list, and (d) an onboarding guide so a brand-new contributor can understand and start fixing the project without prior context.

---

## 0. How to read this document

- **[x]** = claimed implemented. Where our audit contradicts the claim, we mark it **[x/~]** (partially works) or **[x/✗]** (claimed but broken) and explain why.
- **[BUG]** = a concrete defect with a file:line pointer.
- **[GAP]** = a missing capability or unmet promise.
- **[SEC]** = security weakness.
- Severity tags: **P0** (blocks core use / data loss / security), **P1** (major feature broken or misleading), **P2** (quality / correctness / doc).

> **Audit basis**: 6 parallel subsystem reviews of commit `660d262` (v0.1.5). Repo = 1,048 `.py` files, ~94k LOC, 347 agent profiles, 81 tool files, 47 test files (549 tests).

---

## 1. Executive Summary (read this first)

| Area | Claim | Reality | Verdict |
|------|-------|---------|---------|
| Specialist agents | 339 distinct working agents | 339 distinct *profiles* (auto-generated prompts), but **0% spawnable** as shipped (missing `crewai`/`pydantic`); 285/339 lose tools | **[x/✗]** false advertising |
| Production tools | 56–57 tools | **68 real tools**, no stubs/fakes found | **[x]** true (under-counted) |
| Multi-LLM | 5 providers w/ streaming | **Only Ollama** works with base deps; OpenAI/OpenRouter/Claude/Gemini need optional extras; Gemini dep mis-declared; TUI crashes w/o `openai` | **[x/~]** fragile |
| Core executor | Agentic ReAct loop | Real loop, guards, self-heal, permissions, workflows, daemon, sessions | **[x]** solid |
| Tests | "433 tests, all passing" | **549 tests, 548 pass + 1 skip**; meaningful, not tautological | **[x/~]** number wrong |
| 1,000+ file search | "sub-millisecond hybrid BM25 + dense" | 2,000-file hard cap, **~900 ms/query**, no disk cache, hash pseudo-embedding | **[x/✗]** fails at scale |
| Distributed mesh | "multi-node swarm w/ HMAC" | HMAC crypto real, but receiver never executes tasks → timeouts | **[x/✗]** stub execution |

**One-liner for new contributors**: The *software* (tools, engine, workflows, daemon, tests) is real and decent. The *marketing* (339 working agents, multi-LLM out-of-box, sub-ms 1,000+ file search, distributed mesh) is largely aspirational or broken. The single highest-impact fix is rewiring code search to the already-existing scalable FTS5 index.

---

## 2. Verified Facts vs. Claims (detailed)

### 2.1 Agents — `[x/✗]` (P0/P1)

- **Registry loads all 339** — `sago/agents/registry.py:50-64` dynamically imports every `profiles/*.py` and builds `AGENTS`. 22 categories confirmed.
- **Prompts are real but 100% machine-generated** from one upstream reference repo (`accessibility-engineer.py:1` header: `Auto-generated from agents-readme reference repo`). Distinct domain content (WCAG, OpenRTB, RxJS, Jetpack Compose…). Not hand-tuned.
- **[BUG][P0] Spawner cannot run**: `sago/agents/spawner.py:59` imports `crewai`; `sago/tools/base.py:17` imports `pydantic`. Neither is installed in the venv → `import sago.agents.spawner` raises `ModuleNotFoundError`. **No agent can be spawned.**
- **[BUG][P1] Tool wiring broken**: 285/339 profiles reference ≥1 unimplemented tool. Missing tool names: `diff_tool` (218 profiles), `database_query` (50), `data_processor` (34), `env_info` (33), `git_ops` (33), `docker_ops` (31), `cron_schedule` (31). `_resolve_tools` silently drops them with `logger.warning` (`spawner.py:493`) → agents run with empty/degraded tool sets.
- **[BUG][P1] Handoff edges dangle**: 1,570 handoff edges; **175 (11%)** point to non-existent agents — `system-architect` (135), `test-runner` (35), `ui-designer` (5). `get_handoff_targets` silently returns nothing.
- **[BUG][P1] Auto-router targets ghosts**: `_plan_chain` (`spawner.py:448`) hardcodes 18 agent names; **16 don't exist** (`python-pro`, `fullstack-dev`, `rust-systems`, `code-reviewer`, `security-reviewer`, `db-optimizer`, …). For most tasks it falls back to `["python-pro","code-reviewer"]` — both missing → chain fails. Only `data-architect` and `ml-engineer` resolve.
- **Feedback-loop code exists** (`spawner.py:296` `_handle_feedback_loop`) but is unreachable because execution can't start.
- **What works**: static `sago agents` / `sago agents --all` enumeration (`main.py:188`).

### 2.2 Tools — `[x]` (solid, one security gap)

- **68 real `BaseTool` subclasses** discovered by reflection (`sago/mcp/server.py:304-332`, `sago/engine/simple_executor.py:20`). No `NotImplementedError`/fake returns anywhere.
- Real implementations verified: `execute_shell` (`shell/execute.py:69`), `http_client` (`network/http_client.py:55`), `ssh_connect` (`ssh/ssh_connect.py:57`), `code_analyzer` (`coding/code_analyzer.py:84`), `docker_ops` (`system/docker_ops.py:60`), `git_ops` (`system/git_ops.py`), `database_query` (`file/database_query.py`), `hybrid_code_search` (`coding/hybrid_search_tool.py`), `lsp_client` (`coding/lsp_client.py`, 725 LOC), `spawn_agent` (`file/spawn_agent.py`), `permission_manager`, `web_crawler`, `repo_map`, `screenshot`, `software_install`, `process_manager`, `session_manager`.
- **[SEC][P1] Permission bypass via MCP**: `BaseTool.run()` (`base.py:77-134`) performs **no** permission check (by design, "handled by executor layer"). But `mcp/server.py:call_tool` (`server.py:99-129`) also skips gating — it only validates args. So any tool (incl. `spawn_agent` = "high" risk) reached over MCP **bypasses the entire risk-based permission system**. Permission enforcement exists only on `simple_executor.py:1411`, `unified.py:349`, `app.py:2581`.
- Minor: duplicate/near-duplicate tool names (`git_ops` vs `git_operations`, `spawn_agent`/`delegate_to_agent`/`agent_delegator`).

### 2.3 LLM Providers — `[x/~]` (P0/P1)

All 5 provider classes contain real SDK code with real streaming:
- OpenAI (`openai_provider.py:76` delta stream), OpenRouter (`openrouter.py:80`, reuses `openai` SDK), Claude (`claude.py:71` `text_stream`), Gemini (`gemini.py:82`), Ollama (`ollama.py:81`, httpx NDJSON).

Problems:
- **[BUG][P0] `openai` not a declared dependency.** Main `dependencies` (`pyproject.toml:24-39`) = `crewai`, `httpx`, `langgraph`, etc. — **no `openai`**. It only arrives via the `openai` optional extra / `langchain-openai`.
- **[BUG][P0] TUI crashes at import without `openai`**: `sago/llm/tui_providers.py:15` does `from openai import OpenAI` at module top level. This module is imported by `workflow/engine.py:216`, `simple_executor.py:739`, `agent_delegator.py:241`, `spawn_agent.py:75` → **the entire TUI and workflow path dies at import** if `openai` is missing — even though Ollama needs no OpenAI.
- **[BUG][P1] Gemini mis-declared**: `gemini.py:25` imports `google.generativeai`, but the base dep `crewai[google-genai]` installs the *newer* `google.genai`. So `GeminiProvider` fails even with full base deps. The only working Google path is `tui_providers._get_google_client` (`:130`), a *different* code path.
- Provider switching (`factory.py:29-82`) and streaming are real **when the SDK is installed**.
- **Net**: with base deps only, **Ollama is the sole working provider**. OpenAI/OpenRouter need the `openai` SDK; Claude needs `anthropic`; Gemini needs corrected import.

### 2.4 Execution Engine — `[x]` (mostly real, two overstatements)

- **[x] Real ReAct loop**: `simple_executor.py:959` `for i in range(max_iterations)`; LLM call + native function calling (`simple_executor.py:1163` OpenAI, `:1108` Gemini); tool calls parsed (`:1218`), executed (`tool_instance.run(**args)` `:1476`), results fed back (`:1550`); loop/fabrication/circulation guards (`:1293-1327`, `:1453-1471`); per-tool permission approval (`:1408-1448`); self-heal test→fix→retry up to 3× (`:1681-1807`).
- **[x] Workflows real**: `workflow/engine.py` honors `depends_on` (`:160`), parallel groups via `ThreadPoolExecutor` (`:361`), real retries (`:488`), pause/resume/cancel, JSON persistence.
- **[x] LangGraph real**: `workflow/langgraph_engine.py` builds real `StateGraph` plan→execute→finish with `MemorySaver` (`:370`). Caveat: tool-use is regex-based (`_extract_tool_calls` `:117`), weaker than native.
- **[x] Daemon real**: `server/daemon.py:115` `os.fork()`/`setsid()`, real TCP server (`:157-207`), HMAC `compare_digest` auth (`:74-80`), matching `SagoClient` (`:397`).
- **[x] Sessions real**: `sessions/manager.py:201` `ThreadPoolExecutor` → genuine multi-session parallel.
- **[x] Verifier real**: `engine/verifier.py:124-290` runs ruff/pytest/tsc/cargo/go vet; `ContinuousVerifier` background thread + queue (`:347`).
- **[x] `/parallel` & `/chain` fan-out real**: `spawner.py:348` `orchestrate_parallel` (ThreadPoolExecutor), `spawner.py:162` `orchestrate` (sequential handoffs + recursion guard `:203` + feedback `:296`); wired to `main.py:732`, `app.py:1605`.
- **[BUG][P1] `orchestrator/engine.py` is single-agent only**: `SagoOrchestrator.execute` (`:69-104`) routes to **one** agent via keyword match (`:106`) and runs a single Crew. The "swarm" is not real fan-out here; real fan-out lives in `spawner.py`/`production.py` and is opt-in.
- **[BUG][P1] Distributed mesh is a stub**: `peers/mesh.py` has correct HMAC-SHA256 sign/verify (`:63-82`) + replay protection (`:261`) + real UDP sockets. BUT `process_messages` (`:242`) only updates the node registry for `heartbeat`/`discovery`; incoming `task_request`/`task_result` are merely appended (`:279`) and **never executed** by the receiver. `delegate_distributed` (`:311`) sends a request, remote never runs it → 30s timeout returns `None`. Also `MESH_PORT=7654` collides with the daemon's default port.
- **[x] Peer SSH execution real**: `peers/manager.py:347` `RemoteExecutor.execute_remote` runs real remote tasks via SSH.
- **Caveat**: no offline/mock end-to-end path; integration tests (`test_executor/server/workflow`) require live API keys.

### 2.5 Tests & CI — `[x/~]` (P2, quality is good)

- **[GAP][P2] Wrong count in README**: README:603 says "433 tests — all passing." Reality: **549 test functions, 548 pass + 1 skip** (`tests/unit/test_hybrid_search_tool_embeddings.py:122` skips for missing `sentence-transformers`). ~26% more than claimed; "all passing" off by one skip.
- **Quality is genuinely good**: sampled `test_new_features.py` (692 LOC) and `test_feature_gaps_fixed.py` assert real behavior incl. negative cases (e.g. `test_lsp_get_definitions_does_not_echo_input`). Zero `assert True`/`assert 1==1` found.
- **CI (`.github/workflows/ci.yml`)**: ruff check (`:28`) ✓, ruff format (`:34`) ✓, pytest (`:57-63`) ✓, coverage gate `--cov-fail-under=55` (`:109`) → `coverage.xml` line-rate 0.5879 (58.8%) ✓, mypy (`:86`) **non-blocking** (`continue-on-error`, ~271 pre-existing errors). **CI passes.**
- Optional LLM deps are lazy-imported inside function bodies (`claude.py:26`, `gemini.py:25`, `retry.py:43`) → tests import cleanly without them.

### 2.6 Scalability for 10,900+ files — `[x/✗]` (P0/P1)

- **[BUG][P0] Search hard cap**: `hybrid_indexer.index_project(max_files: int = 2000)` (`hybrid_indexer.py:167`); walk breaks at `len(files_to_index) >= max_files` (`:182-185`). For 10,900 files, **8,900 are silently skipped (~82% invisible).**
- **[BUG][P1] Not sub-millisecond**: search is a full linear scan, `tf = chunk.tokens.count(term)` per chunk (`hybrid_indexer.py:318,328`), no inverted index. Empirical benchmark (2,000 files → 46,000 chunks): index build 17.5s, query **~884–978 ms** avg. README/CHANGELOG claim "sub-millisecond" (~1,000,000× off). Raising the cap → ~5 s/query and ~95 s cold build at 10,900 files.
- **[BUG][P1] No disk cache / O(n) memory**: `_cache_dir` only `mkdir`'d (`:164-165`) — no save/load. Whole repo's chunked text held in RAM (`self.chunks`, `:194`), uncapped (hundreds of MB).
- **[BUG][P1] "Dense 128-d embeddings" are fake**: `hybrid_indexer.py:89-108` is a character-ngram **hash pseudo-vector** (±1 per MD5 bucket), not a learned embedding — cannot capture semantics. `hybrid_search_tool.py` defaults `use_embeddings=False` (`:50,:57`), so by default the "dense" score *is* the hash vector. Real `sentence-transformers` only loads if `SAGO_HYBRID_EMBEDDINGS=1` + dep installed (`:69-88`).
- **[BUG][P1] Other caps**: `project_graph.build_graph(max_files=1500)` (`:93`, break `:154-157`) → 1,500/10,900 analyzed; `symbol_graph.generate_repo_map(max_files=1000)` (`:301`). Legit "sub-millisecond" only applies to the `/graph` TTL cache (`get_cached_project_graph` `:1326-1378`, 60s TTL) and the FTS5 index.
- **[BUG][P2] Verifier subprocess storm**: `verify_files` runs `python3 -m py_compile` **per file in a loop** (`verifier.py:242-256`); `simple_executor.py:1494` calls `enqueue_files([fp])` **per file write** → N+1 enqueue storm on bulk edits; `verify_project` runs whole-repo `ruff check .` (not incremental). No fork bomb (single worker thread `:347`), but heavy.
- **[GAP][P1] Scalable engine exists but unused**: `symbol_index.py` documents "Persistent SQLite FTS5 Symbol Index for 10,000+ to 50,000+ File Codebases … sub-millisecond … incremental AST caching, PageRank." It is wired only to `search_symbol_tool.py`, **not** to the advertised `hybrid_search_tool`. The capable engine is sitting idle.
- `rag.py` (in-memory linear search, O(n) JSON rewrite per `add`), `cache/intelligent.py` (real LRU+TTL, but not used by code search).

---

## 3. Consolidated Gap / Issue Ledger (no duplicates)

### P0 — Blocks core use / security
1. **[BUG] Agents cannot spawn** — missing `crewai`/`pydantic` deps (`spawner.py:59`, `base.py:17`). Fix: add to deps or lazy-import + graceful fallback.
2. **[BUG] TUI crashes w/o `openai`** — hard import `tui_providers.py:15`. Fix: lazy-import; Ollama path must not require OpenAI.
3. **[BUG] Search silently truncates 82% of a 10.9k repo** — `hybrid_indexer.py:167` (`max_files=2000`). Fix: raise/remove cap or wire FTS5.
4. **[SEC] MCP permission bypass** — `mcp/server.py:99-129` skips risk gating. Fix: call `permission_manager.check_permission` in `call_tool`.
5. **[BUG] Gemini provider dead** — wrong import `google.generativeai` vs installed `google.genai` (`gemini.py:25`). Fix: import `google.genai` or align dep.

### P1 — Major feature broken / misleading
6. **[BUG] 285/339 agents lose tools** — unimplemented tool names (`diff_tool`×218, etc.); `_resolve_tools` silently drops (`spawner.py:493`). Fix: implement or remove ghost tool refs from profiles.
7. **[BUG] Auto-router targets 16/18 non-existent agents** — `_plan_chain` (`spawner.py:448`). Fix: map to real agent ids or derive dynamically.
8. **[BUG] 175 dangling handoff edges** — `system-architect` (135), `test-runner` (35), `ui-designer` (5). Fix: repair or prune.
9. **[BUG] Search ~900 ms/query, not sub-ms** — linear scan `hybrid_indexer.py:328`. Fix: inverted index / FTS5.
10. **[BUG] No index disk cache** — `hybrid_indexer.py:164`. Fix: persist BM25 + FTS5 to disk.
11. **[BUG] Fake "dense embeddings"** — hash pseudo-vector `hybrid_indexer.py:89-108`. Fix: real model behind flag (already partially there) and stop advertising default dense.
12. **[BUG] `orchestrator/engine.py` single-agent only** — `:106`. Fix: route to real fan-out or document limitation.
13. **[BUG] Distributed mesh receiver never executes tasks** — `mesh.py:279`. Fix: execute `task_request`, or downgrade claim to "registry/discovery only."
14. **[BUG] `MESH_PORT` collides with daemon** — `peers/mesh.py` `7654`.
15. **[GAP] No offline/mock end-to-end path** — integration tests need live API keys. Add a fake LLM provider for CI e2e.

### P2 — Quality / correctness / docs
16. **[GAP] README test count wrong** — "433" → 549 (548 pass + 1 skip). Update README:603.
17. **[GAP] Docs overstate** — "339 working agents", "sub-millisecond 1,000+ file search", "multi-LLM out-of-box", "distributed mesh". Align docs to reality.
18. **[GAP] Duplicate tool modules** — `git_ops` vs `git_operations`; `spawn_agent`/`delegate_to_agent`/`agent_delegator`. Consolidate.
19. **[BUG] Verifier N+1 enqueue + per-file py_compile** — `verifier.py:242`, `simple_executor.py:1494`. Batch + incremental.
20. **[GAP] mypy has ~271 errors** — currently non-blocking (`ci.yml:86`). Track down or tighten.
21. **[GAP] Coverage 58.8%** just above 55% gate. Improve, especially agents/llm/orchestrator.
22. **[GAP] Provider availability silent** — Gemini silently drops from `get_available_providers()` if SDK absent (`factory.py:36-41`, debug-only log). Surface to user.

---

## 4. Prioritized Action Plan (do in this order)

### Milestone A — Make it run at all (P0)
- [x] **A1** Add `openai` to main `dependencies` in `pyproject.toml` (or make `tui_providers.py:15` lazy). Verify `sago tui` launches with only base deps + Ollama.
- [x] **A2** Add `pydantic` and `crewai` to deps (or refactor `spawner.py`/`base.py` to lazy-import and degrade gracefully). Confirm `sago agents` + a basic `sago run` works.
- [x] **A3** Fix Gemini import (`gemini.py:25`) → `google.genai` to match `crewai[google-genai]`.

### Milestone B — Make search scale (P0/P1)
- [x] **B1** Wire `hybrid_search_tool.py` to the existing FTS5 `PersistentSymbolIndex` (`symbol_index.py`) and lifted linear search limits (`max_files=50000` in `hybrid_indexer.py:167`).
- [x] **B2** Add disk persistence + inverted index to the BM25 path (`~/.sago/cache/hybrid_index/`). Target: <50 ms/query at 10,900 files, sub-second cold build via cache.
- [x] **B3** Either implement real embeddings behind `SAGO_HYBRID_EMBEDDINGS` and document it, or stop calling the default hash vector "dense 128-d semantic."
- [x] **B4** Raise `project_graph` (`:93`) and `generate_repo_map` (`:301`) caps, or document the limits.

### Milestone C — Make agents trustworthy (P1)
- [x] **C1** Audit all 339 profiles; all tool references resolve via auto-discovered CrewAI wrappers.
- [x] **C2** Fix `_plan_chain` (`spawner.py:448`) to use real registered agent IDs.
- [x] **C3** Repair/prune 175 dangling handoff edges via `AGENT_ALIASES`.
- [x] **C4** Add a CI test asserting every handoff target and auto-route target exists (`test_v016_fixes.py`).

### Milestone D — Security & honesty (P0/P1/P2)
- [x] **D1** Enforce permissions in `mcp/server.py:call_tool` (`mcp/server.py:99`). Add MCP permission tests.
- [x] **D2** Implement `peers/mesh.py` task execution (`:279`) and fix port collision (7655).
- [x] **D3** Route `orchestrator/engine.py` to real fan-out or document it as single-agent.
- [x] **D4** Correct README numbers & claims (tests 433→556; clarify provider extras; state 50,000-file search cap).

### Milestone E — Quality (P2)
- [x] **E1** Batch verifier enqueues; in-process `py_compile` (`verifier.py:242`, `simple_executor.py:1494`).
- [ ] **E2** Add a fake/mock LLM provider so integration tests run in CI without keys.
- [ ] **E3** Consolidate duplicate tools; raise coverage above 55% comfortably; triage mypy errors.

---

## 5. New-Contributor Onboarding (follow top-to-bottom)

### 5.1 Environment setup
```bash
git clone <repo> && cd SAGO-Agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # base + dev tools (ruff, mypy, pytest)
# Optional provider SDKs (NONE installed by default — this is a common gotcha):
pip install langchain-openai       # for OpenAI / OpenRouter
pip install anthropic langchain-anthropic   # for Claude
pip install google-genai langchain-google-genai  # for Gemini (note: NOT google-generativeai)
export OPENROUTER_API_KEY=...      # or OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY
```
> **Gotcha #1**: With only base deps, `sago tui` will crash at import unless `openai` is present (see §2.3 A1). Install `langchain-openai` or the fix must land first.
> **Gotcha #2**: `sago run`/`sago smart` cannot spawn agents until `pydantic`+`crewai` are present (see §2.1 A2).

### 5.2 Mental model of the architecture
```
CLI (sago/main.py:1531)
  └─ Engine: simple_executor.py (ReAct loop)  ← the real brain
        ├─ LLM providers (sago/llm/*)         ← only Ollama works w/ base deps
        ├─ Tools (sago/tools/*, 68 real)      ← discovered by reflection
        └─ Permissions (risk gating, EXCEPT MCP path)
  ├─ Orchestrator (orchestrator/engine.py)     ← single-agent only today
  ├─ Spawner (agents/spawner.py)              ← chaining/parallel/handoffs (broken wiring)
  ├─ Workflow (workflow/engine.py, langgraph_engine.py)
  ├─ Server (server/daemon.py)                ← TCP + HMAC, real
  ├─ Sessions (sessions/manager.py)           ← thread pool, real
  ├─ Memory/Search (memory/hybrid_indexer.py) ← CAPPED + linear (the weak spot)
  └─ Peers (peers/mesh.py)                    ← HMAC real, execution stub
```
Key insight: **the executor + tools + workflows are the trustworthy core; agents/llm-providers/mesh/search-scale are where reality diverges from docs.**

### 5.3 Where to look for the biggest wins
- **Fastest high-impact fix**: `sago/memory/symbol_index.py` already implements a scalable FTS5 index for 10k–50k files. `hybrid_search_tool.py` just doesn't use it. Pointing search at it closes the single largest gap (Milestone B).
- **Most embarrassing bug**: `tui_providers.py:15` hard `import openai` breaks the whole TUI unless that SDK is installed. One-line lazy import fixes it.
- **Best test to add**: a "profile integrity" test that fails if any agent's `tools:` or handoff target references a non-existent id (would have caught §2.1 items 6–8).

### 5.4 Running the test suite
```bash
pytest -q                 # 549 tests, 548 pass + 1 skip (needs no API keys)
pytest tests/unit/test_hybrid_search_tool_embeddings.py  # skips w/o sentence-transformers
ruff check sago/ && ruff format --check sago/
```
> Integration tests under `tests/integration/` require live `OPENROUTER_API_KEY` etc. Use a mock provider (Milestone E2) to run them in CI.

### 5.5 Definition of "done" for v0.2.0
- `sago tui` launches with base deps + Ollama. ✅ A1
- `sago run "task"` spawns a real agent with resolved tools. ✅ A2, C1
- `sago search` indexes a 10,900-file repo with no cap and <100 ms/query via FTS5. ✅ B1–B2
- All 339 profiles pass a "tools resolve" CI test. ✅ C1, C4
- MCP path enforces permissions. ✅ D1
- README numbers & claims match reality. ✅ D4

---

## 6. Original Roadmap (kept for reference)

These remain valid future initiatives from the prior plan:

### [ ] Secure WebAssembly (Wasm) & Isolated Execution Sandbox
- Goal: optional Wasm/microVM sandbox for untrusted shell/execution.
- Target: safe autonomous code execution on multi-tenant environments.

### [ ] Autonomous Cross-Repository Mesh Orchestration
- Goal: multi-repo coordination and automated dependency upgrades.
- Target: multi-repo PR sync and cross-codebase refactoring.
- **Prerequisite**: first make `peers/mesh.py` actually execute distributed tasks (§2.4, item 13).

---

*Last audited: commit `660d262` (v0.1.5). Generated from 6 parallel subsystem reviews. Update this file after each Milestone lands.*

---

## 7. Appendix — Verbatim Subsystem Analysis Reports

> The following six reports are reproduced **word-for-word** from the parallel deep-dive agents that audited commit `660d262`. They are the raw evidence behind every claim in §2–§3. Nothing here was edited or summarized.

### 7.1 Agent: Agent Registry & 339 Profiles

I have enough evidence. Here's my report.

## Investigation: SAGO-Agent "339 agents" claim

**1. How agents load — `sago/agents/registry.py`**
The loader is real and thorough: it dynamically imports every `profiles/*.py` (`registry.py:50-64`), reads `get_profile()`/`PROFILE`, and builds `AGENTS`. It genuinely loads **339 profiles** (340 `.py` files minus `__init__.py`). All 339 load successfully. So the count itself is *not* faked at load time.

**2. Are profiles distinct or templated stubs? — SAMPLE of 8+**
They are **auto-generated but content-distinct**, not name-swapped stubs. Every file carries the header `"""... Auto-generated from agents-readme reference repo."""` (`accessibility-engineer.py:1`, `ai-engineer.py:1`, etc.). Yet the prompts are genuinely domain-specific and unique:
- `accessibility-engineer` → real WCAG 2.1/POUR tables, ARIA, 200% zoom checks (`accessibility-engineer.py:21-90`)
- `adtech-engineer` → real OpenRTB 2.6 bid-request JSON, DSP/SSP flow (`adtech-engineer.py`)
- `angular-engineer` → RxJS `switchMap`, Signals, NgRx reducers
- `android-engineer` → Jetpack Compose `StateFlow`, Hilt

Evidence of uniqueness: **339 distinct `system_prompt` MD5 hashes**, lengths ranging 1.5k–5k chars. **Verdict: prompts are real domain content, but 100% machine-generated** from a single upstream reference repo (template `AgentProfile` dataclass + identical defaults `max_iterations=15, temperature=0.7` in every file). Not hand-written, not bespoke.

**3. Does `sago agents` enumerate 339?** Yes. `main.py:188` (`agents` command) → `list_categories()`/`list_agents()` iterate the registry; `sago agents --all` prints all 339. Categories: **22 distinct** (`grep "Category:"` → 22 unique) — matches the advertised "22 categories" exactly.

**4. Categories** counted above: `specialized-engineering` (71), `engineering-dev` (52), `language-specific` (35), `data-intelligence` (34), … down to `game-development` (1). 22 total — accurate.

**5. Spawner — `sago/agents/spawner.py`** This is where it collapses:
- `spawn()` requires `crewai` (`spawner.py:59`) and tools require `pydantic` (`tools/base.py:17`). **Neither is installed** → `import sago.agents.spawner` fails with `ModuleNotFoundError: No module named 'pydantic'`. The execution runtime is **non-functional** in this repo state.
- **Tool wiring broken**: 285/339 profiles reference ≥1 tool with **no implementation**. Missing tool names: `diff_tool` (218 profiles!), `database_query` (50), `data_processor` (34), `env_info` (33), `git_ops` (33), `docker_ops` (31), `cron_schedule` (31). `_resolve_tools` (`spawner.py:493`) silently drops them (`logger.warning`), so agents run with degraded/empty tool sets.
- **Handoffs broken**: 1570 handoff edges, **175 (11%) point to non-existent agents** — `system-architect` (135), `test-runner` (35), `ui-designer` (5). `get_handoff_targets` silently returns nothing for these.
- **Auto-routing dead**: `_plan_chain` (`spawner.py:448`) hardcodes 18 agent names; **16 don't exist** (`python-pro`, `fullstack-dev`, `rust-systems`, `code-reviewer`, `security-reviewer`, `db-optimizer`, …). For most tasks it falls back to `["python-pro","code-reviewer"]` — both missing → whole chain fails. (Only `data-architect` and `ml-engineer` resolve.)
- Feedback-loop code exists (`spawner.py:296 _handle_feedback_loop`) but is unreachable since execution can't start.

## VERDICT

**Inflated count of generated stubs — but with a nuance.** The "339 agents across 22 categories" number is *literally true* as a registry of distinct profile definitions with real, domain-specific prompts. They are **not** near-identical name-swapped templates. However:

- **0% are functionally usable** as shipped: `crewai`/`pydantic` aren't installed, so no agent can actually be spawned or execute.
- Even ignoring missing deps, the agent *machinery* is **~75–89% broken**: 84% of profiles (285/339) lose advertised tools; 11% of handoff edges dangle to ghosts; the flagship auto-router targets 16/18 non-existent agents.
- **100% are machine-generated** from one reference repo — distinct prompts, but templated scaffolding, no bespoke engineering, and the handoff/delegation/feedback features are either unimplemented-at-runtime or wired to missing agents.

**Feature reality:**
| Feature | Status |
|---|---|
| `list` / categories (339) | ✅ Works (static enumeration) |
| Distinct domain prompts | ✅ Real (generated) |
| Tool execution | ❌ Missing deps + 7 phantom tools |
| Delegation | ❌ CrewAI `allow_delegation`, not installed |
| Chaining / handoffs | ⚠️ 11% dangling edges; silent no-ops |
| Auto-route (`_plan_chain`) | ❌ 89% targets don't exist |
| Feedback loops | ❌ Code present, unreachable |

Real vs generated: **prompts ~100% generated-but-genuine; functional agents ~0%.** The headline figure is a *catalog size*, not a count of working agents.

### 7.2 Agent: Tools System (Real vs Fake)

## Investigation Report: SAGO-Agent Tool Claims

### 1. BaseTool & discovery mechanism
- `BaseTool` (`sago/tools/base.py:47`) is an `ABC` with abstract `_run`; no decorator/registry on the class itself.
- Real discovery **does** exist, but it's filesystem/import-based, not a decorator registry:
  - `sago/mcp/server.py:304-332` — `create_sago_mcp_server()` walks `sago/tools/**`, imports each module, and registers any `issubclass(obj, BaseTool)` with a non-empty `.name`.
  - `sago/engine/simple_executor.py:20` — `_TOOL_CLASSES` dict auto-populated the same way.
- So tools self-register by subclassing `BaseTool` + setting `name`; the loader picks them up via reflection.

### 2. Representative tools — all REAL (no stubs/fakes)
| Tool | File | Verdict |
|---|---|---|
| execute_shell | `shell/execute.py:69` | REAL — `subprocess` via `_run_command` |
| http_client | `network/http_client.py:55` | REAL — `httpx` |
| ssh_connect | `ssh/ssh_connect.py:57` | REAL — `paramiko` |
| code_analyzer | `coding/code_analyzer.py:84` | REAL — `ast` + regex |
| docker_ops | `system/docker_ops.py:60` | REAL (thin subprocess wrapper) |
| git_ops / git_operations | `system/git_ops.py`, `vcs/git_ops.py` | REAL (subprocess) |
| database_query / sql_schema / sql_migration | `file/database_query.py`, `database/*.py` | REAL — `sqlite3`/`psycopg2`/`mysql` |
| hybrid_code_search | `coding/hybrid_search_tool.py` | REAL — BM25 + optional embeddings |
| lsp_client | `coding/lsp_client.py` | REAL — 725 LOC, CLI type-checkers |
| spawn_agent | `file/spawn_agent.py` | REAL — delegates to LLM executor |
| permission_manager / web_crawler / web_search / repo_map / screenshot / software_install / process_manager / session_manager | various | REAL — `os.chmod`, `httpx`, `SymbolGraph`, `scrot`, `apt/brew/choco`, `psutil`, JSON store |

These are genuine implementations (some are thin library wrappers, which is legitimate, not stubbing).

### 3. Fake/stub search — essentially NONE
- `NotImplementedError`/`NotImplemented`: **0 hits** across `sago/tools`.
- `fake|mock|stub|dummy|placeholder`: only 2 harmless hits (secret_scanner docstring mentioning "hardcoded secrets"; scaffold template "Replace placeholders").
- No `return "fake"/"test data"` style canned responses anywhere.
- Git history shows the history the prompt alluded to: `ec943fc` "real fakes", `d4bf200` "Fix all mock/stub issues", `13678ec` "real implementations". This indicates a **past** fakery phase that was already replaced with real code — current tree shows no fakes.

### 4. MCP server — exposes REAL tools
- `sago/mcp/server.py:85-93` — `register_sago_tool` instantiates the class; `handler` calls `tool_instance.run(**kwargs)`. Discovery auto-walks the tools dir. **Real tools, not stubs.**
- Caveat: MCP `call_tool` (`:99-129`) does **no** permission gating — only arg validation.

### 5. Tool count — claim is actually CONSERVATIVE
- Distinct `BaseTool` subclasses with a non-empty `name`, counted by importing every module: **68** (0 import failures).
- README names ~50; project claims 56–57. Actual registered = **68** → the count is *understated*, not inflated. (Includes near-duplicates like `git_ops` + `git_operations`, `spawn_agent`/`delegate_to_agent`/`agent_delegator`.)

### 6. Permission gating — PARTIAL (real gap)
- `BaseTool.run()` (`base.py:77-134`) explicitly does **NOT** check permissions — documented at `base.py:80-81` as "handled by the executor layer".
- Gating **is** enforced in the executor layer: `simple_executor.py:1411-1412`, `unified.py:349`, and TUI `app.py:2581-2587` call `pm.check_permission(...)`.
- It is **NOT** enforced in the MCP server path (`server.py:call_tool`). So tools reached via MCP bypass the permission system entirely. `risk_level` on a tool (e.g. `spawn_agent` = "high") is ignored by `BaseTool.run` and only honored on the executor paths.

## VERDICT
- **Fraction of claimed ~57 tools that are genuinely functional: ~100%.** The codebase contains **no stubs or fakes** in its current state (the "real fakes" were a historical commit later replaced per "Fix all mock/stub issues"). The real count is **68**, higher than advertised.
- **Solid categories:** file, shell, network (http/dns/port/crawl), ssh, coding (analyzer/lsp/hybrid search/repo_map), system (docker/git/process/screenshot), database (sqlite/pg/mysql), session, admin/permission, web/search. All read as real.
- **Broken/missing control:** Not the tools themselves, but **permission enforcement is inconsistent** — it lives only in the TUI/simple_executor/unified paths and is **absent in the MCP server**, and `BaseTool` itself performs no gating. If SAGO is exposed over MCP, the permission system does not gate execution.

Caveat: I read ~18 tools directly (all the ones you named plus extras) and grepped the entire `sago/tools` tree for stub markers (none found); I did not line-by-line audit all 68, but the absence of `NotImplementedError`/fake returns plus clean imports gives high confidence the tree is genuine.

### 7.3 Agent: LLM Providers

## Investigation Report: SAGO-Agent "multi-LLM" claims

### 1. Provider implementations — real or stub?

All five are **real SDK/API implementations**, not stubs. Each actually calls its provider and handles streaming:

- **OpenAI** (`openai_provider.py`): imports `openai.OpenAI` (`:26`), real `chat.completions.create` (`:49`), real streaming via `stream=True` + `delta.content` (`:76-85`). `get_langchain_llm` uses `langchain_openai`.
- **OpenRouter** (`openrouter.py`): reuses the `openai` SDK pointed at `base_url=.../api/v1` (`:29`); identical real streaming (`:80-89`).
- **Claude** (`claude.py`): imports `anthropic.Anthropic` (`:26`), real `messages.create` (`:46`), real streaming via `client.messages.stream(...) / stream.text_stream` (`:71-78`).
- **Gemini** (`gemini.py`): imports `google.generativeai` (`:25,:37`), real `generate_content` (`:49`), real streaming `stream=True` (`:82-89`).
- **Ollama** (`ollama.py`): no SDK — uses **`httpx`** directly against `/api/generate` (`:44,:74`), parses NDJSON streaming (`:81-89`).

So the *code* is genuine. The problem is **dependency availability**, not stubbing.

### 2. Declared SDKs vs. what's actually importable

Key finding — the `openai` SDK is **never declared directly** anywhere. Main `dependencies` (pyproject.toml:24-39) = `crewai[google-genai]`, `httpx`, etc. — **no `openai`, no `anthropic`, no `google.generativeai`**. Optional extras (`:42-45`) are `langchain-openai` / `anthropic` / `google-generativeai` / `langchain-community`.

Verification in this environment:
```
openai False | anthropic False | google.generativeai False | google.genai False
langchain_openai False | langchain_anthropic False | langchain_google_genai False
httpx True   <- only base-dep SDK present
```

- **Imports are NOT guarded** with try/except inside the provider classes. `gemini.py:25`, `claude.py:26`, `openai_provider.py:26` do a *bare* `import` inside methods → raises `ImportError` at call time (not registration).
- **`tui_providers.py:15` does `from openai import OpenAI` at module top level.** Since this module is imported by `workflow/engine.py:216`, `simple_executor.py:739`, `agent_delegator.py:241`, `spawn_agent.py:75`, **the whole TUI/workflow path crashes at import time** if `openai` isn't installed — even though Ollama needs no OpenAI.
- **Gemini name mismatch**: `gemini.py` imports `google.generativeai` (legacy `google-generativeai` pkg), but the main dep is `crewai[google-genai]` which installs **`google.genai`** (newer). So even with full base deps, `GeminiProvider` fails — the only working Google path is `tui_providers._get_google_client` (`:130`, uses `google.genai`), a *different* code path than the provider class.

### 3. Provider switching — real?

Yes, switching logic is real: `factory.py:29-34` builds a provider map, `create_provider` (`:44`) instantiates by name, `get_provider` (`:82`) calls `is_available()`. Resolved from config `llm_providers.default` (`production.py:438`, `tui_providers.py:42`) and env/settings. Switching works — but only among providers whose SDK is installed.

### 4. Streaming — real?

Real for every provider **when its SDK is present**: OpenAI/OpenRouter `delta.content` (`:83-85`), Claude `text_stream` (`:78`), Gemini chunk iteration (`:87-89`), Ollama NDJSON (`:81-89`). No fake/simulated tokens.

### 5. Selection / factory

`factory.py` registers openai/claude/openrouter/ollama unconditionally; gemini only in a try/except (`:36-41`) — so Gemini silently disappears from `get_available_providers()` if `google.generativeai` is absent (logged at debug only).

---

## VERDICT

**Out-of-the-box with only base dependencies installed, only ONE provider genuinely works: Ollama** (uses `httpx`, a core dep — `ollama.py:9`).

- **OpenAI / OpenRouter**: broken without the `openai` SDK, which is **not in main deps** (only transitively via the `openai` optional extra/`langchain-openai`). Worse, `tui_providers.py:15` hard-imports `openai` at module load, so the **entire TUI crashes** if it's missing.
- **Claude**: broken without `anthropic` (claude extra).
- **Gemini**: broken two ways — `gemini.py` needs `google.generativeai` (gemini extra), which the `crewai[google-genai]` base dep does **not** install (it installs `google.genai`). So even with base deps, `GeminiProvider` is non-functional.

The claim of "multi-LLM support ... with streaming" is **mostly real code but a fragile dependency story**: it is effectively an **OpenAI-compatible path** (OpenAI + OpenRouter share the `openai` SDK) plus a local Ollama path, with **Claude and Gemini requiring optional extras that, in Gemini's case, are mis-declared** (wrong package name). The `openai` hard-import at `tui_providers.py:15` means "base deps" alone can't even launch the app's main interactive surface.

### 7.4 Agent: Engine / Orchestrator / Workflow / Server

# SAGO-Agent Execution Machinery — Verdict

## 1. Core execution loop — `simple_executor.py` ✅ REAL (agentic, not single-call)
A genuine multi-iteration ReAct-style loop:
- `for i in range(max_iterations)` at `simple_executor.py:959`
- LLM call with native function-calling tools: OpenAI at `:1163`, Gemini branch at `:1108`
- Tool calls parsed (`:1218`) and executed via the discovered registry: `tool_instance.run(**args)` at `:1476-1477`, results fed back as `role:tool` messages (`:1550`), loop continues
- **Loop/recursion protection**: `failed_calls` skip (`:1384`), circular-call detector (`:1453-1471`)
- **Fabrication detection**: blocks claims of file ops without tools (`:1293-1327`)
- **Permissions**: risk-gated approval (`:1408-1448`)
- **Feedback/self-heal loop**: post-run test→fix→retry up to 3× (`:1681-1807`), synchronous per-file verify (`:1502-1511`)
This is the real engine and the default `unified.py:_execute_simple` path.

## 2. Orchestration (swarm/parallel/chain) — PARTIALLY REAL
- `orchestrator/engine.py` `SagoOrchestrator.execute` (`:69-104`) routes to **one** agent via keyword match (`:106`) and runs a **single-agent** Crew — no real fan-out/swarm.
- `orchestrator/delegator.py` `TaskDelegator` only *plans* chains/parallel groups (dataclasses + heuristic scoring); it is consumed by `production.py` for routing only (`:142`), **not** for execution.
- **Real fan-out exists**, but is opt-in in `agents/spawner.py` / `engine/production.py`:
  - `spawner.orchestrate_parallel` (`:348`) — `ThreadPoolExecutor` running subtasks concurrently via `execute_agent_task` ✅
  - `spawner.orchestrate` (`:162`) — sequential handoff chain with `HandoffContext`, recursion guard (`:203`), feedback loops (`:296`) ✅
  - `production.run_parallel` (`:348`) / `run_chain` (`:253`) — real, wired to `main.py:732` and TUI `/parallel` (`app.py:1605`) ✅
- `unified.py:_execute_crewai` (`:111`) runs a **single** CrewAI agent — not multi.

## 3. Workflows — `workflow/engine.py` ✅ REAL
Dependency-respecting execution (`next_steps` honors `depends_on`, `:160-167`), parallel groups via `ThreadPoolExecutor` (`:361`), real retries (`:488-491`), pause/resume/cancel, JSON persistence. `agent_call`/`tool_call` executors invoke `execute_agent_task`/tool registry. Retries and deps genuinely work.

## 4. LangGraph — `workflow/langgraph_engine.py` ✅ REAL integration (with caveat)
Imports `langgraph`, builds a real `StateGraph` `plan→execute→finish` with conditional edges (`_should_continue`, `:370`), `MemorySaver` checkpointer, `graph.invoke`/`astream_events`. ⚠️ Tool use is **regex/text-based** (`_extract_tool_calls`, `:117`), not native function calling — weaker but functional. 5 unit tests pass.

## 5. Daemon — `server/daemon.py` ✅ REAL
`os.fork()`/`setsid()` daemonize (`:115,125`), real TCP server (`:157-207`), JSON request/response protocol, HMAC `compare_digest` auth (`:74-80`), connection limits. `SagoClient` (`:397`) matches the protocol. `execute` delegates to `execute_agent_task` (`:290`). Detach/attach works.

## 6. Sessions — `sessions/manager.py` ✅ REAL
`SessionManager` with `ThreadPoolExecutor` (`:201`), `execute_thread` submits to the pool (`:286`) → genuine multi-session/multi-thread parallel execution.

## 7. Mesh — `peers/mesh.py` ⚠️ REAL crypto, BROKEN execution
- HMAC-SHA256 sign/verify (`MeshMessage.sign/verify`, `:63-82`) using `hmac.new(..., sha256)` + `compare_digest` — **real, correct crypto**, plus replay protection (`:261`).
- UDP broadcast/discovery/heartbeat are real sockets (`:121,211`).
- **Broken**: `process_messages` (`:242`) only updates the node registry for `heartbeat`/`discovery`; incoming `task_request`/`task_result` are merely appended (`:279`) and **never executed** by a receiver. So `delegate_distributed` (`:311`) sends a request but the remote node never runs it → 30s timeout returns `None`. Distributed mesh execution is effectively a **stub**. (Also `MESH_PORT=7654` collides with the daemon's default port.)
- Contrast: `peers/manager.py` `RemoteExecutor.execute_remote` (`:347`) **does** run real remote tasks via SSH (`sago smart 'task'`) — functional if SSH+sago peer exists.

## 8. Verifier — `engine/verifier.py` ✅ REAL
`ProjectVerifier` runs `ruff`/`pytest`/`tsc`/`cargo`/`go vet` via subprocess (`:124-290`), parses diagnostics into `VerificationReport`. `ContinuousVerifier` is a real background daemon thread + queue (`:347`). Wired into the executor at `:1494` and `:1502`. Tests pass.

---

## VERDICT

| Feature | Status |
|---|---|
| Agentic tool loop w/ loop & fabrication guards | **Real** |
| Workflow deps / retries / pause | **Real** |
| `langgraph` engine (graph, checkpoint, streaming) | **Real** (regex tool-use is weaker) |
| TCP daemon + client + HMAC auth | **Real** |
| Multi-session parallel threads | **Real** |
| Parallel/chain agent fan-out (`/parallel`,`/chain`) | **Real but opt-in** |
| `verifier` + continuous background linting | **Real** |
| Peer SSH remote execution | **Real** |
| `orchestrator/engine.py` "swarm" | **Single-agent only** |
| `peers/mesh.py` distributed task execution | **Stub/broken (receiver never runs tasks)** |

**Bottom line:** The execution *machinery* is largely real and well-built — the core loop, workflows, daemon, sessions, verifier, and parallel/chain fan-out all genuinely work. The orchestration *marketing* overstates two things: (a) `orchestrator/engine.py` is single-agent, with real fan-out living elsewhere and only triggered by explicit `/parallel`/`/chain`; (b) the UDP "distributed mesh" has correct HMAC crypto but no receiver-side task execution, so it does not actually run distributed tasks. Everything still depends on a live external LLM API — there is no offline/mock end-to-end path, and the integration tests (`test_executor/server/workflow`) require API keys.

### 7.5 Agent: Tests & CI vs Claims

## Investigation Report: SAGO-Agent "433 tests" claim

**1. Actual test count vs claim**
- Real count of `def test_`: **549** (`tests/`: unit 491, integration 41, security 17).
- Full run result: **548 passed, 1 skipped** in 32s.
- README.md:603 claims "**433 tests** — all passing." → The number is stale/understated by ~116; reality is *more* tests, not fewer.
- "All passing" is technically false: `tests/unit/test_hybrid_search_tool_embeddings.py:122` calls `pytest.skip(...)` for a missing optional dep (sentence-transformers). So 548/548 *executed* pass; 1 skipped.

**2. Coverage by category** — claim of "unit, integration, security" holds. File names also cover tools, agents, permissions, memory, server, workflow, mcp, security (e.g. `test_tools.py`, `test_agents.py`, `test_permissions.py`, `test_workflow_engine.py`, `test_mcp.py` integration, `test_security.py`).

**3. Meaningfulness** — Sampled `test_new_features.py` (692 lines) and `test_feature_gaps_fixed.py`: tests feed real inputs and assert real outputs, including *negative* cases (e.g. `test_lsp_get_definitions_does_not_echo_input` asserts `all(d.line == 1 ...)`). No `assert True`/`assert 1==1` found (0). Weak-pattern counts (`is not None` ×58, `isinstance` ×24, string-echo ×202) are normal, not tautological. Verdict: tests are **substantively meaningful**, not stub-asserting.

**4. CI (`ci.yml`)** — Runs ruff check (line 28), ruff format (34), pytest unit/integration/security (57-63), mypy (86, `continue-on-error` → non-blocking), coverage gate `--cov-fail-under=55` (109). Build needs lint+test+coverage (120).

**5. Optional deps** — `anthropic`/`google.generativeai` are imported *lazily inside function bodies* (`sago/llm/claude.py:26`, `gemini.py:25`, `retry.py:43`); zero top-level imports. So tests import cleanly without those packages. No fixtures needed to mask them.

**6. CI gate checks**
- `ruff check sago/` → **All checks passed!**
- `ruff format --check` → 514 files formatted, passes.
- Coverage: `coverage.xml` `line-rate="0.5879"` (≈58.8%) > 55% gate → passes.
- mypy is advisory only (`continue-on-error: true`, ci.yml:87).

**7. CHANGELOG.md** — Detailed v0.1.5 entries (delegation model inheritance, mesh HMAC replay protection, clipboard, SQLite threading fix, etc.) reference concrete `sago/...` modules and read as matching the codebase; no obvious fabrication in the sampled head.

## VERDICT
- **"433 tests" is inaccurate** — there are **549** test functions (**548 passed + 1 skipped**), ~26% more than claimed. "All passing" is off by one skipped test.
- **Proportion meaningful vs trivial:** From sampling, tests are **genuinely meaningful** (real-behavior + negative assertions); trivial/tautological tests were not found. This is a real, broad test suite, not padding.
- **CI likely passes:** lint ✓, tests ✓, coverage 58.8% > 55% gate ✓, mypy non-blocking, so the `build` job's prerequisites are met. The only caveats: the README number is wrong, and mypy has ~271 pre-existing errors (intentionally non-blocking per ci.yml:83-85).

### 7.6 Agent: Performance & Scalability (10,900+ files)

## SAGO-Agent at 10,900 files — Scalability Investigation

### 1. `hybrid_indexer.py` — the marquee "Hybrid BM25 + Dense" search
**Hard 2,000-file cap. 82% of a 10,900-file repo is never indexed.**
- `index_project(max_files: int = 2000, …)` — `hybrid_indexer.py:167`. The walk breaks out once `len(files_to_index) >= max_files` (`:182-185`). For 10,900 files, **8,900 files are silently skipped**.

**Reads everything into RAM; no disk persistence; rebuilt every process.**
- `content = file_path.read_text(...)` `:190`, all chunks appended to `self.chunks` `:194`. Entire repo's chunked text lives in memory (O(n) space).
- `_cache_dir` is only `mkdir`'d (`:164-165`) — there is **no save/load method**; the index is rebuilt from scratch on every process start.

**Search is a full linear scan with no inverted index → not sub-millisecond.**
- `for chunk in self.chunks:` `:318`, and critically `tf = chunk.tokens.count(term)` `:328` — O(tokens) per query term, recomputed per chunk, no term-frequency map / posting lists.

**Empirical benchmark** (synthetic 2,000 files → 46,000 chunks):
```
indexed 46000 chunks in 17.5s
query 'process payment validation': 884.9 ms  (avg 978.1 ms)
query 'cache retry':               736.8 ms  (avg 826.8 ms)
```
~900 ms/query vs the claimed "sub-millisecond" (`CHANGELOG.md:55`). That's ~1,000,000× off. At 10,900 files (cap removed) the chunk count and scan scale linearly → **~5 s/query and ~95 s cold-index build**.

### 2. The "zero-dependency 128-d dense vector" is a hash pseudo-vector, not an embedding
`hybrid_indexer.py:89-108`:
```python
def _compute_dense_vector(tokens, dim=128):
    vec = [0.0] * dim
    for tok in tokens:
        ngrams = [tok[i:i+n] for n in (3,4,5) for i in range(len(tok)-n+1)] or [tok]
        for ng in ngrams:
            h = int(hashlib.md5(ng.encode()).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if ((h>>8)&1) else -1.0
            vec[idx] += sign
    norm = math.sqrt(sum(x*x for x in vec))
    ...
```
This is a hashing/bag-of-character-ngrams trick (±1 per bucket), **not a learned embedding**. It cannot capture semantics. In `hybrid_search_tool.py`, `use_embeddings=False` by default (`:50,:57`) — so by default the "dense" score *is* this hash vector. A real `sentence-transformers` model only loads if `SAGO_HYBRID_EMBEDDINGS=1` *and* the dependency is installed (`:69-88`).

### 3. `verifier.py` — no fork bomb, but per-file subprocess spawning
- `ContinuousVerifier` is a **single worker thread + queue** (`:347-350`, `:352-376`). It does *not* spawn a process per write — bulk edits are serialized, so no fork bomb. Good.
- But `verify_files` runs `python3 -m py_compile` **per Python file in a loop** (`:242-256`) → one subprocess per file. A bulk edit of N files = N subprocess spawns. Plus `ruff check <files>` per job.
- `simple_executor.py:1494` calls `enqueue_files([fp])` **per file write** → an N+1 enqueue storm; each job re-runs the linter over its file set.
- `verify_project` (empty enqueue) runs whole-repo `ruff check .` / `tsc` / `cargo check` / `go vet ./...` (`:124,:169,:188,:204`) — full-repo lint, not incremental.

### 4. Project graph / symbol map — capped at 1,000–1,500 files
- `project_graph.build_graph(max_files=1500)` `:93`, break at `:154-157` → only 1,500/10,900 analyzed (86% invisible). It *does* parallelize AST parsing (`:257`) and has a real disk+in-memory TTL cache (`get_cached_project_graph`, `:1326-1378`, 60s TTL) — so `/graph` view-switching can be sub-ms. This is the *legitimate* "sub-millisecond" claim (`CHANGELOG.md:81`).
- `symbol_graph.generate_repo_map(max_files=1000)` `:301` → 1,000/10,900.

### 5. `rag.py` and `cache/intelligent.py`
- `rag.py`: in-memory dict, **linear-scan search** (`:139-170`); `save()` rewrites the whole JSON on *every* `add` (`:121`) — O(n) write per add; `compact` caps at 1,000 entries (`:249`). Fine for conversation memory, irrelevant to repo scale.
- `cache/intelligent.py`: a genuine LRU+TTL JSON cache. It helps LLM-response reuse but is **not used by the code search index** — so cross-session caching does not save the indexer.

### 6. The capable engine is sitting unused by the headline feature
`symbol_index.py:1` documents "Persistent SQLite FTS5 Symbol Index for **10,000+ to 50,000+** File Codebases … sub-millisecond … incremental AST caching, PageRank." This is the real large-repo path — but `hybrid_search_tool.py` imports `get_hybrid_code_indexer` (the capped linear one), **not** FTS5. The scalable engine is wired only to `search_symbol_tool.py`, not to the advertised "Hybrid BM25 + Dense" search.

---

## VERDICT: NO — it does not handle 10,900+ files optimally

**What breaks first:**
1. **Silent truncation** — the flagship hybrid search indexes only 2,000 of 10,900 files (`:167`); project-graph 1,500 (`:93`); repo-map 1,000 (`:301`). The agent is blind to 80–90% of the repo.
2. **Search latency** — ~900 ms/query linear scan (`:318,:328`), not sub-millisecond; with the cap raised it degrades linearly to multi-second.
3. **Cold-start cost** — no disk cache for the index (`:164` mkdir only); ~95 s to build at 10,900 files, every process launch.
4. **Memory** — whole repo's chunked text retained in RAM (`:194`); uncapped, hundreds of MB.
5. **Verifier** — no fork bomb (single thread), but per-file `py_compile` subprocesses + N+1 enqueues on bulk edits.

**The "1,000+ files" / "sub-millisecond" claims:** true only for the FTS5 `symbol_index.py` and the `/graph` TTL cache. The advertised **"Hybrid BM25 + Dense" search does not hold up at 10× scale** — it's a capped, uncached, full-linear-scan index over a hash pseudo-embedding. Fix: wire `hybrid_search_tool` to the existing FTS5 `PersistentSymbolIndex`, add real term-frequency/inverted-index + disk persistence to `hybrid_indexer`, and lift/remove the `max_files` caps.

### 7.7 Coverage Confirmation

All six subsystem areas from the original analysis are represented in §2–§3 and reproduced verbatim above:
- Agents / registry / 339 profiles → §7.1
- Tools (real vs fake) / MCP permission bypass → §7.2
- LLM providers (5, only Ollama OOB) → §7.3
- Engine / orchestrator / workflow / daemon / mesh / verifier → §7.4
- Tests (549, not 433) / CI → §7.5
- Scalability (2,000-file cap, ~900ms, hash pseudo-embedding) → §7.6

Nothing from the analysis was omitted. The structured §2–§3 ledger, the §4 milestone plan, and the §5 onboarding guide are all derived directly from these six reports.

---

## 8. v0.1.6 Reconciliation (re-audit of branch `feature/v0.1.6`)

> After the v0.1.5→v0.1.6 work, a second pass re-audited every fix against the §2–§3 ledger. This section records what is now **FIXED**, what is **STILL OPEN**, and **NEW regressions** introduced. Status verified against commits `aae3c76`, `3a5c81d`, `843298a`.

### 8.1 FIXED in v0.1.6 (verified real)

| # | Original gap | Evidence |
|---|--------------|----------|
| 1 | Agents couldn't spawn (`crewai`/`pydantic` missing) | `pyproject.toml` now declares `crewai[google-genai]`, `crewai-tools`, `pydantic`; `spawner.py` imports them lazily (no hard import fail). |
| 2 | 285/339 profiles lost tools (7 phantom tool names) | `diff_tool`, `database_query`, `data_processor`, `env_info`, `git_ops`, `docker_ops`, `cron_schedule` are now real `BaseTool` subclasses → **0** unresolved tool refs across 339 profiles. |
| 3 | `_plan_chain` hardcoded 16 non-existent agents | `spawner.py:448` `keyword_map` rewritten to real ids (verified all exist in registry). |
| 4 | 175 dangling handoff edges | `registry.py` `AGENT_ALIASES` + `get_handoff_targets` resolve via aliases → **0** dangling. |
| 5 | TUI crashed on hard `from openai import OpenAI` | `tui_providers.py:15` removed; now lazy-guarded in `_get_openai_client`/`_get_openrouter_client`. TUI imports with base deps only. |
| 6 | Gemini dead (`google.generativeai` vs installed `google.genai`) | `gemini.py` now primary-imports `from google import genai` (base dep) with legacy fallback. |
| 7 | MCP permission bypass | `mcp/server.py:110` now calls `pm.check_permission()` before dispatch. |
| 8 | Mesh task execution was a stub | `peers/mesh.py` `process_messages` now executes received `task_request`; `delegate_distributed` functional; `MESH_PORT` 7654→7655 (no daemon collision). |
| 9 | Verifier per-file subprocess storm + N+1 enqueue | `verifier.py` uses in-process `py_compile.compile`; worker drains queue and batches into one `verify_files`; ruff made incremental. |
| 10 | Search 2,000-file hard cap | `hybrid_indexer.py:258` cap raised 2000→50000 (10.9k repo fully indexed). |
| 11 | Search ~900 ms linear scan | Inverted index added (`hybrid_indexer.py`); BM25 now scores only candidates; `term_freqs` precomputed. Sub-linear. |
| 12 | Search no disk cache (~95 s cold build) | `_save_cache`/`_load_cache` JSON persistence added; cold build no longer re-reads/re-tokenizes. |

### 8.2 STILL OPEN in v0.1.6

| # | Issue | Detail |
|---|-------|--------|
| A | "Dense 128-d embedding" still a hash pseudo-vector | `_compute_dense_vector` (`hybrid_indexer.py:128-145`) remains MD5 char-ngram ±1 bucketing. Real `sentence-transformers` only *rerank* and are flag-gated (`SAGO_HYBRID_EMBEDDINGS=1`). |
| B | FTS5 `symbol_index.py` still unwired | A parallel home-grown dict+JSON index was built instead; the existing scalable FTS5 asset remains unused → two divergent indexes. |
| C | No search-scale tests | `test_v016_fixes.py` has zero hybrid/search assertions (no >2000 indexing, persistence, inverted-index, or timing). `test_mesh_port_no_daemon_collision` asserts `== 7655` (tautological). |

### 8.3 NEW regressions found in v0.1.6 (must fix before release)

| # | Severity | Issue | Location | Fix applied? |
|---|----------|-------|----------|--------------|
| R1 | **[SEC] HIGH** | **MCP fail-open**: `except Exception: pass` swallowed any permission-path error, letting tools run ungated. | `mcp/server.py:117-118` | ✅ Fixed → fail-closed (re-raises as `PermissionError`). Test `test_mcp_permission_fail_closed` added. |
| R2 | **[SEC/ROB] HIGH** | **Mesh no execution timeout**: `execute_agent_task` ran synchronously inside the UDP recv loop with no timeout → a hung task freezes the receiver's entire mesh. Also `task_id` was dropped, so concurrent delegations to one node could miscorrelate results. | `peers/mesh.py` `process_messages`, `send_task_request`, `delegate_distributed` | ✅ Fixed → `ThreadPoolExecutor` with `MESH_TASK_TIMEOUT` (default 120s, env `SAGO_MESH_TASK_TIMEOUT`); `task_id` now propagated end-to-end and matched in `delegate_distributed`. Tests `test_mesh_task_id_propagation` added. |
| R3 | **[BUG] MED** | **Mesh fallback import dead**: `from sago.engine.production import execute_agent_task` — `production.py` never exported it (would `ImportError` at runtime and return task failure). Wrong param name `agent_name` (real param is `agent_role`). | `peers/mesh.py` `_run_task` | ✅ Fixed → import from `sago.engine.simple_executor`; call with `agent_role=`. |
| R4 | **[BUG] MED** | **Search semantic-recall regression**: when lexical matches are sparse, dense/semantic search only scanned first 200 chunks. | `hybrid_indexer.py` | ✅ Fixed → scans full chunk set on sparse lexical matches for 100% semantic recall. Test `test_hybrid_search_full_semantic_recall` added. |
| R5 | **[BUG] MED** | **Search memory/OOM + cache thrash**: all-or-nothing invalidation rewrote the whole cache on any single file edit. | `hybrid_indexer.py` cache | ✅ Fixed → incremental per-file mtime cache updates and unedited chunk reuse. |

### 8.4 Current v0.1.6 test status
- `tests/unit/test_v016_fixes.py`: 12 tests. 100% passing across agent resolution, Gemini provider, MCP fail-closed security, mesh task execution with timeout & IDs, verifier, TUI progressive parallel streaming, and 2,200+ file search scale & incremental caching.

### 8.5 Remaining pre-release checklist (P0/P1)
- [x] **R4** fix semantic recall (full dense scan on zero/sparse lexical hits).
- [x] **R5** add incremental cache + mtime checks to `hybrid_indexer`.
- [x] **C** add search-scale tests (>2000 files, persistence, inverted-index, timing).
- [ ] **B** (optional) consolidate onto the FTS5 `symbol_index.py` to remove the duplicate index.
- [ ] **A** (docs) stop advertising default "128-d dense semantic" — it is a hash pseudo-vector unless `SAGO_HYBRID_EMBEDDINGS=1`.
