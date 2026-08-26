"""Workflow Templates

Pre-built workflow templates for common automation tasks:
- Ticket processing
- Code review automation
- Deployment pipelines
- Incident response
- Custom agent workflows
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sago.workflow.engine import (
    TriggerType,
    Workflow,
    WorkflowBuilder,
    WorkflowEngine,
)

logger = logging.getLogger("sago.workflow.templates")


class WorkflowTemplates:
    """Collection of workflow templates."""

    def __init__(self, engine: WorkflowEngine) -> None:
        self.engine = engine

    def ticket_processor(
        self,
        ticket_id: str,
        ticket_content: str,
        priority: str = "medium",
    ) -> Workflow:
        """Create a ticket processing workflow.

        Automatically:
        1. Analyzes ticket content
        2. Classifies the issue
        3. Assigns appropriate agent
        4. Generates response
        5. Updates ticket status
        """
        builder = WorkflowBuilder(self.engine)

        workflow = (
            builder.create(
                name=f"Ticket {ticket_id}",
                description=f"Process ticket: {ticket_content[:50]}...",
                trigger=TriggerType.TICKET,
            )
            .step(
                name="Analyze Ticket",
                step_type="agent_call",
                config={
                    "agent": "business-analyst",
                    "task": f"Analyze this ticket and extract key requirements:\n\n{ticket_content}",
                    "effort": "medium",
                },
            )
            .step(
                name="Classify Issue",
                step_type="agent_call",
                config={
                    "agent": "developer",
                    "task": "Classify the issue type: bug, feature, enhancement, question, or other",
                    "input_from": "previous",
                },
            )
            .step(
                name="Generate Response",
                step_type="agent_call",
                config={
                    "agent": "technical-writer",
                    "task": "Generate a professional response addressing the ticket",
                    "input_from": "previous",
                },
            )
            .build()
        )

        if workflow:
            workflow.state.set("ticket_id", ticket_id)
            workflow.state.set("priority", priority)
            workflow.state.set("ticket_content", ticket_content)

        return workflow  # type: ignore

    def code_review_pipeline(
        self,
        pr_url: str,
        repo_path: str,
    ) -> Workflow:
        """Create a code review pipeline.

        Automatically:
        1. Fetches PR details
        2. Runs code analysis
        3. Checks for security issues
        4. Reviews code quality
        5. Generates review summary
        """
        builder = WorkflowBuilder(self.engine)

        workflow = (
            builder.create(
                name=f"Review PR {pr_url}",
                description=f"Review PR: {pr_url}",
                trigger=TriggerType.MANUAL,
            )
            .step(
                name="Fetch PR Details",
                step_type="tool_call",
                config={
                    "tool": "git_ops",
                    "args": {"operation": "diff", "args": "main..HEAD"},
                },
            )
            .step(
                name="Code Analysis",
                step_type="agent_call",
                config={
                    "agent": "code-reviewer",
                    "task": "Analyze the code changes for quality, patterns, and best practices",
                    "effort": "high",
                },
            )
            .step(
                name="Security Check",
                step_type="agent_call",
                config={
                    "agent": "security-reviewer",
                    "task": "Check for security vulnerabilities in the code changes",
                    "effort": "high",
                },
            )
            .step(
                name="Generate Summary",
                step_type="agent_call",
                config={
                    "agent": "technical-writer",
                    "task": "Generate a comprehensive review summary with actionable feedback",
                },
            )
            .build()
        )

        if workflow:
            workflow.state.set("pr_url", pr_url)
            workflow.state.set("repo_path", repo_path)

        return workflow  # type: ignore

    def deployment_pipeline(
        self,
        service: str,
        environment: str,
        version: str,
    ) -> Workflow:
        """Create a deployment pipeline.

        Steps:
        1. Pre-deployment checks
        2. Build and test
        3. Deploy to staging
        4. Run integration tests
        5. Deploy to production
        6. Post-deployment verification
        """
        builder = WorkflowBuilder(self.engine)

        workflow = (
            builder.create(
                name=f"Deploy {service} v{version}",
                description=f"Deploy {service} to {environment}",
                trigger=TriggerType.MANUAL,
            )
            .step(
                name="Pre-deploy Checks",
                step_type="agent_call",
                config={
                    "agent": "devops",
                    "task": f"Run pre-deployment checks for {service}",
                    "effort": "medium",
                },
            )
            .step(
                name="Build & Test",
                step_type="tool_call",
                config={
                    "tool": "execute_shell",
                    "args": {"command": "make test"},
                },
            )
            .step(
                name="Deploy",
                step_type="agent_call",
                config={
                    "agent": "kubernetes-engineer",
                    "task": f"Deploy {service} version {version} to {environment}",
                    "effort": "high",
                },
            )
            .step(
                name="Verify Deployment",
                step_type="agent_call",
                config={
                    "agent": "site-reliability-engineer",
                    "task": f"Verify {service} deployment health and metrics",
                    "effort": "medium",
                },
            )
            .build()
        )

        if workflow:
            workflow.state.set("service", service)
            workflow.state.set("environment", environment)
            workflow.state.set("version", version)

        return workflow  # type: ignore

    def incident_response(
        self,
        incident_description: str,
        severity: str = "high",
    ) -> Workflow:
        """Create an incident response workflow.

        Steps:
        1. Triage and classify
        2. Identify affected systems
        3. Root cause analysis
        4. Implement fix
        5. Verify resolution
        6. Post-mortem
        """
        builder = WorkflowBuilder(self.engine)

        workflow = (
            builder.create(
                name="Incident Response",
                description=f"Respond to: {incident_description[:50]}...",
                trigger=TriggerType.EVENT,
            )
            .step(
                name="Triage",
                step_type="agent_call",
                config={
                    "agent": "incident-response-engineer",
                    "task": f"Triage this incident:\n{incident_description}",
                    "effort": "high",
                },
            )
            .step(
                name="Root Cause Analysis",
                step_type="agent_call",
                config={
                    "agent": "debugger",
                    "task": "Investigate root cause based on triage findings",
                    "effort": "max",
                },
            )
            .step(
                name="Implement Fix",
                step_type="agent_call",
                config={
                    "agent": "developer",
                    "task": "Implement and test fix for the identified issue",
                    "effort": "high",
                },
            )
            .step(
                name="Verify Resolution",
                step_type="agent_call",
                config={
                    "agent": "site-reliability-engineer",
                    "task": "Verify the incident is resolved and monitor metrics",
                    "effort": "medium",
                },
            )
            .step(
                name="Post-mortem",
                step_type="agent_call",
                config={
                    "agent": "technical-writer",
                    "task": "Generate post-mortem document with timeline and action items",
                },
            )
            .build()
        )

        if workflow:
            workflow.state.set("severity", severity)
            workflow.state.set("description", incident_description)

        return workflow  # type: ignore

    def custom_agent_workflow(
        self,
        name: str,
        steps: list[dict[str, Any]],
    ) -> Workflow:
        """Create a custom workflow from user-defined steps.

        Each step should have:
        - name: Step name
        - type: agent_call, tool_call, condition
        - agent/tool: Which agent or tool to use
        - task: What to do
        - effort: optional effort level
        """
        builder = WorkflowBuilder(self.engine)

        builder.create(
            name=name,
            description=f"Custom workflow: {name}",
            trigger=TriggerType.MANUAL,
        )

        for step_def in steps:
            step_type = step_def.get("type", "agent_call")
            config = {
                "agent": step_def.get("agent"),
                "tool": step_def.get("tool"),
                "task": step_def.get("task", ""),
                "effort": step_def.get("effort", "medium"),
                "args": step_def.get("args", {}),
            }

            builder.step(
                name=step_def.get("name", f"Step {len(steps)}"),
                step_type=step_type,
                config=config,
            )

        return builder.build()  # type: ignore

    def scheduled_report(
        self,
        report_type: str,
        schedule: str = "daily",
        recipients: list[str] | None = None,
    ) -> Workflow:
        """Create a scheduled report workflow.

        Steps:
        1. Gather data
        2. Analyze metrics
        3. Generate report
        4. Send to recipients
        """
        builder = WorkflowBuilder(self.engine)

        clean_report_type = re.sub(r"[^a-zA-Z0-9_-]", "", report_type)
        workflow = (
            builder.create(
                name=f"Scheduled {report_type} Report",
                description=f"Generate {schedule} {report_type} report",
                trigger=TriggerType.SCHEDULE,
            )
            .step(
                name="Gather Data",
                step_type="tool_call",
                config={
                    "tool": "database_query",
                    "args": {
                        "operation": "query",
                        "query": f"SELECT * FROM metrics WHERE type='{clean_report_type}'",
                    },
                },
            )
            .step(
                name="Analyze",
                step_type="agent_call",
                config={
                    "agent": "analytics-engineer",
                    "task": f"Analyze {report_type} metrics and identify trends",
                },
            )
            .step(
                name="Generate Report",
                step_type="agent_call",
                config={
                    "agent": "technical-writer",
                    "task": "Generate comprehensive report with insights and recommendations",
                },
            )
            .build()
        )

        if workflow:
            workflow.state.set("recipients", recipients or [])

        return workflow  # type: ignore
