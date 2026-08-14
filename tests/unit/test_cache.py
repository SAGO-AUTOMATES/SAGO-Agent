"""Unit tests for intelligent cache: TTL, eviction, persistence, content hash."""

import time

import pytest

from sago.cache.intelligent import Cache, CacheEntry, CacheStats, ContentHashCache

# ── CacheEntry ───────────────────────────────────────────────────────────


class TestCacheEntry:
    def test_not_expired(self):
        entry = CacheEntry(key="k", value="v", created_at=time.time(), ttl=60)
        assert not entry.is_expired()

    def test_expired(self):
        entry = CacheEntry(key="k", value="v", created_at=time.time() - 100, ttl=10)
        assert entry.is_expired()

    def test_touch(self):
        entry = CacheEntry(key="k", value="v", created_at=time.time(), ttl=60)
        assert entry.access_count == 0
        entry.touch()
        assert entry.access_count == 1
        assert entry.last_accessed > 0


# ── CacheStats ───────────────────────────────────────────────────────────


class TestCacheStats:
    def test_hit_rate(self):
        stats = CacheStats(hits=7, misses=3)
        assert stats.hit_rate == pytest.approx(70.0)

    def test_hit_rate_zero(self):
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_to_dict(self):
        stats = CacheStats(hits=10, misses=5, total_entries=3, total_size_bytes=1024)
        d = stats.to_dict()
        assert d["hits"] == 10
        assert d["total_size_kb"] == 1.0
        assert d["hit_rate_percent"] == pytest.approx(66.67, abs=0.1)


# ── Basic Cache Operations ──────────────────────────────────────────────


