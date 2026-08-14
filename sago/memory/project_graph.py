"""Project & Data Graph Engine - Deep dependency, symbol, process, and architecture graph.

Analyzes multi-language codebases to build a complete project topology:
- File & module dependency graph (imports, exports, calls)
- Code symbol graph (classes, functions, interfaces, types)
- Layered Architecture Box Diagrams (Presentation, Engine, Domain, Storage, External)
- Process & Execution Pipeline Maps (Request -> Dispatch -> Execution -> Verification -> State)
- Data model & schema relationships (database tables, ORM models, Pydantic schemas)
- Architectural metrics (coupling, centrality, hub modules)
- Multi-format rendering (Curated Dashboard, Architecture Diagram, Process Map, Mermaid, ASCII tree, JSON)
"""

from __future__ import annotations

import ast
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node in the project graph."""

    id: str
    label: str
    node_type: str  # "file", "module", "class", "function", "data_model", "endpoint"
    language: str = ""
    file_path: str = ""
    line_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.node_type,
            "language": self.language,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "metadata": self.metadata,
        }


@dataclass
class GraphEdge:
    """A directed edge in the project graph."""

    source: str
    target: str
    relation: str  # "imports", "inherits", "calls", "defines", "data_flow", "implements"
    weight: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "weight": self.weight,
        }


class ProjectGraph:
    """Constructs and queries the comprehensive code, data, and process architecture graph."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self.file_symbols: dict[str, list[str]] = defaultdict(list)
        self.data_models: list[str] = []
        self.endpoints: list[str] = []

    def build_graph(
        self,
        max_files: int = 1500,
        include_symbols: bool = True,
        include_data_flow: bool = True,
    ) -> ProjectGraph:
        """Scan workspace and generate all nodes, edges, and data models."""
        self.nodes.clear()
        self.edges.clear()
        self.file_symbols.clear()
        self.data_models.clear()
        self.endpoints.clear()

        ignore_dirs = {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".sago",
            "dist",
            "build",
            ".idea",
            ".vscode",
        }

        # 1. Discover candidate source files
        candidate_files: list[Path] = []
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in {
                    ".py",
                    ".ts",
                    ".tsx",
                    ".js",
                    ".jsx",
                    ".go",
                    ".rs",
                    ".java",
                    ".cpp",
                    ".c",
                    ".h",
                    ".sql",
                    ".yaml",
                    ".json",
                    ".toml",
                }:
                    candidate_files.append(Path(root) / f)
                    if len(candidate_files) >= max_files:
                        break
            if len(candidate_files) >= max_files:
                break

        # 2. Add file nodes
        module_to_node: dict[str, str] = {}
        for fpath in candidate_files:
            try:
                rel_path = str(fpath.relative_to(self.root_dir))
            except ValueError:
                rel_path = str(fpath)

            lang = self._detect_language(fpath)
            node_id = f"file:{rel_path}"
            self.nodes[node_id] = GraphNode(
                id=node_id,
                label=fpath.name,
                node_type="file",
                language=lang,
                file_path=rel_path,
                metadata={"size": fpath.stat().st_size if fpath.exists() else 0},
            )

            if lang == "python":
                mod_key = rel_path.replace("/", ".").replace("\\", ".")
                if mod_key.endswith(".py"):
                    mod_key = mod_key[:-3]
                if mod_key.endswith(".__init__"):
                    mod_key = mod_key[:-9]
                module_to_node[mod_key] = node_id
                module_to_node[mod_key.split(".")[-1]] = node_id

        # 3. Analyze content
        for fpath in candidate_files:
            try:
                rel_path = str(fpath.relative_to(self.root_dir))
            except ValueError:
                rel_path = str(fpath)

            file_node_id = f"file:{rel_path}"
            lang = self._detect_language(fpath)

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            if lang == "python":
                self._analyze_python(
                    file_node_id,
                    rel_path,
                    content,
                    module_to_node,
                    include_symbols,
                    include_data_flow,
                )
            elif lang in {"typescript", "javascript"}:
                self._analyze_js_ts(
                    file_node_id, rel_path, content, include_symbols, include_data_flow
                )
            elif lang in {"go", "rust"}:
                self._analyze_go_rust(file_node_id, rel_path, content, lang, include_symbols)
            elif lang == "sql":
                self._analyze_sql(file_node_id, rel_path, content)

        return self

    def _detect_language(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext == ".py":
            return "python"
        if ext in {".ts", ".tsx"}:
            return "typescript"
        if ext in {".js", ".jsx"}:
            return "javascript"
        if ext == ".go":
            return "go"
        if ext == ".rs":
            return "rust"
        if ext in {".cpp", ".c", ".h", ".hpp"}:
            return "cpp"
        if ext == ".java":
            return "java"
        if ext == ".sql":
            return "sql"
        if ext in {".yaml", ".yml"}:
            return "yaml"
        if ext == ".json":
            return "json"
        return "other"

    def _analyze_python(
        self,
        file_node_id: str,
        rel_path: str,
        content: str,
        module_to_node: dict[str, str],
        include_symbols: bool,
        include_data_flow: bool,
    ) -> None:
        try:
            tree = ast.parse(content, filename=rel_path)
        except SyntaxError:
            return

        for node in tree.body:
            # Imports
            if isinstance(node, ast.Import):
                for name in node.names:
                    imp_name = name.name
                    target = module_to_node.get(imp_name) or module_to_node.get(
                        imp_name.split(".")[0]
                    )
                    if target and target != file_node_id:
                        self.edges.append(
                            GraphEdge(source=file_node_id, target=target, relation="imports")
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                target = module_to_node.get(mod) or module_to_node.get(mod.split(".")[0])
                if target and target != file_node_id:
                    self.edges.append(
                        GraphEdge(source=file_node_id, target=target, relation="imports")
                    )

            # Classes
            elif isinstance(node, ast.ClassDef):
                sym_id = f"sym:{rel_path}#{node.name}"
                is_data_model = (
                    any(
                        base_name
                        in ["BaseModel", "Model", "DeclarativeBase", "Schema", "Table", "Base"]
                        for base_name in [
                            ast.unparse(b) for b in node.bases if hasattr(ast, "unparse")
                        ]
                    )
                    or "model" in node.name.lower()
                    or "schema" in node.name.lower()
                    or "meta" in node.name.lower()
                )

                node_type = "data_model" if (is_data_model and include_data_flow) else "class"
                if is_data_model:
                    self.data_models.append(sym_id)

                if include_symbols:
                    self.nodes[sym_id] = GraphNode(
                        id=sym_id,
                        label=node.name,
                        node_type=node_type,
                        language="python",
                        file_path=rel_path,
                        line_number=node.lineno,
                    )
                    self.edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )

                for base in node.bases:
                    base_name = ast.unparse(base) if hasattr(ast, "unparse") else ""
                    if base_name:
                        self.edges.append(
                            GraphEdge(
                                source=sym_id, target=f"class:{base_name}", relation="inherits"
                            )
                        )

            # Functions & API Endpoints
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sym_id = f"sym:{rel_path}#{node.name}"
                decorators = [
                    ast.unparse(d) for d in node.decorator_list if hasattr(ast, "unparse")
                ]
                is_endpoint = any(
                    any(
                        verb in d.lower()
                        for verb in [
                            ".get(",
                            ".post(",
                            ".put(",
                            ".delete(",
                            ".patch(",
                            "@app.",
                            "@router.",
                        ]
                    )
                    for d in decorators
                )

                node_type = "endpoint" if (is_endpoint and include_data_flow) else "function"
                if is_endpoint:
                    self.endpoints.append(sym_id)

                if include_symbols:
                    self.nodes[sym_id] = GraphNode(
                        id=sym_id,
                        label=f"{node.name}()",
                        node_type=node_type,
                        language="python",
                        file_path=rel_path,
                        line_number=node.lineno,
                        metadata={"decorators": decorators},
                    )
                    self.edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )

    def _analyze_js_ts(
        self,
        file_node_id: str,
        rel_path: str,
        content: str,
        include_symbols: bool,
        include_data_flow: bool,
    ) -> None:
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            line_str = line.strip()

            imp_match = re.search(r"import\s+.*?from\s+['\"](.*?)['\"]", line_str)
            if imp_match:
                imp_target = imp_match.group(1)
                self.edges.append(
                    GraphEdge(
                        source=file_node_id,
                        target=f"module:{imp_target}",
                        relation="imports",
                    )
                )

            class_match = re.search(
                r"(?:export\s+)?(class|interface|type)\s+([A-Za-z0-9_]+)", line_str
            )
            if class_match and include_symbols:
                kind = class_match.group(1)
                name = class_match.group(2)
                sym_id = f"sym:{rel_path}#{name}"
                is_data = (
                    kind in {"interface", "type"}
                    or "schema" in name.lower()
                    or "dto" in name.lower()
                )
                self.nodes[sym_id] = GraphNode(
                    id=sym_id,
                    label=name,
                    node_type="data_model" if is_data else "class",
                    language="typescript",
                    file_path=rel_path,
                    line_number=i,
                )
                self.edges.append(GraphEdge(source=file_node_id, target=sym_id, relation="defines"))

            func_match = re.search(
                r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)|const\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(",
                line_str,
            )
            if func_match and include_symbols:
                name = func_match.group(1) or func_match.group(2)
                if name:
                    sym_id = f"sym:{rel_path}#{name}"
                    self.nodes[sym_id] = GraphNode(
                        id=sym_id,
                        label=f"{name}()",
                        node_type="function",
                        language="typescript",
                        file_path=rel_path,
                        line_number=i,
                    )
                    self.edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )

    def _analyze_go_rust(
        self,
        file_node_id: str,
        rel_path: str,
        content: str,
        lang: str,
        include_symbols: bool,
    ) -> None:
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            line_str = line.strip()
            if lang == "rust" and include_symbols:
                r_match = re.search(
                    r"(?:pub\s+)?(struct|enum|trait|fn)\s+([A-Za-z0-9_]+)", line_str
                )
                if r_match:
                    kind, name = r_match.group(1), r_match.group(2)
                    sym_id = f"sym:{rel_path}#{name}"
                    self.nodes[sym_id] = GraphNode(
                        id=sym_id,
                        label=f"{name}()" if kind == "fn" else name,
                        node_type="function" if kind == "fn" else "data_model",
                        language="rust",
                        file_path=rel_path,
                        line_number=i,
                    )
                    self.edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )

            elif lang == "go" and include_symbols:
                g_match = re.search(r"type\s+([A-Za-z0-9_]+)\s+(struct|interface)", line_str)
                if g_match:
                    name = g_match.group(1)
                    sym_id = f"sym:{rel_path}#{name}"
                    self.nodes[sym_id] = GraphNode(
                        id=sym_id,
                        label=name,
                        node_type="data_model",
                        language="go",
                        file_path=rel_path,
                        line_number=i,
                    )
                    self.edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )
                fn_match = re.search(r"func\s+(?:\(.*?\)\s+)?([A-Za-z0-9_]+)\s*\(", line_str)
                if fn_match and include_symbols:
                    name = fn_match.group(1)
                    sym_id = f"sym:{rel_path}#{name}"
                    self.nodes[sym_id] = GraphNode(
                        id=sym_id,
                        label=f"{name}()",
                        node_type="function",
                        language="go",
                        file_path=rel_path,
                        line_number=i,
                    )
                    self.edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )

    def _analyze_sql(self, file_node_id: str, rel_path: str, content: str) -> None:
        table_matches = re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[\`\"\[]?(\w+)[\`\"\]]?\.)?[\`\"\[]?(\w+)[\`\"\]]?",
            content,
            re.IGNORECASE,
        )
        for m in table_matches:
            table_name = m.group(2) or m.group(1)
            sym_id = f"db_table:{table_name}"
            self.nodes[sym_id] = GraphNode(
                id=sym_id,
                label=f"TABLE {table_name}",
                node_type="data_model",
                language="sql",
                file_path=rel_path,
            )
            self.edges.append(GraphEdge(source=file_node_id, target=sym_id, relation="defines"))

    # ─────────────────────────────────────────────────────────────
    # Smart Architectural & Process Renderers
    # ─────────────────────────────────────────────────────────────

    def to_architecture_diagram(self) -> str:
        """Render a layered system architecture box diagram."""
        # Categorize detected files into architectural layers
        layers: dict[str, list[str]] = {
            "Presentation & Interface": [],
            "Orchestration & Workflow Engine": [],
            "Specialist Agents & Tools Domain": [],
            "Memory, State & Database": [],
            "Integration, Mesh & Plugins": [],
        }

        for node in self.nodes.values():
            if node.node_type != "file":
                continue
            path = node.file_path.lower()
            name = node.label.replace(".py", "")

            if any(
                k in path for k in ["tui", "cli", "main.py", "screen", "widget", "server", "daemon"]
            ):
                layers["Presentation & Interface"].append(name)
            elif any(
                k in path
                for k in ["engine", "orchestrat", "workflow", "delegat", "checkpoint", "verifier"]
            ):
                layers["Orchestration & Workflow Engine"].append(name)
            elif any(
                k in path
                for k in ["agent", "tool", "coding", "security", "shell", "network", "ssh"]
            ):
                layers["Specialist Agents & Tools Domain"].append(name)
            elif any(
                k in path
                for k in [
                    "memory",
                    "database",
                    "rag",
                    "symbol",
                    "cache",
                    "session",
                    "tasks",
                    "learning",
                ]
            ):
                layers["Memory, State & Database"].append(name)
            elif any(k in path for k in ["mcp", "mesh", "peer", "plugin", "skill", "llm"]):
                layers["Integration, Mesh & Plugins"].append(name)

        lines = [
            "┌──────────────────────────────────────────────────────────────────────────┐",
            "│                     SAGO SYSTEM ARCHITECTURE MAP                         │",
            "└──────────────────────────────────────────────────────────────────────────┘",
        ]

        for layer_name, comps in layers.items():
            if not comps:
                continue
            comp_sample = ", ".join(sorted(list(set(comps)))[:8])
            if len(comps) > 8:
                comp_sample += f" + {len(comps) - 8} more"

            lines.append(f"\n┌── [ {layer_name.upper()} ] ────────────────────────────────────────")
            lines.append(f"│  Components: {comp_sample}")
            lines.append(
                "└──────────────────────────────────────────────────────────────────────────"
            )
            lines.append("                                    ▼")

        lines[-1] = "                                 (Stable)"
        return "\n".join(lines)

    def to_process_map(self) -> str:
        """Render end-to-end autonomous execution pipeline and process lifecycle."""
        lines = [
            "==========================================================================",
            "                   SAGO END-TO-END PROCESS & EXECUTION PIPELINE            ",
            "==========================================================================",
            "",
            "   [ USER REQUEST ]",
            "          │",
            "          ▼",
            "   [ 1. Context & RAG Ingestion ] ────► SymbolGraph / RepoMap / ProjectGraph",
            "          │                              (AST Extraction & Codebase Index)",
            "          ▼",
            "   [ 2. Intent Routing & Delegation ] ─► Orchestrator / Multi-Agent Swarm",
            "          │                              (200+ Specialist Profiles / Handoff)",
            "          ▼",
            "   [ 3. Checkpoint Snapshot ] ────────► CheckpointManager",
            "          │                              (Atomic workspace delta backup)",
            "          ▼",
            "   [ 4. Autonomous Tool Execution ] ──► 50+ Tools Matrix",
            "          │                              (File / Shell / Coding / DB / SSH)",
            "          ▼",
            "   [ 5. Self-Healing Verification ] ──► ProjectVerifier (ruff / mypy / pytest)",
            "          │                              ├── Passed  ──► [ 6. State Commit ]",
            "          │                              └── Failed  ──► (Loop back to Step 4)",
            "          ▼",
            "   [ 6. Persistent Learning & State ] ─► LearningStore / SQLite / Tasks",
            "          │                              (Success patterns & error fixes cached)",
            "          ▼",
            "   [ STREAM RESPONSE TO USER ]",
            "",
            "==========================================================================",
        ]
        return "\n".join(lines)

    def to_curated_dashboard(self, focus_filter: str | None = None) -> str:
        """Generate a complete, curated architecture and graph dashboard."""
        sections = []

        # 1. Header & Metrics
        sections.append(
            f"### SAGO Project Topology & Architecture Dashboard: `{self.root_dir.name}`"
        )
        sections.append(
            f"**Metrics**: {len([n for n in self.nodes.values() if n.node_type == 'file'])} Files | "
            f"{len(self.data_models)} Data Models/Schemas | {len(self.edges)} Active Relations\n"
        )

        # 2. Architecture Box Diagram
        sections.append("#### 🏗️ System Architecture Map")
        sections.append(f"```text\n{self.to_architecture_diagram()}\n```\n")

        # 3. Process Execution Flow
        sections.append("#### 🔄 Autonomous Process & Execution Flywheel")
        sections.append(f"```text\n{self.to_process_map()}\n```\n")

        # 4. Data Models & Hub Modules
        models = [n for n in self.nodes.values() if n.node_type == "data_model"]
        if models:
            sections.append("#### 📊 Core Data Models & Schemas")
            model_items = [f"- **`{m.label}`** (`{m.file_path}`)" for m in models[:12]]
            sections.append("\n".join(model_items) + "\n")

        # Central Hub Modules
        in_degree: dict[str, int] = defaultdict(int)
        for e in self.edges:
            if e.relation == "imports":
                in_degree[e.target] += 1
        top_hubs = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:8]
        if top_hubs:
            sections.append("#### 🌟 Top Dependent Hub Modules (Core Architecture)")
            hub_items = [
                f"- **`{hub_id.replace('file:', '')}`** (Depended on by {count} modules)"
                for hub_id, count in top_hubs
            ]
            sections.append("\n".join(hub_items) + "\n")

        # 5. Mermaid Flowchart Block
        sections.append("#### 📈 Visual Mermaid Graph")
        sections.append(self.to_mermaid(max_edges=30, focus_filter=focus_filter))

        return "\n".join(sections)

    def to_mermaid(self, max_edges: int = 40, focus_filter: str | None = None) -> str:
        """Render the project graph in Mermaid flowchart syntax."""
        lines = ["```mermaid", "flowchart TD"]
        lines.append("  classDef fileNode fill:#1f2937,stroke:#3b82f6,stroke-width:1px,color:#fff;")
        lines.append(
            "  classDef modelNode fill:#065f46,stroke:#10b981,stroke-width:2px,color:#fff;"
        )
        lines.append(
            "  classDef endpointNode fill:#7c2d12,stroke:#f97316,stroke-width:2px,color:#fff;"
        )
        lines.append(
            "  classDef classNode fill:#312e81,stroke:#818cf8,stroke-width:1px,color:#fff;"
        )

        added_nodes = set()
        filtered_edges = self.edges
        if focus_filter:
            q = focus_filter.lower()
            filtered_edges = [
                e for e in self.edges if q in e.source.lower() or q in e.target.lower()
            ]

        import_and_data_edges = [
            e for e in filtered_edges if e.relation in {"imports", "inherits", "data_flow"}
        ]
        if not import_and_data_edges:
            import_and_data_edges = filtered_edges

        for edge in import_and_data_edges[:max_edges]:
            src_node = self.nodes.get(edge.source)
            tgt_node = self.nodes.get(edge.target)

            src_label = src_node.label if src_node else edge.source.split(":")[-1]
            tgt_label = tgt_node.label if tgt_node else edge.target.split(":")[-1]

            src_clean_id = re.sub(r"[^a-zA-Z0-9_]", "_", edge.source)
            tgt_clean_id = re.sub(r"[^a-zA-Z0-9_]", "_", edge.target)

            if src_clean_id not in added_nodes:
                lines.append(f'  {src_clean_id}["{src_label}"]')
                added_nodes.add(src_clean_id)
            if tgt_clean_id not in added_nodes:
                lines.append(f'  {tgt_clean_id}["{tgt_label}"]')
                added_nodes.add(tgt_clean_id)

            arrow = "-->" if edge.relation == "imports" else "-.->|inherits|"
            lines.append(f"  {src_clean_id} {arrow} {tgt_clean_id}")

        lines.append("```")
        return "\n".join(lines)

    def to_ascii_tree(self) -> str:
        """Render a formatted ASCII structural hierarchy and data relationships."""
        out = []
        out.append(f"Project Topology Graph: {self.root_dir.name}")
        out.append(f"Total Nodes: {len(self.nodes)} | Dependencies & Relations: {len(self.edges)}")
        out.append("=" * 65)

        file_nodes = [n for n in self.nodes.values() if n.node_type == "file"]
        model_nodes = [n for n in self.nodes.values() if n.node_type == "data_model"]
        endpoint_nodes = [n for n in self.nodes.values() if n.node_type == "endpoint"]

        out.append(
            f"Structure: {len(file_nodes)} Source Files | {len(model_nodes)} Data Models/Schemas | {len(endpoint_nodes)} Endpoints"
        )
        out.append("-" * 65)

        by_dir: dict[str, list[GraphNode]] = defaultdict(list)
        for f in file_nodes:
            p = Path(f.file_path)
            parent = str(p.parent) if str(p.parent) != "." else "/"
            by_dir[parent].append(f)

        for d, f_list in sorted(by_dir.items()):
            out.append(f"\n📂 {d}/")
            for f in sorted(f_list, key=lambda x: x.label):
                out_edges = [e for e in self.edges if e.source == f.id and e.relation == "imports"]
                imports_desc = ""
                if out_edges:
                    imp_targets = [e.target.split(":")[-1] for e in out_edges[:3]]
                    imports_desc = f" ➔ imports ({', '.join(imp_targets)})"

                defined_syms = [
                    n
                    for n in self.nodes.values()
                    if n.file_path == f.file_path and n.node_type != "file"
                ]
                sym_badge = f" [{len(defined_syms)} symbols]" if defined_syms else ""
                out.append(f"   📄 {f.label}{sym_badge}{imports_desc}")

        if model_nodes:
            out.append("\n" + "=" * 65)
            out.append("📊 Core Data Models & Schemas:")
            for m in model_nodes[:15]:
                out.append(f"  • {m.label} ({m.file_path})")

        return "\n".join(out)

    def to_llm_context(self) -> str:
        """Render a high-density, compact context block optimized for LLM prompts."""
        lines = [
            "### Project Dependency & Architecture Graph",
            f"Workspace: `{self.root_dir.name}` ({len(self.nodes)} total components)",
        ]

        in_degree: dict[str, int] = defaultdict(int)
        for e in self.edges:
            if e.relation == "imports":
                in_degree[e.target] += 1

        top_hubs = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:10]
        if top_hubs:
            lines.append("\n**Core Depended-On Modules (Hubs)**:")
            for hub_id, count in top_hubs:
                clean_name = hub_id.replace("file:", "").replace("module:", "")
                lines.append(f"- `{clean_name}` (referenced by {count} files)")

        models = [n for n in self.nodes.values() if n.node_type == "data_model"]
        if models:
            lines.append("\n**Data Models & Schemas**:")
            for m in models[:12]:
                lines.append(f"- `{m.label}` at `{m.file_path}`")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize full graph to dictionary."""
        return {
            "root": str(self.root_dir),
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }
