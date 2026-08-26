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

        logger.info("Building orchestrator crew")

        # Load tool registry
        self._load_tools()

        # Create agents from config
        for agent_name in self.config.agents.enabled:
            if agent_name == "sago":
                logger.debug("Skipping 'sago' (orchestrator, not a crew member)")
                continue  # Sago is the orchestrator, not a crew member

            agent_config = self._get_agent_config(agent_name)
            if agent_config is None:
                logger.warning("No agent config found for: %s", agent_name)
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
            logger.info(
                "Built agent: name=%s, role=%s, tools=%d, max_iter=%d",
                agent_name,
                agent_config["role"],
                len(tools),
                agent_config.get("max_iterations", 15),
            )

        logger.info("Orchestrator build complete: %d agents created", len(self._agents))

    def execute(self, task: str) -> str:
        """Execute a task using the appropriate agents.

        Args:
            task: The task description.

        Returns:
            The task result.
        """
        from crewai import Crew, Task

        logger.info("Executing task: task_preview=%s", task[:80])

        if not self._agents:
            logger.debug("No agents built yet, calling build()")
            self.build()

        # Route task to appropriate agent
        agent_name = self._route_task(task)
        agent = self._agents.get(agent_name)

        if agent is None:
            logger.error(
                "No agent found for task after routing: agent=%s, task=%s", agent_name, task[:50]
            )
            return f"Error: No agent found for task: {task}"

        logger.info("Routed task to agent: %s", agent_name)

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

        logger.debug("Starting CrewAI execution for agent %s", agent_name)
        result = crew.kickoff()
        result_str = str(result)
        logger.info(
            "CrewAI execution completed: agent=%s, result_len=%d", agent_name, len(result_str)
        )

        # Run hallucination verification on CrewAI result
        try:
            from sago.engine.hallucination_verifier import get_verifier

            verifier = get_verifier()
            verification = verifier.verify(result_str, tool_history=[], task_type="create")
            if verification.has_hallucinations:
                logger.warning(
                    "Hallucinations detected in orchestrator result: issues=%s",
                    verification.all_issues[:3],
                )
                result_str = verification.cleaned_content
                if verification.confidence < 50:
                    result_str += "\n\n[Confidence Warning]\nThis response may contain unverified claims. Please verify independently."
            else:
                logger.debug(
                    "Hallucination verification passed (confidence=%d)", verification.confidence
                )
        except Exception as e:
            logger.debug("Hallucination verification skipped: %s", e)

        # Quality gate: validate result addresses the task
        quality_issues = self._validate_result(result_str, task)
        if quality_issues:
            logger.warning("Quality issues in orchestrator result: %s", quality_issues)
            result_str += "\n\n[Quality Review]\n" + "\n".join(
                f"- {issue}" for issue in quality_issues
            )

        logger.info("Task execution complete: agent=%s, result_len=%d", agent_name, len(result_str))
        return result_str

    def _validate_result(self, result: str, task: str) -> list[str]:
        """Validate that the result addresses the task. Returns list of issues."""
        issues = []
        if not result or len(result.strip()) < 50:
            issues.append(f"Result too short ({len(result or '')} chars) — likely incomplete")
        result_lower = (result or "").lower()
        failure_indicators = [
            "i cannot",
            "i'm unable",
            "i don't have",
            "not possible",
            "error:",
            "failed to",
        ]
        for fi in failure_indicators:
            if fi in result_lower:
                issues.append(f"Result contains failure indicator: '{fi}'")
        task_keywords = [w.lower() for w in task.split() if len(w) > 4]
        if task_keywords:
            matched = sum(1 for kw in task_keywords if kw in result_lower)
            coverage = matched / len(task_keywords) if task_keywords else 0
            if coverage < 0.2:
                issues.append(
                    f"Result covers only {coverage:.0%} of task keywords — may not address the request"
                )
        return issues

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
            chosen = max(scores, key=scores.get)  # type: ignore[arg-type]
            logger.info(
                "Task routed via config triggers: agent=%s, score=%d, all_scores=%s",
                chosen,
                scores[chosen],
                scores,
            )
            return chosen

        # Default to coder for code-related tasks
        if any(word in task_lower for word in ["code", "function", "class", "file", "write"]):
            logger.debug("Task routed to 'coder' (code-related keywords detected)")
            return "coder"

        logger.debug("Task routed to default agent: 'coder'")
        return "coder"  # Default agent

    def _load_tools(self) -> None:
        """Load all available tools from the dynamic tool registry."""
        try:
            from sago.tools.registry import discover_tools

            discovered = discover_tools()
            for tool_name, tool_def in discovered.items():
                self._tools[tool_name] = tool_def.tool_class
            logger.info("Loaded %d tools from registry", len(self._tools))
        except Exception as e:
            logger.warning("Error discovering tools in orchestrator: %s", e)

    def _resolve_tools(self, tool_names: list[str]) -> list[Any]:
        """Resolve tool names to CrewAI tool instances."""
        resolved = []
        missing = []
        for name in tool_names:
            tool_class = self._tools.get(name)
            if tool_class:
                try:
                    resolved.append(tool_class.to_langchain_tool())
                except Exception as e:
                    logger.warning("Could not convert tool %s: %s", name, e)
            else:
                missing.append(name)
        if missing:
            logger.debug("Missing tools: %s", missing)
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
                config = agents.get(agent_name)
                if config:
                    logger.debug("Loaded agent config from YAML: %s", agent_name)
                else:
                    logger.debug("Agent %s not found in YAML, using built-in", agent_name)
                return config

        # Fallback to built-in configs
        config = self._get_builtin_agent_config(agent_name)
        if config:
            logger.debug("Using built-in config for agent: %s", agent_name)
        return config

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
