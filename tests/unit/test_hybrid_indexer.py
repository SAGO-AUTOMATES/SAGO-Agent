"""Tests for HybridCodeIndexer and BM25 + dense vector code search."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sago.memory.hybrid_indexer import (
    HybridCodeIndexer,
    _compute_dense_vector,
    _cosine_similarity,
    _tokenize_code,
)


def test_tokenize_and_dense_vector() -> None:
    tokens = _tokenize_code("def calculate_total_balance(user_account_id: str):")
    assert "calculate" in tokens
    assert "total" in tokens
    assert "balance" in tokens
    assert "user" in tokens
    assert "account" in tokens

    vec1 = _compute_dense_vector(tokens)
    assert len(vec1) == 128
    # Test identical vector similarity is ~1.0
    sim = _cosine_similarity(vec1, vec1)
    assert 0.99 <= sim <= 1.01


def test_hybrid_code_indexer_search() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        f1 = tmp_path / "auth.py"
        f1.write_text(
            "class AuthenticationService:\n"
            "    def authenticate_jwt_token(self, token: str) -> bool:\n"
            "        return token.startswith('bearer_')\n",
            encoding="utf-8",
        )

        f2 = tmp_path / "database.py"
        f2.write_text(
            "def connect_postgres_pool(dsn: str):\n"
            "    return {'status': 'connected', 'dsn': dsn}\n",
            encoding="utf-8",
        )

        indexer = HybridCodeIndexer(root_dir=tmp_path)
        count = indexer.index_project()
        assert count >= 2

        # Search for JWT authentication
        res = indexer.search("authenticate jwt token", limit=3)
        assert len(res) > 0
        assert "auth.py" in res[0].chunk.file_path
        assert res[0].combined_score > 0.3

        # Search for database postgres
        res_db = indexer.search("postgres connection database", limit=3)
        assert len(res_db) > 0
        assert "database.py" in res_db[0].chunk.file_path
