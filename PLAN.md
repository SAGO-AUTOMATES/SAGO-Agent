# SAGO-Agent Production Fix Plan — Deep Analysis from 2e6cdf4e-ea4_export.md

**Date:** 2026-08-26
**Branch:** main (direct) → next: `feature/production-fixes-v0.1.14` recommended
**Version:** 0.1.13 → 0.1.14 (bump AFTER validation, not before)
**Source of truth:** `2e6cdf4e-ea4_export.md` (chain: architect → python-engineer, 14 + 14 tool calls, stealth/ox-alpha, no summary)

---

## 1. Deep Diagnosis — What’s Broken (Evidence from Export + Screenshots)

### 1.1 Thinking / Reasoning Hidden & Out-of-Order (Critical)
- **Evidence:** Export `ASSISTANT [Agent: python-engineer] Tools used: read_file, execute_shell ×4, ... grep×5` then `<thinking>No .gitignore entry...` appears **once at end**, but TUI screenshot shows `Working... (step 6/20 | Step 2/7)` with `Handoff Flow architect → python-engineer` and only 3 `OK Tool: read_file/grep_content` cards visible. The `Interaction Graph` lists 28 tool nodes but the chat stream shows 3. The sequence should be `thinking1 → tool1 → thinking2 → tool2...` interleaved **in chat order**, not one big reasoning at end.
- **Root cause:** `sago/tui/processor.py` + `sago/tui/orchestrator.py` + `sago/engine/simple_executor.py` all produce thinking, but:
  - `sago/tui/helpers.py:_add_assistant_message` and `_add_tool_call` mount to `ExchangeTurnCard` but `on_thinking` mounts thinking via `call_from_thread(self._add_thinking_card)` which appends **after** all tool cards (or before, but not between). The per-iteration loop in `processor.py` does `on_thinking` → `LLM call` → `tool calls` → next iteration’s `on_thinking`, so the order in the card is `thinking (step6)`, then bulk tools, not interleaved.
  - `sago/tracking/dev_tracer.py:244` `record_thinking` coalesces **source-agnostic within 120s** into ONE block (our last fix). That hides per-agent, per-step reasoning in Dev UI — user sees `3 thinking` coalesced but wants distinction `which tool is called by whom or what agent and even in reasoning blocks`.
  - `sago/tui/trace_viewer.py:659` `_tab_thinking` dedupes by `t[:300]` → further hides distinct per-agent reasoning.
  - Other agents’ reasoning (e.g., `architect` thinking before `ast_grep`) is never recorded — only `python-engineer` final thinking is in export. `subagent` delegation via `spawn_agent` does not propagate `on_thinking` correctly.
- **Production impact:** User reloads session → `commands.py:_load_session` only restores `thinking` from `messages.metadata.thinking` (single field) so all intermediate thinking lost. Dev UI `Flow`/`Event Graph` shows 1 reasoning, chat shows 1, but DB has 1 — feels “broken, hidden”.

### 1.2 No Summary / Categorized Output — Wasted Tokens (Critical)
- **Evidence:** Export `USER: so what was the sumamry ?` → `ASSISTANT: Here's the verified summary...` does **not** use cached analysis; the `Interaction Graph` shows after that query there is no new tool — the next `Tool Executions` table in export still shows old 29 tools, not new ones, but user says “when I asked for what was summary it again stated using tools like why already did the analysis no ?? why waste tokens”. Screenshot `so what was the sumamry ?` with `Step 3/30...` spinner indicates a **new chain** is being started instead of summarizing from memory.
- **Root cause:** `sago/engine/context_assembler.py` and `sago/sessions/manager.py` do not short-circuit `summary`/`what was done` queries. The orchestrator (`sago/tui/orchestrator.py` and `sago/engine/simple_executor.py`) treats every user message as a new task and re-runs tools. There is no `/summary` handler that categorizes `by agent: architect (ast_grep, write_file) → python-engineer (execute_shell, grep...)` and no `response delivered` aggregation.
- **Expected:** After `chain` finishes, the final assistant message should be a **categorized summary** by agent with distinct sections, token costs, and not re-trigger tools when user says “so what was the summary?” — it should read from `self.messages` + `ToolUsageStore` + `DevTracer` without new LLM tool calls, or with a single `LLM` call that has `tool_choice: none` and context injection.

