# SAGO Intelligent Prompt Enhancement

## Overview

In SAGO, users **never need to write a "perfect prompt"**. 

When any task is dispatched to an agent, orchestrated across a specialist team, or executed through a multi-agent feedback chain, SAGO's **Prompt Enhancer** automatically analyzes, expands, and structures the raw user input into an intent-rich, unambiguous, and constraint-guided prompt before passing it to the agent.

---

## Key Capabilities

1. **Automatic Intent Extraction & Synthesis**
   - Classifies task intent (bug fix, feature implementation, refactoring, verification/testing, performance optimization, technical explanation).
   - Formulates clear, explicit primary objectives and step-by-step action plans.

2. **Workspace & Target Scope Resolution**
   - Detects referenced file paths, directories, modules, and AST symbols across the repository.
   - Restricts execution scope to relevant files and dependencies.

3. **Concrete Acceptance Criteria & Verification**
   - Injects domain-specific criteria (e.g. self-testing with pytest, regression prevention, input sanitization).
   - Enforces operational boundaries (preserving unrelated comments, type safety, error boundaries).

4. **Domain-Specific Engineering Guidelines**
   - Automatically injects best-practice constraints tailored to the agent's specialty (Python, Web, Security, Database, DevOps).

5. **Full Transparency & User Feedback**
   - Displays the synthesized objective and key enhancements in CLI (`sago run`, `sago smart`, `sago chain`) and interactive TUI (`/delegate`, `/chain`).
   - Shows the exact modifications and intent additions.

6. **Developer Mode Telemetry & Event Tracing**
   - Automatically logs `PROMPT_ENHANCED` trace events into `DevTracer`.
   - Exportable via `sago telemetry --export otel/prometheus/json/md` for audits and observability.

---

## How It Works

```
Raw User Input (e.g. "fix auth bug in login")
                     │
                     ▼
        ┌─────────────────────────┐
        │  SAGO Prompt Enhancer   │
        │  - Intent Extraction    │
        │  - AST Target Scope     │
        │  - Acceptance Criteria  │
        │  - Domain Constraints   │
        └─────────────────────────┘
                     │
                     ▼
   ✨ Structured, Actionable Prompt (with verification rules)
                     │
                     ▼
         Specialist Agent / Chain Execution
```

---

## Example

### Input (Raw Prompt)
```bash
sago run "fix login error handling" --agent security-engineer
```

### Prompt Enhancer Output
```
╭────────────────────────────── Sago Prompt Enhancer ──────────────────────────────╮
│ ✨ Prompt Automatically Enhanced with Intent & Scope                             │
│                                                                                  │
│ Synthesized Objective: Diagnose and resolve the reported issue: fix login error  │
│ handling                                                                         │
│                                                                                  │
│ Key Additions: Structured bug fix intent • Defined explicit acceptance criteria  │
│ • Injected domain & verification constraints                                     │
╰──────────────────────────────────────────────────────────────────────────────────╯
```

### Injected Structure to Agent
```markdown
### Primary Objective
Diagnose and resolve the reported issue: fix login error handling

### User Intent & Core Request
fix login error handling

### Target Scope & Relevant Paths
- `sago/auth/`
- `sago/main.py`

### Acceptance Criteria & Verification
1. Identify and isolate the underlying root cause of the failure.
2. Implement a targeted fix that resolves the issue cleanly.
3. Ensure no regressions are introduced into adjacent functionality.
4. Verify fix execution with relevant tests or diagnostics.

### Operational Constraints & Standards
- Follow the principle of least privilege and strict input validation.
- Eliminate any hardcoded secrets, credentials, or insecure deserialization.
- Ensure secure credential handling and error messages that don't leak internals.
- Preserve unrelated existing comments and interfaces.
- Ensure no placeholders or unfinished mock code remain.
```
