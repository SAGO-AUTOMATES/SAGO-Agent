"""Unit tests for learning store: persistence, learning, edge cases."""


import pytest

from sago.learning import LearningStore


@pytest.fixture
def store(tmp_path):
    """Create a LearningStore backed by a temporary file."""
    s = LearningStore()
    s._path = tmp_path / "learning.json"
    s._data = {
        "successful_patterns": {},
        "failed_patterns": {},
        "tool_effectiveness": {},
        "language_patterns": {},
        "error_fixes": {},
    }
    return s


# ── Record Success ───────────────────────────────────────────────────────


class TestRecordSuccess:
    def test_record_success(self, store):
        store.record_success("create", ["write_file"], "Used write_file approach")
        assert "create" in store._data["successful_patterns"]
        assert len(store._data["successful_patterns"]["create"]) == 1
        assert store._data["successful_patterns"]["create"][0]["tools"] == ["write_file"]

    def test_record_success_multiple(self, store):
        store.record_success("fix", ["execute_shell"], "Approach 1")
        store.record_success("fix", ["read_file", "edit_file"], "Approach 2")
        assert len(store._data["successful_patterns"]["fix"]) == 2

    def test_record_success_keeps_last_10(self, store):
        for i in range(15):
            store.record_success("task", [f"tool_{i}"], f"Approach {i}")
        assert len(store._data["successful_patterns"]["task"]) == 10
        # Most recent should be kept
        assert store._data["successful_patterns"]["task"][-1]["approach"] == "Approach 14"


# ── Record Failure ───────────────────────────────────────────────────────


class TestRecordFailure:
    def test_record_failure(self, store):
        store.record_failure("deploy", "ConnectionError", "during deploy")
        assert "deploy" in store._data["failed_patterns"]
        assert store._data["failed_patterns"]["deploy"][0]["error"] == "ConnectionError"

    def test_record_failure_truncates_long_error(self, store):
        long_error = "x" * 1000
        store.record_failure("task", long_error)
        assert len(store._data["failed_patterns"]["task"][0]["error"]) == 500

    def test_record_failure_keeps_last_10(self, store):
        for i in range(15):
            store.record_failure("task", f"error_{i}")
        assert len(store._data["failed_patterns"]["task"]) == 10


# ── Record Error Fix ─────────────────────────────────────────────────────


class TestRecordErrorFix:
    def test_record_error_fix(self, store):
        store.record_error_fix("ImportError", "pip install foo")
        assert len(store._data["error_fixes"]) == 1

    def test_error_fix_truncates_key(self, store):
        long_key = "x" * 200
        store.record_error_fix(long_key, "fix")
        assert len(list(store._data["error_fixes"].keys())[0]) == 100

    def test_error_fix_truncates_value(self, store):
        long_val = "y" * 1000
        store.record_error_fix("err", long_val)
        assert len(store._data["error_fixes"]["err"]["fix"]) == 500

    def test_error_fix_keeps_last_50(self, store):
        for i in range(60):
            store.record_error_fix(f"error_{i}", f"fix_{i}")
        assert len(store._data["error_fixes"]) <= 50

    def test_get_known_fixes(self, store):
        store.record_error_fix("ImportError: no module", "pip install it")
        fix = store.get_known_fixes("ImportError: no module found in code")
        assert fix == "pip install it"

    def test_get_known_fixes_none(self, store):
        fix = store.get_known_fixes("unknown error")
        assert fix is None

    def test_get_known_fixes_case_insensitive(self, store):
        store.record_error_fix("RuntimeError", "restart")
        fix = store.get_known_fixes("runtimeerror occurred")
        assert fix == "restart"


# ── Tool Effectiveness ───────────────────────────────────────────────────


class TestToolEffectiveness:
    def test_record_tool_effectiveness(self, store):
        store.record_tool_effectiveness("write_file", True)
        store.record_tool_effectiveness("write_file", True)
        store.record_tool_effectiveness("write_file", False)
        stats = store.get_tool_stats()
        assert stats["write_file"]["total_uses"] == 3
        assert stats["write_file"]["success_rate"] == pytest.approx(2 / 3, abs=0.01)

    def test_get_tool_stats_empty(self, store):
        stats = store.get_tool_stats()
        assert stats == {}

    def test_get_tool_stats_multiple_tools(self, store):
        store.record_tool_effectiveness("a", True)
        store.record_tool_effectiveness("b", False)
        stats = store.get_tool_stats()
        assert "a" in stats
        assert "b" in stats


