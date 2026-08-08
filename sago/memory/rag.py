"""RAG Memory System

Retrieval-Augmented Generation memory for context-aware conversations.
Stores, indexes, and retrieves relevant context from past interactions.
"""

from __future__ import annotations

import json
import time
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    """A single memory entry."""

    id: str
    content: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = 0.0
    importance: float = 0.5  # 0.0 to 1.0
    tags: list[str] = field(default_factory=list)
    session_id: str | None = None
    user_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content[:1000],
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "access_count": self.access_count,
            "importance": self.importance,
            "tags": self.tags,
            "session_id": self.session_id,
            "user_id": self.user_id,
        }


@dataclass
class MemoryStats:
    """Memory system statistics."""

    total_entries: int = 0
    total_size_bytes: int = 0
    avg_importance: float = 0.0
    most_accessed: list[dict[str, Any]] = field(default_factory=list)
    recent_entries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "total_size_kb": round(self.total_size_bytes / 1024, 2),
            "avg_importance": round(self.avg_importance, 3),
            "most_accessed_count": len(self.most_accessed),
            "recent_count": len(self.recent_entries),
        }


class RAGMemory:
    """RAG-based memory system for context retrieval."""

    def __init__(self, persist_dir: Path | None = None) -> None:
        self.persist_dir = persist_dir
        self._entries: dict[str, MemoryEntry] = {}
        self._tag_index: dict[str, set[str]] = {}
        self._session_index: dict[str, set[str]] = {}
        self._user_index: dict[str, set[str]] = {}

        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def add(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        importance: float = 0.5,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> MemoryEntry:
        """Add a new memory entry."""
        entry_id = hashlib.sha256(content.encode()).hexdigest()[:16]

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            metadata=metadata or {},
            importance=importance,
            tags=tags or [],
            session_id=session_id,
            user_id=user_id,
        )

        self._entries[entry_id] = entry

        # Update indexes
        for tag in entry.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(entry_id)

        if session_id:
            if session_id not in self._session_index:
                self._session_index[session_id] = set()
            self._session_index[session_id].add(entry_id)

        if user_id:
            if user_id not in self._user_index:
                self._user_index[user_id] = set()
            self._user_index[user_id].add(entry_id)

        return entry

    def search(
        self,
        query: str,
        limit: int = 10,
        min_importance: float = 0.0,
        tags: list[str] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> list[MemoryEntry]:
        """Search memory entries by relevance."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_entries: list[tuple[float, MemoryEntry]] = []

        for entry in self._entries.values():
            # Filter by importance
            if entry.importance < min_importance:
                continue

            # Filter by session
            if session_id and entry.session_id != session_id:
                continue

            # Filter by user
            if user_id and entry.user_id != user_id:
                continue

            # Filter by tags
            if tags:
                if not any(t in entry.tags for t in tags):
                    continue

            # Score by relevance
            score = self._score_relevance(entry, query_words, query_lower)
            if score > 0:
                scored_entries.append((score, entry))

        # Sort by score
        scored_entries.sort(key=lambda x: x[0], reverse=True)

        # Update access counts
        for _, entry in scored_entries[:limit]:
            entry.access_count += 1
            entry.last_accessed = time.time()

        return [entry for _, entry in scored_entries[:limit]]

    def get(self, entry_id: str) -> MemoryEntry | None:
        """Get a specific memory entry."""
        entry = self._entries.get(entry_id)
        if entry:
            entry.access_count += 1
            entry.last_accessed = time.time()
        return entry

    def get_by_session(self, session_id: str) -> list[MemoryEntry]:
        """Get all entries for a session."""
        entry_ids = self._session_index.get(session_id, set())
        return [self._entries[eid] for eid in entry_ids if eid in self._entries]

    def get_by_user(self, user_id: str) -> list[MemoryEntry]:
        """Get all entries for a user."""
        entry_ids = self._user_index.get(user_id, set())
        return [self._entries[eid] for eid in entry_ids if eid in self._entries]

    def get_by_tag(self, tag: str) -> list[MemoryEntry]:
        """Get all entries with a specific tag."""
        entry_ids = self._tag_index.get(tag, set())
        return [self._entries[eid] for eid in entry_ids if eid in self._entries]

    def update_importance(self, entry_id: str, importance: float) -> bool:
        """Update the importance of an entry."""
        entry = self._entries.get(entry_id)
        if entry:
            entry.importance = max(0.0, min(1.0, importance))
            return True
        return False

    def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        entry = self._entries.pop(entry_id, None)
        if entry:
            # Clean indexes
            for tag in entry.tags:
                if tag in self._tag_index:
                    self._tag_index[tag].discard(entry_id)
            if entry.session_id and entry.session_id in self._session_index:
                self._session_index[entry.session_id].discard(entry_id)
            if entry.user_id and entry.user_id in self._user_index:
                self._user_index[entry.user_id].discard(entry_id)
            return True
        return False

    def get_stats(self) -> MemoryStats:
        """Get memory statistics."""
        stats = MemoryStats()
        stats.total_entries = len(self._entries)

        if self._entries:
            total_size = sum(len(e.content.encode()) for e in self._entries.values())
            stats.total_size_bytes = total_size

            importances = [e.importance for e in self._entries.values()]
            stats.avg_importance = sum(importances) / len(importances)

            # Most accessed
            sorted_by_access = sorted(
                self._entries.values(),
                key=lambda e: e.access_count,
                reverse=True,
            )
            stats.most_accessed = [e.to_dict() for e in sorted_by_access[:5]]

            # Recent
            sorted_by_time = sorted(
                self._entries.values(),
                key=lambda e: e.timestamp,
                reverse=True,
            )
            stats.recent_entries = [e.to_dict() for e in sorted_by_time[:5]]

        return stats

    def compact(self, max_entries: int = 1000) -> int:
        """Compact memory by removing low-importance entries."""
        if len(self._entries) <= max_entries:
            return 0

        # Sort by importance and access count
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: (e.importance * 0.7 + (e.access_count / 100) * 0.3),
            reverse=True,
        )

        # Keep top entries
        to_remove = sorted_entries[max_entries:]
        removed = 0
        for entry in to_remove:
            if self.delete(entry.id):
                removed += 1

        return removed

    def get_context_window(
        self,
        query: str,
        max_tokens: int = 4000,
        session_id: str | None = None,
    ) -> str:
        """Get relevant context for a query within token limit."""
        entries = self.search(query, limit=20, session_id=session_id)

        context_parts = []
        current_tokens = 0

        for entry in entries:
            # Rough token estimate (1 token ~= 4 chars)
            entry_tokens = len(entry.content) // 4
            if current_tokens + entry_tokens > max_tokens:
                break

            context_parts.append(f"[Memory {entry.timestamp:.0f}] {entry.content}")
            current_tokens += entry_tokens

        return "\n\n".join(context_parts)

    def _score_relevance(
        self,
        entry: MemoryEntry,
        query_words: set[str],
        query_lower: str,
    ) -> float:
        """Score entry relevance to query."""
        content_lower = entry.content.lower()
        content_words = set(content_lower.split())

        # Word overlap score
        overlap = query_words & content_words
        word_score = len(overlap) / len(query_words) if query_words else 0

        # Exact phrase match
        phrase_score = 1.0 if query_lower in content_lower else 0.0

        # Importance score
        importance_score = entry.importance

        # Recency score (more recent = higher)
        age_hours = (time.time() - entry.timestamp) / 3600
        recency_score = max(0, 1.0 - (age_hours / 168))  # Decay over 1 week

        # Access frequency score
        access_score = min(1.0, entry.access_count / 10)

        # Tag match score
        tag_score = 0.0
        if entry.tags:
            tag_overlap = query_words & set(entry.tags)
            tag_score = len(tag_overlap) / len(entry.tags) if entry.tags else 0

        # Combined score
        score = (
            word_score * 0.3
            + phrase_score * 0.3
            + importance_score * 0.15
            + recency_score * 0.1
            + access_score * 0.1
            + tag_score * 0.05
        )

        return score

    def _load(self) -> None:
        """Load memory from disk."""
        if not self.persist_dir:
            return

        memory_file = self.persist_dir / "rag_memory.json"
        if not memory_file.exists():
            return

        try:
            data = json.loads(memory_file.read_text())
            for entry_data in data.get("entries", []):
                entry = MemoryEntry(**entry_data)
                self._entries[entry.id] = entry

                # Rebuild indexes
                for tag in entry.tags:
                    if tag not in self._tag_index:
                        self._tag_index[tag] = set()
                    self._tag_index[tag].add(entry.id)

                if entry.session_id:
                    if entry.session_id not in self._session_index:
                        self._session_index[entry.session_id] = set()
                    self._session_index[entry.session_id].add(entry.id)

                if entry.user_id:
                    if entry.user_id not in self._user_index:
                        self._user_index[entry.user_id] = set()
                    self._user_index[entry.user_id].add(entry.id)
        except Exception:
            pass

    def save(self) -> None:
        """Persist memory to disk."""
        if not self.persist_dir:
            return

        memory_file = self.persist_dir / "rag_memory.json"
        data = {
            "entries": [e.to_dict() for e in self._entries.values()],
            "stats": self.get_stats().to_dict(),
        }

        memory_file.write_text(json.dumps(data, default=str))


# Global memory instance
_global_memory: RAGMemory | None = None


def get_memory(persist: bool = True) -> RAGMemory:
    """Get or create the global RAG memory instance."""
    global _global_memory
    if _global_memory is None:
        from sago.paths import get_sago_home
        persist_dir = get_sago_home() / "memory" if persist else None
        _global_memory = RAGMemory(persist_dir=persist_dir)
    return _global_memory
