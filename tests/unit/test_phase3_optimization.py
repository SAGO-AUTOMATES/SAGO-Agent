"""Unit tests for Phase 3: Prompt Caching, Parallel Tools, and Persistent Markdown Memory."""

from sago.llm.caching import (
    format_anthropic_messages_with_cache,
    format_anthropic_system_with_cache,
)
from sago.memory.persistent_store import PersistentMemoryStore
from sago.tools.parallel_executor import (
    execute_tools_batch,
    is_read_only_tool,
)


class TestPromptCaching:
    """Test Anthropic prompt caching headers."""

    def test_system_prompt_caching(self):
        sys_str = "You are a helpful coding assistant."
        res = format_anthropic_system_with_cache(sys_str)
        assert isinstance(res, list)
        assert res[0]["type"] == "text"
        assert res[0]["cache_control"] == {"type": "ephemeral"}

    def test_message_caching(self):
        long_content = "x" * 200
        msgs = [
            {"role": "user", "content": "turn 1"},
            {"role": "assistant", "content": "turn 2"},
            {"role": "user", "content": long_content},
        ]
        res = format_anthropic_messages_with_cache(msgs, cache_last_turns=1)
        assert res[-1]["content"][0]["cache_control"] == {"type": "ephemeral"}


class TestParallelToolExecutor:
    """Test concurrent tool dispatch."""

    def test_read_only_detection(self):
        assert is_read_only_tool("read_file") is True
        assert is_read_only_tool("grep_content") is True
        assert is_read_only_tool("web_search") is True
        assert is_read_only_tool("write_file") is False
        assert is_read_only_tool("execute_shell") is False

    def test_parallel_batch_execution(self):
        tool_calls = [
            {"id": "1", "name": "read_file", "args": {"file": "a.txt"}},
            {"id": "2", "name": "read_file", "args": {"file": "b.txt"}},
        ]

        def dummy_executor(tc):
            return f"content of {tc['args']['file']}"

        results = execute_tools_batch(tool_calls, dummy_executor, max_workers=2)
        assert results == ["content of a.txt", "content of b.txt"]


class TestPersistentMemoryStore:
    """Test dual-store markdown persistent memory with auto-init."""

    def test_memory_auto_init_and_snapshot(self, tmp_path):
        store = PersistentMemoryStore(base_dir=tmp_path)

        # Confirm auto-creation of default starter files
        assert (tmp_path / "MEMORY.md").exists()
        assert (tmp_path / "USER.md").exists()
        assert "Initial workspace memory initialized" in store.get_frozen_memory_snapshot()
        assert "Prefer clear, maintainable" in store.get_frozen_user_snapshot()

        # Add new custom notes
        store.add_memory("Project uses Python 3.13 and Pytest")
        store.add_user_preference("Prefer concise code with type hints")

        assert "Python 3.13" in (tmp_path / "MEMORY.md").read_text()
        assert "concise code" in (tmp_path / "USER.md").read_text()

        # Reload creates new frozen snapshot containing added notes
        new_store = PersistentMemoryStore(base_dir=tmp_path)
        assert "Python 3.13" in new_store.get_frozen_memory_snapshot()
        assert "concise code" in new_store.get_frozen_user_snapshot()
