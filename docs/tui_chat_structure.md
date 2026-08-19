# TUI Chat Message Structures — Complete Reference

Every possible message flow in the Sago TUI, with exact component order and nesting.

---

## Table of Contents

1. [Normal Message (No Tools)](#1-normal-message-no-tools)
2. [Normal Message With Tools (Single Iteration)](#2-normal-message-with-tools-single-iteration)
3. [Normal Message With Multiple Iterations](#3-normal-message-with-multiple-iterations)
4. [/chain Command](#4-chain-command)
5. [/delegate Command](#5-delegate-command)
6. [/orchestrate Command](#6-orchestrate-command)
7. [Parallel Execution](#7-parallel-execution)
8. [Session Reload (/load or --resume)](#8-session-reload)
9. [Error States](#9-error-states)
10. [Approval Prompts (YOLO Mode)](#10-approval-prompts)
11. [System Messages (Standalone)](#11-system-messages-standalone)
12. [Thinking/Reasoning Blocks](#12-thinking-reasoning-blocks)
13. [Execution Plan Card](#13-execution-plan-card)
14. [Turn Summary](#14-turn-summary)
15. [Dev Trace Bar](#15-dev-trace-bar)
16. [Confidence/Verification Score](#16-confidenceverification-score)
17. [Hallucination/Fabrication Warnings](#17-hallucinationfabrication-warnings)
18. [Spinner/Thinking Indicator](#18-spinnerthinking-indicator)

---

## Key Conventions

| Symbol | Meaning |
|--------|---------|
| `┌─ ─ ─┐` | ExchangeTurnCard boundary |
| `├─ ─ ─┤` | Divider between prompt and response |
| `│  │` | Nesting level |
| `▶` | Collapsed collapsible |
| `▼` | Expanded collapsible |
| `[ DEV ]` | Only shown in developer mode |
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
│ │ ┌─ ▶ Technical Reasoning & Analysis ─────────────┐  │ │
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

**Components mounted (in order):**
1. Thinking collapsible (if `<thinking>` tags present) — collapsed
2. Agent tag: `Static("[SAGO]")`
3. Assistant message: `Static(RichMarkdown(content))`
4. Code snippet collapsibles (if code blocks in content) — expanded
5. Dev trace bar (if `developer_mode=True`)
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
│ │ ┌─ ▶ ● OK Tool: env_info ──────────────────────┐   │ │
│ │ │  Parameters:                                   │   │ │
│ │ │    operation: system                           │   │ │
│ │ │    detail: full                                │   │ │
│ │ │  Result Output:                                │   │ │
│ │ │    OS: Linux, Arch: aarch64, Hostname: pi5    │   │ │
│ │ └────────────────────────────────────────────────┘   │ │
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

**Components mounted (in order):**
1. Enhanced prompt collapsible — collapsed (if enhancement enabled)
2. Individual tool call collapsibles — collapsed (one per tool, no wrapper)
3. Agent tag: `Static("[SAGO]")`
4. Assistant message: `Static(RichMarkdown(content))`
5. Dev trace bar (if dev mode)
6. Summary collapsible (if `show_summary`) — collapsed

---

## 3. Normal Message With Multiple Iterations

**Trigger:** LLM calls tools, reasons, calls more tools across multiple loop iterations.

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
│ │ │  ...                                           │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ ┌─ ▶ ● OK Tool: read_file ─────────────────────┐   │ │
│ │ │  Parameters: {path: "src/auth.py"}            │   │ │
│ │ │  Result: (file contents)                       │   │ │
│ │ └────────────────────────────────────────────────┘   │ │
│ │                                                     │ │
│ │ ┌─ ▶ ● OK Tool: write_file ────────────────────┐   │ │
│ │ │  Parameters: {path: "src/auth.py", ...}       │   │ │
│ │ │  Result: File written successfully             │   │ │
│ │ └────────────────────────────────────────────────┘   │ │
│ │                                                     │ │
│ │ ┌─ ▶ ✗ FAILED Tool: run_shell ─────────────────┐   │ │
│ │ │  Parameters: {cmd: "pytest tests/"}           │   │ │
│ │ │  Result: 1 test failed in test_login...       │   │ │
│ │ └────────────────────────────────────────────────┘   │ │
│ │                                                     │ │
│ │ ┌─ ▶ ● OK Tool: run_shell ─────────────────────┐   │ │
│ │ │  Parameters: {cmd: "pytest tests/"}           │   │ │
│ │ │  Result: All 12 tests passed                   │   │ │
│ │ └────────────────────────────────────────────────┘   │ │
│ │                                                     │ │
│ │ ┌─ ▶ Technical Reasoning & Analysis ─────────────┐  │ │
│ │ │  (if LLM output contains <thinking> tags)      │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ [SAGO]                                              │ │
│ │ Auth module has been refactored with clean          │ │
│ │ separation of concerns. Tests added for...          │ │
│ │                                                     │ │
│ │ ┌─ ▶ Turn Summary (8.3s) ─────────────────────┐   │ [DEV]
│ │ │  5 tool(s) (4 ok, 1 fail) | 2.1k tokens     │   │ [DEV]
│ │ │  Files: src/auth.py, tests/test_auth.py      │   │ [DEV]
│ │ └────────────────────────────────────────────────┘   │ [DEV]
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Components mounted (in order):**
1. Enhanced prompt collapsible — collapsed
2. Individual tool call collapsibles — collapsed (one per tool call, flat list)
3. Thinking collapsible (if present) — collapsed
4. Agent tag: `Static("[SAGO]")`
5. Assistant message: `Static(RichMarkdown(content))`
6. Dev trace bar (if dev mode)
7. Summary collapsible (if `show_summary`) — collapsed

**Note:** Tool calls are flat — no nesting, no iteration grouping. Each tool call is a standalone collapsible.

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
│ │ [devops-engineer]                                   │ │
│ │ Deployment complete. App is running on port 8080.   │ │
│ │ Health check passing. All tests green.              │ │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**What's visible:**
- Only the FINAL accumulated output from the last agent
- Intermediate agent tool calls happen inside `SpawnAgentTool` — NOT individually visible
- If an agent is skipped, an inline notice is mounted: `"Skip {agent}: {reason}"`

**Components mounted (in order):**
1. Skip notices (if any agents were skipped)
2. Agent tag: `Static("[{last_agent}]")`
3. Final accumulated assistant message

**Not shown:**
- Individual agent outputs from intermediate steps
- Tool calls made by spawned agents
- Enhanced prompts from intermediate agents

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
│ │ │  (only if enhancement.was_modified)            │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ [python-engineer]                                   │ │
│ │ Created hello.py with a simple "Hello, World!"     │ │
│ │ print statement.                                    │ │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Components mounted (in order):**
1. Enhanced prompt collapsible (if applicable) — collapsed
2. Agent tag: `Static("[python-engineer]")`
3. Assistant message (or error inline on failure)

**Not shown:**
- Tool calls made by the delegated agent (happens inside `SpawnAgentTool`)

---

## 6. /orchestrate Command

**Trigger:** `/orchestrate build a full REST API with auth`

**Card:** `card_type="orchestrate"`, `tag_label="ORCHESTRATE"`, `tag_color="#3fb950"`

### Phase 1: Planning

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▶ ORCHESTRATE  build a full REST API with auth          │
├─────────────────────────────────────────────────────────┤
│ ─────────────────────────────────────────────────────── │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ ⠹ Analyzing task for delegation...                  │ │  (spinner)
│ │                                                     │ │
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
│ ─────────────────────────────────────────────────────── │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ ⠹ Step 2/4: python-engineer                        │ │  (spinner)
│ │                                                     │ │
│ │ ... (each step runs SpawnAgentTool internally)      │ │
│ │                                                     │ │
│ │ [devops-engineer]                                   │ │
│ │ Orchestration complete (4 steps): API built with    │ │
│ │ auth, tested, and containerized.                    │ │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Components mounted (in order):**
1. Plan summary (system message, not a card)
2. Approval bar (if not YOLO mode)
3. Spinner updates per step
4. Final assistant message from last agent

**Not shown:**
- Individual step outputs (only final accumulated result)
- Tool calls from spawned agents

---

## 7. Parallel Execution

**Trigger:** `/parallel python-engineer,go-engineer,tailwind-engineer build a web page`

**Card:** Standard `card_type="user"` (created by `_add_user_message`)

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▼ USER  /parallel python-engineer,go-engineer,...       │
├─────────────────────────────────────────────────────────┤
│ User Prompt:                                            │
│ /parallel python-engineer,go-engineer,... build a page  │
│ ─────────────────────────────────────────────────────── │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ (spinner during execution)                          │ │
│ │                                                     │ │
│ │ ✓ [AGENT: python-engineer] (completed in 3.2s)      │ │
│ │ Created index.html with responsive layout...        │ │
│ │ ```html                                             │ │
│ │ <div class="container">...</div>                    │ │
│ │ ```                                                 │ │
│ │                                                     │ │
│ │ ✓ [AGENT: go-engineer] (completed in 2.8s)          │ │
│ │ Built Go API server with routes for...              │ │
│ │ ```go                                               │ │
│ │ func main() { ... }                                 │ │
│ │ ```                                                 │ │
│ │                                                     │ │
│ │ ✓ [AGENT: tailwind-engineer] (completed in 2.1s)    │ │
│ │ Generated Tailwind config and utility classes...    │ │
│ │                                                     │ │
│ │ ● Parallel complete: 3 ok, 0 failed | 3.2s wall    │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Components mounted (in order):**
1. Agent results (one per agent, mounted as they complete):
   - Agent tag with completion time
   - Markdown content or code collapsibles
2. Summary system message: `"Parallel complete: X ok, Y failed | Xs wall time"`

**Note:** Results appear in completion order (not input order). Each agent's output is self-contained.

---

## 8. Session Reload

**Trigger:** `/load <session-id>` or `sago tui --resume <session-id>`

Reconstructs the conversation from DB. Order of mounting:

```
┌─ ExchangeTurnCard (user msg 1) ────────────────────────┐
│ ▼ USER  first question                                 │
│ ...                                                    │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ [thinking collapsible if stored]                    │ │
│ │ [SAGO] first answer...                              │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

┌─ ExchangeTurnCard (user msg 2) ────────────────────────┐
│ ▼ USER  follow-up question                             │
│ ...                                                    │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │ ┌─ ▶ ● OK Tool: env_info ──────────────────────┐   │ │
│ │ │  Parameters: {operation: "system"}            │   │ │
│ │ │  Result: OS: Linux, Arch: aarch64...          │   │ │
│ │ └────────────────────────────────────────────────┘   │ │
│ │ ┌─ ▶ ● OK Tool: env_info ──────────────────────┐   │ │
│ │ │  Parameters: {operation: "memory"}            │   │ │
│ │ │  Result: Total: 15 GB, Available: 4 GB...     │   │ │
│ │ └────────────────────────────────────────────────┘   │ │
│ │ [SAGO] second answer...                             │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Reconstruction order per turn:**
1. ExchangeTurnCard with user prompt
2. Enhanced prompt collapsible (if stored in metadata) — mounted in exchange-body BEFORE response container, collapsed
3. Tool call collapsibles (matched by timestamp from `ToolUsageStore`, args parsed from DB) — mounted in exchange-body BEFORE response container, collapsed
4. Thinking collapsible (if stored in message content) — inside response container
5. Agent tag — inside response container
6. Assistant message (markdown) — inside response container

**Reconstructed from DB:**
- Enhanced prompt cards (stored in message metadata)
- Tool calls with full args and results (stored in `tool_usage` table)
- Thinking blocks (stored in assistant message content)

**Not reconstructed:**
- Execution plan cards (not stored)
- Turn summaries (not stored)
- Dev trace bars (not stored)

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
│ │                                                     │ │
│ │ ✗ Error: Permission denied for tool "shell_exec"    │ │
│ │   Hint: Enable YOLO mode with /yolo to auto-allow  │ │
│ │                                                     │ │
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
│ ...                                                    │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ ❌ **Error:** Connection timeout. The model did not │ │
│ │ respond within 60 seconds.                         │ │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 9d. Chain/Orchestration Error

```
┌─ ExchangeTurnCard (chain) ─────────────────────────────┐
│ ▶ CHAIN  deploy my app                                 │
│ ...                                                    │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ ✗ Error: Chain error: Agent "invalid-agent" not     │ │
│ │   found in registry                                 │ │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 10. Approval Prompts

### 10a. Tool Permission Approval

```
┌─ ExchangeTurnCard ──────────────────────────────────────┐
│ ▼ USER  edit the config file                            │
│ ...                                                    │
│ ┌─ exchange-response ─────────────────────────────────┐ │
│ │                                                     │ │
│ │ Allow edit_file? (risk: high) -- Press [Y] or [N]  │ │
│ │                                                     │ │
│ │ ● edit_file({"path": "config.yaml", ...})           │ │
│ │                                                     │ │
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

● ✅ Confidence: 92/100 -- verified (3 tool calls)

● ⚠️ Low confidence (35/100): Content claims file creation without tool usage

● Loaded session abc123def456 (24 messages)

● Orchestration plan (4 steps):
    1. architect: Design API schema
    2. python-engineer: Implement endpoints
    ...
```

---

## 12. Thinking/Reasoning Blocks

**Trigger:** LLM output contains `<thinking>...</thinking>` or `<thought>...</thought>` tags.

```
┌─ ▶ Technical Reasoning & Analysis ─────────────────────┐
│  The user wants system info. I should call env_info    │
│  to get OS, architecture, and Python version. This    │
│  is a straightforward request that requires one tool.  │
└────────────────────────────────────────────────────────┘
```

**Properties:**
- Always collapsed by default
- Content is stripped from the assistant message before rendering
- Mounted BEFORE the agent tag + assistant message

---

## 13. Execution Plan Card

**Trigger:** Complex task detected by `_is_complex_task()`.

```
┌─ ▶ Execution Plan (4 steps) ───────────────────────────┐
│  1. Read existing auth module structure                │
│  2. Refactor into separate concerns (auth, token,     │
│     session)                                           │
│  3. Add comprehensive test suite                       │
│  4. Run tests and verify coverage > 80%               │
└────────────────────────────────────────────────────────┘
```

**Properties:**
- Collapsed by default
- Only created for complex tasks (not all messages)
- Mounted before tool calls in the response container

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
- Only visible in dev mode or when explicitly enabled
- Shows tool counts, tokens, elapsed time, cache stats, files modified

---

## 15. Dev Trace Bar

**Trigger:** Only when `developer_mode=True` AND trace events exist.

```
[12 events · 3 LLM · 5 tools · 2 routes] [View Trace ⚡]
```

**Properties:**
- Only visible in developer mode
- Clicking "View Trace" opens TraceViewerScreen
- Shows event counts by category

---

## 16. Confidence/Verification Score

**Trigger:** Tools were used in the turn.

| Level | Condition | Display |
|-------|-----------|---------|
| High | confidence >= 80 | `✅ Confidence: 92/100 — verified (3 tool calls)` |
| Medium | 50 <= confidence < 80 | `🔍 Confidence: 65/100 — minor verification notes` |
| Low | confidence < 50 | `⚠️ Low confidence (35/100): content claims without tools` |

**Current behavior:** Always shown as system message in `#messages`.

**Desired behavior:** Log to file only, show in UI only if `developer_mode=True`.

---

## 17. Hallucination/Fabrication Warnings

**Trigger:** LLM claims to have done something without actually calling the corresponding tool.

**Internal behavior (not user-visible):**
- LLM receives correction: `"STOP. You are fabricating results..."`
- Loop continues with another iteration

**User-visible behavior:**
- Hallucination verifier runs AFTER the loop
- If hallucinations detected, content is cleaned before display
- No explicit warning shown to user (content is silently corrected)

---

## 18. Spinner/Thinking Indicator

**Trigger:** Any processing starts (message, delegation, chain, orchestration).

```
⠹ Running: env_info({})                    (during tool execution)
⠹ Step 2/5...                              (during iteration)
⠹ Delegating to python-engineer...         (during delegation)
⠹ Step 1/4: architect                      (during chain)
⠹ Enhanced: Gather system information      (during enhancement)
```

**Properties:**
- Animated braille spinner
- Mounts inside exchange-response container
- Text updates as processing progresses
- Removed when processing completes

---

## Unused/Dead Code Widgets

These widgets are defined but NEVER used in the TUI:

| Widget | File | Status |
|--------|------|--------|
| `HandoffFlow` | `widgets/__init__.py:293` | Used in chain execution (orchestrator.py) |
| `OrchestrationPlanWidget` | `widgets/__init__.py:355` | Used in orchestrate execution (orchestrator.py) |

---

## Summary: What Gets Mounted Where

### Inside `exchange-body` (per turn, in order):
1. User Prompt header
2. User Prompt content
3. Divider (`───`)
4. **Enhanced prompt collapsible** (if enhancement enabled, collapsed) — inserted BEFORE response container
5. **Tool call collapsibles** (flat list, one per tool, smart-summarized results, collapsed) — inserted BEFORE response container
6. Response container (`.exchange-response`):
   - Thinking collapsible (if present, collapsed)
   - Agent tag
   - Assistant message (markdown + code blocks)
   - Dev trace bar (if dev mode)
   - Turn summary collapsible (if enabled)

### Inside `#messages` (standalone, between turns):
- System messages (errors, checkpoints, etc.)
- Approval bars
- Parallel agent results
- Confidence score (only shown in developer mode, always logged)

### NOT mounted anywhere:
- Hallucination warnings (content silently cleaned)
- Tool calls from spawned agents (happens inside SpawnAgentTool)
