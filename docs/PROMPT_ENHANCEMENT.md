# SAGO Intelligent Prompt Enhancement

## Overview

In SAGO, users **never need to write a "perfect prompt"**. 

When any task is dispatched to an agent, orchestrated across a specialist team, or executed through a multi-agent feedback chain, SAGO's **Prompt Enhancer** automatically analyzes, expands, and structures the raw user input into an intent-rich, unambiguous, and constraint-guided prompt before passing it to the agent.

---

## Key Capabilities

1. **Automatic Intent Extraction & Synthesis**
   - Classifies task intent (bug fix, feature implementation, refactoring, verification/testing, performance optimization, technical explanation, lightweight query).
   - Formulates clear, explicit primary objectives and step-by-step action plans.

2. **Workspace & Target Scope Resolution**
   - Detects referenced file paths, directories, modules, and AST symbols across the repository.
   - Restricts execution scope to relevant files and dependencies.

3. **Concrete Acceptance Criteria & Verification**
   - Injects domain-specific criteria (e.g. self-testing with pytest, regression prevention, input sanitization).
   - Enforces operational boundaries (preserving unrelated comments, type safety, error boundaries).
   - Universal anti-hallucination criteria: never claim verification without running actual tools.

4. **Domain-Specific Engineering Guidelines**
   - Automatically injects best-practice constraints tailored to the agent's specialty (Python, Web, Security, Database, DevOps).

5. **Complexity Assessment & Overthinking Prevention**
   - Classifies queries as simple/medium/complex to calibrate response depth.
   - Simple queries ("hi", "what is 2+2") get minimal enhancement — no heavy tooling overhead.
   - Lightweight "query" type for quick info lookups ("what's in this file", "where is X defined").
   - Complex tasks get structured multi-step workflows.

6. **Anti-Hallucination Safeguards**
   - 10 anti-hallucination constraints injected into all enhanced prompts.
   - Prohibits claiming file reads, test results, or fixes without actual tool evidence.
   - Prevents overclaiming ("production-ready", "fully tested") without verification.

7. **Full Transparency & User Feedback**
   - Displays the synthesized objective and key enhancements in CLI (`sago run`, `sago smart`, `sago chain`) and interactive TUI (`/delegate`, `/chain`).
   - Shows the exact modifications and intent additions.

8. **Developer Mode Telemetry & Event Tracing**
   - Automatically logs `PROMPT_ENHANCED` trace events into `DevTracer`.
   - Exportable via `sago telemetry --export otel/prometheus/json/md` for audits and observability.

---

## How It Works

```
Raw User Input (e.g. "fix auth bug in login")
                     │
                     ▼
        ┌─────────────────────────┐
        │  Complexity Assessment  │
        │  simple → skip enhance  │
        │  medium → full enhance  │
        │  complex → structured   │
        └─────────────────────────┘
                     │ (medium/complex only)
                     ▼
        ┌─────────────────────────┐
        │  LLM-Aware Enhancement  │
        │  If LLM client available│
        │  - Dynamic intent from  │
        │    LLM classification   │
        │  - Smart criteria from  │
        │    LLM generation       │
        │  - Context-aware prompt │
        │    structuring          │
        │  Fallback: regex-based  │
        │  - Pattern matching     │
        │  - Template injection   │
        │  - Static criteria      │
        └─────────────────────────┘
                     │
                     ▼
        ┌─────────────────────────┐
        │  Hard Constraints       │
        │  (always injected)      │
        │  - Anti-hallucination   │
        │  - Domain guidelines    │
        │  - Verification rules   │
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

---

## Supported Trigger Scenarios & Natural Phrasing

SAGO's prompt enhancement and intent classifier are not confined to rigid keywords. They dynamically interpret natural engineering phrasing:

| Scenario / Category | Natural Input Examples | Synthesized Intent & Focus |
|---|---|---|
| **Quick Information Query** | `"what's in this file"`, `"show me main.py"`, `"where is User defined"`, `"explain this function"`, `"what does this do"` | Read ONE specific file/concept, give brief answer. Maximum 1-2 tool calls. No heavy analysis. |
| **Failure Troubleshooting** | `"why is this not working"`, `"why does this fail"`, `"it crashes when I click submit"`, `"500 Internal Server Error"` | Isolates failure root causes, inspects stack traces, and implements targeted fixes. |
| **Codebase Exploration** | `"projects"`, `"what projects are in here"`, `"project structure"`, `"review the architecture"` | Explores repository topology, maps component relationships, and summarizes architecture. |
| **Performance & Profiling** | `"this feels slow"`, `"make it faster"`, `"is there a memory leak"`, `"profile CPU usage"`, `"bottleneck in query"` | Profiles computational bottlenecks, optimizes memory allocations, and adds benchmarking. |
| **Refactoring & Cleanup** | `"clean this up"`, `"make this cleaner"`, `"tidy up code"`, `"modularize database handlers"` | Refactors code structure for maintainability while preserving external contracts and tests. |
| **DevOps & Infrastructure** | `"how do I run this"`, `"how to start"`, `"dockerize this application"`, `"set up CI/CD workflow"` | Configures environment variables, Dockerfiles, docker-compose, and deployment pipelines. |
| **Testing & Quality Assurance** | `"write pytest tests"`, `"why is test failing"`, `"increase unit test coverage"` | Synthesizes test suites covering happy paths, edge cases, and regression assertions. |
| **Conversational Inquiries** | `"hello"`, `"hoi"`, `"how are you?"`, `"what's the weather today?"`, `"tell me a joke"` | Bypasses heavy codebase dumping and responds naturally without unsolicited boilerplate. |

---

## Zero-Token Local Overhead & Isolation

1. **Dynamic LLM Enhancement**: When an LLM client is available (during message processing), the enhancer uses a small LLM call (500 tokens max, temperature=0.1) for dynamic intent classification and structured prompt generation. This produces context-aware, intelligent enhancements that understand the user's actual intent.
2. **Regex Fallback**: When LLM is unavailable (commands like `/delegate`, session loads), the enhancer falls back to regex-based pattern matching with template injection — still effective but static.
3. **Clean Main LLM Payload**: Internal prompt generator/enhancer logs, intermediate decision trees, and metadata are **never injected into the main LLM payload**. Only the clean, distilled task prompt is passed.
4. **Selective Context Assembly**: Casual chat, lightweight queries, and general Q&A bypass repository file scanning, AST symbol indexing, and README instruction dumps, keeping token usage minimal.
5. **Complexity-Calibrated Enhancement**: Simple queries ("hi", "what is 2+2") skip prompt enhancement entirely. Medium queries get standard enhancement. Complex queries get structured multi-step workflows with anti-hallucination constraints.
6. **Anti-Hallucination by Design**: Even with LLM enhancement, anti-hallucination constraints and domain guidelines are always injected as hard rules (never LLM-generated). This ensures the enhancement never hallucinates constraints or acceptance criteria.

---

## Runtime Verification Layer

The prompt enhancer is the **prevention** layer — it injects constraints into the LLM prompt to discourage hallucinations. The **detection** layer is `sago/engine/hallucination_verifier.py`, which runs after the LLM responds:

1. **Prevention** (prompt_enhancer.py): "Do NOT claim verification without running actual tools"
2. **Detection** (hallucination_verifier.py): "I've verified" detected — no read/grep tool was called

Both layers work together:
- Prompt constraints reduce hallucination frequency
- Runtime verification catches remaining hallucinations
- Confidence scoring determines whether to strip or warn
- Response sanitization removes hallucinated sentences when confidence is low