class TestCacheBasicOps:
    def test_set_and_get(self):
        cache = Cache(max_size=100, default_ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_miss(self):
        cache = Cache(max_size=100)
        assert cache.get("nonexistent") is None

    def test_has(self):
        cache = Cache(max_size=100, default_ttl=60)
        cache.set("k", "v")
        assert cache.has("k") is True
        assert cache.has("no") is False

    def test_delete(self):
        cache = Cache(max_size=100, default_ttl=60)
        cache.set("k", "v")
        assert cache.delete("k") is True
        assert cache.get("k") is None
        assert cache.delete("k") is False

    def test_clear(self):
        cache = Cache(max_size=100, default_ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_get_or_set_factory(self):
        cache = Cache(max_size=100, default_ttl=60)
        result = cache.get_or_set("k", lambda: "computed")
        assert result == "computed"
        assert cache.get("k") == "computed"

    def test_get_or_set_existing(self):
        cache = Cache(max_size=100, default_ttl=60)
        cache.set("k", "existing")
        result = cache.get_or_set("k", lambda: "new")
        assert result == "existing"

    def test_get_or_set_static_value(self):
        cache = Cache(max_size=100, default_ttl=60)
        result = cache.get_or_set("k", "static_val")
        assert result == "static_val"


# ── TTL Expiration ───────────────────────────────────────────────────────


class TestCacheTTL:
    def test_entry_expires(self):
        cache = Cache(max_size=100, default_ttl=0.1)
        cache.set("k", "v")
        assert cache.get("k") == "v"
        time.sleep(0.15)
        assert cache.get("k") is None

    def test_custom_ttl(self):
        cache = Cache(max_size=100, default_ttl=0.1)
        cache.set("short", "v1", ttl=0.05)
        cache.set("long", "v2", ttl=5.0)
        time.sleep(0.1)
        assert cache.get("short") is None
        assert cache.get("long") == "v2"

    def test_has_respects_ttl(self):
        cache = Cache(max_size=100, default_ttl=0.05)
        cache.set("k", "v")
        time.sleep(0.1)
        assert cache.has("k") is False


# ── LRU Eviction ────────────────────────────────────────────────────────


class TestCacheEviction:
    def test_lru_eviction(self):
        cache = Cache(max_size=3, default_ttl=3600)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Adding 'd' should evict 'a' (least recently used)
        cache.set("d", 4)
        assert cache.get("a") is None
        assert cache.get("b") == 2

    def test_get_refreshes_lru(self):
        cache = Cache(max_size=3, default_ttl=3600)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Access 'a' to make it most recently used
        cache.get("a")
        # Adding 'd' should now evict 'b'
        cache.set("d", 4)
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_eviction_stats(self):
        cache = Cache(max_size=2, default_ttl=3600)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # evicts a
        stats = cache.get_stats()
        assert stats.evictions == 1

    def test_replace_existing_no_eviction(self):
        cache = Cache(max_size=2, default_ttl=3600)
        cache.set("a", 1)
        cache.set("a", 2)  # replace, no eviction
        stats = cache.get_stats()
        assert stats.evictions == 0
        assert cache.get("a") == 2


# ── Pattern Invalidation ─────────────────────────────────────────────────


class TestCachePattern:
    def test_invalidate_pattern(self):
        cache = Cache(max_size=100, default_ttl=3600)
        cache.set("user:1", "a")
        cache.set("user:2", "b")
        cache.set("session:1", "c")
        removed = cache.invalidate_pattern("user:*")
        assert removed == 2
        assert cache.get("user:1") is None
        assert cache.get("session:1") == "c"


# ── Cleanup Expired ──────────────────────────────────────────────────────


class TestCacheCleanup:
    def test_cleanup_expired(self):
        cache = Cache(max_size=100, default_ttl=0.05)
        cache.set("a", 1)
        cache.set("b", 2)
        time.sleep(0.1)
        removed = cache.cleanup_expired()
        assert removed == 2

    def test_cleanup_partial(self):
        cache = Cache(max_size=100, default_ttl=0.1)
        cache.set("short", "v1", ttl=0.05)
        cache.set("long", "v2", ttl=5.0)
        time.sleep(0.1)
        removed = cache.cleanup_expired()
        assert removed == 1
        assert cache.get("long") == "v2"


# ── Hit/Miss Stats ───────────────────────────────────────────────────────


class TestCacheStatsTracking:
    def test_hit_miss_counting(self):
        cache = Cache(max_size=100, default_ttl=60)
        cache.set("k", "v")
        cache.get("k")   # hit
        cache.get("no")  # miss
        cache.get("no")  # miss
        stats = cache.get_stats()
        assert stats.hits == 1
        assert stats.misses == 2

    def test_total_entries(self):
        cache = Cache(max_size=100, default_ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        stats = cache.get_stats()
        assert stats.total_entries == 2

    def test_total_size(self):
        cache = Cache(max_size=100, default_ttl=60)
        cache.set("a", "hello world")
        stats = cache.get_stats()
        assert stats.total_size_bytes > 0


# ── Persistence ──────────────────────────────────────────────────────────


class TestCachePersistence:
    def test_save_and_load(self, tmp_path):
        persist_path = tmp_path / "cache.json"
        cache1 = Cache(max_size=100, default_ttl=3600, persist_path=persist_path)
        cache1.set("persist_key", "persist_val")
        cache1.save()

        cache2 = Cache(max_size=100, default_ttl=3600, persist_path=persist_path)
        assert cache2.get("persist_key") == "persist_val"

    def test_load_expired_not_restored(self, tmp_path):
        persist_path = tmp_path / "cache.json"
        cache1 = Cache(max_size=100, default_ttl=0.05, persist_path=persist_path)
        cache1.set("k", "v")
        cache1.save()
        time.sleep(0.1)
        cache2 = Cache(max_size=100, default_ttl=3600, persist_path=persist_path)
        assert cache2.get("k") is None

    def test_save_no_persist_path(self):
        cache = Cache(max_size=100, default_ttl=3600)
        cache.set("k", "v")
        cache.save()  # should not raise

    def test_load_nonexistent_file(self, tmp_path):
        cache = Cache(max_size=100, default_ttl=3600, persist_path=tmp_path / "nope.json")
        assert cache.get("any") is None


# ── ContentHashCache ────────────────────────────────────────────────────


class TestContentHashCache:
    def test_set_and_get_by_content(self):
        cache = ContentHashCache(max_size=100, default_ttl=60)
        cache.set_by_content("my prompt text", "response")
        result = cache.get_by_content("my prompt text")
        assert result == "response"

    def test_different_content_different_key(self):
        cache = ContentHashCache(max_size=100, default_ttl=60)
        cache.set_by_content("prompt A", "resp A")
        cache.set_by_content("prompt B", "resp B")
        assert cache.get_by_content("prompt A") == "resp A"
        assert cache.get_by_content("prompt B") == "resp B"

    def test_prefix(self):
        cache = ContentHashCache(max_size=100, default_ttl=60)
        cache.set_by_content("content", "val", prefix="llm")
        result = cache.get_by_content("content", prefix="llm")
        assert result == "val"

    def test_make_key_format(self):
        cache = ContentHashCache()
        key = cache._make_key("test content", prefix="pfx")
        assert key.startswith("pfx:")
        assert len(key) > 4

    def test_make_key_no_prefix(self):
        cache = ContentHashCache()
        key = cache._make_key("test content")
        assert ":" not in key
