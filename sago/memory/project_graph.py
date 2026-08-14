"""Project & Data Graph Engine - Deep dependency, symbol, process, ER, and architecture graph.

Analyzes multi-language codebases to build a complete project topology:
- File & module dependency graph (imports, exports, calls)
- Code symbol graph (classes, functions, interfaces, types)
- Layered Architecture Box Diagrams (Presentation, Engine, Domain, Storage, External)
- Process & Execution Pipeline Maps (Request -> Dispatch -> Execution -> Verification -> State)
- Entity Relationship (ER) Data Model Map (ORM models, Pydantic schemas, database tables)
- Architectural metrics (coupling, centrality, hub modules)
- Multi-format rendering (Curated Dashboard, Architecture Diagram, Process Map, ER Map, Mermaid, ASCII tree, JSON)
- ThreadPoolExecutor parallelized AST parsing & TTL caching for high performance on complex monorepos
"""

from __future__ import annotations

import ast
import concurrent.futures
import logging
import os
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Global thread-safe graph cache: root_dir -> (cached_timestamp, ProjectGraph)
_GRAPH_CACHE_LOCK = threading.Lock()
_GRAPH_CACHE: dict[str, tuple[float, ProjectGraph]] = {}


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
        self.model_fields: dict[str, list[str]] = defaultdict(list)
        self._lock = threading.Lock()

    def build_graph(
        self,
        max_files: int = 1500,
        include_symbols: bool = True,
        include_data_flow: bool = True,
    ) -> ProjectGraph:
        """Scan workspace in parallel and generate all nodes, edges, and data models."""
        self.nodes.clear()
        self.edges.clear()
        self.file_symbols.clear()
        self.data_models.clear()
        self.endpoints.clear()
        self.model_fields.clear()

        ignore_dirs = {
            ".git",
            ".venv",
            "venv",
            "env",
            ".env",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".sago",
            "dist",
            "build",
            "target",
            "vendor",
            "coverage",
            ".next",
            ".nuxt",
            ".turbo",
            ".gradle",
            ".cache",
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

        # 2. Add file nodes and build module map
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

        # 3. Parallel worker parsing across multi-core CPUs
        def _process_single_file(fpath: Path) -> dict[str, Any]:
            try:
                rel_path = str(fpath.relative_to(self.root_dir))
            except ValueError:
                rel_path = str(fpath)

            file_node_id = f"file:{rel_path}"
            lang = self._detect_language(fpath)

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return {}

            local_nodes: list[GraphNode] = []
            local_edges: list[GraphEdge] = []
            local_models: list[str] = []
            local_endpoints: list[str] = []
            local_fields: dict[str, list[str]] = defaultdict(list)

            if lang == "python":
                self._parse_python_local(
                    file_node_id,
                    rel_path,
                    content,
                    module_to_node,
                    include_symbols,
                    include_data_flow,
                    local_nodes,
                    local_edges,
                    local_models,
                    local_endpoints,
                    local_fields,
                )
            elif lang in {"typescript", "javascript"}:
                self._parse_js_ts_local(
                    file_node_id,
                    rel_path,
                    content,
                    include_symbols,
                    local_nodes,
                    local_edges,
                    local_models,
                )
            elif lang in {"go", "rust"}:
                self._parse_go_rust_local(
                    file_node_id,
                    rel_path,
                    content,
                    lang,
                    include_symbols,
                    local_nodes,
                    local_edges,
                    local_models,
                )
            elif lang == "sql":
                self._parse_sql_local(
                    file_node_id, rel_path, content, local_nodes, local_edges, local_models
                )

            return {
                "nodes": local_nodes,
                "edges": local_edges,
                "models": local_models,
                "endpoints": local_endpoints,
                "fields": local_fields,
            }

        max_workers = min(32, (os.cpu_count() or 4) * 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(_process_single_file, candidate_files)

        # Merge thread results
        for res in results:
            if not res:
                continue
            for n in res.get("nodes", []):
                self.nodes[n.id] = n
            self.edges.extend(res.get("edges", []))
            self.data_models.extend(res.get("models", []))
            self.endpoints.extend(res.get("endpoints", []))
            for k, v in res.get("fields", {}).items():
                self.model_fields[k].extend(v)

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

    def _parse_python_local(
        self,
        file_node_id: str,
        rel_path: str,
        content: str,
        module_to_node: dict[str, str],
        include_symbols: bool,
        include_data_flow: bool,
        out_nodes: list[GraphNode],
        out_edges: list[GraphEdge],
        out_models: list[str],
        out_endpoints: list[str],
        out_fields: dict[str, list[str]],
    ) -> None:
        try:
            tree = ast.parse(content, filename=rel_path)
        except SyntaxError:
            return

        for node in tree.body:
            if isinstance(node, ast.Import):
                for name in node.names:
                    imp_name = name.name
                    target = module_to_node.get(imp_name) or module_to_node.get(
                        imp_name.split(".")[0]
                    )
                    if target and target != file_node_id:
                        out_edges.append(
                            GraphEdge(source=file_node_id, target=target, relation="imports")
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                target = module_to_node.get(mod) or module_to_node.get(mod.split(".")[0])
                if target and target != file_node_id:
                    out_edges.append(
                        GraphEdge(source=file_node_id, target=target, relation="imports")
                    )

            elif isinstance(node, ast.ClassDef):
                sym_id = f"sym:{rel_path}#{node.name}"
                is_data_model = (
                    any(
                        base_name
                        in [
                            "BaseModel",
                            "Model",
                            "DeclarativeBase",
                            "Schema",
                            "Table",
                            "Base",
                            "dataclass",
                        ]
                        for base_name in [
                            ast.unparse(b) for b in node.bases if hasattr(ast, "unparse")
                        ]
                    )
                    or "model" in node.name.lower()
                    or "schema" in node.name.lower()
                    or "meta" in node.name.lower()
                )

                if is_data_model:
                    out_models.append(sym_id)
                    for item in node.body:
                        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            ann = ast.unparse(item.annotation) if hasattr(ast, "unparse") else ""
                            out_fields[sym_id].append(f"{item.target.id}: {ann}")

                node_type = "data_model" if (is_data_model and include_data_flow) else "class"

                if include_symbols:
                    out_nodes.append(
                        GraphNode(
                            id=sym_id,
                            label=node.name,
                            node_type=node_type,
                            language="python",
                            file_path=rel_path,
                            line_number=node.lineno,
                        )
                    )
                    out_edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )

                for base in node.bases:
                    base_name = ast.unparse(base) if hasattr(ast, "unparse") else ""
                    if base_name:
                        out_edges.append(
                            GraphEdge(
                                source=sym_id, target=f"class:{base_name}", relation="inherits"
                            )
                        )

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
                    out_endpoints.append(sym_id)

                if include_symbols:
                    out_nodes.append(
                        GraphNode(
                            id=sym_id,
                            label=f"{node.name}()",
                            node_type=node_type,
                            language="python",
                            file_path=rel_path,
                            line_number=node.lineno,
                            metadata={"decorators": decorators},
                        )
                    )
                    out_edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )

    def _parse_js_ts_local(
        self,
        file_node_id: str,
        rel_path: str,
        content: str,
        include_symbols: bool,
        out_nodes: list[GraphNode],
        out_edges: list[GraphEdge],
        out_models: list[str],
    ) -> None:
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            line_str = line.strip()

            imp_match = re.search(r"import\s+.*?from\s+['\"](.*?)['\"]", line_str)
            if imp_match:
                imp_target = imp_match.group(1)
                out_edges.append(
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
                    or "model" in name.lower()
                )
                if is_data:
                    out_models.append(sym_id)

                out_nodes.append(
                    GraphNode(
                        id=sym_id,
                        label=name,
                        node_type="data_model" if is_data else "class",
                        language="typescript",
                        file_path=rel_path,
                        line_number=i,
                    )
                )
                out_edges.append(GraphEdge(source=file_node_id, target=sym_id, relation="defines"))

            func_match = re.search(
                r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)|const\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(",
                line_str,
            )
            if func_match and include_symbols:
                name = func_match.group(1) or func_match.group(2)
                if name:
                    sym_id = f"sym:{rel_path}#{name}"
                    out_nodes.append(
                        GraphNode(
                            id=sym_id,
                            label=f"{name}()",
                            node_type="function",
                            language="typescript",
                            file_path=rel_path,
                            line_number=i,
                        )
                    )
                    out_edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )

    def _parse_go_rust_local(
        self,
        file_node_id: str,
        rel_path: str,
        content: str,
        lang: str,
        include_symbols: bool,
        out_nodes: list[GraphNode],
        out_edges: list[GraphEdge],
        out_models: list[str],
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
                    is_data = kind in ("struct", "enum")
                    if is_data:
                        out_models.append(sym_id)
                    out_nodes.append(
                        GraphNode(
                            id=sym_id,
                            label=f"{name}()" if kind == "fn" else name,
                            node_type="data_model" if is_data else "function",
                            language="rust",
                            file_path=rel_path,
                            line_number=i,
                        )
                    )
                    out_edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )

            elif lang == "go" and include_symbols:
                g_match = re.search(r"type\s+([A-Za-z0-9_]+)\s+(struct|interface)", line_str)
                if g_match:
                    name = g_match.group(1)
                    sym_id = f"sym:{rel_path}#{name}"
                    out_models.append(sym_id)
                    out_nodes.append(
                        GraphNode(
                            id=sym_id,
                            label=name,
                            node_type="data_model",
                            language="go",
                            file_path=rel_path,
                            line_number=i,
                        )
                    )
                    out_edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )
                fn_match = re.search(r"func\s+(?:\(.*?\)\s+)?([A-Za-z0-9_]+)\s*\(", line_str)
                if fn_match and include_symbols:
                    name = fn_match.group(1)
                    sym_id = f"sym:{rel_path}#{name}"
                    out_nodes.append(
                        GraphNode(
                            id=sym_id,
                            label=f"{name}()",
                            node_type="function",
                            language="go",
                            file_path=rel_path,
                            line_number=i,
                        )
                    )
                    out_edges.append(
                        GraphEdge(source=file_node_id, target=sym_id, relation="defines")
                    )

    def _parse_sql_local(
        self,
        file_node_id: str,
        rel_path: str,
        content: str,
        out_nodes: list[GraphNode],
        out_edges: list[GraphEdge],
        out_models: list[str],
    ) -> None:
        table_matches = re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[\`\"\[]?(\w+)[\`\"\]]?\.)?[\`\"\[]?(\w+)[\`\"\]]?",
            content,
            re.IGNORECASE,
        )
        for m in table_matches:
            table_name = m.group(2) or m.group(1)
            sym_id = f"db_table:{table_name}"
            out_models.append(sym_id)
            out_nodes.append(
                GraphNode(
                    id=sym_id,
                    label=f"TABLE {table_name}",
                    node_type="data_model",
                    language="sql",
                    file_path=rel_path,
                )
            )
            out_edges.append(GraphEdge(source=file_node_id, target=sym_id, relation="defines"))

    # ─────────────────────────────────────────────────────────────
    # Smart Architectural, Process, & ER Renderers
    # ─────────────────────────────────────────────────────────────

    def to_architecture_diagram(self) -> str:
        """Render a crisp, layered system architecture box diagram based on real project topology."""
        layers: dict[str, list[str]] = {
            "Presentation & Interface": [],
            "Orchestration & Workflow Engine": [],
            "Specialist Agents & Tools Domain": [],
            "Memory, State & Database": [],
            "Integration, Mesh & Plugins": [],
            "Test Suites & Quality Verification": [],
        }

        unassigned_by_dir: dict[str, list[str]] = defaultdict(list)

        for node in self.nodes.values():
            if node.node_type != "file":
                continue
            path = node.file_path.lower()
            name = node.label

            if any(k in path for k in ("test", "spec", "verify", "mock", "fixture", "audit")):
                layers["Test Suites & Quality Verification"].append(name)
            elif any(
                k in path
                for k in (
                    "ui",
                    "frontend",
                    "client",
                    "screen",
                    "view",
                    "page",
                    "widget",
                    "tui",
                    "cli",
                    "route",
                    "api",
                    "handler",
                    "endpoint",
                    "controller",
                    "server",
                    "router",
                    "grpc",
                    "ws",
                )
            ):
                layers["Presentation & Interface"].append(name)
            elif any(
                k in path
                for k in (
                    "engine",
                    "orchestrat",
                    "workflow",
                    "logic",
                    "executor",
                    "pipeline",
                    "checkpoint",
                    "verifier",
                    "runtime",
                    "delegat",
                )
            ):
                layers["Orchestration & Workflow Engine"].append(name)
            elif any(
                k in path
                for k in (
                    "agent",
                    "tool",
                    "coding",
                    "security",
                    "shell",
                    "network",
                    "ssh",
                    "service",
                    "domain",
                )
            ):
                layers["Specialist Agents & Tools Domain"].append(name)
            elif any(
                k in path
                for k in (
                    "model",
                    "schema",
                    "entity",
                    "dto",
                    "types",
                    "tables",
                    "sql",
                    "migration",
                    "db",
                    "database",
                    "store",
                    "storage",
                    "repository",
                    "cache",
                    "memory",
                    "dao",
                    "redis",
                    "rag",
                    "session",
                    "tasks",
                )
            ):
                layers["Memory, State & Database"].append(name)
            elif any(
                k in path
                for k in (
                    "util",
                    "helper",
                    "common",
                    "lib",
                    "config",
                    "client",
                    "adapter",
                    "mcp",
                    "mesh",
                    "peer",
                    "plugin",
                    "skill",
                    "llm",
                    "auth",
                )
            ):
                layers["Integration, Mesh & Plugins"].append(name)
            else:
                p = Path(node.file_path)
                top_dir = str(p.parent) if str(p.parent) != "." else "root"
                unassigned_by_dir[top_dir].append(name)

        # Merge unassigned directories into dynamic layers if any exist
        for d, files in sorted(unassigned_by_dir.items()):
            if files:
                layer_title = f"Module Package: {d}"
                layers[layer_title] = files

        w = max(72, min(96, len(self.root_dir.name) + 36))
        proj_title = f"{self.root_dir.name.upper()} SYSTEM ARCHITECTURE MAP"
        lines = [
            "╔" + "═" * (w - 2) + "╗",
            "║" + proj_title.center(w - 2) + "║",
            "╚" + "═" * (w - 2) + "╝",
        ]

        active_layers = [layer for layer in layers.items() if layer[1]]
        for layer_name, comps in active_layers:
            comp_sample = ", ".join(sorted(list(set(comps)))[:7])
            if len(comps) > 7:
                comp_sample += f" + {len(comps) - 7} more"

            lines.append(
                f"\n┌── [ {layer_name.upper()} ] " + "─" * max(2, (w - len(layer_name) - 10))
            )
            lines.append(f"│  Components: {comp_sample}")
            lines.append("└" + "─" * (w - 2))
            lines.append(" " * (w // 2 - 1) + "│")
            lines.append(" " * (w // 2 - 1) + "▼")

        if len(lines) >= 2 and lines[-1].strip() == "▼":
            lines[-2] = " " * max(0, (w // 2 - 8)) + "(State Stable)"
            lines.pop()
        return "\n".join(lines)

    def to_process_map(self) -> str:
        """Dynamically render project process lifecycle, entry points, and execution pipelines."""
        w = max(72, min(96, len(self.root_dir.name) + 40))
        proj_title = f"{self.root_dir.name.upper()} EXECUTION & LIFECYCLE PIPELINE"
        lines = [
            "╔" + "═" * (w - 2) + "╗",
            "║" + proj_title.center(w - 2) + "║",
            "╚" + "═" * (w - 2) + "╝",
            "",
        ]

        # 1. Discover Entrypoints
        entry_nodes = [
            n.label
            for n in self.nodes.values()
            if any(
                k in n.file_path.lower()
                for k in ("main.", "app.", "cli.", "server.", "index.", "router.", "api.", "entry.")
            )
        ]
        entry_str = (
            ", ".join(sorted(list(set(entry_nodes)))[:4])
            if entry_nodes
            else "User Invocation / CLI / API Entrypoint"
        )

        # 2. Discover Core Logic / Services
        core_nodes = [
            n.label
            for n in self.nodes.values()
            if any(
                k in n.file_path.lower()
                for k in (
                    "engine",
                    "core",
                    "service",
                    "executor",
                    "workflow",
                    "agent",
                    "handler",
                    "manager",
                    "controller",
                )
            )
        ]
        core_str = (
            ", ".join(sorted(list(set(core_nodes)))[:5])
            if core_nodes
            else "Core Domain & Service Logic"
        )

        # 3. Discover Persistence / Data Layer
        data_nodes = [
            n.label
            for n in self.nodes.values()
            if n.node_type == "data_model"
            or any(
                k in n.file_path.lower()
                for k in ("db", "database", "model", "schema", "store", "repo", "cache", "memory")
            )
        ]
        data_str = (
            ", ".join(sorted(list(set(data_nodes)))[:5])
            if data_nodes
            else "Database / State Store / Repository"
        )

        # 4. Discover Verifiers / Linters / Tests
        test_nodes = [
            n.label
            for n in self.nodes.values()
            if any(
                k in n.file_path.lower()
                for k in ("test", "verify", "check", "lint", "audit", "spec")
            )
        ]
        test_str = (
            ", ".join(sorted(list(set(test_nodes)))[:4])
            if test_nodes
            else "Test Suites & Quality Checks"
        )

        lines.extend(
            [
                f"   [ 📥 1. Ingestion & Entry ] ─────────► {entry_str}",
                "                 │",
                "                 ▼",
                f"   [ ⚙️ 2. Core Execution Pipeline ] ────► {core_str}",
                "                 │",
                "                 ▼",
                f"   [ 🛡️ 3. Verification & Checks ] ──────► {test_str}",
                "                 │                              ├── Passed ──► Proceed to Persistence",
                "                 │                              └── Failed ──► Diagnostic Feedback Loop",
                "                 ▼",
                f"   [ 💾 4. Persistence & State ] ────────► {data_str}",
                "                 │",
                "                 ▼",
                "   [ 📤 5. Output / Response Delivery ] ─► Viewport / Client Response",
                "",
                "═" * w,
            ]
        )
        return "\n".join(lines)

    def to_er_diagram(self) -> str:
        """Render an Entity-Relationship (ER) Schema & Data Model Diagram."""
        w = max(72, min(96, len(self.root_dir.name) + 36))
        proj_title = f"{self.root_dir.name.upper()} DATA MODEL & ENTITY SCHEMA GRAPH"
        lines = [
            "╔" + "═" * (w - 2) + "╗",
            "║" + proj_title.center(w - 2) + "║",
            "╚" + "═" * (w - 2) + "╝",
            "",
        ]

        models = [n for n in self.nodes.values() if n.node_type == "data_model"]
        if not models:
            lines.append("No explicit data models or schemas detected in current scope.")
            return "\n".join(lines)

        for m in models[:18]:
            fields = self.model_fields.get(m.id, [])
            lines.append(f"┌── [ {m.label} ] ── ({m.file_path})")
            if fields:
                for f in fields[:6]:
                    lines.append(f"│   • {f}")
                if len(fields) > 6:
                    lines.append(f"│   • ... and {len(fields) - 6} more fields")
            else:
                lines.append(f"│   • Type: {m.language.upper()} Entity / Schema")
            lines.append("└──" + "─" * (w - 2) + "\n")

        return "\n".join(lines)

    def to_detailed_llm_blueprint(self) -> str:
        """Render a structured AST blueprint to feed directly to LLM for architectural synthesis."""
        lines = [
            f"Project: {self.root_dir.name}",
            f"Total Nodes: {len(self.nodes)} | Dependencies: {len(self.edges)}",
            "\nDirectory Structure & Source Files:",
        ]

        file_nodes = [n for n in self.nodes.values() if n.node_type == "file"]
        by_dir: dict[str, list[str]] = defaultdict(list)
        for f in file_nodes:
            p = Path(f.file_path)
            parent = str(p.parent) if str(p.parent) != "." else "/"
            by_dir[parent].append(f.label)

        for d, f_list in sorted(by_dir.items())[:20]:
            lines.append(f"  - {d}/: {', '.join(f_list[:10])}")

        in_degree: dict[str, int] = defaultdict(int)
        for e in self.edges:
            if e.relation == "imports":
                in_degree[e.target] += 1
        top_hubs = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:8]
        if top_hubs:
            lines.append("\nHigh-Dependency Backbone Modules (Hubs):")
            for hub_id, count in top_hubs:
                lines.append(
                    f"  - {hub_id.replace('file:', '').replace('module:', '')} (depended on by {count} files)"
                )

        models = [n for n in self.nodes.values() if n.node_type == "data_model"]
        if models:
            lines.append("\nData Models / Schemas:")
            for m in models[:12]:
                fields = self.model_fields.get(m.id, [])
                field_str = f" ({', '.join(fields[:4])})" if fields else ""
                lines.append(f"  - {m.label} at {m.file_path}{field_str}")

        return "\n".join(lines)

    def to_topological_architectural_summary(self) -> str:
        """High-density topological architectural summary."""
        file_count = len([n for n in self.nodes.values() if n.node_type == "file"])
        model_count = len(self.data_models)
        edge_count = len(self.edges)

        in_degree: dict[str, int] = defaultdict(int)
        for e in self.edges:
            if e.relation == "imports":
                in_degree[e.target] += 1
        top_hubs = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:6]

        lines = [
            f"### 🏛️ Architecture & Topology Breakdown: `{self.root_dir.name}`\n",
            f"- **System Scope**: `{file_count}` source files, `{model_count}` data schemas, `{edge_count}` dependency edges.",
            "- **Architectural Backbone (Core Hubs)**:",
        ]
        for hub_id, count in top_hubs:
            clean = hub_id.replace("file:", "").replace("module:", "")
            lines.append(f"  - `{clean}` (imported by {count} modules)")

        models = [n for n in self.nodes.values() if n.node_type == "data_model"][:8]
        if models:
            lines.append("- **Core Data Entities**:")
            for m in models:
                lines.append(f"  - `{m.label}` (`{m.file_path}`)")

        lines.append(
            "\n*Tip: Run `/graph arch`, `/graph process`, `/graph er`, or `/graph flow` for interactive views.*"
        )
        return "\n".join(lines)

    def to_ai_architectural_analysis(
        self,
        provider: str = "",
        model: str = "",
    ) -> str:
        """Query LLM to generate a rich, accurate Architectural Synthesis based on the parsed AST graph."""
        try:
            from sago.llm.tui_providers import generate_with_provider

            blueprint = self.to_detailed_llm_blueprint()
            prompt = (
                f"Analyze this actual codebase topology and provide a crisp, professional Architectural Report for `{self.root_dir.name}`:\n\n"
                f"{blueprint}\n\n"
                "Format your response with the following markdown sections:\n"
                "### 🏛️ System Architecture & Pattern\n"
                "Identify the architectural paradigm (e.g. Clean/Layered Architecture, Event-Driven Agentic System, Microservice/Modular Monolith) with concrete justification.\n\n"
                "### 📦 Subsystems & Component Breakdown\n"
                "List the main functional subsystems and their exact file/module locations.\n\n"
                "### 🔄 Data & Execution Flow\n"
                "Trace the end-to-end lifecycle from user entrypoint to execution and state persistence.\n\n"
                "### 📊 Key Data Models & Backbone Entities\n"
                "Summarize the core models, schemas, and high-dependency hub modules.\n\n"
                "### 💡 Architectural Insights & Recommendations\n"
                "Highlight strengths and potential architectural improvements."
            )

            prov = provider or "openrouter"
            mod = model or "openrouter/auto"
            messages = [{"role": "user", "content": prompt}]
            resp = generate_with_provider(
                provider=prov,
                model=mod,
                messages=messages,
                system_prompt="You are a Principal Software Architect providing accurate, insightful codebase architecture analysis.",
                max_tokens=2048,
                temperature=0.2,
                stream=False,
            )
            if hasattr(resp, "choices") and resp.choices:
                return resp.choices[0].message.content.strip()
            elif hasattr(resp, "text"):
                return resp.text.strip()
            elif isinstance(resp, str):
                return resp.strip()
            return str(resp)
        except Exception as ex:
            logger.debug(f"LLM architectural synthesis fallback: {ex}")
            return self.to_topological_architectural_summary()

    def to_curated_dashboard(
        self, focus_filter: str | None = None, provider: str = "", model: str = ""
    ) -> str:
        """Generate a complete, curated architecture, process, and data graph dashboard."""
        sections = []

        file_count = len([n for n in self.nodes.values() if n.node_type == "file"])
        model_count = len(self.data_models)
        edge_count = len(self.edges)

        # 1. Header & Metrics
        sections.append(
            f"### SAGO Project Topology & Architecture Dashboard: `{self.root_dir.name}`\n"
            f"**Topology Metrics**: `{file_count}` Source Files │ `{model_count}` Data Models/Schemas │ `{edge_count}` Active Relations\n"
        )

        # 2. Architecture Box Diagram
        sections.append("#### 🏗️ System Architecture Map")
        sections.append(f"```text\n{self.to_architecture_diagram()}\n```\n")

        # 3. Process Execution Flow
        sections.append("#### 🔄 Execution & Lifecycle Pipeline")
        sections.append(f"```text\n{self.to_process_map()}\n```\n")

        # 4. ER & Data Models
        sections.append("#### 📊 Core Data Models & Schema Graph")
        sections.append(f"```text\n{self.to_er_diagram()}\n```\n")

        # 5. Top Hub Modules
        in_degree: dict[str, int] = defaultdict(int)
        for e in self.edges:
            if e.relation == "imports":
                in_degree[e.target] += 1
        top_hubs = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:8]
        if top_hubs:
            sections.append("#### 🌟 Top Dependent Hub Modules (Core Architectural Backbone)")
            hub_items = [
                f"- **`{hub_id.replace('file:', '').replace('module:', '')}`** (Depended on by `{count}` modules)"
                for hub_id, count in top_hubs
            ]
            sections.append("\n".join(hub_items) + "\n")

        # 6. Interactive Visual Flowchart & Data Pipeline
        sections.append("#### 📈 Component Dependency & Data Pipeline")
        sections.append(
            f"```text\n{self.to_visual_flowchart(max_edges=25, focus_filter=focus_filter)}\n```\n"
        )

        return "\n".join(sections)

    def to_visual_flowchart(self, max_edges: int = 25, focus_filter: str | None = None) -> str:
        """Render a terminal-native, visual flowchart with ASCII/Unicode boxes, arrows, and data paths."""
        w = 78
        lines = [
            "╔" + "═" * (w - 2) + "╗",
            "║" + "COMPONENT DEPENDENCY & DATA FLOW PIPELINE".center(w - 2) + "║",
            "╚" + "═" * (w - 2) + "╝",
            "",
        ]

        filtered_edges = self.edges
        if focus_filter:
            q = focus_filter.lower()
            filtered_edges = [
                e for e in self.edges if q in e.source.lower() or q in e.target.lower()
            ]

        # Group edges by source
        flows: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for e in filtered_edges[:max_edges]:
            src = self.nodes.get(e.source)
            tgt = self.nodes.get(e.target)
            src_lbl = src.label if src else e.source.split(":")[-1]
            tgt_lbl = tgt.label if tgt else e.target.split(":")[-1]
            flows[src_lbl].append((tgt_lbl, e.relation))

        if not flows:
            lines.append("No active component dependency flows found in scope.")
            return "\n".join(lines)

        for src_name, targets in list(flows.items())[:12]:
            lines.append(f"  ┌── [ {src_name} ]")
            for i, (tgt_name, rel) in enumerate(targets[:4]):
                connector = "└──►" if i == len(targets[:4]) - 1 else "├──►"
                rel_badge = f"({rel})" if rel != "imports" else ""
                lines.append(f"  │    {connector} [ {tgt_name} ] {rel_badge}")
            if len(targets) > 4:
                lines.append(f"  │    └──► ... and {len(targets) - 4} more targets")
            lines.append("  │")

        if lines and lines[-1] == "  │":
            lines.pop()

        return "\n".join(lines)

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
        """Render a formatted ASCII structural hierarchy and data relationships with visual cues."""
        out = []
        out.append(f"Project Topology Graph: {self.root_dir.name}")
        out.append(f"Total Nodes: {len(self.nodes)} │ Dependencies & Relations: {len(self.edges)}")
        out.append("═" * 70)

        file_nodes = [n for n in self.nodes.values() if n.node_type == "file"]
        model_nodes = [n for n in self.nodes.values() if n.node_type == "data_model"]
        endpoint_nodes = [n for n in self.nodes.values() if n.node_type == "endpoint"]

        out.append(
            f"Structure: {len(file_nodes)} Source Files │ {len(model_nodes)} Data Models/Schemas │ {len(endpoint_nodes)} Endpoints"
        )
        out.append("─" * 70)

        by_dir: dict[str, list[GraphNode]] = defaultdict(list)
        for f in file_nodes:
            p = Path(f.file_path)
            parent = str(p.parent) if str(p.parent) != "." else "/"
            by_dir[parent].append(f)

        lang_badges = {
            "python": "[PY]",
            "typescript": "[TS]",
            "javascript": "[JS]",
            "rust": "[RS]",
            "go": "[GO]",
            "sql": "[SQL]",
            "yaml": "[YML]",
            "json": "[JSON]",
        }

        for d, f_list in sorted(by_dir.items()):
            out.append(f"\n📂 {d}/")
            for f in sorted(f_list, key=lambda x: x.label):
                out_edges = [e for e in self.edges if e.source == f.id and e.relation == "imports"]
                imports_desc = ""
                if out_edges:
                    imp_targets = [e.target.split(":")[-1] for e in out_edges[:3]]
                    imports_desc = f" ➔ imports ({', '.join(imp_targets)})"

                badge = lang_badges.get(f.language, "[FILE]")
                defined_syms = [
                    n
                    for n in self.nodes.values()
                    if n.file_path == f.file_path and n.node_type != "file"
                ]
                sym_badge = f" ({len(defined_syms)} syms)" if defined_syms else ""
                out.append(f"   {badge:<7} 📄 {f.label:<25}{sym_badge}{imports_desc}")

        if model_nodes:
            out.append("\n" + "═" * 70)
            out.append("📊 Core Data Models & Schemas:")
            for m in model_nodes[:15]:
                out.append(f"  • {m.label:<28} at {m.file_path}")

        return "\n".join(out)

    def to_compact_llm_context(self, max_tokens: int = 200) -> str:
        """Render a token-minimized, lean structural summary specifically designed to prevent LLM context exhaustion."""
        in_degree: dict[str, int] = defaultdict(int)
        for e in self.edges:
            if e.relation == "imports":
                in_degree[e.target] += 1

        top_hubs = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:6]
        hub_str = ", ".join(h[0].replace("file:", "").replace("module:", "") for h in top_hubs)

        models = [n.label for n in self.nodes.values() if n.node_type == "data_model"][:8]
        model_str = ", ".join(models) if models else "None"

        return (
            f"[PROJECT BLUEPRINT: {self.root_dir.name}]\n"
            f"Components: {len(self.nodes)} nodes, {len(self.edges)} relations\n"
            f"Core Hub Modules: {hub_str}\n"
            f"Data Schemas / Entities: {model_str}"
        )

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
            "data_models": list(self.data_models),
            "model_fields": {k: list(v) for k, v in self.model_fields.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectGraph:
        """Reconstruct ProjectGraph instance from serialized dictionary."""
        pg = cls(root_dir=data.get("root", "."))
        for n_data in data.get("nodes", []):
            node = GraphNode(
                id=n_data["id"],
                label=n_data["label"],
                node_type=n_data.get("node_type") or n_data.get("type", "file"),
                file_path=n_data.get("file_path", ""),
                language=n_data.get("language", ""),
                line_number=n_data.get("line_number", 0),
                metadata=n_data.get("metadata", {}),
            )
            pg.nodes[node.id] = node

        for e_data in data.get("edges", []):
            edge = GraphEdge(
                source=e_data["source"],
                target=e_data["target"],
                relation=e_data["relation"],
                weight=e_data.get("weight", 1),
                metadata=e_data.get("metadata", {}),
            )
            pg.edges.append(edge)

        pg.data_models = list(data.get("data_models", []))
        pg.model_fields = {k: list(v) for k, v in data.get("model_fields", {}).items()}
        return pg


def get_cached_project_graph(
    root_dir: str | Path | None = None,
    max_files: int = 1500,
    ttl_seconds: float = 60.0,
    force_refresh: bool = False,
) -> ProjectGraph:
    """Get a cross-session cached ProjectGraph or rebuild if modified."""
    import hashlib
    import json

    from sago.paths import get_sago_home

    target_path = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
    cache_key = str(target_path)
    now = time.time()

    # 1. Check in-memory process cache
    with _GRAPH_CACHE_LOCK:
        if not force_refresh and cache_key in _GRAPH_CACHE:
            ts, cached_graph = _GRAPH_CACHE[cache_key]
            if now - ts < ttl_seconds:
                return cached_graph

    # 2. Check persistent cross-session disk cache
    dir_hash = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
    disk_cache_dir = get_sago_home() / "cache" / "project_graphs"
    disk_cache_dir.mkdir(parents=True, exist_ok=True)
    disk_cache_file = disk_cache_dir / f"{dir_hash}.json"

    if not force_refresh and disk_cache_file.exists():
        try:
            mtime = disk_cache_file.stat().st_mtime
            if now - mtime < ttl_seconds:
                cached_data = json.loads(disk_cache_file.read_text(encoding="utf-8"))
                pg = ProjectGraph.from_dict(cached_data)
                with _GRAPH_CACHE_LOCK:
                    _GRAPH_CACHE[cache_key] = (now, pg)
                return pg
        except Exception:
            pass

    # 3. Build fresh graph and persist
    pg = ProjectGraph(root_dir=target_path)
    pg.build_graph(max_files=max_files)

    try:
        disk_cache_file.write_text(json.dumps(pg.to_dict(), indent=2), encoding="utf-8")
    except Exception:
        pass

    with _GRAPH_CACHE_LOCK:
        _GRAPH_CACHE[cache_key] = (now, pg)

    return pg
