"""Unified code-intelligence facade (additive).

Wraps the existing indexers/graphs behind a single entry point so callers do
not need to know which subsystem to use. Non-breaking: existing APIs remain.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sago.memory.hybrid_indexer import get_hybrid_code_indexer
from sago.memory.project_graph import ProjectGraph
from sago.memory.symbol_graph import SymbolGraph


class CodeIntelligenceService:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir else Path.cwd()
        self.symbol_graph = SymbolGraph(root_dir=self.root_dir)
        self.hybrid_indexer = get_hybrid_code_indexer(root_dir=self.root_dir)
        self.project_graph = ProjectGraph(root_dir=self.root_dir)

    def repo_map(self, **kwargs: Any) -> str:
        return self.symbol_graph.generate_repo_map(**kwargs)

    def search(self, query: str, **kwargs: Any) -> Any:
        return self.hybrid_indexer.search(query, **kwargs)

    def project_graph(self, **kwargs: Any) -> ProjectGraph:
        self.project_graph.build_graph(**kwargs)
        return self.project_graph


def get_code_intelligence(root_dir: str | Path | None = None) -> CodeIntelligenceService:
    return CodeIntelligenceService(root_dir=root_dir)