### 1.3 Chain / Parallel / Delegate / Normal Chat — Not Uniform (High)
- **Evidence:** `2e6cdf4e` is `orchestrator.chain` → `spawn_agent architect` → `spawn_agent python-engineer`. The chat shows `Handoff Flow ✓ architect → python-engineer` but the `Tool: read_file/grep_content` cards are **uncategorized** — header says `[Agent: python-engineer] Tools used: read_file, execute_shell...` as a single line, not per-step. The `Event Graph` Mermaid shows `User → prompt_enhancer → sago.tui.app → tui.llm.openrouter → llm_stealth... → tool_ask_question...` — the `architect` chain is hidden behind `agent_subagent`.
- **Root cause:** Chain, parallel, delegate, and normal chat each have **different rendering paths**:
  - `sago/tui/orchestrator.py:_process_chain_thread`, `_process_parallel_thread`, `_process_delegation_thread`, `sago/tui/processor.py:_process_message_thread` — each mounts tools differently (`_add_tool_call` vs `_add_parallel_result` vs `_add_orchestrate_step`). None of them mount thinking in order.
  - `sago/tui/helpers.py:ExchangeTurnCard` mounts all tools `before=resp` — so tools from `architect` and `python-engineer` appear mixed, not grouped.
- **Production requirement:** “thinking1 → toolcall1 → maybe another thinking → another tool call → and so on … systematic in order and in db as well … all chain parallel delegate normal chat orchestrate everything should be handled properly”.

### 1.4 TUI Chat Structure & Docs (Medium)
- **Evidence:** User: “make sure tui chat structure file is also updated and all you know and it should be in caps ig not small like other docs”
- **Current:** `docs/tui_chat_structure.md` exists but is lowercase, may be stale (last updated before thinking coalesce, spinner, etc.). Needs to be `docs/TUI_CHAT_STRUCTURE.md` (caps) and updated with systematic flow: `Inspector`, `Thinking`, `Flow`, `Event Graph`, `DB persistence`, etc. Also other docs in `docs/` are caps (`DEVELOPER_MODE.md`, `ARCHITECTURE.md`) — this one is outlier.
- **Also:** “update all md” — `README.md`, `DEVELOPER_MODE.md`, `ARCHITECTURE.md`, `COMMANDS.md`, `PROJECT.md`, `CHANGELOG.md` all Direct-on-main changes need to be documented, plus new `PLAN.md`.

### 1.5 Dev Mode Default (Medium)
- **Evidence:** User: “every time this dev on is set to false automatically i have to manually on it its kinda bs i think make default config to on till we are in beta”
- **Current:** `sago/config/sago.yaml` or `sago/tui/app.py` or `sago/tracking/dev_tracer.py` defaults `developer_mode: false` / `is_enabled: false`. `sago/config/loader.py` loads `sago.yaml` with `dev_mode: false`.
- **Required:** Default to `true` until `version != beta` (i.e., keep on for `0.1.14` beta, add `// TODO: flip to false at 1.0`).

### 1.6 Version & Release Process (Medium)
- **Evidence:** User: “we should have create a feature branch ig but its fine for now update all md and update the version from 0.1.13 -> 0.1.14 validate everything and then commit and push and then create proper tag and release then so its deployed … dont bump the version before all these issues are fixed and i test them”
- **Current:** `pyproject.toml:3`, `sago/version.py`, `README.md` badges show `0.1.13`. `git log` shows direct-on-main commits (`5aaa0ad`, `fc8b584`, etc.) without feature branch — okay for now per user, but next must validate **before** bump.
- **Required:** After fixes, run full validation (`ruff`, `pytest 806`, `security`), then bump `pyproject.toml`, `sago/version.py`, `README`, `CHANGELOG.md`, commit `chore(release): 0.1.14`, `git tag v0.1.14`, `git push origin v0.1.14`, `gh release create v0.1.14 --generate-notes`.

### 1.7 Additional Production Gaps (from screenshots)
- **Lag:** `ask_question` caused `Running: ask_question(questions=[{'options': [{'description': )` with huge args in spinner → markup leak `[/italic #8b949e]` and `daemon` thread at exit → fatal `_enter_buffered_busy`. Fixed in `3db8f73`/`5aaa0ad` but not yet validated on `chain` with 20 steps.
- **Leakage `[/italic #8b949e]`:** Fixed via `widgets/__init__.py:35` `[/]` not `[/italic #8b949e]`.
- **Ask Question stuck:** `ask_question` now `SAFE` but still not interactive MCQ — next fix needs `pause_event` + `Button`s.

---

## 2. Plan — Fixes Grouped by Priority (No Easy Way Out)

### Phase A — Data & Order Correctness (must be first, blocks everything)
**Goal:** `thinking ↔ tool` strict interleaving, per-agent distinction, DB + Dev UI + reload all show same.

