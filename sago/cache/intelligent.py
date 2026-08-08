"""Intelligent Cache System

Provides caching with hit/miss tracking, TTL, LRU eviction,
and content-based deduplication for LLM responses.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    """A single cache entry."""

    key: str
    value: Any
    created_at: float
    ttl: float  # Time to live in seconds
    access_count: int = 0
    last_accessed: float = 0.0
    size_bytes: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl

    def touch(self) -> None:
        """Update access count and time."""
        self.access_count += 1
        self.last_accessed = time.time()


@dataclass
class CacheStats:
    """Cache statistics."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_entries: int = 0
    total_size_bytes: int = 0
    avg_access_time_ms: float = 0.0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate percentage."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "total_entries": self.total_entries,
            "total_size_bytes": self.total_size_bytes,
            "total_size_kb": round(self.total_size_bytes / 1024, 2),
            "hit_rate_percent": round(self.hit_rate, 2),
            "avg_access_time_ms": round(self.avg_access_time_ms, 2),
        }


class Cache:
    """Intelligent cache with LRU eviction and TTL support."""

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float = 3600.0,  # 1 hour
        persist_path: Path | None = None,
    ) -> None:
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.persist_path = persist_path
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = CacheStats()
        self._access_times: list[float] = []

        # Load persisted cache if exists
        if persist_path and persist_path.exists():
            self._load()

    def get(self, key: str) -> Any | None:
        """Get value from cache."""
        start = time.time()

        entry = self._entries.get(key)
        if entry is None:
            self._stats.misses += 1
            self._record_access_time(start)
            return None

        if entry.is_expired():
            self._remove(key)
            self._stats.misses += 1
            self._record_access_time(start)
            return None

        # Move to end (most recently used)
        self._entries.move_to_end(key)
        entry.touch()
        self._stats.hits += 1
        self._record_access_time(start)

        return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Set value in cache."""
        # Remove existing entry if present
        if key in self._entries:
            self._remove(key)

        # Evict if at capacity
        while len(self._entries) >= self.max_size:
            self._evict()

        # Calculate size
        try:
            size_bytes = len(json.dumps(value, default=str).encode())
        except Exception:
            size_bytes = 0

        entry = CacheEntry(
            key=key,
            value=value,
            created_at=time.time(),
            ttl=ttl or self.default_ttl,
            size_bytes=size_bytes,
            metadata=metadata or {},
        )

        self._entries[key] = entry
        self._stats.total_entries = len(self._entries)
        self._stats.total_size_bytes += size_bytes

    def delete(self, key: str) -> bool:
        """Delete entry from cache."""
        if key in self._entries:
            self._remove(key)
            return True
        return False

    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        entry = self._entries.get(key)
        if entry is None:
            return False
        if entry.is_expired():
            self._remove(key)
            return False
        return True

    def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()
        self._stats = CacheStats()

    def get_or_set(
        self,
        key: str,
        factory: Any,
        ttl: float | None = None,
    ) -> Any:
        """Get from cache or compute and store."""
        value = self.get(key)
        if value is not None:
            return value

        # Compute value
        if callable(factory):
            value = factory()
        else:
            value = factory

        self.set(key, value, ttl=ttl)
        return value

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate entries matching a pattern."""
        import fnmatch
        keys_to_remove = [
            key for key in self._entries
            if fnmatch.fnmatch(key, pattern)
        ]
        for key in keys_to_remove:
            self._remove(key)
        return len(keys_to_remove)

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        self._stats.total_entries = len(self._entries)
        self._stats.total_size_bytes = sum(
            e.size_bytes for e in self._entries.values()
        )
        return self._stats

    def get_stats_dict(self) -> dict[str, Any]:
        """Get stats as dictionary."""
        return self.get_stats().to_dict()

    def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        expired_keys = [
            key for key, entry in self._entries.items()
            if entry.is_expired()
        ]
        for key in expired_keys:
            self._remove(key)
        return len(expired_keys)

    def _evict(self) -> None:
        """Evict least recently used entry."""
        if self._entries:
            key, _ = self._entries.popitem(last=False)
            self._stats.evictions += 1
            self._stats.total_entries = len(self._entries)

    def _remove(self, key: str) -> None:
        """Remove entry and update stats."""
        entry = self._entries.pop(key, None)
        if entry:
            self._stats.total_size_bytes -= entry.size_bytes
            self._stats.total_entries = len(self._entries)

    def _record_access_time(self, start: float) -> None:
        """Record access time for average calculation."""
        elapsed_ms = (time.time() - start) * 1000
        self._access_times.append(elapsed_ms)
        if len(self._access_times) > 1000:
            self._access_times = self._access_times[-500:]
        self._stats.avg_access_time_ms = (
            sum(self._access_times) / len(self._access_times)
        )

    def _load(self) -> None:
        """Load cache from disk."""
        try:
            if self.persist_path and self.persist_path.exists():
                data = json.loads(self.persist_path.read_text())
                for key, entry_data in data.get("entries", {}).items():
                    entry = CacheEntry(**entry_data)
                    if not entry.is_expired():
                        self._entries[key] = entry
                self._stats.hits = data.get("stats", {}).get("hits", 0)
                self._stats.misses = data.get("stats", {}).get("misses", 0)
        except Exception:
            pass

    def save(self) -> None:
        """Persist cache to disk."""
        if not self.persist_path:
            return

        data = {
            "entries": {
                key: {
                    "key": e.key,
                    "value": e.value,
                    "created_at": e.created_at,
                    "ttl": e.ttl,
                    "access_count": e.access_count,
                    "last_accessed": e.last_accessed,
                    "size_bytes": e.size_bytes,
                    "metadata": e.metadata,
                }
                for key, e in self._entries.items()
            },
            "stats": {
                "hits": self._stats.hits,
                "misses": self._stats.misses,
            },
        }

        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self.persist_path.write_text(json.dumps(data, default=str))


class ContentHashCache(Cache):
    """Cache that uses content hashing for deduplication."""

    def _make_key(self, content: str, prefix: str = "") -> str:
        """Create a content-based cache key."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"{prefix}:{content_hash}" if prefix else content_hash

    def get_by_content(self, content: str, prefix: str = "") -> Any | None:
        """Get by content hash."""
        key = self._make_key(content, prefix)
        return self.get(key)

    def set_by_content(
        self,
        content: str,
        value: Any,
        prefix: str = "",
        ttl: float | None = None,
    ) -> None:
        """Set by content hash."""
        key = self._make_key(content, prefix)
        self.set(key, value, ttl=ttl, metadata={"content_prefix": prefix})


# Global cache instance
_global_cache: Cache | None = None


def get_cache(
    max_size: int = 1000,
    default_ttl: float = 3600.0,
    persist: bool = True,
) -> Cache:
    """Get or create the global cache instance."""
    global _global_cache
    if _global_cache is None:
        from sago.paths import get_sago_home
        persist_path = get_sago_home() / "cache.json" if persist else None
        _global_cache = Cache(
            max_size=max_size,
            default_ttl=default_ttl,
            persist_path=persist_path,
        )
    return _global_cache