# ── Language Patterns ────────────────────────────────────────────────────


class TestLanguagePatterns:
    def test_record_language_pattern(self, store):
        store.record_language_pattern("python", "decorator", "Uses @pytest.fixture")
        patterns = store.get_language_patterns("python")
        assert len(patterns) == 1
        assert patterns[0]["pattern"] == "decorator"

    def test_record_multiple_patterns(self, store):
        store.record_language_pattern("python", "p1", "d1")
        store.record_language_pattern("python", "p2", "d2")
        patterns = store.get_language_patterns("python")
        assert len(patterns) == 2

    def test_keeps_last_5(self, store):
        for i in range(8):
            store.record_language_pattern("python", f"p{i}", f"d{i}")
        patterns = store.get_language_patterns("python")
        assert len(patterns) == 5

    def test_get_unknown_language(self, store):
        patterns = store.get_language_patterns("nonexistent")
        assert patterns == []


# ── Successful Approaches ────────────────────────────────────────────────


class TestSuccessfulApproaches:
    def test_get_successful_approaches(self, store):
        store.record_success("create", ["write_file"], "Approach A")
        approaches = store.get_successful_approaches("create")
        assert len(approaches) == 1
        assert approaches[0]["approach"] == "Approach A"

    def test_get_successful_approaches_empty(self, store):
        approaches = store.get_successful_approaches("unknown")
        assert approaches == []


# ── Suggest Approach ─────────────────────────────────────────────────────


class TestSuggestApproach:
    def test_suggest_with_matching_tools(self, store):
        store.record_success("create", ["write_file", "execute_shell"], "Best approach")
        suggestion = store.suggest_approach("create", ["write_file", "execute_shell", "read_file"])
        assert suggestion == "Best approach"

    def test_suggest_returns_most_recent(self, store):
        store.record_success("fix", ["tool_a"], "Old approach")
        store.record_success("fix", ["tool_b"], "New approach")
        suggestion = store.suggest_approach("fix", ["tool_b"])
        assert suggestion == "New approach"

    def test_suggest_no_match(self, store):
        store.record_success("deploy", ["deploy_tool"], "Deploy approach")
        suggestion = store.suggest_approach("deploy", ["unrelated_tool"])
        assert suggestion is None

    def test_suggest_empty_successes(self, store):
        suggestion = store.suggest_approach("unknown", ["any_tool"])
        assert suggestion is None


# ── Persistence ──────────────────────────────────────────────────────────


class TestLearningPersistence:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "learning.json"

        # Save
        store1 = LearningStore()
        store1._path = path
        store1._data = {
            "successful_patterns": {},
            "failed_patterns": {},
            "tool_effectiveness": {},
            "language_patterns": {},
            "error_fixes": {},
        }
        store1.record_success("create", ["tool1"], "approach1")
        store1.record_error_fix("err1", "fix1")

        # Load
        store2 = LearningStore()
        store2._path = path
        store2._data = store2._load()
        assert "create" in store2._data["successful_patterns"]
        assert store2._data["successful_patterns"]["create"][0]["approach"] == "approach1"
        assert "err1" in store2._data["error_fixes"]

    def test_load_nonexistent_file(self, tmp_path):
        store = LearningStore()
        store._path = tmp_path / "nonexistent.json"
        data = store._load()
        assert "successful_patterns" in data
        assert "failed_patterns" in data

    def test_load_corrupted_file(self, tmp_path):
        path = tmp_path / "learning.json"
        path.write_text("not valid json {{{")
        store = LearningStore()
        store._path = path
        data = store._load()
        # Should fall back to defaults
        assert "successful_patterns" in data

    def test_save_creates_parent_dirs(self, tmp_path):
        store = LearningStore()
        store._path = tmp_path / "nested" / "dir" / "learning.json"
        store._data = {
            "successful_patterns": {},
            "failed_patterns": {},
            "tool_effectiveness": {},
            "language_patterns": {},
            "error_fixes": {},
        }
        store._save()
        assert store._path.exists()


# ── Thread Safety ────────────────────────────────────────────────────────


class TestLearningThreadSafety:
    def test_concurrent_writes(self, store):
        import threading

        def writer():
            for i in range(10):
                store.record_success("task", [f"tool_{i}"], f"approach_{i}")

        threads = [threading.Thread(target=writer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have 50 entries (5 threads x 10 records), but capped at 10
        assert len(store._data["successful_patterns"]["task"]) == 10
