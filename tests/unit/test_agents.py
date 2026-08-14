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
        assert "architect" in agent.role.lower() or "system" in agent.role.lower()

    def test_reviewer_exists(self):
        agent = get_agent("reviewer")
        assert agent is not None

    def test_agents_have_roles(self, agents):
        for agent in agents:
            assert len(agent["role"]) > 0

    def test_agents_have_descriptions(self, agents):
        for agent in agents:
            assert len(agent["description"]) > 0

    def test_agents_have_skills(self, agents):
        for agent in agents:
            assert isinstance(agent["skills"], list)
