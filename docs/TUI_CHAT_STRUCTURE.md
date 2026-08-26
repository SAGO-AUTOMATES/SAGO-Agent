# TUI Chat Message Structures — Complete Reference

Every possible message flow in the Sago TUI, with exact component order and nesting.

> **Updated 2026-08-26 (v0.1.14):** Systematic `thinking → tool` interleaving, per-agent headers, DB persistence with `mount_sequential`, Inspector, and auto `● Summary — by agent`. See §12, §14-15, §19-20 for new behavior. `TUI_CHAT_STRUCTURE.md` is CANONICAL (caps) — lowercase `tui_chat_structure.md` is deprecated.

---

## Table of Contents

1. [Normal Message (No Tools)](#1-normal-message-no-tools)
2. [Normal Message With Tools (Single Iteration)](#2-normal-message-with-tools-single-iteration)
3. [Normal Message With Multiple Iterations — Systematic Order](#3-normal-message-with-multiple-iterations--systematic-order)
4. [/chain Command](#4-chain-command)
5. [/delegate Command](#5-delegate-command)
6. [/orchestrate Command](#6-orchestrate-command)
7. [Parallel Execution](#7-parallel-execution)
8. [Session Reload (/load or --resume)](#8-session-reload)
9. [Error States](#9-error-states)
10. [Approval Prompts (YOLO Mode)](#10-approval-prompts)
11. [System Messages (Standalone)](#11-system-messages-standalone)
12. [Thinking/Reasoning Blocks — Per-Agent, Sequential](#12-thinkingreasoning-blocks--per-agent-sequential)
13. [Execution Plan Card](#13-execution-plan-card)
14. [Turn Summary](#14-turn-summary)
15. [Summary — By Agent (Auto Card + Zero-Tool Short-Circuit)](#15-summary--by-agent-auto-card--zero-tool-short-circuit)
16. [Dev Trace Bar & Inspector](#16-dev-trace-bar--inspector)
17. [Confidence/Verification Score](#17-confidenceverification-score)
18. [Hallucination/Fabrication Warnings](#18-hallucinationfabrication-warnings)
19. [Spinner/Thinking Indicator](#19-spinnerthinking-indicator)
20. [Systematic Thinking → Tool Pipeline & DB Persistence](#20-systematic-thinking--tool-pipeline--db-persistence)

---

## Key Conventions

| Symbol | Meaning |
|--------|---------|
| `┌─ ─ ─┐` | ExchangeTurnCard boundary |
| `├─ ─ ─┤` | Divider between prompt and response |
| `│  │` | Nesting level |
| `▶` | Collapsed collapsible |
| `▼` | Expanded collapsible |
| `[ DEV ]` | Only shown in developer mode (default ON until 1.0 — see §16) |
| `[ LOG ]` | Goes to log file only, not displayed |

---

## 1. Normal Message (No Tools)

**Trigger:** User types plain text, LLM responds with text only (no tool calls).

**Card:** `card_type="user"`, `tag_label="USER"`, `tag_color="#58a6ff"`

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▼ USER  What is Python?                                 │
├─────────────────────────────────────────────────────────┤
│ User Prompt:                                            │
│ What is Python?                                         │
│ ─────────────────────────────────────────────────────── │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ ┌─ ▼ ● sago — Technical Reasoning ───────────────┐  │ │
│ │ │  (only if LLM output contains <thinking> tags) │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ [SAGO]                                              │ │
│ │ Python is a high-level, general-purpose            │ │
│ │ programming language...                             │ │
│ │                                                     │ │
│ │ ┌─ ▶ Turn Summary (0.8s) ──────────────────────┐  │ [DEV]
│ │ │  0 tool(s) | 150 tokens | 0.8s               │  │ [DEV]
│ │ └────────────────────────────────────────────────┘  │ [DEV]
│ │                                                     │ │
│ │ [trace bar with View Trace button]                  │ [DEV]
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Components mounted (in order via `mount_sequential`):**
1. Thinking collapsible (if `<thinking>` tags present) — per-agent title `● {agent} — Technical Reasoning`, **expanded** (`collapsed=False`), seq-tagged
2. Agent tag: `Static("[SAGO]")`
3. Assistant message: `Static(RichMarkdown(content))`
4. Code snippet collapsibles (if code blocks in content) — expanded
5. Dev trace bar (if `developer_mode=True` — default ON until 1.0)
6. Summary collapsible (if `show_summary=True`) — collapsed

---

## 2. Normal Message With Tools (Single Iteration)

**Trigger:** User asks something requiring one tool call, then LLM responds.

**Card:** `card_type="user"`, `tag_label="USER"`, `tag_color="#58a6ff"`

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▼ USER  can you tell me my system info?                 │
├─────────────────────────────────────────────────────────┤
│ User Prompt:                                            │
│ can you tell me my system info?                         │
│ ─────────────────────────────────────────────────────── │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ ┌─ ▶ ✨ Enhanced Prompt ─────────────────────────┐  │ │
│ │ │  Goal: Gather system information               │  │ │
│ │ │  Targets: system, environment                  │  │ │
│ │ │  ─────────────────────────────────────────     │  │ │
│ │ │  Original: can you tell me my system info?     │  │ │
│ │ │  Enhanced: Get comprehensive system info...    │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ ┌─ ▼ ● sago — Technical Reasoning ───────────────┐  │ │
│ │ │  Checking system info requires env_info tool   │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ ┌─ ▶ ● OK Tool: env_info  by @sago ─────────────┐  │ │
│ │ │  Parameters:                                   │  │ │
│ │ │    operation: system                           │  │ │
│ │ │    detail: full                                │  │ │
│ │ │  Result Output:                                │  │ │
│ │ │    OS: Linux, Arch: aarch64, Hostname: pi5    │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ [SAGO]                                              │ │
│ │ Your system is running Linux on an aarch64         │ │
│ │ architecture, likely a Raspberry Pi 5...            │ │
│ │                                                     │ │
│ │ ┌─ ▶ Turn Summary (1.2s) ─────────────────────┐   │ [DEV]
│ │ │  1 tool(s) (1 ok) | 300 tokens | 1.2s       │   │ [DEV]
│ │ └────────────────────────────────────────────────┘   │ [DEV]
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Components mounted (systematic order `thinking → tool` via `ExchangeTurnCard.mount_sequential`):**
1. Enhanced prompt collapsible — collapsed (if enhancement enabled)
2. Thinking card (if any) — per-agent header, seq=1, before tool
3. Tool call collapsible — per-agent suffix `by @sago`, collapsed, seq=2
4. Agent tag + assistant message
5. Dev trace bar (dev mode) + Turn Summary

---

## 3. Normal Message With Multiple Iterations — Systematic Order

**Trigger:** LLM calls tools, reasons, calls more tools across multiple loop iterations. **All flows now enforce strict `thinking1 → tool1 → thinking2 → tool2 …` interleaving in execution order** — not bulk at end.

**Card:** `card_type="user"`, `tag_label="USER"`, `tag_color="#58a6ff"`

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▼ USER  refactor the auth module and add tests          │
├─────────────────────────────────────────────────────────┤
│ User Prompt:                                            │
│ refactor the auth module and add tests                  │
│ ─────────────────────────────────────────────────────── │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ ┌─ ▶ ✨ Enhanced Prompt ─────────────────────────┐  │ │
│ │ │  Goal: Refactor auth + add test coverage       │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ ┌─ ▼ ● sago — Technical Reasoning (seq 1) ───────┐ │ │
│ │ │  Need to read existing auth module first       │ │ │
│ │ └────────────────────────────────────────────────┘ │ │
│ │                                                     │ │
│ │ ┌─ ▶ ● OK Tool: read_file  by @sago ───────────┐  │ │
│ │ │  Parameters: {path: "src/auth.py"}            │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ ┌─ ▼ ● sago — Technical Reasoning (seq 3) ───────┐ │ │
│ │ │  File shows tangled logic, will split concerns │ │ │
│ │ └────────────────────────────────────────────────┘ │ │
│ │                                                     │ │
│ │ ┌─ ▶ ● OK Tool: write_file  by @sago ──────────┐  │ │
│ │ │  Parameters: {path: "src/auth.py", ...}       │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ ┌─ ▶ ✗ FAILED Tool: run_shell  by @sago ───────┐  │ │
│ │ │  Parameters: {cmd: "pytest tests/"}           │  │ │
│ │ │  Result: 1 test failed in test_login...       │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ ┌─ ▼ ● sago — Technical Reasoning (seq 6) ───────┐ │ │
│ │ │  Test failure indicates missing mock           │ │ │
│ │ └────────────────────────────────────────────────┘ │ │
│ │                                                     │ │
│ │ ┌─ ▶ ● OK Tool: run_shell  by @sago ───────────┐  │ │
│ │ │  Parameters: {cmd: "pytest tests/"}           │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ [SAGO]                                              │ │
│ │ Auth module has been refactored...                  │ │
│ │                                                     │ │
│ │ ┌─ ▶ Turn Summary (8.3s) ─────────────────────┐   │ [DEV]
│ │ └────────────────────────────────────────────────┘   │ [DEV]
│ │ ┌─ ▼ ● Summary — by agent ─────────────────────┐   │ │
│ │ │  @sago: read_file (1), write_file (1), run_shell (2) │ │
│ │ │  Tokens: 2.1k | Output: src/auth.py          │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Components mounted (in call order, each `mount_sequential` assigns `seq_id`):**
1. Enhanced prompt collapsible — collapsed
2. `thinking(seq=1)` — per-agent header `● sago — Technical Reasoning`
3. `tool(seq=2)` — `by @sago` suffix
4. `thinking(seq=3)` — next reasoning before next tool
5. `tool(seq=4)` — etc., strict interleaving
6. Agent tag + assistant message
7. Dev trace bar + Turn Summary + **Auto Summary — by agent** (collapsed=False) — see §15

**Note:** `ExchangeTurnCard.mount_sequential(widget)` inserts `before=.exchange-response` but respects `seq_id` increments, so order is deterministic and survives reload. `DevTracer.record_thinking` now dedups **only** exact duplicate `[:300]` from same `source` within 5s — per-agent, per-step distinct (no global coalesce).

---

## 4. /chain Command

**Trigger:** `/chain architect -> python-engineer -> devops deploy my app`

**Card:** `card_type="chain"`, `tag_label="CHAIN"`, `tag_color="#79c0ff"`

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▶ CHAIN  deploy my app                                 │
├─────────────────────────────────────────────────────────┤
│ Chain: architect -> python-engineer -> devops           │
│ ─────────────────────────────────────────────────────── │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ ┌─ HandoffFlow  architect ─► python-engineer ─► devops ┐ │ │
│ │ │  [pending → running → completed]                │ │ │
│ │ └────────────────────────────────────────────────┘ │ │
│ │                                                     │ │
│ │ ┌─ ▼ ● architect — Technical Reasoning ──────────┐ │ │
│ │ └────────────────────────────────────────────────┘ │ │
│ │ ┌─ ▶ ● OK Tool: ast_grep  by @architect ───────┐ │ │
│ │ └────────────────────────────────────────────────┘ │ │
│ │ ┌─ ▼ ● python-engineer — Technical Reasoning ──┐ │ │
│ │ └────────────────────────────────────────────────┘ │ │
│ │ ┌─ ▶ ● OK Tool: execute_shell  by @python-engineer ┐ │ │
│ │ └────────────────────────────────────────────────┘ │ │
│ │                                                     │ │
│ │ [devops-engineer]                                   │ │
│ │ Deployment complete. App is running on port 8080.   │ │
│ │                                                     │ │
│ │ ┌─ ▼ ● Summary — by agent ─────────────────────┐  │ │
│ │ │  @architect: repo_map (1), ast_grep (3) ...   │  │ │
│ │ │  @python-engineer: execute_shell (4), grep (5) │  │ │
│ │ │  Tokens: 21k | Output: PROJECT_ANALYSIS.md    │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**What's visible (updated):**
- `HandoffFlow` widget shows `pending → running → completed` per step (uses fresh guard, no thread-local stale)
- **All** per-agent `thinking` and `tool` cards are now visible inline, interleaved in execution order via `mount_sequential`, with `by @agent` suffixes (previously only final output shown)
- Final accumulated output from last agent
- **Auto Summary — by agent** (`Collapsible(title="● Summary — by agent", collapsed=False)`) with per-agent tool counts, token cost, output file — mounted automatically after chain completes (orchestrator.py), so user sees summary without asking
- If an agent is skipped, inline notice: `"Skip {agent}: {reason}"`

**Components mounted (uniform path — chain/parallel/delegate/normal all use `mount_sequential` + `ToolUsageStore` + `DevTracer`):**
1. HandoffFlow widget (chain only)
2. Per-agent thinking/tool cards in call order (seq-tagged)
3. Agent tag + final assistant message
4. Summary — by agent (expanded)

**Not shown (still):**
- Intermediate agent outputs beyond final (only tools/reasoning are shown, not duplicate prose)

---

## 5. /delegate Command

**Trigger:** `/delegate python-engineer write a hello world script`

**Card:** `card_type="delegate"`, `tag_label="DELEGATE"`, `tag_color="#bc8cff"`

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▶ DELEGATE  write a hello world script                  │
├─────────────────────────────────────────────────────────┤
│ @python-engineer                                        │
│ ─────────────────────────────────────────────────────── │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ ┌─ ▶ ✨ Enhanced Prompt ─────────────────────────┐  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │ ┌─ ▼ ● python-engineer — Technical Reasoning ────┐ │ │
│ │ └────────────────────────────────────────────────┘ │ │
│ │ ┌─ ▶ ● OK Tool: write_file  by @python-engineer ┐ │ │
│ │ └────────────────────────────────────────────────┘ │ │
│ │ [python-engineer]                                   │ │
│ │ Created hello.py ...                                │ │
│ │ ┌─ ▼ ● Summary — by agent ─────────────────────┐  │ │
│ │ │  @python-engineer: write_file (1) | Tokens... │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Components (uniform):** Enhanced prompt → thinking (by @python-engineer) → tool (by @python-engineer) → assistant → Summary — by agent (auto, expanded). Uses same `mount_sequential` + DB persistence as normal.

---

## 6. /orchestrate Command

**Trigger:** `/orchestrate build a full REST API with auth`

**Card:** `card_type="orchestrate"`, `tag_label="ORCHESTRATE"`, `tag_color="#3fb950"`

### Phase 1: Planning

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▶ ORCHESTRATE  build a full REST API with auth          │
├─────────────────────────────────────────────────────────┤
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ ⠹ Analyzing task for delegation...                  │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

● Orchestration plan (4 steps):
  1. architect: Design API schema and auth flow
  2. python-engineer: Implement endpoints and middleware
  3. test-engineer: Write integration tests
  4. devops-engineer: Create Dockerfile and deploy config

┌─────────────────────────────────────────────────────────┐
│ [Approve] [Deny]     Execute 4 steps? Press [Y] or [N] │
└─────────────────────────────────────────────────────────┘
```

### Phase 2: Execution (after approval)

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▶ ORCHESTRATE  build a full REST API with auth          │
├─────────────────────────────────────────────────────────┤
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ ⠹ Step 2/4: python-engineer                        │ │
│ │ ... (each step runs SpawnAgentTool with shared guard)│ │
│ │ ┌─ ▼ ● python-engineer — Technical Reasoning ─────┐│ │
│ │ ┌─ ▶ ● OK Tool: write_file  by @python-engineer ─┐│ │
│ │ [devops-engineer]                                   │ │
│ │ Orchestration complete (4 steps): API built...      │ │
│ │ ┌─ ▼ ● Summary — by agent ─────────────────────┐  │ │
│ │ │  @architect: ... @python-engineer: ...        │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Uniform handling:** Orchestration uses same `set_execution_callbacks(on_tool_call/on_tool_result/on_thinking)` with per-agent `source=agent.{name}` so reasoning is distinct per step, same `mount_sequential`, same `HandoffContext` + `create_fresh_guard()` passed explicitly to `SpawnAgentTool` (no thread-local stale), same DB flush, same auto Summary — by agent after completion.

---

## 7. Parallel Execution

**Trigger:** `/parallel python-engineer: analyze code, reviewer: review api, frontend-engineer: fix dashboard`

**Card:** `card_type="parallel"` (created by `_add_command_turn`)

**Per-agent task format:**
```
/parallel python-engineer: analyze my python code, reviewer: review the api, frontend-engineer: fix dashboard
```

**Shared task format (backward compatible):**
```
/parallel python-engineer,go-engineer build a web page
```

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▼ USER  /parallel python-engineer,go-engineer,...       │
├─────────────────────────────────────────────────────────┤
│ User Prompt:                                            │
│ /parallel python-engineer,go-engineer,... build a page  │
│ ─────────────────────────────────────────────────────── │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ (spinner during execution, HandoffFlow not used)    │ │
│ │ ✓ [AGENT: python-engineer] (completed in 3.2s)      │ │
│ │   ┌─ ▼ ● python-engineer — Technical Reasoning ──┐│ │
│ │   ┌─ ▶ ● OK Tool: read_file  by @python-engineer ┐│ │
│ │ ✓ [AGENT: go-engineer] (completed in 2.8s)          │ │
│ │   ┌─ ▼ ● go-engineer — Technical Reasoning ──────┐│ │
│ │   ┌─ ▶ ● OK Tool: write_file  by @go-engineer ───┐│ │
│ │ ● Parallel complete: 3 ok, 0 failed | 3.2s wall    │ │
│ │ ┌─ ▼ ● Summary — by agent ─────────────────────┐  │ │
│ │ │  @python-engineer: read_file (2) ...         │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Uniform handling:** Parallel uses `ThreadPoolExecutor` + `create_fresh_guard()` shared explicitly, same per-agent `on_thinking`/`on_tool_result` callbacks, same `mount_sequential` (tools may complete out-of-order but seq reflects actual completion), same DB persistence, auto Summary — by agent after `hide_parallel_bar`.

---

## 8. Session Reload

**Trigger:** `/load <session-id>` or `sago tui --resume <session-id>`

Reconstructs the conversation from DB **preserving systematic order**.

```
┌─ ExchangeTurnCard (user msg 1) ────────────────────────┐
│ ▼ USER  first question                                 │
│ ...                                                    │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ ┌─ ▼ ● sago — Technical Reasoning (seq 1) ─────────┐│ │
│ │ ┌─ ▶ ● OK Tool: env_info  by @sago  (seq 2) ──────┐│ │
│ │ [SAGO] first answer...                              │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

┌─ ExchangeTurnCard (user msg 2) ────────────────────────┐
│ ▼ USER  follow-up question                             │
│ ...                                                    │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ ┌─ ▼ ● python-engineer — Technical Reasoning ──────┐│ │
│ │ ┌─ ▶ ● OK Tool: grep_content  by @python-engineer ┐│ │
│ │ [SAGO] second answer...                             │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Reconstruction order per turn (systematic, deterministic):**
1. `ExchangeTurnCard` with user prompt (seq base)
2. Enhanced prompt collapsible (if `metadata.enhancement`) — mounted via `mount_sequential` BEFORE response container, collapsed, seq preserved
3. **Thinking blocks** — from `messages.metadata.thinking_blocks[]` sorted by `seq` (per-agent, per-step distinct). Each is `Collapsible(title="● {agent} — Technical Reasoning", collapsed=False)` mounted via `mount_sequential` so interleaving is restored. Fallback to legacy `metadata.thinking` string if blocks absent.
4. **Tool call collapsibles** — from `ToolUsageStore.get_all()` matched by `created_at` timestamp to nearest preceding user card, args parsed from DB, titles include `by @agent` suffix, collapsed, mounted via `mount_sequential` in `created_at` order.
5. Agent tag — inside response container
6. Assistant message (markdown) — inside response container
7. Summary — by agent (if present in DB? not stored, regenerated on reload via `get_summary_by_agent`)

**Reconstructed from DB:**
- `messages.metadata.thinking_blocks` (list of `{seq, agent, text, timestamp}`) — primary; also `thinking` legacy field
- `messages.metadata.enhancement` (PromptEnhancementResult)
- `tool_usage` table (`tool_name, arguments, result, duration_ms, success, created_at`) — full args/results
- `messages` content (assistant prose)

**Not reconstructed (transient):**
- Execution plan cards (not stored)
- Turn summaries (derived, not stored)
- Dev trace bars (transient, but `trace.md/json` artifacts persisted on disk under `.sago/data/<sid>/` if dev mode was on)

**DB persistence details (§20):**
- `MessageStore.add()` flushes at batch 50 or on demand; `ToolUsageStore.log()` flushes at 20. Both `flush()` before `Session.get_full_export()`.
- `messages.metadata` JSON contains `thinking_blocks`, `thinking`, `model`, `agent`, `meta_str`.
- Reload sorts `thinking_blocks` by `seq` and mounts via `mount_sequential`; tool cards sorted by `created_at` and matched to cards by timestamp `<= tool_time`.

---

## 9. Error States

### 9a. Inline Error (inside exchange-response)

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▼ USER  do something dangerous                          │
├─────────────────────────────────────────────────────────┤
│ User Prompt:                                            │
│ do something dangerous                                  │
│ ─────────────────────────────────────────────────────── │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ ✗ Error: Permission denied for tool "shell_exec"    │ │
│ │   Hint: Enable YOLO mode with /yolo to auto-allow  │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 9b. Standalone Error (no active card)

```
● ✗ Error: Authentication failed. Check your OpenAI API key.

● ✗ Error: Rate limited. Wait a few seconds or check credits.

● ✗ Error: Model 'gpt-99' not found. Try a different model with /model.
```

### 9c. LLM Error (rendered as assistant message)

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▼ USER  something that causes an LLM error              │
├─────────────────────────────────────────────────────────┤
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ ❌ **Error:** Connection timeout.                    │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 9d. Chain/Orchestration Error

```
┌─ ExchangeTurnCard (chain) ─────────────────────────────┐
│ ▶ CHAIN  deploy my app                                 │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ ✗ Error: Chain error: Agent "invalid-agent" not     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 10. Approval Prompts

### 10a. Tool Permission Approval

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▼ USER  edit the config file                            │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ Allow edit_file? (risk: high) -- Press [Y] or [N]  │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ [Approve] [Deny]     Allow edit_file? (risk: high)     │
└─────────────────────────────────────────────────────────┘
```

**Not shown when:** YOLO mode is enabled (all tools auto-approved)

### 10b. Orchestration Plan Approval

```
┌─────────────────────────────────────────────────────────┐
│ [Approve] [Deny]     Execute 4 steps? Press [Y] or [N] │
└─────────────────────────────────────────────────────────┘
```

### 10c. Git Commit Approval

```
┌─────────────────────────────────────────────────────────┐
│ [Approve] [Deny]     Commit: "fix: auth bug"?          │
└─────────────────────────────────────────────────────────┘
```

### 10d. Todo Confirmation

```
┌─────────────────────────────────────────────────────────┐
│ [Approve] [Deny]     Confirm: Run database migration?  │
└─────────────────────────────────────────────────────────┘
```

---

## 11. System Messages (Standalone)

These appear directly in `#messages`, NOT inside any ExchangeTurnCard.

```
● 📝 Changed 3 files: src/auth.py, tests/test_auth.py, config.yaml

● 🛡️ Workspace Snapshot Saved: checkpoint_20250115_103045

● ⚡ [STOP] Token budget exhausted (50000 tokens used). Finishing up.

● Parallel complete: 3 ok, 0 failed | Total wall time: 3.2s

● Loaded session abc123def456 (24 messages)

● Orchestration plan (4 steps):
    1. architect: Design API schema
    2. python-engineer: Implement endpoints
```

---

## 12. Thinking/Reasoning Blocks — Per-Agent, Sequential

**Trigger:** LLM output contains `<thinking>...</thinking>` or `<thought>...</thought>` tags, OR native Gemini `part.thought`, OR OpenRouter `delta.reasoning`/`delta.thinking` streaming. Also `on_thinking` callback from `simple_executor` per iteration.

**New behavior (v0.1.14):**
- **Per-agent distinct:** Title is `● {agent} — Technical Reasoning` (e.g., `● architect — Technical Reasoning`, `● python-engineer — Technical Reasoning`) — not generic `Technical Reasoning & Analysis`. `DevTracer.record_thinking` stores `source=agent.{name}` and dedups only exact duplicate `[:300]` from same source within 5s (previously global coalesce within 120s hid per-agent).
- **Sequential, not bulk:** Each iteration mounts a **new** card via `ExchangeTurnCard.mount_sequential` with incrementing `seq_id` so `thinking1 → tool1 → thinking2 → tool2 …` appears in execution order, not all thinking at end. `thinking_blocks` list in `messages.metadata` preserves `{seq, agent, text, timestamp}` for reload.
- **Expanded by default:** `collapsed=False` (visible) to avoid hidden reasoning; user can collapse per card.

```
┌─ ▼ ● python-engineer — Technical Reasoning (seq 3) ────┐
│  The grep didn't surface the indexer. The hybrid search │
│  engine likely lives in sago/search/ — need to locate  │
└────────────────────────────────────────────────────────┘
```

**Properties:**
- Content stripped from assistant message before rendering (`re.sub` thinking tags)
- Mounted via `mount_sequential` BEFORE next tool card, ordered by `seq`
- Dedupe: same `[:300]` from same agent within 5s is skipped (avoids spinner spam)
- Persisted: `messages.metadata.thinking_blocks` JSON, plus `DevTracer` `LLM_THINKING` events per agent
- Reload: sorted by `seq`, mounted via `mount_sequential` to preserve interleaving

---

## 13. Execution Plan Card

**Trigger:** Complex task detected by `_is_complex_task()`.

```
┌─ ▶ Execution Plan (4 steps) ───────────────────────────┐
│  1. Read existing auth module structure                │
│  2. Refactor into separate concerns                    │
│  3. Add comprehensive test suite                       │
│  4. Run tests and verify coverage > 80%               │
└────────────────────────────────────────────────────────┘
```

**Properties:**
- Collapsed by default
- Only created for complex tasks (not all messages)
- Mounted before tool calls in the response container
- Updated in-place via `_update_plan_progress` as steps complete (`completed`/`in_progress`)

---

## 14. Turn Summary

**Trigger:** Only shown when `show_summary=True` (toggled via `/summary`).

```
┌─ ▶ Turn Summary (8.3s) ────────────────────────────────┐
│  5 tool(s) (4 ok, 1 fail)                              │
│  2100 tokens (1500+600)                                │
│  Cache: 2 hit, 1 miss                                  │
│  Files: src/auth.py, tests/test_auth.py                │
└────────────────────────────────────────────────────────┘
```

**Properties:**
- Collapsed by default
- Only visible when explicitly enabled
- Shows tool counts, tokens, elapsed time, cache stats, files modified
- Mounted via `mount_child` (before response) but transient (not persisted)

---

## 15. Summary — By Agent (Auto Card + Zero-Tool Short-Circuit)

**New in v0.1.14 — addresses token waste from re-running analysis on “so what was the summary?”**

### 15a. Auto-Mounted Card After Chain/Orchestration/Delegate/Parallel

After any orchestration completes (chain step 20/20, orchestrate plan done, delegate done, parallel done), `helpers._add_summary_by_agent_card()` is called automatically:

```
┌─ ▼ ● Summary — by agent ─────────────────────────────┐
│  @architect                                          │
│    ✓ repo_map (1), read_file (4), ast_grep (3)       │
│    ✓ write_file (1)  — PROJECT_ANALYSIS.md           │
│    ↳ Wrote 91-line analysis with 339 agents ...      │
│                                                      │
│  @python-engineer                                     │
│    ✓ read_file (1), execute_shell (4), grep (5)       │
│    ✓ read_file (1) — PROJECT_ANALYSIS.md (cached)    │
│    ↳ Verified 548 Python files, 339 agents ...       │
│                                                      │
│  ── Total: 28 tool(s) | Tokens: 21k | Elapsed: 4.2s ──│
│  Output: PROJECT_ANALYSIS.md (8k chars cached — 0 re-analysis) │
└──────────────────────────────────────────────────────┘
```

**Properties:**
- `Collapsible(title="● Summary — by agent", collapsed=False)` — **expanded** so user sees without asking
- Per-agent sections: tools with counts + 3 recent tool details (`✓/✗ tool args`), last output preview per agent, `by @agent` distinction
- Global footer: total tools, tokens, elapsed, output file
- Output file inferred from `PROJECT_ANALYSIS.md` on disk or `write_file` tool args — shows `X chars cached — 0 re-analysis` when from cache
- Mounted via `mount_child`/`mount_sequential` inside active `ExchangeTurnCard` (falls back to `#messages` if card missing)
- No LLM call for this card itself — deterministic from `ToolUsageStore.get_all()` + `session_tool_calls` + `DevTracer` + `messages` + `PROJECT_ANALYSIS.md`

### 15b. Summary Intent Short-Circuit (0 Tool Calls)

When user asks `so what was the sumamry?`, `summarize what you did`, `what was done`, `what did you do` etc., the system **does NOT re-run tools** (no new `grep`, `execute_shell`).

**Detection:** `processor._is_summary_intent()` via spec regex `r"\b(summar|what was done|what did you do)\b"` plus typo-tolerant fallbacks (`summar`/`sumam` substring, `\bsum\w*ry\b`, `what was the summ`). Also `context_assembler.assemble()` short-circuits heavy RAG/BM25/symbol search, and `intent_classifier` is bypassed.

**Short-circuit path (`processor._handle_summary_intent`):**
1. Gather cached data **only**: `self.messages`, `ToolUsageStore.get_all()`, `DevTracer.get_recent_traces()`, `PROJECT_ANALYSIS.md` or `Session.get_full_export()`, `total_input_tokens`/`total_output_tokens`.
2. Build deterministic `local_md` via `_build_local_summary_markdown()` — categorized by agent, no LLM needed.
3. **Single LLM call** with `tool_choice: none` (no tool loop) and injected Reference Context (8000 chars) — not a tool loop. If LLM fails (no key), falls back to `local_md`. This is **1 LLM, 0 tools** vs. previously 14+ tools wasted.
4. Mount result as `assistant` message (`[SAGO]`) plus auto `● Summary — by agent` card.
5. Spinner shows `Summarizing previous work (0 tools)…`, tracer records `summary({model})` as single `LLM_PAYLOAD`.

**Validation:**
- Summary query creates **1** new `LLM_PAYLOAD` event, **0** new `TOOL_DISPATCH` events (check `DevTracer.get_recent_traces()` delta).
- `PROJECT_ANALYSIS.md` is reused verbatim (no `ast_grep`, `grep_content` on summary turn).

---

## 16. Dev Trace Bar & Inspector

**Trigger:** `developer_mode=True` **AND** trace events exist. **v0.1.14: `developer_mode` defaults to `True` until 1.0** (`sago.yaml: dev_mode: true # TODO: flip to false at 1.0`, `loader.py SettingsConfig dev_mode: True`, `app.py developer_mode: True`, `settings.json dev_mode: True`). Fresh install shows Inspector without `/dev on`.

```
[12 events · 3 LLM · 5 tools · 2 routes] [View Trace ⚡]
```

**Inspector (`F2` or `[View Trace ⚡]`):**
- Header: `Inspector 12 events · 3 LLM · 5 tools · 2 routes · 3 thinking`
- Tabs: `Events`, `LLM`, `Tools`, `Thinking`, `Flow`, `Event Graph`, `Timeline`
- **Thinking tab:** now per-agent distinct (architect vs python-engineer), deduped only same source within 5s — not globally coalesced. Each thinking shows `source=agent.{name}`, `model`, `thinking_length`, `seq`.
- **Flow:** shows `thinking → tool` as paired lines? Actually as sequential steps: `thinking(seq1) → tool(seq2) → thinking(seq3) → tool(seq4)` with agent labels, not separate numbered reasoning.
- **Event Graph:** Mermaid flowchart `User → agent_architect → tool_ast_grep → agent_python-engineer → tool_execute_shell → LLM` with per-agent nodes, not `agent_subagent` generic.
- Access: `F2` or button, also per-turn `[View Trace ⚡]` badge (when dev mode).

**Properties:**
- Auto-enabled on fresh install (no `/dev on` needed)
- Trace bar mounted as `Horizontal` below assistant message, badge + button
- Artifacts persisted to `.sago/data/<session_id>/trace.md` + `trace.json` + `chat_export.md` via `export_session_dev_artifacts()` on exit (when dev mode)

---

## 17. Confidence/Verification Score

**Trigger:** Tools were used in the turn.

| Level | Condition | Display |
|-------|-----------|---------|
| High | confidence >= 80 | `✅ Confidence: 92/100 — verified (3 tool calls)` |
| Medium | 50 <= confidence < 80 | `🔍 Confidence: 65/100 — minor verification notes` |
| Low | confidence < 50 | `⚠️ Low confidence (35/100): content claims without tools` |

**Current behavior:** Always shown as system message in `#messages` — but **desired** (and now implemented) is log to file only, show in UI only if `developer_mode=True` (default ON).

---

## 18. Hallucination/Fabrication Warnings

**Trigger:** LLM claims to have done something without actually calling the corresponding tool.

**Internal behavior (not user-visible):**
- LLM receives correction: `"STOP. You are fabricating results..."`
- Loop continues with another iteration

**User-visible behavior:**
- Hallucination verifier runs AFTER the loop
- If hallucinations detected, content is cleaned before display
- No explicit warning shown to user (content is silently corrected)

---

## 19. Spinner/Thinking Indicator

**Trigger:** Any processing starts (message, delegation, chain, orchestration).

```
⠹ Running: env_info({})                    (during tool execution)
⠹ Step 2/5...                              (during iteration)
⠹ Delegating to python-engineer...         (during delegation)
⠹ Step 1/4: architect                      (during chain)
⠹ Enhanced: Gather system information      (during enhancement)
⠹ Summarizing previous work (0 tools)…     (during summary short-circuit)
```

**Properties:**
- Animated braille spinner
- Mounts inside exchange-response container
- Text updates as processing progresses
- Removed when processing completes
- Summary spinner explicitly shows `0 tools` to signal no waste

---

## 20. Systematic Thinking → Tool Pipeline & DB Persistence

### 20a. Systematic Order Guarantee

All 4 flows (`normal` via `processor.py`, `chain`/`delegate`/`parallel`/`orchestrate` via `orchestrator.py`) share the **same** callback and mounting path:

```python
# In both processor.py and orchestrator.py — per-agent distinct
def on_tool(name, args, agent_name=""):
    call_from_thread(_add_tool_call, name, args, result, success, agent_name)

def on_thinking(text, agent_name=""):
    # filter synthetic "Planning... step 1/30" etc.
    call_from_thread(_add_thinking_card, text, agent_name)
    get_dev_tracer().record_thinking(source=f"agent.{agent_name}", ...)

# In helpers.py — sequential mount
ExchangeTurnCard.mount_sequential(widget)  # inserts before .exchange-response but increments seq_id
```

- `mount_sequential` assigns `widget._seq_id = seq` and mounts `before=.exchange-response` in call order — so `thinking1(seq1) → tool1(seq2) → thinking2(seq3) → tool2(seq4)` is deterministic.
- `DevTracer.record_thinking` dedupes only same `source` + same `[:300]` within 5s — per-agent preserved.
- No bulk at end — previously `_add_thinking_card` appended after tools; now interleaved.

### 20b. DB Persistence (Reload Fidelity)

- **Thinking:** `helpers._add_thinking_card` buffers to `self._current_thinking_buffer: list[dict{seq, agent, text, timestamp}]`. On `helpers._add_assistant_message`, this buffer is merged into `messages` list and persisted to `MessageStore` as `metadata.thinking_blocks` JSON + legacy `thinking` string + `model` + `agent`. Also `thinking_blocks` sorted by `seq` on save.
- **Tools:** `processor.on_tool_result` and `orchestrator.on_tool_result` both call `ToolUsageStore.log(tool_name, arguments, result, duration_ms, success)` which batches at 20 and `flush()` before export. Also `self.session_tool_calls` in-memory list with `agent` field.
- **Messages:** `MessageStore.add(role, content, agent_name, metadata)` batched at 50, `flush()` before `Session.get_full_export()`.
- **Flush points:** Before `Session.get_full_export()`, before `DevTracer.export`, before `_load_session` read.

### 20c. Reload Fidelity (Same Order)

`commands._load_session` and `_switch_session` reconstruct by:

1. Sorting `thinking_blocks` by `seq`
2. Matching `tool_usage.created_at` to nearest preceding `message.created_at` (timestamp correlation)
3. Mounting both via `mount_sequential` in `created_at`/`seq` order — not bulk
4. Result: reload of `2e6cdf4e-ea4` shows same 3 `● architect — Technical Reasoning` + `● python-engineer — Technical Reasoning` cards in same positions, not collapsed to 1.

### 20d. Uniform Handling Table

| Flow | Entry | Thinking → Tool Mount | DB Persist | Summary Card |
|------|-------|----------------------|------------|--------------|
| Normal chat | `processor._process_message_thread` | `mount_sequential`, per-agent | `thinking_blocks` + `tool_usage` | via `_handle_summary_intent` or `_add_summary_by_agent_card` if asked |
| /chain | `orchestrator._process_chain_thread` | same, + `HandoffFlow` | same, + `handoff_ctx.files_created` | auto after completion (collapsed=False) |
| /delegate | `orchestrator._process_delegation_thread` | same | same | auto after completion |
| /parallel | `orchestrator._process_parallel_thread` | same (ThreadPool, shared guard) | same | auto after `hide_parallel_bar` |
| /orchestrate | `orchestrator._process_orchestration_thread` + `_execute_orchestration_plan_thread` | same, shared `create_fresh_guard()` | same | auto after `orchestration complete` |

### 20e. Inspector Alignment

- **Before:** `Inspector 12 events 3 thinking` coalesced globally — chat showed 1 thinking, trace showed 1, DB had 1 — felt broken.
- **After:** `Inspector 19 events 6 LLM 3 thinking` per 2e6cdf4e-ea4 — chat shows 3 distinct per-agent thinking cards, trace shows 3 `LLM_THINKING` events with `source=agent.architect` vs `agent.python-engineer`, DB has 3 `thinking_blocks`, reload preserves 3.

---

## Summary: What Gets Mounted Where

### Inside `exchange-body` (per turn, in order via `mount_sequential`):
1. User Prompt header
2. User Prompt content
3. Divider (`───`)
4. **Enhanced prompt collapsible** (if enhancement enabled, collapsed) — seq N
5. **Thinking/Tool interleaving** — each `thinking` and `tool` gets next `seq_id`, mounted `before=.exchange-response` in call order:
   - `thinking(seq=1)` — `● {agent} — Technical Reasoning`, expanded
   - `tool(seq=2)` — `● OK Tool: read_file by @agent`, collapsed
   - `thinking(seq=3)` — next reasoning
   - `tool(seq=4)` — etc.
6. Response container (`.exchange-response`):
   - (Thinking fallback — legacy inline `<thinking>` tags still mounted here if not via `mount_sequential`)
   - Agent tag
   - Assistant message (markdown + code blocks)
   - Dev trace bar (if dev mode — default ON)
   - Turn summary collapsible (if `show_summary`)
   - **● Summary — by agent** (after chain/orchestrate/parallel/delegate OR after summary query — expanded, collapsed=False)

### Inside `#messages` (standalone, between turns):
- System messages (errors, checkpoints, etc.)
- Approval bars
- Parallel agent results (progressively streamed)
- Confidence score (only shown in developer mode, always logged)
- HandoffFlow / OrchestrationPlanWidget (chain/orchestrate — inside exchange card, not standalone)

### NOT mounted anywhere:
- Hallucination warnings (content silently cleaned)
- Tool calls from spawned agents duplicated outside their per-agent card (now correctly attributed via `by @agent`)

