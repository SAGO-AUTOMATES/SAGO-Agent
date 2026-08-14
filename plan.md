# SAGO Production-Grade Master Architecture & Implementation Plan

> **Objective**: Elevate SAGO from a prototype multi-agent library into an enterprise-grade, state-of-the-art autonomous software engineering platform capable of indexing, architecting, generating, modifying, testing, and debugging complex projects ranging from 1 to 1,000+ files with zero hallucinations, deterministic edits, and self-healing test loops.

---

## 1. Architectural Vision & Core Pillars

To handle codebases with **1,000+ files** and generate **30–50+ file projects** autonomously without losing context or failing on tool execution, SAGO is organized around six core pillars:

1. **Universal LLM & Streaming Tool Loop**:
   - First-class, resilient native function calling across **OpenAI, Anthropic, Gemini, OpenRouter, and Ollama**.
   - True multi-turn autonomous tool loops (eliminates the Gemini early-exit bug and hardcoded iteration caps).
   - Dynamic role-based tool filtering (injecting only the relevant 5–8 tools per sub-task rather than all 50+ tools).
   - Dynamic context distillation: automatic pruning and summarization of massive tool outputs.

2. **Large-Scale (1,000+ File) Codebase Indexing & Symbol Map**:
   - Fast, token-efficient Symbol & Dependency Graph (classes, methods, signatures, exports, imports).
   - AST-based outline extraction (Python, TypeScript, JavaScript, Rust, Go) giving the LLM a 360° view of 1,000+ files in under 2,000 tokens.
   - High-speed indexed grep and regex search with `.gitignore` and binary file filters.

3. **Topological Multi-File Project Synthesizer**:
   - Multi-phase project scaffolding for 30–50+ files:
     - **Phase 1**: Requirements & Architecture Specification.
     - **Phase 2**: Dependency DAG & File Manifest (topological ordering).
     - **Phase 3**: Types, Interfaces & Schemas (contract locking).
     - **Phase 4**: Core Logic, Models & Database.
     - **Phase 5**: Business Services, Adapters & APIs.
     - **Phase 6**: User Interface / CLI / Orchestration.
     - **Phase 7**: Comprehensive Test Suites & Mock Fixtures.
     - **Phase 8**: Verification & Automated Repair.

4. **Deterministic & Resilient File Patcher**:
   - Multi-tier matching: Exact match -> Normalized Whitespace/Indentation match -> Fuzzy Block Levenshtein match -> AST/CST structure match.
   - Multi-chunk atomic replacements (`multi_replace_file_content`) to edit 10+ locations in a single turn without re-writing entire files.
   - Standard unified diff patch generator and applier.

5. **Continuous Self-Healing Verification Flywheel**:
   - Automated post-execution checks: Syntax validation -> Linters (`ruff`, `eslint`) -> Type-checkers (`mypy`, `tsc`) -> Test runners (`pytest`, `vitest`, `cargo test`, `go test`).
   - Self-healing loop: Automatically feed error traces, stdout/stderr back into the specialized debugging agent to auto-fix errors until green.

6. **Transactional Checkpointing & Rollbacks**:
   - Snapshot repository state before destructive operations.
   - Instant `/undo`, `/rollback`, or `/diff` to restore or inspect project states across multi-file refactors.

---

## 2. Phased Implementation Roadmap

### Phase 1: Universal Execution Engine & Provider Tool Calling Hardening
- [ ] Fix provider-specific tool execution bugs (GeminiSDK function-call loop, Anthropic tool use, OpenRouter stream handling).
- [ ] Replace naive message compaction (`msgs[-5:]`) with **Semantic Context Management & Tool Output Distillation**.
- [ ] Implement dynamic tool scoping to minimize prompt token overhead from 50 tools down to task-relevant subsets.
- [ ] Add adaptive iteration controls and dynamic token budgeting.

### Phase 2: Resilient File Editing & Patching Engine
- [ ] Build `sago/tools/file/resilient_editor.py` with multi-tier fuzzy matching and whitespace tolerance.
- [ ] Build `multi_replace_file_content` tool for atomic multi-location edits in single files.
- [ ] Implement unified diff generator and patch applier tool (`patch_file`).
- [ ] Update `write_file` with atomic write safety, directory auto-creation, and syntax pre-validation.

### Phase 3: Large-Scale Codebase Indexer (1,000+ Files) & Symbol Graph
- [ ] Build `sago/memory/symbol_graph.py` to extract symbols, classes, functions, docstrings, and imports across whole repositories.
- [ ] Build `sago/tools/coding/repo_map.py` to provide compact, hierarchical repository maps for massive codebases.
- [ ] Optimize fast AST parsing and caching with TTL and file modification timestamps.

### Phase 4: Topological Project Synthesis Engine (30–50+ Files)
- [ ] Build `sago/engine/project_synthesizer.py` supporting topological multi-stage project generation.
- [ ] Implement contract-locking mechanism so dependent modules strictly adhere to generated types and interfaces.
- [ ] Add progress tracking, resumability, and checkpointing for large generation workflows.

### Phase 5: Automated Self-Healing Verification Flywheel
- [ ] Build `sago/engine/verifier.py` with multi-language linting, type-checking, and test execution.
- [ ] Build automated feedback loop to intercept errors, format tracebacks, and prompt the agent to auto-repair without user intervention.

### Phase 6: CLI & TUI Integration & Testing
- [ ] Expose `sago synth`, `sago map`, `sago verify`, `sago rollback` in the CLI.
- [ ] Update TUI components with real-time multi-file progress trees and diff previews.
- [ ] Write end-to-end tests validating multi-file generation, fuzzy editing, and provider execution.

---

## 3. Progress Tracking Log

| Component | Status | Target Date | Notes |
| :--- | :--- | :--- | :--- |
| `plan.md` Master Blueprint | Done | Today | Architectural blueprint established |
| Resilient File Editor & Multi-Chunk Patcher | In Progress | Today | Eliminating exact string match failures |
| Universal Execution Engine & Provider Tool Loop | In Progress | Today | Fixing Gemini loop & context compaction |
| 1,000+ File Symbol Graph & Repo Mapper | Queued | Today | Scalable code map for large repos |
| Topological Project Synthesizer | Queued | Today | For 30–50+ file generation |
| Self-Healing Verification Flywheel | Queued | Today | Automated lint-test-fix loop |
| E2E Tests & CLI Commands | Queued | Today | Full test suite validation |
