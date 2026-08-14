"""CrewAI Orchestration Engine for Sago.

Handles agent creation, task routing, and execution.
"""

from __future__ import annotations

import logging
from typing import Any

from sago.config.loader import SagoConfig, get_config

logger = logging.getLogger("sago.orchestrator")


class SagoOrchestrator:
    """Main orchestration engine that manages agents and tasks.

    Sago is the master orchestrator that:
    1. Receives all tasks
    2. Analyzes requirements
    3. Routes to appropriate specialist agents
    4. Manages context and state
    5. Synthesizes final results
    """

    def __init__(self, config: SagoConfig | None = None) -> None:
        """Initialize the orchestrator.

        Args:
            config: Sago configuration. Loads from defaults if not provided.
        """
        self.config = config or get_config()
        self._crew = None
        self._agents: dict[str, Any] = {}
        self._tools: dict[str, Any] = {}

    def build(self) -> None:
        """Build the CrewAI crew from configuration."""
        from crewai import Agent

        # Load tool registry
        self._load_tools()

        # Create agents from config
        for agent_name in self.config.agents.enabled:
            if agent_name == "sago":
                continue  # Sago is the orchestrator, not a crew member

            agent_config = self._get_agent_config(agent_name)
            if agent_config is None:
                continue

            tools = self._resolve_tools(agent_config.get("tools", []))

            agent = Agent(
                role=agent_config["role"],
                goal=agent_config["goal"],
                backstory=agent_config["backstory"],
                tools=tools,
                verbose=self.config.settings.verbose_output,
                allow_delegation=agent_config.get("allow_delegation", False),
                max_iter=agent_config.get("max_iterations", 15),
            )
            self._agents[agent_name] = agent

        logger.info(f"Built orchestrator with {len(self._agents)} agents")

    def execute(self, task: str) -> str:
        """Execute a task using the appropriate agents.

        Args:
            task: The task description.

        Returns:
            The task result.
        """
        from crewai import Crew, Task

        if not self._agents:
            self.build()

        # Route task to appropriate agent
        agent_name = self._route_task(task)
        agent = self._agents.get(agent_name)

        if agent is None:
            return f"Error: No agent found for task: {task}"

        # Create and execute task
        crew_task = Task(
            description=task,
            agent=agent,
            expected_output="A comprehensive response addressing the task.",
        )

        crew = Crew(
            agents=[agent],
            tasks=[crew_task],
            verbose=self.config.settings.verbose_output,
        )

        result = crew.kickoff()
        return str(result)

    def _route_task(self, task: str) -> str:
        """Route a task to the most appropriate agent.

        Uses keyword matching from config to determine the best agent.
        """
        task_lower = task.lower()
        scores: dict[str, int] = {}

        for agent_name, triggers in self.config.routing.triggers.items():
            score = sum(1 for trigger in triggers if trigger.lower() in task_lower)
            if score > 0:
                scores[agent_name] = score

        if scores:
            return max(scores, key=scores.get)  # type: ignore[arg-type]

        # Default to coder for code-related tasks
        if any(word in task_lower for word in ["code", "function", "class", "file", "write"]):
            return "coder"

        return "coder"  # Default agent

    def _load_tools(self) -> None:
        """Load all available tools from the tool registry."""
        import importlib

        tool_modules = {
            "read_file": "sago.tools.file.read_file",
            "write_file": "sago.tools.file.write_file",
            "edit_file": "sago.tools.file.edit_file",
            "glob_files": "sago.tools.file.glob_files",
            "grep_content": "sago.tools.file.grep_content",
            "file_operations": "sago.tools.file.file_ops",
            "execute_shell": "sago.tools.shell.execute",
            "background_process": "sago.tools.shell.background",
            "ssh_connect": "sago.tools.ssh.ssh_connect",
            "ssh_command": "sago.tools.ssh.ssh_command",
            "ssh_transfer": "sago.tools.ssh.ssh_transfer",
            "session_manager": "sago.tools.session.session_manager",
            "clipboard": "sago.tools.session.clipboard",
            "code_analyzer": "sago.tools.coding.code_analyzer",
            "linter": "sago.tools.coding.linter",
            "formatter": "sago.tools.coding.formatter",
            "test_runner": "sago.tools.coding.test_runner",
            "debugger": "sago.tools.coding.debugger",
            "log_analyzer": "sago.tools.coding.log_analyzer",
            "http_client": "sago.tools.network.http_client",
            "dns_lookup": "sago.tools.network.dns_lookup",
            "port_scan": "sago.tools.network.port_scan",
            "network_config": "sago.tools.network.config_manager",
            "software_install": "sago.tools.admin.software_install",
            "permission_manager": "sago.tools.admin.permission_manager",
            "sudo_executor": "sago.tools.admin.sudo_executor",
            "prompt_generator": "sago.tools.admin.prompt_generator",
            "os_detector": "sago.tools.system.os_detector",
            "process_manager": "sago.tools.system.process_manager",
            "env_manager": "sago.tools.system.env_manager",
        }

        for tool_name, module_path in tool_modules.items():
            try:
                module = importlib.import_module(module_path)
                # Find the tool class (non-BaseTool subclasses)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and hasattr(attr, "name")
                        and hasattr(attr, "_run")
                        and attr_name != "BaseTool"
                    ):
                        self._tools[tool_name] = attr
                        break
            except ImportError as e:
                logger.warning(f"Could not load tool {tool_name}: {e}")

    def _resolve_tools(self, tool_names: list[str]) -> list[Any]:
        """Resolve tool names to CrewAI tool instances."""
        resolved = []
        for name in tool_names:
            tool_class = self._tools.get(name)
            if tool_class:
                try:
                    resolved.append(tool_class.to_langchain_tool())
                except Exception as e:
                    logger.warning(f"Could not convert tool {name}: {e}")
        return resolved

    def _get_agent_config(self, agent_name: str) -> dict[str, Any] | None:
        """Get agent configuration from the agents config."""
        from sago.paths import get_sago_home

        agents_yaml = get_sago_home() / "agents.yaml"

        # Load from YAML if available
        if agents_yaml.exists():
            import yaml

            with open(agents_yaml) as f:
                data = yaml.safe_load(f) or {}
                agents = data.get("agents", {})
                return agents.get(agent_name)

        # Fallback to built-in configs
        return self._get_builtin_agent_config(agent_name)

    def _get_builtin_agent_config(self, agent_name: str) -> dict[str, Any] | None:
        """Get built-in agent configuration."""
        configs = {
            "coder": {
                "role": "Senior Software Engineer",
                "goal": "Write clean, efficient, and maintainable code",
                "backstory": "A seasoned engineer with deep expertise across multiple languages and frameworks.",
                "tools": ["read_file", "write_file", "edit_file", "execute_shell"],
                "max_iterations": 15,
            },
            "debugger": {
                "role": "Senior Debug Engineer",
                "goal": "Find and fix bugs efficiently with minimal side effects",
                "backstory": "A meticulous debugger who approaches problems systematically.",
                "tools": ["read_file", "edit_file", "execute_shell", "debugger"],
                "max_iterations": 20,
            },
            "architect": {
                "role": "Solutions Architect",
                "goal": "Design robust, scalable, and maintainable architectures",
                "backstory": "An experienced architect who thinks in systems.",
                "tools": ["read_file", "glob_files", "code_analyzer"],
                "max_iterations": 10,
            },
            "devops": {
                "role": "Senior DevOps Engineer",
                "goal": "Automate and optimize infrastructure and deployment processes",
                "backstory": "A DevOps veteran who lives and breathes automation.",
                "tools": [
                    "read_file",
                    "write_file",
                    "execute_shell",
                    "ssh_connect",
                    "software_install",
                ],
                "max_iterations": 15,
            },
            "reviewer": {
                "role": "Senior Code Reviewer",
                "goal": "Ensure code quality, security, and adherence to best practices",
                "backstory": "A thorough reviewer who catches issues others miss.",
                "tools": ["read_file", "grep_content", "code_analyzer", "linter"],
                "max_iterations": 10,
            },
            "researcher": {
                "role": "Technical Researcher",
                "goal": "Provide accurate, comprehensive research and analysis",
                "backstory": "A curious researcher who digs deep into topics.",
                "tools": ["read_file", "http_client", "execute_shell"],
                "max_iterations": 10,
            },
            "planner": {
                "role": "Technical Planner",
                "goal": "Create clear, actionable plans for complex tasks",
                "backstory": "A strategic planner who sees the big picture.",
                "tools": ["read_file", "glob_files", "code_analyzer"],
                "max_iterations": 10,
            },
        }
        return configs.get(agent_name)
