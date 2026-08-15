# SAGO System Architecture & Execution Flows

> Comprehensive technical guide to SAGO's internal workflows: Vector DB & RAG Memory, Database Persistence, 5-Layer Failure Prevention, Multi-Agent Swarm Orchestration, Dynamic Task Delegation, Autonomous Tool Execution, Self-Healing Verification, and Detached Background Workers.

---

## Table of Contents

1. [High-Level System Topology](#1-high-level-system-topology)
2. [Database Structure & Persistence Engine](#2-database-structure--persistence-engine)
3. [5-Layer Smart Failure Prevention Matrix](#3-5-layer-smart-failure-prevention-matrix)
4. [Vector DB, RAG & Context Providers](#4-vector-db-rag--context-providers)
5. [Multi-Agent Swarm & Dynamic Delegation Engine](#5-multi-agent-swarm--dynamic-delegation-engine)
6. [Multi-Agent Execution Modes](#6-multi-agent-execution-modes)
7. [Typed Context Handoffs & Recursion Protection](#7-typed-context-handoffs--recursion-protection)
8. [Tool Matrix & Risk-Gated Permission Model](#8-tool-matrix--risk-gated-permission-model)
9. [Self-Healing Verification Flywheel](#9-self-healing-verification-flywheel)
10. [Atomic Checkpoints & Workspace Snapshotting](#10-atomic-checkpoints--workspace-snapshotting)
11. [Daemon & Detach Mode Background Workers](#11-daemon--detach-mode-background-workers)
12. [Distributed Peer Mesh Network](#12-distributed-peer-mesh-network)

---

## 1. High-Level System Topology

SAGO is engineered as an autonomous, multi-layered agentic operating system designed to handle complex software engineering workflows without human micromanagement.

```mermaid
flowchart TD
    User["👤 User Request / Prompt"] --> Gateway["Frontend Gateway (TUI / CLI / Daemon Server)"]
    Gateway --> Checkpoint["🛡️ Checkpoint Snapshot (Workspace Delta Backup)"]
    Checkpoint --> Context["🧠 Tri-Partite Context Assembly (RAG + SymbolGraph + Compactor)"]
    Context --> Orchestrator["⚙️ Master Orchestrator & TaskDelegator"]
    
    subgraph Swarm["🤖 Multi-Agent Swarm (339 Specialists / 22 Domains)"]
        Orchestrator --> AgentA["Specialist Agent A (e.g. System Architect)"]
        AgentA -->|Handoff / Chain| AgentB["Specialist Agent B (e.g. Backend Engineer)"]
        AgentB -->|Feedback / Review| AgentC["Specialist Agent C (e.g. Code Reviewer)"]
    end
    
    Swarm --> Tools["🛠️ Tool Matrix (56+ Safe / Risk-Gated Tools)"]
    Tools --> Codebase[("💻 Local Codebase & Workspace")]
    Codebase --> Verifier["🔍 Self-Healing Verifier (Linter, Typecheck, Tests)"]
    
    Verifier -->|❌ Diagnostics Feedback Loop| Swarm
    Verifier -->|✅ Success| StateCommit["💾 SQLite DB & Persistent Learning Store"]
    StateCommit --> Response["📤 Token-by-Token Streaming Response"]
```

---

## 2. Database Structure & Persistence Engine

Implemented in [`sago/database.py`](file:///mnt/ramdisk/sago/sago/database.py), SAGO uses an embedded, high-performance SQLite database with write-ahead logging (WAL mode) and thread-isolated connection pooling.

```mermaid
flowchart LR
    subgraph SQLite_Core["SQLite Persistent Storage (WAL Mode)"]
        direction TB
        Sessions["📁 sessions table\n• id (UUID)\n• title & status\n• created_at"]
        Messages["💬 messages table\n• id & role\n• content & tokens\n• batch flushed"]
        Tasks["📋 tasks table\n• id & parent_id\n• chain & deps\n• circular guard"]
        ToolUsage["📊 tool_usage table\n• tool_name\n• success / failure\n• latency & args"]
    end

    Pool["🔄 ConnectionPool (Thread-Local)"] --> Sessions
    Pool --> Messages
    Pool --> Tasks
    Pool --> ToolUsage
```

### Key Database Subsystems:
* **Thread-Isolated Connection Pooling (`ConnectionPool`)**: Eliminates SQLite concurrency locks during parallel multi-agent swarms by assigning isolated connections per thread.
* **Buffered Message Store (`MessageStore`)**: Queues conversation turns in memory and writes them in atomic disk transactions, preventing I/O stalls during high-speed streaming.
* **Task Store with Circular Graph Guard (`TaskStore`)**: Tracks hierarchical subtasks and prevents circular dependency deadlocks when agents dynamically schedule prerequisite tasks.
* **Tool Usage Analytics (`ToolUsageStore`)**: Records tool invocation latencies, arguments, error counts, and success rates.

---

## 3. 5-Layer Smart Failure Prevention Matrix

SAGO employs a 5-layer defensive safety matrix to ensure autonomous execution never damages a project or enters infinite loops:

| Safety Layer | Implementation Module | Defensive Mechanism |
| :--- | :--- | :--- |
| **1. Atomic Checkpoints** | [`sago/engine/checkpoint.py`](file:///mnt/ramdisk/sago/sago/engine/checkpoint.py) | Takes lightweight copy-on-write workspace snapshots before high-risk changes. Enables **1-click instant rollback** (`/checkpoint restore <id>`). |
| **2. Self-Healing Verifier** | [`sago/engine/verifier.py`](file:///mnt/ramdisk/sago/sago/engine/verifier.py) | Automatically resolves `.venv/bin/*`, `uv run`, `pytest`, `ruff`, `tsc`, `cargo`, and `go vet`. Captures compiler errors and feeds them directly back to agents for autonomous correction. |
| **3. Recursion & Loop Guards** | [`sago/orchestrator/delegator.py`](file:///mnt/ramdisk/sago/sago/orchestrator/delegator.py) | Enforces maximum delegation depth (`max_depth = 5`) and tracks a `visited_agents` set to block circular ping-pong loops between agents. |
| **4. Persistent Learning Store** | [`sago/memory/learning_store.py`](file:///mnt/ramdisk/sago/sago/memory/learning_store.py) | Persists proven error fixes and successful strategies across sessions. When an error recurs, `get_known_fixes()` instantly suggests the verified fix. |
| **5. Risk-Gated Permissions** | [`sago/permissions.py`](file:///mnt/ramdisk/sago/sago/permissions.py) | Enforces granular risk policies (`SAFE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) with path traversal guards, secret leak detection, and shell sanitization. |

---

## 4. Vector DB, Hybrid BM25 & Context Providers

SAGO uses three complementary context providers in [`sago/memory/`](file:///mnt/ramdisk/sago/sago/memory/) to supply agents with exact workspace context while preventing context-window blowout.

```mermaid
flowchart TD
    UserRequest["Active User Request / Goal"] --> Router{"Context Assembler"}
    
    subgraph Context_Tiers["Multi-Tiered Context Assembly"]
        Router -->|1. Structural Outline| SymbolGraph["AST Symbol Graph & Project Graph\n• Dynamic multi-language ASTs & schemas\n• Cross-session persistent disk cache\n• Zero-token architecture topology"]
        Router -->|2. Hybrid Search| HybridSearch["BM25 & Dense Semantic Index\n• Probabilistic BM25 term weighting\n• 128-d zero-dep dense vector similarity\n• AST symbol boosting & code chunking"]
        Router -->|3. Hierarchical Pyramid| Compactor["3-Tier Hierarchical Pyramid\n• Tier 1: Architectural Goals\n• Tier 2: Working File Deltas\n• Tier 3: High-Fidelity Turns"]
    end
    
    SymbolGraph --> HighDensityPrompt["High-Density Assembled Prompt"]
    HybridSearch --> HighDensityPrompt
    Compactor --> HighDensityPrompt
    HighDensityPrompt --> LLM["LLM Inference Engine"]
```

1. **AST Structural Graph Provider (`ProjectGraph` & `SymbolGraph`)**:
   * Analyzes multi-language ASTs (Python, TypeScript, Rust, Go, SQL, C++) to inject high-level signatures, ER schemas, and file hierarchies directly into prompt headers with cross-session disk caching (`~/.sago/cache/project_graphs/`).
2. **Hybrid BM25 & Dense Semantic Vector Search (`HybridCodeIndexer` & `HybridSearchTool`)**:
   * Combines probabilistic BM25 rank scoring ($k_1=1.5, b=0.75$) with 128-dimensional dense sub-token vector hashing for sub-second semantic search across 1,000+ files without external cloud vector DBs.
3. **Hierarchical Context Compactor & Memory Pyramid (`HierarchicalMemoryPyramid` in `sago/memory/compaction.py`)**:
   * Maintains a 3-tier memory pyramid, saving ~70% token overhead and preventing context exhaustion during complex agent handoffs (`to_state_delta()`).

---

## 5. Multi-Agent Swarm & Dynamic Intent Classification

SAGO houses **339 specialized agents** classified into **22 functional engineering domains**. Intent routing is powered by the **Semantic Intent Classifier** ([`sago/engine/intent_classifier.py`](file:///mnt/ramdisk/sago/sago/engine/intent_classifier.py)) and `TaskDelegator` ([`sago/orchestrator/delegator.py`](file:///mnt/ramdisk/sago/sago/orchestrator/delegator.py)).

### Dynamic Intent Routing & Classification

```mermaid
flowchart LR
    Task["User Prompt / Goal"] --> Intent["IntentClassifier\n(LRU Cache -> Micro-LLM -> Heuristic)"]
    Intent --> Type["Identify Intent (chat, fix, create, analyze, test, devops)"]
    Type --> TD["TaskDelegator.classify()"]
    TD --> AgentMatch["Select Specialist Agent (e.g. debugger, python-engineer)"]
    TD --> Plan["Generate Execution Plan & Handoff Delta"]
```

---

## 6. Multi-Agent Execution Modes

SAGO provides four distinct orchestration execution paradigms:

```mermaid
flowchart TD
    subgraph Mode1["1. Direct Delegation (/delegate)"]
        User1["User"] --> Orch1["Orchestrator"] --> Spec1["Specialist Agent"] --> Res1["Result"]
    end

    subgraph Mode2["2. Sequential Chain (/chain)"]
        User2["User"] --> Arch["System Architect"] --> Back["Backend Engineer"] --> Rev["Code Reviewer"] --> Res2["Verified Code"]
    end

    subgraph Mode3["3. Parallel Swarm (/parallel)"]
        User3["User"] --> Disp["Dispatcher"]
        Disp --> Th1["Security Auditor"]
        Disp --> Th2["Performance Engineer"]
        Disp --> Th3["Test Engineer"]
        Th1 --> Agg["Aggregate Report"]
        Th2 --> Agg
        Th3 --> Agg
    end

    subgraph Mode4["4. Stateful Workflow Engine (sago workflow)"]
        User4["User"] --> LangGraph["State Graph with Checkpoints, Retries & Conditional Nodes"]
    end
```

---

## 7. Typed Context Handoffs & Recursion Protection

To allow seamless collaboration between agents without data loss or infinite loops, SAGO enforces strict handoff protocols:

* **Recursion Guard**: Tracks current delegation depth (`max_depth = 5`). If an agent attempts to delegate beyond the limit, the system gracefully handles the request locally.
* **Cycle & Loop Detection**: Tracks visited agents in a chain. If Agent A calls Agent B, Agent B cannot call Agent A unless explicitly flagged as a feedback loop.
* **Typed State Handoffs**: Passes structured context metadata including created files, active diffs, lint diagnostics, and test outcomes.

---

## 8. Tool Matrix & Risk-Gated Permission Model

Agents interact with the environment via **56+ production tools** registered under `sago/tools/`. Every tool execution is evaluated by the **Permission Manager** ([`sago/permissions.py`](file:///mnt/ramdisk/sago/sago/permissions.py)):

| Risk Level | Operations Included | Security Policy |
| :--- | :--- | :--- |
| **`SAFE`** | Read file, AST symbol lookup, grep search, project graph, list directory | Automatically executed without prompt |
| **`LOW`** | Web search, token cost estimation, lint diagnostics | Auto-allowed with audit log |
| **`MEDIUM`** | Write file, edit file content, create directory | Monitored file diff tracking |
| **`HIGH`** | Bash command execution, package installation (`pip`, `npm`, `cargo`) | User confirmation prompt (or `/yolo` mode) |
| **`CRITICAL`**| Destructive filesystem commands (`rm -rf`), Git force pushes, remote SSH execution | Strict confirmation modal with explicit warnings |

---

## 9. Self-Healing Verification Flywheel

When agents edit code, SAGO automatically runs a background verification loop ([`sago/engine/verifier.py`](file:///mnt/ramdisk/sago/sago/engine/verifier.py)):

```mermaid
flowchart TD
    Edit["Agent Writes / Modifies Code"] --> Verifier["Virtualenv-Aware Verifier\nAuto-resolves .venv/bin/*, ruff, pytest, mypy, tsc, cargo, go"]
    
    Verifier --> Decision{"Checks Passed?"}
    Decision -->|✅ Yes| Commit["Commit Workspace & Stream Success"]
    Decision -->|❌ No| Diagnostics["Capture Compiler Errors & Lints"]
    Diagnostics --> Loopback["Auto-Feed Diagnostics to Agent Loop"]
    Loopback --> Edit
```

---

## 10. Atomic Checkpoints, Workspace Snapshots & 1-Click Rollback

Implemented in [`sago/engine/checkpoint.py`](file:///mnt/ramdisk/sago/sago/engine/checkpoint.py), SAGO incorporates an atomic, copy-on-write workspace versioning system designed for fail-safe agentic refactoring.

```mermaid
flowchart TD
    TaskStart["⚡ High-Impact Task / Refactor Triggered"] --> PreCheck["📸 CheckpointManager.create_checkpoint()"]
    PreCheck --> Hash["1. Hash target workspace files (SHA-256)"]
    Hash --> Delta["2. Store file content snapshots in .sago/checkpoints/<id>/"]
    Delta --> Exec["🤖 Multi-Agent Execution & Tool Operations (Edits, Writes, Moves)"]
    
    Exec --> Evaluation{"Execution Result / Verification"}
    Evaluation -->|✅ Successful & Verified| Keep["Keep checkpoint in history (audit trail)"]
    Evaluation -->|❌ Failure / Unwanted Changes| Rollback["⏪ /checkpoint restore <id> or /undo"]
    Rollback --> Restore["Restore exact file bytes & directory structure from snapshot"]
```

### Checkpoint Operations & Lifecycle
1. **Automated Baseline Snapshotting**: Before executing risk-gated tools (`write_file`, `edit_file`, `multi_replace_file`), SAGO captures the exact byte state and relative paths of touched files.
2. **Manual Point-in-Time Snapshots (`/checkpoint create [description]`)**: Users can capture a comprehensive snapshot of their workspace prior to testing major architectural migrations or prompting agents for large rewrites.
3. **Instant Rollback (`/checkpoint restore <id>`)**: Restores all files within the checkpoint snapshot back to their exact state, overwriting unwanted modifications and cleaning up newly created artifacts.
4. **Granular Turn Undo (`/undo`)**: Reverts only the file changes made during the most recent assistant turn without affecting earlier changes.
5. **Modification Audit Log (`/changes`)**: Streams a chronological diff of all files modified in the active session.

---

## 11. Daemon, Detach Mode & Background Workers

SAGO supports non-blocking detached execution across both CLI and TUI:

```mermaid
flowchart LR
    subgraph Detached_Launch["1. Detached Execution"]
        Cmd["$ sago run 'Task' --detach\nor /detach in TUI"] --> DaemonWorker["Spawn Background Daemon Worker\n(Independent Subprocess / Thread)"]
        DaemonWorker --> DiskLog["Stream output to .sago/logs/task_<id>.log"]
        DaemonWorker --> SafeTerminal["Terminal tab / SSH session safe to exit"]
    end

    subgraph Reattach_Flow["2. Reattach & Monitoring"]
        AttachLog["$ sago attach task_<id>"] --> LiveTail["Live tail background task output"]
        AttachTUI["$ sago attach <session_id>"] --> ReconnectTUI["Re-open full interactive TUI state"]
    end
```

### Detach Capabilities
* **Zero-Interruption Remote Work**: Launch long-running builds, test suites, or multi-agent workflows over SSH, detach safely (`/detach` or `sago run --detach`), and disconnect without terminating jobs.
* **Live Task Tail (`sago attach`)**: Running `sago attach` without arguments lists all active and recent background tasks with their PID, status, elapsed duration, and log path.

---

## 12. Distributed Peer Mesh Network & HMAC-SHA256 Security

Implemented in [`sago/peers/mesh.py`](file:///mnt/ramdisk/sago/sago/peers/mesh.py), SAGO instances can form secure peer-to-peer swarms across local subnets and cloud clusters:

```mermaid
flowchart LR
    subgraph NodeA["🖥️ SAGO Node A (Sender)"]
        Msg["Task Payload / Handoff"] --> Sign["HMAC-SHA256 Sign(payload, timestamp, SAGO_MESH_SECRET)"]
        Sign --> Packet["Signed MeshMessage Packet"]
    end
    
    Packet -->|UDP Port 7655 / Mesh Broadcast| NodeB
    
    subgraph NodeB["🖥️ SAGO Node B (Receiver)"]
        Packet --> VerifyTime{"Timestamp within 300s window?"}
        VerifyTime -->|❌ Expired| DropReplay["Drop (Replay Attack Guard)"]
        VerifyTime -->|✅ Valid| VerifyHMAC{"HMAC Signature Valid?"}
        VerifyHMAC -->|❌ Tampered| DropUntrusted["Drop (Unauthorized Node)"]
        VerifyHMAC -->|✅ Valid| Dispatch["Dispatch task to local specialist agent"]
    end
```

### Mesh Security Guarantees
* **HMAC-SHA256 Message Authentication**: Every mesh packet is cryptographically signed using a shared cluster secret (`SAGO_MESH_SECRET`), guaranteeing packet integrity and authenticity.
* **Replay Attack Prevention**: Inbound packets include microsecond timestamps; messages outside a configurable 300-second window or with duplicate nonces are rejected.
* **Automatic Node Discovery**: Nodes announce their capabilities (e.g. `gpu`, `database`, `rust`) over UDP broadcast, allowing automatic multi-node task routing.
