"""User Profiles and Workspaces

Manages user profiles, preferences, and project workspaces
for persistent context across sessions.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class UserPreferences:
    """User preference settings."""

    default_effort: str = "medium"
    show_thinking: bool = False
    streaming: bool = True
    theme: str = "dark"
    auto_save: bool = True
    context_window: int = 4000
    summarization_threshold: int = 500  # words
    preferred_agents: list[str] = field(default_factory=list)
    blocked_agents: list[str] = field(default_factory=list)
    preferred_tools: list[str] = field(default_factory=list)
    language: str = "en"

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_effort": self.default_effort,
            "show_thinking": self.show_thinking,
            "streaming": self.streaming,
            "theme": self.theme,
            "auto_save": self.auto_save,
            "context_window": self.context_window,
            "summarization_threshold": self.summarization_threshold,
            "preferred_agents": self.preferred_agents,
            "blocked_agents": self.blocked_agents,
            "preferred_tools": self.preferred_tools,
            "language": self.language,
        }


@dataclass
class UserProfile:
    """User profile with preferences and history."""

    id: str
    name: str
    email: str | None = None
    preferences: UserPreferences = field(default_factory=UserPreferences)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    total_sessions: int = 0
    total_tokens: int = 0
    favorite_agents: dict[str, int] = field(default_factory=dict)
    recent_projects: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "preferences": self.preferences.to_dict(),
            "created_at": self.created_at,
            "last_active": self.last_active,
            "total_sessions": self.total_sessions,
            "total_tokens": self.total_tokens,
            "favorite_agents": self.favorite_agents,
            "recent_projects": self.recent_projects,
        }


@dataclass
class ProjectContext:
    """Project-specific context and memory."""

    project_path: str
    name: str
    description: str = ""
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    session_count: int = 0
    last_session: float = 0.0
    summaries: list[dict[str, Any]] = field(default_factory=list)
    key_decisions: list[str] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    custom_agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "name": self.name,
            "description": self.description,
            "languages": self.languages,
            "frameworks": self.frameworks,
            "session_count": self.session_count,
            "last_session": self.last_session,
            "summaries": self.summaries[-10:],  # Keep last 10
            "key_decisions": self.key_decisions,
            "known_issues": self.known_issues,
            "custom_agents": self.custom_agents,
        }


@dataclass
class SessionSummary:
    """Summary of a completed session."""

    session_id: str
    project_path: str
    user_id: str | None
    started_at: float
    completed_at: float
    message_count: int
    tokens_used: int
    agents_used: list[str]
    tasks_completed: list[str]
    key_topics: list[str]
    summary: str
    decisions: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_path": self.project_path,
            "user_id": self.user_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "message_count": self.message_count,
            "tokens_used": self.tokens_used,
            "agents_used": self.agents_used,
            "tasks_completed": self.tasks_completed,
            "key_topics": self.key_topics,
            "summary": self.summary,
            "decisions": self.decisions,
            "action_items": self.action_items,
        }


class UserProfileManager:
    """Manages user profiles and workspaces."""

    def __init__(self, persist_dir: Path | None = None) -> None:
        self.persist_dir = persist_dir
        self._profiles: dict[str, UserProfile] = {}
        self._projects: dict[str, ProjectContext] = {}
        self._summaries: list[SessionSummary] = []

        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def create_profile(
        self,
        name: str,
        email: str | None = None,
        preferences: UserPreferences | None = None,
    ) -> UserProfile:
        """Create a new user profile."""
        profile = UserProfile(
            id=str(uuid.uuid4()),
            name=name,
            email=email,
            preferences=preferences or UserPreferences(),
        )
        self._profiles[profile.id] = profile
        self._save()
        return profile

    def get_profile(self, profile_id: str) -> UserProfile | None:
        """Get a user profile by ID."""
        return self._profiles.get(profile_id)

    def get_or_create_profile(
        self,
        name: str,
        email: str | None = None,
    ) -> UserProfile:
        """Get existing profile or create new one."""
        # Try to find by name
        for profile in self._profiles.values():
            if profile.name.lower() == name.lower():
                profile.last_active = time.time()
                self._save()
                return profile

        return self.create_profile(name, email)

    def update_profile(
        self,
        profile_id: str,
        **kwargs: Any,
    ) -> bool:
        """Update a user profile."""
        profile = self._profiles.get(profile_id)
        if not profile:
            return False

        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        profile.last_active = time.time()
        self._save()
        return True

    def record_session(
        self,
        profile_id: str,
        project_path: str,
        tokens_used: int = 0,
        agent: str | None = None,
    ) -> None:
        """Record a session for a user."""
        profile = self._profiles.get(profile_id)
        if not profile:
            return

        profile.total_sessions += 1
        profile.total_tokens += tokens_used
        profile.last_active = time.time()

        if agent:
            profile.favorite_agents[agent] = profile.favorite_agents.get(agent, 0) + 1

        if project_path not in profile.recent_projects:
            profile.recent_projects.insert(0, project_path)
            profile.recent_projects = profile.recent_projects[:10]

        self._save()

    def create_project(
        self,
        project_path: str,
        name: str | None = None,
        description: str = "",
    ) -> ProjectContext:
        """Create or get a project context."""
        if project_path in self._projects:
            return self._projects[project_path]

        project = ProjectContext(
            project_path=project_path,
            name=name or Path(project_path).name,
            description=description,
        )
        self._projects[project_path] = project
        self._save()
        return project

    def get_project(self, project_path: str) -> ProjectContext | None:
        """Get a project context."""
        return self._projects.get(project_path)

    def add_project_summary(
        self,
        project_path: str,
        summary: SessionSummary,
    ) -> None:
        """Add a session summary to a project."""
        project = self._projects.get(project_path)
        if project:
            project.summaries.append(summary.to_dict())
            project.session_count += 1
            project.last_session = time.time()
            self._save()

    def add_project_decision(self, project_path: str, decision: str) -> None:
        """Add a key decision to a project."""
        project = self._projects.get(project_path)
        if project:
            project.key_decisions.append(decision)
            self._save()

    def add_known_issue(self, project_path: str, issue: str) -> None:
        """Add a known issue to a project."""
        project = self._projects.get(project_path)
        if project:
            project.known_issues.append(issue)
            self._save()

    def get_project_context(self, project_path: str, max_tokens: int = 2000) -> str:
        """Get project context as a string for prompts."""
        project = self._projects.get(project_path)
        if not project:
            return ""

        parts = [f"Project: {project.name}"]

        if project.languages:
            parts.append(f"Languages: {', '.join(project.languages)}")
        if project.frameworks:
            parts.append(f"Frameworks: {', '.join(project.frameworks)}")

        if project.summaries:
            recent = project.summaries[-3:]
            parts.append("\nRecent session summaries:")
            for s in recent:
                parts.append(f"  - {s.get('summary', '')[:200]}")

        if project.key_decisions:
            parts.append("\nKey decisions:")
            for d in project.key_decisions[-5:]:
                parts.append(f"  - {d}")

        if project.known_issues:
            parts.append("\nKnown issues:")
            for i in project.known_issues[-5:]:
                parts.append(f"  - {i}")

        context = "\n".join(parts)

        # Truncate if too long
        if len(context) // 4 > max_tokens:
            context = context[: max_tokens * 4]

        return context

    def create_session_summary(
        self,
        session_id: str,
        project_path: str,
        messages: list[dict[str, Any]],
        user_id: str | None = None,
    ) -> SessionSummary:
        """Create a summary from session messages."""
        # Extract key information
        agents_used = set()
        tasks_completed = []
        key_topics = set()

        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("agent_name"):
                agents_used.add(msg["agent_name"])

            content = msg.get("content", "").lower()
            if "completed" in content or "finished" in content:
                tasks_completed.append(msg.get("content", "")[:100])

            # Extract topics (simple keyword extraction)
            words = content.split()
            for word in words:
                if len(word) > 5 and word.isalpha():
                    key_topics.add(word)

        # Create summary
        summary = SessionSummary(
            session_id=session_id,
            project_path=project_path,
            user_id=user_id,
            started_at=messages[0].get("timestamp", time.time()) if messages else time.time(),
            completed_at=time.time(),
            message_count=len(messages),
            tokens_used=sum(m.get("tokens", 0) for m in messages),
            agents_used=list(agents_used),
            tasks_completed=tasks_completed[:5],
            key_topics=list(key_topics)[:10],
            summary=f"Session with {len(messages)} messages using {len(agents_used)} agents",
        )

        self._summaries.append(summary)
        self.add_project_summary(project_path, summary)
        self._save()

        return summary

    def get_user_stats(self, profile_id: str) -> dict[str, Any]:
        """Get user statistics."""
        profile = self._profiles.get(profile_id)
        if not profile:
            return {}

        return {
            "total_sessions": profile.total_sessions,
            "total_tokens": profile.total_tokens,
            "favorite_agents": profile.favorite_agents,
            "recent_projects": profile.recent_projects,
            "member_since": profile.created_at,
            "last_active": profile.last_active,
        }

    def _load(self) -> None:
        """Load data from disk."""
        if not self.persist_dir:
            return

        # Load profiles
        profiles_file = self.persist_dir / "profiles.json"
        if profiles_file.exists():
            try:
                data = json.loads(profiles_file.read_text())
                for profile_data in data:
                    profile = UserProfile(
                        id=profile_data["id"],
                        name=profile_data["name"],
                        email=profile_data.get("email"),
                        preferences=UserPreferences(**profile_data.get("preferences", {})),
                        created_at=profile_data.get("created_at", time.time()),
                        last_active=profile_data.get("last_active", time.time()),
                        total_sessions=profile_data.get("total_sessions", 0),
                        total_tokens=profile_data.get("total_tokens", 0),
                        favorite_agents=profile_data.get("favorite_agents", {}),
                        recent_projects=profile_data.get("recent_projects", []),
                    )
                    self._profiles[profile.id] = profile
            except Exception:
                pass

        # Load projects
        projects_file = self.persist_dir / "projects.json"
        if projects_file.exists():
            try:
                data = json.loads(projects_file.read_text())
                for path, project_data in data.items():
                    project = ProjectContext(
                        project_path=project_data["project_path"],
                        name=project_data["name"],
                        description=project_data.get("description", ""),
                        languages=project_data.get("languages", []),
                        frameworks=project_data.get("frameworks", []),
                        session_count=project_data.get("session_count", 0),
                        last_session=project_data.get("last_session", 0),
                        summaries=project_data.get("summaries", []),
                        key_decisions=project_data.get("key_decisions", []),
                        known_issues=project_data.get("known_issues", []),
                    )
                    self._projects[path] = project
            except Exception:
                pass

    def _save(self) -> None:
        """Persist data to disk."""
        if not self.persist_dir:
            return

        # Save profiles
        profiles_file = self.persist_dir / "profiles.json"
        profiles_data = [p.to_dict() for p in self._profiles.values()]
        profiles_file.write_text(json.dumps(profiles_data, default=str))

        # Save projects
        projects_file = self.persist_dir / "projects.json"
        projects_data = {path: p.to_dict() for path, p in self._projects.items()}
        projects_file.write_text(json.dumps(projects_data, default=str))


# Global instance
_global_profile_manager: UserProfileManager | None = None


def get_profile_manager(persist: bool = True) -> UserProfileManager:
    """Get or create the global profile manager."""
    global _global_profile_manager
    if _global_profile_manager is None:
        from sago.paths import get_sago_home

        persist_dir = get_sago_home() / "profiles" if persist else None
        _global_profile_manager = UserProfileManager(persist_dir=persist_dir)
    return _global_profile_manager
