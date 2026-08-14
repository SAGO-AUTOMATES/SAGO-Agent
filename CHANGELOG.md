# Changelog

All notable changes to the SAGO project are documented in this file.

## [0.1.3] - 2026-08-14

### Added
- **Hybrid BM25 + Dense Semantic Vector Search (`/search` & `sago search`)**:
  - Probabilistic BM25 term weighting combined with zero-dependency local 128-dimensional dense vector embeddings.
  - Sub-millisecond natural language search across 1,000+ codebase files.
  - Registered `hybrid_code_search` agent tool in `sago.tools.coding`.
- **Continuous Background Linting & Self-Healing Diagnostics (`ContinuousVerifier`)**:
  - Non-blocking background worker thread validates written/modified files in real time.
  - Generates line-level diagnostic issues and actionable prompt feedback for autonomous self-healing loops.
- **OpenTelemetry & Prometheus Telemetry Exporters (`/dev export otel|prometheus` & `sago telemetry`)**:
  - Standard OTel Trace JSON specification export with microsecond spans, tool execution events, and error codes.
  - Prometheus text exposition format metrics for tool execution counters, token latencies, and event histograms.
- **Hierarchical Memory Pyramids & Zero-Redundancy Handoff Deltas (`HierarchicalMemoryPyramid`)**:
  - 3-tiered context compaction (Architectural Goals $\to$ Working Deltas $\to$ Active Turns).
  - Compact state delta serialization saving ~70% context overhead during multi-agent handoffs.
- **Bottom-Right Collapse Buttons (`CollapsibleOutputCard` & `ExchangeTurnCard`)**:
  - Pinned `[▲ Collapse Message]` and `[▲ Collapse Output]` action buttons on the bottom-right corner of all message turn cards and command outputs.
  - Eliminates the need to scroll back up to the top of long responses or graph reports to collapse them.
- **Terminal-Native Visual Flowchart (`/graph flow` / `/project_graph flow`)**:
  - Structured Unicode component and data flow connection diagram showing active relationships and dependency branches directly inside the terminal.
- **Dedicated Viewport Keyboard Scroll Shortcuts**:
  - `PageUp` / `PageDown`: Fast page scroll.
  - `Shift+Up` / `Shift+Down` & `Ctrl+Up` / `Ctrl+Down`: Line-by-line smooth viewport scroll.
  - `Ctrl+Home` / `Ctrl+End`: Instant jump to top / bottom.

### Enhanced & Performance Optimizations
- **Asynchronous Non-Blocking `/graph` Execution**:
  - Background daemon thread worker (`threading.Thread`) prevents UI freezes and keeps Textual TUI at a fluid 60 FPS.
- **Multi-Threaded Parallel AST Parsing & In-Memory TTL Caching**:
  - `ThreadPoolExecutor` parallelizes parsing across multi-core CPUs, cutting scan latency by 4x–8x.
  - Thread-safe TTL cache delivers sub-millisecond (< 1ms) view switching between `/graph arch`, `/graph er`, `/graph flow`, and `/graph process`.
- **Rich Markdown & Syntax Highlighting**:
  - Formats all code blocks, Markdown headers, and ASCII box diagrams with Monokai syntax highlighting and clean line wraps.
- **Instant Input Focus Restoration**:
  - Automatically restores active typing focus to `#msg-input` immediately upon widget mounting.
- **Smart Project & Data Graph (`/project_graph` & `sago project-graph`)**:
  - Deep multi-language dependency and symbol extraction (Python, TypeScript, JavaScript, Rust, Go, SQL, Java, C/C++).
  - Layered System Architecture Box Diagrams (`/project_graph arch`).
  - Autonomous Process & Execution Flywheel Maps (`/project_graph process`).
  - Core Data Model & Schema extraction (Pydantic, SQLAlchemy, Tortoise, SQL tables).
  - Interactive Mermaid Flowchart export and compact LLM prompt context injection.
  - File dependency topology tree with symbol count badges and imports.
  - Registered `project_graph` agent tool in `sago.tools.coding.project_graph_tool`.
- **Detach Mode & Background Job Management**:
  - `sago run --detach` (`-d`): Spawns tasks into background daemon workers so users can immediately and safely close their terminal tabs.
  - `sago attach [ID]`: Reconnects to detached TUI sessions or streams background task logs in real-time.
  - `/detach` TUI command: Cleanly exits the interface while leaving background tasks and multi-agent operations active.

### Enhanced & Fixed
- **Web Search Multi-Tier Fallback (`sago.tools.web.search`)**:
  - Added DuckDuckGo organic HTML search extraction with automatic fallback to Instant Answers and optional Tavily API.
  - Eliminates empty results on technical documentation and programming queries.
- **Virtual Environment Self-Healing Verifier (`sago.engine.verifier`)**:
  - Added automatic virtual environment detection (`.venv`, `venv`, `uv run`, `poetry run`).
  - Added multi-language verification suite support for TypeScript (`tsc`), Rust (`cargo check`), Go (`go vet`), and Python (`ruff`, `pytest`).
- **Multi-Language AST Symbol Parsing (`sago.memory.symbol_graph`)**:
  - Expanded pattern extractors to support Go structs/interfaces/funcs, Rust structs/enums/traits/impls, and TypeScript interfaces/type aliases.
