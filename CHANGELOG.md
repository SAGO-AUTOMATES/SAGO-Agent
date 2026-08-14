# Changelog

All notable changes to the SAGO project are documented in this file.

## [Unreleased]

### Added
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
