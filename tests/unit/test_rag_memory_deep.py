from sago.memory.rag import MemoryEntry, MemoryStats, RAGMemory, get_memory


def test_memory_entry_and_stats_to_dict():
    entry = MemoryEntry(
        id="e1",
        content="Important fact about architecture",
        importance=0.9,
        tags=["arch", "design"],
        session_id="s1",
        user_id="u1",
    )
    d = entry.to_dict()
    assert d["id"] == "e1"
    assert d["importance"] == 0.9
    assert d["tags"] == ["arch", "design"]

    stats = MemoryStats(
        total_entries=5,
        total_size_bytes=2048,
        avg_importance=0.8,
        most_accessed=[{"id": "e1"}],
        recent_entries=[{"id": "e1"}],
    )
    sd = stats.to_dict()
    assert sd["total_entries"] == 5
    assert sd["total_size_kb"] == 2.0


def test_rag_memory_add_get_and_indexes(tmp_path):
    mem = RAGMemory(persist_dir=tmp_path)
    e1 = mem.add(
        content="Python 3.13 features",
        tags=["python", "release"],
        importance=0.8,
        session_id="sess_a",
        user_id="user_1",
    )
    assert e1.id is not None
    assert mem.get(e1.id) is not None
    assert mem.get("nonexistent") is None

    # By session
    s_entries = mem.get_by_session("sess_a")
    assert len(s_entries) == 1
    assert s_entries[0].id == e1.id

    # By user
    u_entries = mem.get_by_user("user_1")
    assert len(u_entries) == 1

    # By tag
    t_entries = mem.get_by_tag("python")
    assert len(t_entries) == 1


def test_rag_memory_update_importance_and_delete(tmp_path):
    mem = RAGMemory(persist_dir=tmp_path)
    e = mem.add(content="Temporary note", tags=["temp"], session_id="s_temp", user_id="u_temp")

    assert mem.update_importance(e.id, 0.95) is True
    assert mem.get(e.id).importance == 0.95
    assert mem.update_importance("invalid_id", 0.5) is False

    assert mem.delete(e.id) is True
    assert mem.get(e.id) is None
    assert mem.delete("invalid_id") is False
    assert len(mem.get_by_tag("temp")) == 0


def test_rag_memory_search_and_relevance(tmp_path):
    mem = RAGMemory(persist_dir=tmp_path)
    mem.add(
        "FastAPI async REST endpoints", tags=["fastapi", "web"], importance=0.9, session_id="s1"
    )
    mem.add("Django template inheritance", tags=["django", "web"], importance=0.4, session_id="s2")
    mem.add("SQLite database migrations", tags=["database"], importance=0.7, session_id="s1")

    # Search query
    res = mem.search("FastAPI endpoints", limit=5)
    assert len(res) >= 1
    assert "FastAPI" in res[0].content

    # Search with min_importance
    res_imp = mem.search("web", min_importance=0.8)
    assert len(res_imp) == 1
    assert "FastAPI" in res_imp[0].content

    # Search by session
    res_sess = mem.search("database", session_id="s1")
    assert len(res_sess) >= 1
    assert "SQLite" in res_sess[0].content

    # Search by tag
    res_tag = mem.search("endpoints", tags=["fastapi"])
    assert len(res_tag) == 1


def test_rag_memory_compact_and_stats(tmp_path):
    mem = RAGMemory(persist_dir=tmp_path)
    for i in range(10):
        mem.add(f"Content entry {i}", importance=i / 10.0)

    stats = mem.get_stats()
    assert stats.total_entries == 10
    assert stats.avg_importance > 0

    removed = mem.compact(max_entries=5)
    assert removed == 5
    assert len(mem._entries) == 5


def test_rag_memory_context_window(tmp_path):
    mem = RAGMemory(persist_dir=tmp_path)
    mem.add("Important config setting: MAX_WORKERS=16")
    mem.add("Database connection string: postgresql://localhost:5432/db")

    ctx = mem.get_context_window("database setting", max_tokens=100)
    assert "Memory" in ctx
    assert len(ctx) > 0


def test_rag_memory_persistence(tmp_path):
    mem = RAGMemory(persist_dir=tmp_path)
    mem.add("Persistent item", tags=["persist"], session_id="s_p", user_id="u_p")
    mem.save()

    # Load in new instance
    mem2 = RAGMemory(persist_dir=tmp_path)
    assert len(mem2._entries) == 1
    assert len(mem2.get_by_tag("persist")) == 1


def test_get_global_memory(tmp_path):
    from unittest.mock import patch

    with patch("sago.paths.get_sago_home", return_value=tmp_path):
        m = get_memory(persist=True)
        assert isinstance(m, RAGMemory)
