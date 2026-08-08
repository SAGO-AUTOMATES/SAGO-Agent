"""Agent Spawner - Creates and manages CrewAI agent instances.

Handles agent creation, context passing, and multi-agent orchestration.
"""

from __future__ import annotations

import logging
from typing import Any

from sago.agents.registry import (
    AgentDefinition,
    AGENTS,
    get_agent,
    get_handoff_targets,
    list_agents,
)
from sago.config.loader import SagoConfig, get_config
from sago.database import MessageStore, Session, TaskStore, ToolUsageStore

logger = logging.getLogger("sago.spawner")


class AgentSpawner:
    """Spawns and manages specialist agents.

    Handles:
    - Creating CrewAI agents from definitions
    - Multi-agent handoffs and context passing
    - Session persistence
    - Tool resolution
    """

    def __init__(self, config: SagoConfig | None = None) -> None:
        self.config = config or get_config()
        self._crew_agents: dict[str, Any] = {}
        self._tools: dict[str, Any] = {}
        self._tool_classes: dict[str, type] = {}

    def spawn(
        self,
        agent_name: str,
        session: Session | None = None,
        context: dict[str, Any] | None = None,
        provider: str | None = None,
        model_override: str | None = None,
    ) -> Any | None:
        """Spawn a specialist agent as a CrewAI Agent.

        Args:
            agent_name: Name of the agent to spawn.
            session: Optional session for persistence.
            context: Optional context from previous agents.
            provider: Optional LLM provider override (e.g., 'openrouter').
            model_override: Optional model override (e.g., 'openrouter/free').

        Returns:
            CrewAI Agent instance or None if not found.
        """
        from crewai import Agent

        definition = get_agent(agent_name)
        if definition is None:
            logger.error(f"Agent not found: {agent_name}")
            return None

        # Load tools
        self._load_tool_classes()
        tools = self._resolve_tools(definition.tools)

        # Build system prompt with context
        system_prompt = definition.system_prompt
        if context:
            context_str = "\n\n".join(f"## {k}\n{v}" for k, v in context.items())
            system_prompt += f"\n\n## Context from Previous Agent\n{context_str}"

        # Create CrewAI agent
        agent = Agent(
            role=definition.role,
            goal=definition.description,
            backstory=system_prompt,
            tools=tools,
            verbose=self.config.settings.verbose_output,
            allow_delegation=len(definition.handoff_to) > 0,
            max_iter=definition.max_iterations,
            llm=self._get_llm(model_override or definition.model_preference, provider),
        )

        self._crew_agents[agent_name] = agent
        logger.info(f"Spawned agent: {agent_name} ({definition.codename})")
        return agent

    def execute_with_agent(
        self,
        agent_name: str,
        task: str,
        session_id: str | None = None,
        parent_context: dict[str, Any] | None = None,
        provider: str | None = None,
        model_override: str | None = None,
    ) -> str:
        """Execute a task using a specific agent.

        Args:
            agent_name: Agent to use.
            task: Task description.
            session_id: Optional session ID for persistence.
            parent_context: Context from parent agent.
            provider: Optional LLM provider override (e.g., 'openrouter').
            model_override: Optional model override (e.g., 'openrouter/free').

        Returns:
            Task result.
        """
        from crewai import Crew, Task

        # Create or get session
        if session_id:
            session = Session(session_id)
        else:
            session = Session()
            session.create(title=task[:100])

        # Spawn the agent
        agent = self.spawn(agent_name, session=session, context=parent_context, provider=provider, model_override=model_override)
        if agent is None:
            return f"Error: Could not spawn agent '{agent_name}'"

        # Create task
        crew_task = Task(
            description=task,
            agent=agent,
            expected_output="A comprehensive response addressing the task completely.",
        )

        # Execute
        crew = Crew(
            agents=[agent],
            tasks=[crew_task],
            verbose=self.config.settings.verbose_output,
        )

        result = crew.kickoff()

        # Store result
        msg_store = MessageStore(session.id)
        msg_store.add(
            role="assistant",
            content=str(result),
            agent_name=agent_name,
        )

        return str(result)

    def orchestrate(
        self,
        task: str,
        session_id: str | None = None,
        agent_chain: list[str] | None = None,
        max_handoffs: int = 5,
    ) -> str:
        """Orchestrate a task through multiple agents with handoffs.

        This is the multi-agent loop that:
        1. Spawns the initial agent
        2. Executes the task
        3. If the agent hands off, spawns the next agent
        4. Continues until done or max handoffs reached

        Args:
            task: Task description.
            session_id: Optional session ID.
            agent_chain: Optional predefined chain of agents.
            max_handoffs: Maximum number of agent handoffs.

        Returns:
            Final result.
        """
        # Create session
        session = Session(session_id)
        if not session_id:
            session.create(title=task[:100], agent_chain=agent_chain or [])

        # Initialize context
        context: dict[str, Any] = {
            "original_task": task,
            "completed_agents": [],
        }

        # Use predefined chain or auto-route
        if agent_chain:
            chain = agent_chain
        else:
            chain = self._plan_chain(task)

        result = ""
        for i, agent_name in enumerate(chain[:max_handoffs + 1]):
            logger.info(f"Agent {i + 1}/{len(chain)}: {agent_name}")

            # Build context from previous steps
            step_context = {
                "original_task": task,
                "completed_agents": context["completed_agents"],
            }
            if result:
                step_context["previous_result"] = str(result)

            # Execute
            step_task = task if i == 0 else f"Based on the previous work:\n\n{result}\n\nContinue with: {task}"
            result = self.execute_with_agent(
                agent_name=agent_name,
                task=step_task,
                session_id=session.id,
                parent_context=step_context,
            )

            context["completed_agents"].append(agent_name)

            # Check if we should continue (for now, just run the chain)
            if i >= len(chain) - 1:
                break

        return result

    def _plan_chain(self, task: str) -> list[str]:
        """Plan an agent chain based on the task.

        Uses keyword matching to determine which agents should handle the task.
        """
        task_lower = task.lower()
        chain: list[str] = []

        # Analyze task to determine needed agents
        keyword_map: dict[str, list[str]] = {
            "python-pro": ["python", "fastapi", "django", "flask", "pydantic", "pip"],
            "fullstack-dev": ["web", "frontend", "backend", "api", "fullstack", "react", "vue"],
            "rust-systems": ["rust", "systems", "performance", "memory", "concurrent"],
            "go-backend": ["go", "golang", "microservice", "grpc"],
            "debugger": ["debug", "error", "bug", "fix", "crash", "exception", "traceback"],
            "security-debugger": ["security", "vulnerability", "injection", "xss", "csrf", "auth"],
            "system-architect": ["architecture", "design", "scale", "pattern", "structure", "plan"],
            "data-architect": ["database", "schema", "data", "sql", "model", "er diagram"],
            "devops-engineer": ["deploy", "docker", "kubernetes", "ci/cd", "pipeline", "container"],
            "cloud-engineer": ["aws", "gcp", "azure", "cloud", "serverless", "lambda"],
            "sre-engineer": ["reliability", "monitoring", "incident", "slo", "sli", "uptime"],
            "code-reviewer": ["review", "quality", "check", "audit", "best practice"],
            "security-reviewer": ["security review", "threat model", "owasp"],
            "db-optimizer": ["optimize", "slow query", "index", "performance", "explain"],
            "api-designer": ["api design", "rest", "graphql", "openapi", "swagger", "endpoint"],
            "ml-engineer": ["machine learning", "ml", "model", "train", "neural", "ai", "llm"],
            "frontend-expert": ["ui", "ux", "css", "layout", "component", "responsive"],
            "tech-writer": ["documentation", "docs", "readme", "guide", "tutorial", "write"],
        }

        # Score each agent
        scores: dict[str, int] = {}
        for agent_name, keywords in keyword_map.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > 0:
                scores[agent_name] = score

        if scores:
            # Sort by score and take top agents
            sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            chain = [name for name, _ in sorted_agents[:3]]
        else:
            # Default chain for general tasks
            chain = ["python-pro", "code-reviewer"]

        # Ensure we start with a builder agent, not a reviewer
        if chain and chain[0] in ("code-reviewer", "security-reviewer", "db-optimizer"):
            if len(chain) > 1:
                chain = [chain[1], chain[0]]
            else:
                chain = ["python-pro"] + chain

        return chain

    def _load_tool_classes(self) -> None:
        """Load tool classes for conversion to CrewAI tools."""
        import importlib

        if self._tool_classes:
            return

        tool_modules = {
            "read_file": "sago.tools.file.read_file",
            "write_file": "sago.tools.file.write_file",
            "edit_file": "sago.tools.file.edit_file",
            "glob_files": "sago.tools.file.glob_files",
            "grep_content": "sago.tools.file.grep_content",
            "execute_shell": "sago.tools.shell.execute",
            "code_analyzer": "sago.tools.coding.code_analyzer",
            "linter": "sago.tools.coding.linter",
            "formatter": "sago.tools.coding.formatter",
            "test_runner": "sago.tools.coding.test_runner",
            "debugger": "sago.tools.coding.debugger",
            "log_analyzer": "sago.tools.coding.log_analyzer",
            "http_client": "sago.tools.network.http_client",
            "dns_lookup": "sago.tools.network.dns_lookup",
            "ssh_connect": "sago.tools.ssh.ssh_connect",
            "ssh_command": "sago.tools.ssh.ssh_command",
            "software_install": "sago.tools.admin.software_install",
            "process_manager": "sago.tools.system.process_manager",
            "network_config": "sago.tools.network.config_manager",
        }

        for tool_name, module_path in tool_modules.items():
            try:
                module = importlib.import_module(module_path)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and hasattr(attr, "name")
                        and hasattr(attr, "_run")
                        and attr_name != "BaseTool"
                    ):
                        self._tool_classes[tool_name] = attr
                        break
            except ImportError as e:
                logger.warning(f"Could not load tool {tool_name}: {e}")

    def _resolve_tools(self, tool_names: list[str]) -> list[Any]:
        """Convert tool names to CrewAI tool instances."""
        from sago.tools.crewai_wrappers import get_crewai_tool
        resolved = []
        for name in tool_names:
            crewai_tool = get_crewai_tool(name)
            if crewai_tool:
                resolved.append(crewai_tool)
            else:
                logger.warning(f"No CrewAI wrapper for tool: {name}")
        return resolved

    def _get_llm(self, model_override: str | None = None, provider_override: str | None = None) -> Any:
        """Get a CrewAI LLM for the configured provider."""
        import os
        from crewai import LLM

        provider_name = provider_override or self.config.llm_providers.default
        provider_config = self.config.llm_providers.providers.get(provider_name)

        if provider_config is None:
            return None

        # Get API key from environment
        api_key_env = provider_config.api_key_env or f"{provider_name.upper()}_API_KEY"
        api_key = os.environ.get(api_key_env, "")
        
        # For OpenRouter, also check OPENAI_API_KEY as fallback
        if not api_key and provider_name == "openrouter":
            api_key = os.environ.get("OPENAI_API_KEY", "")
        
        if not api_key:
            logger.warning(f"No API key found for {provider_name} (env: {api_key_env})")
            return None

        model = model_override or provider_config.model
        base_url = provider_config.base_url

        # For OpenRouter, use OPENAI_API_KEY and base_url
        if provider_name == "openrouter" and not base_url:
            base_url = "https://openrouter.ai/api/v1"
            if not api_key:
                api_key = os.environ.get("OPENAI_API_KEY", "")

        try:
            llm = LLM(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=provider_config.temperature,
                max_tokens=min(provider_config.max_tokens, 4096),  # Limit to avoid credit issues
            )
            return llm
        except Exception as e:
            logger.warning(f"Could not create LLM: {e}")
            return None