| # | File(s) | Change | Validation |
|---|---------|--------|------------|
| A1 | `sago/tracking/dev_tracer.py:244` | **Revert coalesce to per-step, per-agent** — keep `source`+`agent_name` in key, do NOT coalesce `Intent:` synthetic. Store `thinking_count` per `agent` not global. Keep 120s window but per `source`. This gives `Inspector 12 events 4 LLM 3 thinking` → actually `4 thinking` (one per LLM) distinct by `model+agent`, not 1. TUI will show 4, not hidden. | `2e6cdf4e` should show `architect: thinking` + `python-engineer: thinking` distinct |
| A2 | `sago/tui/processor.py`, `sago/engine/simple_executor.py`, `sago/tui/orchestrator.py` | **Systematic mount order:** Change `on_thinking`, `on_tool`, `on_tool_result` to **append in call order** to `ExchangeTurnCard` via new method `mount_sequential(widget, order)` that inserts `before=resp` but respects `seq_id`. Store `seq_id` increment per turn. So `thinking1` (step1) → `tool1` → `thinking2` → `tool2` appears in chat exactly as executed, not bulk at end. | TUI screenshot `Working... (step 6/20 | Step 2/7)` should show `● Technical Reasoning` **between** `OK Tool: read_file` cards, not all at end |
| A3 | `sago/tui/helpers.py:_add_assistant_message`, `_add_thinking_card`, `_add_tool_call` | **Per-agent headers:** Change `title="● Technical Reasoning & Analysis"` → `title="● {agent_name} — Technical Reasoning"` (and `Tool:` already has `● OK Tool: read_file` but add `by @python-engineer`). Pass `agent_name` through `on_thinking` and `on_tool`. | Export `Tool Executions` already has `Key Arguments / Target` but chat should have `by @architect` |
| A4 | `sago/database.py:148` `messages.metadata` + `sago/tracking/dev_tracer.py` | **Persist every thinking+tool in order:** `messages.metadata = {"thinking":..., "thinking_seq": seq_id, "agent":..., "model":..., "tool_seq":...}`. On `_load_session` (`commands.py:1221`), reconstruct **in seq order** not just `thinking_html` bulk. Add `tool_usage` table already has `session_id` + `created_at`; ensure `ToolUsageStore` is flushed before export. | Reload `2e6cdf4e` → same 3 `Technical Reasoning` blocks in same positions |
| A5 | `sago/tui/commands.py:_load_session` + `sago/tui/app.py:on_mount` | Ensure all 4 flows use same sequential path: `chain`/`parallel`/`delegate`/`chat` all go through `helpers.mount_sequential` and same `MessageStore` + `DevTracer` recording. | Test `chain`, `parallel`, `delegate`, `chat` each |

### Phase B — Summary & Token Waste (user-facing correctness)
| # | File(s) | Change | Validation |
|---|---------|--------|------------|
| B1 | `sago/tui/processor.py` + `sago/engine/context_assembler.py` | **Detect summary query** (`so what was the sumamry?` / `what was summary` / `summarize what you did`) via `intent_classifier` → short-circuit: do **not** call tools, instead build `summary` from `self.messages` + `ToolUsageStore.get_all()` + `DevTracer.get_recent_traces()` categorized **by agent**. Prompt: `Summarize what was done, categorized by @architect vs @python-engineer, tools used, output, cost` with `tool_choice: none`. | `2e6cdf4e` second turn should not have `│ 6 LLM 2 thinking` again, just 1 LLM 0 tools |
| B2 | `sago/tui/helpers.py:_add_assistant_message` final mount | After chain finishes (`step 20/20`), mount a **Summary Card** `Collapsible(title="● Summary — by agent", collapsed=False)` with `Tools used: read_file (2) by @python-engineer, ast_grep (2) by @architect`, `Cost`, `Output: PROJECT_ANALYSIS.md` — so user sees output without asking. | TUI shows summary without extra `/chain` |
| B3 | `sago/sessions/manager.py` + `sago/engine/hallucination_verifier.py` | Ensure summary reads from `Session.get_full_export()` already cached analysis (`PROJECT_ANALYSIS.md`) rather than re-grep. | No `grep_content` on summary turn |

### Phase C — Dev UI & Responsiveness
| # | File(s) | Change | Validation |
|---|---------|--------|------------|
| C1 | `sago/tui/trace_viewer.py:236` | Title already `Inspector` (short). Make sure `subtitle` not duplicated. Keep `Inspector 12 events...` as is. | Screenshot header short |
| C2 | `sago/tui/trace_viewer.py:93` `_TV_CSS` | Already fixed `height:auto wrap` but Flow still interleaves reasoning as separate numbered steps. Change `Flow` to show `thinking → tool` as **paired** lines, not separate `step_idx` increments for reasoning. Already partially done in `fe2e1da` but still `2. reasoning` separate — make `2. LLM → ...` with `↳ reasoning` indented not numbered. | `Event Graph` screenshot `1. LLM 2. reasoning 3. LLM 4. tool` → `1. LLM (reasoning) 2. tool` |
| C3 | `sago/tui/trace_viewer.py` | Ensure `Inspector` is responsive: already `width:96% height:94%` + `wrap`, but test on 80×24 terminal. Add `Horizontal` `flex-wrap` for `tv-header` buttons. | Manual `uv run sago/main.py tui` on small terminal |

