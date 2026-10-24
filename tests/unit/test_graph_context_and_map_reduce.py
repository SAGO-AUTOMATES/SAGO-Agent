"""Unit tests for Phase 3 (Graph-guided context assembler) and Phase 4 (Map-Reduce refactoring swarm)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sago.engine.context_assembler import ContextAssembler
from sago.memory.call_graph import CallGraph, MultiLanguageCallGraphExtractor
from sago.orchestrator.delegator import (
    MapReduceRefactorCoordinator,
    RefactorCluster,
    TaskDelegator,
    WorkerRefactorResult,
)


def test_call_graph_neighborhood() -> None:
    """Test 2-hop graph neighborhood expansion."""
    cg = CallGraph()
    cg.add("dispatch", "route_request", line=10)
    cg.add("route_request", "handle_auth", line=25)
    cg.add("route_request", "execute_handler", line=30)
    cg.add("execute_handler", "query_database", line=45)
    cg.add("main", "dispatch", line=5)

    hops = cg.get_n_hop_neighborhood(["route_request"], max_hops=2)

    hop1 = hops[1]
    hop1_targets = {t for _, _, t in hop1}
    hop1_sources = {s for s, _, _ in hop1}
    assert "handle_auth" in hop1_targets
    assert "execute_handler" in hop1_targets
    assert "dispatch" in hop1_sources

    hop2 = hops[2]
    hop2_targets = {t for _, _, t in hop2}
    hop2_sources = {s for s, _, _ in hop2}
    assert "query_database" in hop2_targets
    assert "main" in hop2_sources


def test_multi_language_call_graph_extractor() -> None:
    """Test CallGraph extraction across multiple languages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Python
        py_file = root / "app.py"
        py_file.write_text("def start():\n    setup()\n\ndef setup():\n    pass\n")

        # Go
        go_file = root / "service.go"
        go_file.write_text("func Init() {\n    connectDb()\n}\n")

        extractor = MultiLanguageCallGraphExtractor()
        graph = extractor.extract_directory(root)

        assert "start" in graph.callers
        assert "setup" in graph.get_callees("start")
        assert "Init" in graph.callers
        assert "connectDb" in graph.get_callees("Init")


def test_assemble_graph_guided_context() -> None:
    """Test ContextAssembler graph-guided context generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        f = root / "core.py"
        f.write_text("def calculate():\n    compute_sub()\n\ndef compute_sub():\n    pass\n")

        ca = ContextAssembler(root)
        ctx = ca.assemble_graph_guided_context(seed_symbols=["calculate"], max_hops=2)
        assert "Seed Symbols" in ctx
        assert "calculate" in ctx
        assert "compute_sub" in ctx


def test_map_reduce_clustering() -> None:
    """Test partitioning affected files into coherent clusters."""
    coordinator = MapReduceRefactorCoordinator("/tmp/test")
    files = [
        "/tmp/test/models/user.py",
        "/tmp/test/models/order.py",
        "/tmp/test/api/user.py",
        "/tmp/test/api/order.py",
        "/tmp/test/api/payment.py",
        "/tmp/test/utils/helpers.py",
    ]

    clusters = coordinator.partition_clusters(files, max_cluster_size=2)
    assert len(clusters) >= 3
    # Models cluster should have priority
    assert clusters[0].priority >= clusters[-1].priority
    total_clustered_files = sum(len(c.files) for c in clusters)
    assert total_clustered_files == len(files)


def test_map_reduce_execution() -> None:
    """Test parallel worker dispatch and reduce aggregation."""
    coordinator = MapReduceRefactorCoordinator()
    files = [f"sago/module_{i}.py" for i in range(10)]

    def custom_worker(cluster: RefactorCluster) -> WorkerRefactorResult:
        return WorkerRefactorResult(
            cluster_id=cluster.cluster_id,
            success=True,
            modified_files=list(cluster.files),
            diff=f"Refactored {len(cluster.files)} files",
        )

    result = coordinator.execute_map_reduce_refactor(
        task="Refactor modules to new interface",
        affected_files=files,
        max_workers=2,
        worker_fn=custom_worker,
        run_verifier=False,
    )

    assert result.success is True
    assert result.total_files == 10
    assert len(result.worker_results) == len(result.clusters)
    assert "Map-Reduce refactor succeeded" in result.summary

    # Test serialization
    data = result.to_dict()
    assert data["success"] is True
    assert data["total_files"] == 10


def test_task_delegator_map_reduce_integration() -> None:
    """Test TaskDelegator Map-Reduce methods."""
    delegator = TaskDelegator()
    files = ["sago/a.py", "sago/b.py", "sago/c.py"]

    plan = delegator.create_map_reduce_plan("rename core method", files)
    assert len(plan) > 0

    result = delegator.execute_map_reduce(
        task="rename core method",
        affected_files=files,
        run_verifier=False,
    )
    assert result.success is True
    assert result.total_files == 3
