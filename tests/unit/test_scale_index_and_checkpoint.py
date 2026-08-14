"""Tests for 10,000+ File FTS5 Symbol Index and Checkpoint Rollback System."""

from pathlib import Path

from sago.engine.checkpoint import CheckpointManager
from sago.memory.symbol_index import PersistentSymbolIndex
from sago.tools.coding.search_symbol_tool import SearchSymbolsTool
from sago.tools.system.checkpoint_tool import CheckpointTool


def test_persistent_symbol_index_crud(tmp_path: Path):
    # Create sample python files
    f1 = tmp_path / "module_a.py"
    f1.write_text(
        "class PaymentProcessor:\n    def charge(self, amount: float):\n        '''Process transaction.'''\n        pass\n"
    )

    f2 = tmp_path / "module_b.py"
    f2.write_text(
        "def refund_payment(txn_id: str):\n    '''Refund specific payment.'''\n    return True\n"
    )

    db_path = tmp_path / "test_symbols.db"
    idx = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)

    stats = idx.update_index()
    assert stats["scanned"] >= 2
    assert stats["indexed"] >= 2

    # Query with FTS5
    results = idx.search_symbols("PaymentProcessor")
    assert len(results) >= 1
    assert results[0]["name"] == "PaymentProcessor"
    assert results[0]["type"] == "class"

    # Search for refund
    results_refund = idx.search_symbols("refund_payment")
    assert len(results_refund) >= 1
    assert results_refund[0]["name"] == "refund_payment"

    # Ranked outline
    outline = idx.get_ranked_repo_map(query="PaymentProcessor")
    assert "PaymentProcessor" in outline


def test_search_symbols_tool(tmp_path: Path):
    f = tmp_path / "auth.py"
    f.write_text("class Authenticator:\n    def verify_token(self, token: str):\n        pass\n")

    db_path = tmp_path / "test_syms.db"
    idx = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
    idx.update_index()

    tool = SearchSymbolsTool()
    # Tool instantiation check
    assert tool.name == "search_symbols"


def test_checkpoint_manager_and_rollback(tmp_path: Path):
    mgr = CheckpointManager(workspace_root=tmp_path)

    doc = tmp_path / "config.json"
    doc.write_text('{"version": "1.0", "env": "prod"}')

    meta = mgr.create_checkpoint(description="Pre-upgrade state", files=[doc])
    assert meta.checkpoint_id.startswith("chk_")

    # Modify file
    doc.write_text('{"version": "2.0", "env": "broken"}')
    assert "broken" in doc.read_text()

    # List
    chks = mgr.list_checkpoints()
    assert len(chks) == 1
    assert chks[0].checkpoint_id == meta.checkpoint_id

    # Restore
    res = mgr.restore_checkpoint(meta.checkpoint_id)
    assert res["success"] is True
    assert doc.read_text() == '{"version": "1.0", "env": "prod"}'


def test_checkpoint_tool(tmp_path: Path):
    tool = CheckpointTool()
    assert tool.name == "checkpoint_ops"
    res = tool.run(action="list")
    assert "checkpoints" in res.lower()
