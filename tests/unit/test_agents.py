"""Unit tests for agent registry."""

import pytest

from sago.agents.registry import (
    get_agent,
    get_agents_by_skill,
    list_agents,
    reload_agents,
)


@pytest.fixture
def agents():
    """List all agents."""
    return list_agents()


class TestAgentRegistry:
    def test_agents_loaded(self, agents):
        assert len(agents) >= 300

    def test_agent_structure(self, agents):
        for agent in agents:
            assert "name" in agent
            assert "role" in agent
            assert "description" in agent
            assert "skills" in agent

    def test_agent_names_unique(self, agents):
        names = [a["name"] for a in agents]
        assert len(names) == len(set(names))

    def test_get_agent(self):
        agent = get_agent("reviewer")
        assert agent is not None
        assert agent.name == "reviewer"

    def test_get_agent_not_found(self):
        agent = get_agent("nonexistent-agent-xyz")
        assert agent is None

    def test_get_agents_by_skill(self):
        agents = get_agents_by_skill("python")
        assert len(agents) > 0

    def test_get_agents_by_skill_not_found(self):
        agents = get_agents_by_skill("xyznonexistent")
        assert len(agents) == 0

    def test_reload_agents(self):
        reload_agents()
        agents = list_agents()
        assert len(agents) >= 300


class TestAgentProfiles:
    def test_architect_exists(self):
        agent = get_agent("architect")
        assert agent is not None
        assert "architecture" in agent.role.lower() or "architect" in agent.role.lower()

    def test_security_engineer_exists(self):
        agent = get_agent("security-engineer")
        assert agent is not None


class TestResolveSpecialistAgent:
    def test_resolve_by_technology_keywords(self):
        from sago.agents.registry import resolve_specialist_agent

        # Next.js
        assert (
            resolve_specialist_agent("Build a modern dashboard using Next.js 15 app router")
            == "nextjs-engineer"
        )

        # Java / Spring Boot
        assert (
            resolve_specialist_agent("Create a Spring Boot REST API with Hibernate")
            == "spring-boot-engineer"
        )

        # Azure
        assert (
            resolve_specialist_agent("Deploy AKS cluster and Azure Functions with Bicep")
            == "azure-engineer"
        )

        # Rust
        assert (
            resolve_specialist_agent("Implement async worker using Rust tokio and axum")
            == "rust-engineer"
        )

        # Go
        assert resolve_specialist_agent("Build microservice with Golang and gin") == "go-engineer"

        # Dotnet
        assert resolve_specialist_agent("Build ASP.NET Core web API in C#") == "dotnet-engineer"

    def test_resolve_by_file_extensions(self):
        from sago.agents.registry import resolve_specialist_agent

        assert resolve_specialist_agent("fix bug in app/page.tsx") == "nextjs-engineer"
        assert resolve_specialist_agent("refactor UserService.java") == "java-engineer"
        assert resolve_specialist_agent("optimize main.rs") == "rust-engineer"
        assert resolve_specialist_agent("update infra.tf") == "terraform-engineer"

    def test_resolve_by_workspace_context(self, tmp_path):
        from sago.agents.registry import resolve_specialist_agent

        # Workspace with package.json containing Next.js
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"next": "15.0.0", "react": "19.0.0"}}'
        )
        assert (
            resolve_specialist_agent("add a new user profile component", cwd=str(tmp_path))
            == "nextjs-engineer"
        )

        # Workspace with pom.xml
        tmp_java = tmp_path / "java_project"
        tmp_java.mkdir()
        (tmp_java / "pom.xml").write_text("<project></project>")
        assert (
            resolve_specialist_agent("add authentication filter", cwd=str(tmp_java))
            == "spring-boot-engineer"
        )

    def test_resolve_chat_fallback(self):
        from sago.agents.registry import resolve_specialist_agent

        assert resolve_specialist_agent("hello, how are you today?") == "general-assistant"

    def test_agents_have_roles(self, agents):
        for agent in agents:
            assert len(agent["role"]) > 0

    def test_agents_have_descriptions(self, agents):
        for agent in agents:
            assert len(agent["description"]) > 0

    def test_agents_have_skills(self, agents):
        for agent in agents:
            assert isinstance(agent["skills"], list)
