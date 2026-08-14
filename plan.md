# SAGO Future Roadmap & Architectural Insights

> **Mission**: Deliver a world-class autonomous software engineering platform capable of full-repo reasoning across 1,000+ files, self-healing test loops, and seamless multi-agent orchestration.

---

## 1. Pending Tasks & Active Initiatives

### [ ] Multi-Language Tree-sitter AST Symbol Extractor
- **Goal**: Expand AST symbol mapping beyond Python to first-class C++, Rust, Go, TypeScript, Java, and C# using `tree-sitter`.
- **Target**: Sub-millisecond incremental symbol caching for codebases exceeding 5,000+ files.

### [ ] Local Vector Embeddings & Hybrid BM25 Code Index
- **Goal**: Augment the symbol graph with local semantic embeddings (e.g., `sentence-transformers` / `FastEmbed`) combined with BM25 keyword search.
- **Benefit**: Natural language semantic code search across large repositories without external cloud dependencies.

### [ ] Secure WebAssembly (Wasm) & Isolated Execution Sandbox
- **Goal**: Provide an optional WebAssembly or microVM sandbox for running untrusted shell and execution tasks.
- **Target**: Safe autonomous code execution on multi-tenant developer environments.

### [ ] Distributed Multi-Node Agent Swarm Mesh
- **Goal**: Connect multiple Sago instances across machines over peer-to-peer WebSockets / mTLS.
- **Target**: Large-scale distributed builds, parallel testing matrices, and cross-repo coordination.

---

## 2. Future Architectural Insights

### Autonomous Intent Pipeline
- **Continuous Background Linting**: After modifying files, automatically spawn a lightweight background verification job and surface diagnostics before the user even asks.
- **Predictive Handoff Routing**: Use fast embeddings on prompt intent to pre-warm and route directly to specialized agents (e.g., `postgresql-engineer`, `kubernetes-engineer`).

### Token Optimization & Memory Compaction
- **Hierarchical Context Compaction**: For conversations with 100+ turns, maintain structured memory pyramids (active working set $\to$ recent diffs $\to$ high-level architectural decisions).
- **Zero-Redundancy Handoffs**: Pass compact state delta objects instead of raw conversational history during multi-agent delegation chains.

### Enterprise Governance & Observability
- **OpenTelemetry & Prometheus Export**: Native tracing metrics for token latency, tool execution times, agent handoffs, and error rates.
- **Role-Based Workspace Isolation**: Fine-grained project boundary policies for enterprise monorepos.