### Phase D — Docs & Release
| # | File(s) | Change | Validation |
|---|---------|--------|------------|
| D1 | `docs/tui_chat_structure.md` → `docs/TUI_CHAT_STRUCTURE.md` | Rename to caps, update with systematic flow diagram `thinking1 → tool1 → thinking2 → tool2`, `ExchangeTurnCard` `mount_sequential`, `Inspector` tabs, `DB` `messages.metadata` + `tool_usage`, `reload` sequence. Add `chain/parallel/delegate/chat` handling table. | `ls docs/` all caps |
| D2 | `README.md`, `docs/DEVELOPER_MODE.md`, `docs/ARCHITECTURE.md`, `docs/COMMANDS.md`, `CHANGELOG.md` | Update with: dev default `on` till beta, thinking order, summary by agent, no duplicate thinking. | `grep -r "0.1.13" docs/` → updated |
| D3 | `sago/config/sago.yaml` + `sago/tui/app.py` or `sago/config/loader.py` | Default `dev_mode: true` (was `false`). Add comment `# TODO: flip to false at 1.0`. Ensure `DevTracer.is_enabled` true on start. | Fresh `rm -rf .sago/data` + `uv run sago/main.py tui` → `Inspector` shows events without `/dev on` |
| D4 | `pyproject.toml:3`, `sago/version.py`, `README.md` badge | Bump `0.1.13` → `0.1.14` **after** A+B+C validated, then `git tag v0.1.14`, `gh release create`. | `uv run pytest` + `ruff` green before bump |

---

## 3. Execution Order (Strict — No Version Bump Before Fixes Tested)

1. **Phase A** (data correctness) → validate via `2e6cdf4e` reload + `uv run sago/main.py tui` manual chain test + `pytest` `test_tui_turn_container`, `test_tracing`, `test_database`.
2. **Phase B** (summary) → validate `so what was the sumamry?` does 0 tool calls.
3. **Phase C** (UI) → manual small terminal test.
4. **Phase D** (docs + default dev on) → `ruff` + `pytest 806`.
5. **Bump** `0.1.14` → commit `chore(release): 0.1.14` → `git tag` → `push` → `gh release` → PyPI via `.github/workflows/workflow.yml` (trusted publishing).

---

## 4. Risks & Mitigations

- **Coalesce revert may reintroduce 12 thinking blocks:** Mitigate by per-agent `source` key, not global — user sees distinction not flood. Keep 120s window but per `agent`.
- **Sequential mount may break existing 80+ card perf:** Keep `TUI_MAX_RENDERED_CARDS=60` debounce, but now order is correct.
- **Summary short-circuit may miss fresh work:** Only for `summary` intent with no new task keywords; otherwise normal chain.

---

## 5. Acceptance Criteria (User Can Test)

- [ ] `i wanted you to use the tool bro` → `Technical Reasoning` appears **between** `read_file` tools, not only at end, and shows `by @architect` / `by @python-engineer`.
- [ ] `so what was the sumamry?` → no new `grep_content`/`execute_shell`, just `Inspector 1 LLM 0 tools 1 thinking`, and TUI shows `● Summary — by agent` with categorized tools and `PROJECT_ANALYSIS.md` output.
- [ ] `ask me my nasme` → `ask_question` shows MCQ buttons (if options) or `Input` with `What is your name?` and next `USER` input is correctly picked up as `Selected Answer: satyaa` in same turn, not new `Step 1/30`.
- [ ] Reload `sago tui --resume 2e6cdf4e-ea4` → same 3 `Technical Reasoning` blocks in same positions, `Inspector` `19 events 6 LLM 3 thinking` not `12`.
- [ ] Fresh install `dev on` by default, `docs/TUI_CHAT_STRUCTURE.md` caps and updated, `pyproject.toml` `0.1.14`, `git tag v0.1.14` pushed.

---

## 6. Next Step

If you approve this plan, I will start with **Phase A1** (revert coalesce to per-agent) on a **new feature branch** `feature/production-fixes-v0.1.14` (since you noted we should have created one), then proceed sequentially. Otherwise, I’ll adjust the plan.
