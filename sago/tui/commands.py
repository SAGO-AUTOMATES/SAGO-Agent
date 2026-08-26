"""TUI Commands - All command handler methods."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from textual.containers import VerticalScroll  # noqa: F401
from textual.widgets import Collapsible, Static

from sago.utils.safe import log_exception

logger = logging.getLogger("sago.tui.commands")

if TYPE_CHECKING:
    from sago.tui.app import SagoApp


class CommandHandlers:
    """Mixin class providing command handlers for SagoApp."""

    def is_scrolled_to_bottom(self: SagoApp, threshold: int = 100) -> bool:  # noqa: D401
        """Check if #messages is within threshold px of bottom via VerticalScroll scroll_y + virtual_size + size.height."""
        try:
            container = self.query_one("#messages")
            scroll_y = getattr(container, "scroll_y", 0)
            virtual_size = getattr(container, "virtual_size", None)
            size = getattr(container, "size", None)
            if virtual_size is None or size is None:
                return True
            v_h = virtual_size.height if hasattr(virtual_size, "height") else 0
            s_h = size.height if hasattr(size, "height") else 0
            if v_h == 0 or s_h == 0:
                return True
            return (v_h - s_h - scroll_y) <= threshold
        except Exception:
            return True

    def _show_new_messages_badge(self: SagoApp) -> None:
        try:
            badge = self.query_one("#new-messages-badge", Static)
            badge.remove_class("hidden")
            badge.add_class("visible")
        except Exception:
            pass

    def _hide_new_messages_badge(self: SagoApp) -> None:
        try:
            badge = self.query_one("#new-messages-badge", Static)
            badge.add_class("hidden")
            badge.remove_class("visible")
        except Exception:
            pass

    def _smart_scroll_end(self: SagoApp, animate: bool = False) -> None:
        try:
            if self.is_scrolled_to_bottom():
                self.query_one("#messages").scroll_end(animate=animate)
                self._hide_new_messages_badge()
            else:
                self._show_new_messages_badge()
        except Exception as e:
            log_exception(e, "smart scroll failed in commands")
            try:
                self.query_one("#messages").scroll_end(animate=animate)
            except Exception:
                pass

    def action_scroll_end(self: SagoApp) -> None:  # type: ignore[override]
        """Handle End key: scroll to bottom and hide new-messages badge."""
        try:
            self.query_one("#messages").scroll_end(animate=False)
            self._hide_new_messages_badge()
        except Exception as e:
            log_exception(e, "Failed to scroll to end (End key)")

    def _show_help(self: SagoApp) -> None:
        from sago.tui.models import COMMANDS

        container = self.query_one("#messages")

        categories = {
            "CORE & WORKFLOW": [
                "/help",
                "/?",
                "/status",
                "/session",
                "/compact",
                "/clear",
                "/export",
                "/exit",
            ],
            "AGENT ORCHESTRATION": [
                "/agent",
                "/delegate",
                "/chain",
                "/orchestrate",
                "/plan",
                "/parallel",
                "/tasks",
                "/tools",
                "/skills",
                "/mcp",
                "/plugins",
            ],
            "CODE INTELLIGENCE & VCS": [
                "/graph",
                "/map",
                "/verify",
                "/git",
                "/diff",
                "/undo",
                "/checkpoint",
                "/search",
            ],
            "SETTINGS & RUNTIME": [
                "/model",
                "/provider",
                "/effort",
                "/cost",
                "/perms",
                "/todo",
                "/theme",
                "/buttons",
                "/dev",
                "/yolo",
            ],
        }

        lines = ["[bold cyan]COMMAND REFERENCE[/bold cyan]\n"]
        for cat, cmds in categories.items():
            lines.append(f"[bold]{cat}[/bold]")
            for cmd in cmds:
                desc = COMMANDS.get(cmd, "")
                lines.append(f"  [cyan]{cmd:<16}[/cyan] [white]{desc}[/white]")
            lines.append("")

        lines.append(
            "[dim]Shortcuts: F1 Help | F2 Traces | Ctrl+D Dashboard | Ctrl+T Tasks | Ctrl+C Cancel | @agent | #file[/dim]"
        )

        body = "\n".join(lines)
        container.mount(
            Collapsible(
                Static(body),
                title="Command Reference",
                collapsed=True,
            )
        )
        container.scroll_end()

    def _show_tools(self: SagoApp, query: str = "") -> None:
        try:
            from rich.markup import escape

            from sago.tools.registry import get_tool, list_categories, list_tools

            container = self.query_one("#messages")

            # Case 1: Specific tool detailed inspection
            if query and get_tool(query.strip()):
                t = get_tool(query.strip())
                assert t is not None
                lines = [
                    f"[bold cyan]Tool:[/] [bold yellow]{t.name}[/bold yellow]  [dim]Category: ({t.category}) | Source: {t.source}[/dim]\n",
                    f"[bold]Description:[/]\n{escape(t.description)}\n",
                    f"[dim]Module: {t.module_path}[/dim]\n",
                ]
                if t.args_schema:
                    lines.append("[bold]Parameters:[/bold]")
                    for pname, pinfo in t.args_schema.items():
                        req = "[red]REQ[/red]" if pinfo.get("required") else "[dim]opt[/dim]"
                        ptype = pinfo.get("type", "str")
                        pdesc = pinfo.get("description", "-")
                        lines.append(
                            f"  • [yellow]{pname}[/yellow] [dim]({ptype}, {req})[/dim]: {escape(pdesc)}"
                        )
                body = "\n".join(lines)
                container.mount(
                    Collapsible(
                        Static(body),
                        title=f"Tool: {t.name}",
                        collapsed=False,
                    )
                )
                container.scroll_end()
                return

            # Case 2: Categories overview
            if not query:
                categories = list_categories()
                total_tools = sum(len(v) for v in categories.values())
                lines = [
                    f"[bold]Dynamic Tool Registry ({total_tools} tools across {len(categories)} categories):[/bold]\n"
                ]
                for cat, tool_list in sorted(categories.items()):
                    sample = ", ".join(t.name for t in tool_list[:4])
                    if len(tool_list) > 4:
                        sample += f", +{len(tool_list) - 4} more"
                    lines.append(
                        f"  [bold yellow]{cat:<18}[/bold yellow] [green]({len(tool_list):>2})[/green]  [dim]{escape(sample)}[/dim]"
                    )
                lines.append(
                    "\n[dim]To view tools in a category or search: [/dim][bold cyan]/tools <category_or_query>[/bold cyan]"
                )
                lines.append(
                    "[dim]Example: [/dim][bold]/tools coding[/bold]  or  [bold]/tools read_file[/bold]"
                )
                title = f"Tool Categories ({len(categories)} categories, {total_tools} tools)"
            else:
                # Case 3: Filtered tools search
                matched = list_tools(query=query)
                lines = [f"[bold]Tools matching '{query}' ({len(matched)}):[/bold]\n"]
                for t in matched[:40]:
                    lines.append(
                        f"  [cyan]{t.name:<24}[/cyan] [yellow][{t.category}][/yellow] [dim]{escape(t.description[:60])}[/dim]"
                    )
                if len(matched) > 40:
                    lines.append(f"\n  [dim]... and {len(matched) - 40} more[/dim]")
                title = f"Tools matching '{query}' ({len(matched)})"

            body = "\n".join(lines)
            container.mount(
                Collapsible(
                    Static(body),
                    title=title,
                    collapsed=False,
                )
            )
            container.scroll_end()
        except Exception as e:
            self._add_system_message(f"Error displaying tools: {e}")

    def _show_agents(self: SagoApp, f: str = "") -> None:
        try:
            from rich.markup import escape

            from sago.agents.registry import get_agents_by_category, list_categories

            categories = list_categories()
            total_agents = sum(len(v) for v in categories.values())

            if not f:
                lines = [
                    f"[bold]Specialist Agent Categories ({total_agents} agents across {len(categories)} domains):[/bold]\n"
                ]
                for cat, agent_list in sorted(categories.items()):
                    sample = ", ".join(a.name for a in agent_list[:3])
                    if len(agent_list) > 3:
                        sample += f", +{len(agent_list) - 3} more"
                    lines.append(
                        f"  [bold yellow]{cat:<26}[/bold yellow] [green]({len(agent_list):>2})[/green]  [dim]{escape(sample)}[/dim]"
                    )
                lines.append(
                    "\n[dim]To view agents in a category, run: [/dim][bold cyan]/agents <category>[/bold cyan]"
                )
                lines.append(
                    "[dim]Example: [/dim][bold]/agents database[/bold]  or  [bold]/agents security[/bold]"
                )
                title = f"Agent Categories ({len(categories)})"
            else:
                matched = get_agents_by_category(f)
                lines = [f"[bold]Specialist Agents matching '{f}' ({len(matched)}):[/bold]\n"]
                for a in matched[:40]:
                    tools = ", ".join(a.tools[:3])
                    lines.append(
                        f"  [cyan]{a.name:<26}[/cyan] [yellow][{a.category}][/yellow] [dim]{escape(tools)}[/dim]"
                    )
                if len(matched) > 40:
                    lines.append(f"\n  [dim]... and {len(matched) - 40} more[/dim]")
                title = f"Agents matching '{f}' ({len(matched)})"

            body = "\n".join(lines)
            container = self.query_one("#messages")
            container.mount(
                Collapsible(
                    Static(body),
                    title=title,
                    collapsed=True,
                )
            )
            container.scroll_end()
        except Exception as e:
            self._add_system_message(f"Error listing agents: {e}")

    def _set_agent(self: SagoApp, name: str) -> None:
        if not name:
            self._add_system_message(f"Current: {self.current_agent}")
            return
        self.current_agent = name
        self._add_system_message(f"Agent: {name}")

    def _delegate_task(self: SagoApp, args: str) -> None:
        parts = args.split(None, 1)
        if len(parts) < 2:
            self._add_system_message("Usage: /delegate <agent> <task>")
            return
        agent_name, task = parts

        from sago.engine.prompt_enhancer import enhance_prompt

        enhancement = enhance_prompt(task=task, agent_role=agent_name)

        self._add_command_turn(
            "delegate",
            task,
            meta=f"@{agent_name}",
            tag_label="DELEGATE",
            tag_color="#bc8cff",
        )
        if enhancement.was_modified:
            self._add_prompt_enhancement_card(enhancement)

        self._process_delegation(agent_name, task)

    def _valid_agent_names(self: SagoApp) -> set[str]:
        """All valid agent names including aliases, from the registry."""
        try:
            from sago.agents.registry import AGENT_ALIASES, AGENTS

            return set(AGENTS) | set(AGENT_ALIASES)
        except Exception as e:
            logger.debug("Agent registry unavailable for chain parsing: %s", e)
            return set()

    def _looks_like_agent(self: SagoApp, word: str) -> bool:
        """Check if a word is a known agent name or alias (registry-validated)."""
        w = word.lower().strip()
        if not w:
            return False
        valid = self._valid_agent_names()
        if w in valid:
            return True
        # Short forms like "python" count only when "<word>-engineer" exists
        return f"{w}-engineer" in valid

    def _parse_chain_spec(self: SagoApp, raw: str) -> tuple[list[str], str]:
        """Parse /chain input into (ordered agent names, task).

        Supported forms:
          /chain architect -> reviewer <task>
          /chain frontend-engineer,backend-engineer <task>
          /chain <task>                        → ([], task), caller auto-routes
          /chain a1,a2                         → pure agent list, synthetic task

        Only '->' is an arrow separator; bare '>' stays part of the task text
        (e.g. "/chain write code that prints > 5 items"). Agent words are
        validated against the registry instead of the old '-' heuristic.
        """
        normalized = re.sub(r"\s*->\s*", " → ", raw).strip()
        agents: list[str] = []
        task_parts: list[str] = []

        if "→" not in normalized and "," not in normalized:
            words = normalized.split()
            idx = 0
            while idx < len(words) and self._looks_like_agent(words[idx]):
                agents.append(words[idx].lower())
                idx += 1
            task = " ".join(words[idx:])
            return agents, task

        for chunk in re.split(r"→|,", normalized):
            chunk = chunk.strip()
            if not chunk:
                continue
            words = chunk.split()
            idx = 0
            while idx < len(words) and self._looks_like_agent(words[idx]):
                agents.append(words[idx].lower())
                idx += 1
            remainder = " ".join(words[idx:])
            if remainder:
                task_parts.append(remainder)

        return agents, " ".join(task_parts)

    def _chain_agents(self: SagoApp, args: str) -> None:
        raw_args = args.strip()
        if not raw_args:
            self._add_system_message(
                "⚡ [bold cyan]Multi-Agent Chain Usage[/bold cyan]:\n"
                "  • [bold white]/chain <task>[/bold white] — Autonomous multi-agent pipeline routing\n"
                "  • [bold white]/chain architect -> python-engineer -> test-engineer <task>[/bold white]\n"
                "  • [bold white]/chain frontend-engineer,backend-engineer <task>[/bold white]"
            )
            return

        try:
            agent_names, task = self._parse_chain_spec(raw_args)
        except Exception as e:
            log_exception(e, "parse delegate chain args")
            agent_names, task = [], raw_args

        if not agent_names:
            # Pure task — auto-route a chain
            try:
                from sago.agents.router import route_for_chain

                agent_names = route_for_chain(task, max_agents=4) or ["python-engineer"]
                self._add_system_message(f"Auto-routed: {' → '.join(agent_names)}")
            except Exception:
                agent_names = ["python-engineer"]
                self._add_system_message("Using default: python-engineer")
        elif not task:
            task = f"Execute chain: {' → '.join(agent_names)}"

        self._add_command_turn(
            "chain",
            task,
            meta=f"[{' → '.join(agent_names)}]",
            tag_label="CHAIN",
            tag_color="#79c0ff",
        )
        self._process_chain([[a] for a in agent_names], task)

    def _orchestrate_task(self: SagoApp, task: str) -> None:
        if not task:
            self._add_system_message("Usage: /orchestrate <task>")
            return
        self._add_command_turn(
            "orchestrate",
            task,
            tag_label="ORCHESTRATE",
            tag_color="#3fb950",
        )
        self._process_orchestration(task)

    def _plan_or_show(self: SagoApp, args: str) -> None:
        """Unified /plan handler: orchestration plan edit/add/remove OR task plan show."""
        raw = args.strip()
        # Check if this is an orchestration plan edit command
        if raw and raw.split()[0].lower() in ("edit", "add", "remove"):
            self._plan_command(args)
        else:
            self._show_plan(args)

    def _plan_command(self: SagoApp, args: str) -> None:
        """Handle /plan edit/add/remove commands for orchestration plan modification."""
        pending = getattr(self, "pending_orchestration", None)
        if not pending or not pending.get("plan"):
            self._add_system_message("No pending orchestration plan. Run /orchestrate first.")
            return

        plan = pending["plan"]
        parts = args.strip().split(None, 2)
        if not parts:
            # Show current plan
            lines = []
            for i, step in enumerate(plan):
                lines.append(f"  {i + 1}. [{step.get('agent', '?')}] {step.get('task', '')[:80]}")
            self._add_system_message("Current plan:\n" + "\n".join(lines))
            return

        action = parts[0].lower()
        if action == "edit" and len(parts) >= 3:
            try:
                step_num = int(parts[1]) - 1
                new_task = parts[2]
                if 0 <= step_num < len(plan):
                    old_agent = plan[step_num].get("agent", "?")
                    plan[step_num]["task"] = new_task
                    self._add_system_message(
                        f"Step {step_num + 1} updated: [{old_agent}] {new_task[:60]}"
                    )
                else:
                    self._add_system_message(f"Invalid step number. Plan has {len(plan)} steps.")
            except ValueError:
                self._add_system_message("Usage: /plan edit <step_number> <new task>")

        elif action == "add" and len(parts) >= 2:
            agent_task = " ".join(parts[1:])
            if ":" in agent_task:
                agent, task_text = agent_task.split(":", 1)
                agent = agent.strip()
                task_text = task_text.strip()
            else:
                agent = "python-engineer"
                task_text = agent_task
            plan.append({"agent": agent, "task": task_text})
            self._add_system_message(f"Added step {len(plan)}: [{agent}] {task_text[:60]}")

        elif action == "remove" and len(parts) >= 2:
            try:
                step_num = int(parts[1]) - 1
                if 0 <= step_num < len(plan):
                    removed = plan.pop(step_num)
                    self._add_system_message(
                        f"Removed step {step_num + 1}: [{removed.get('agent', '?')}] {removed.get('task', '')[:60]}"
                    )
                else:
                    self._add_system_message(f"Invalid step number. Plan has {len(plan)} steps.")
            except ValueError:
                self._add_system_message("Usage: /plan remove <step_number>")
        else:
            self._add_system_message(
                "Usage: /plan [edit <step> <task> | add <agent>: <task> | remove <step>]"
            )

    def _show_status(self: SagoApp) -> None:
        try:
            from sago.agents.registry import list_agents

            n = len(list_agents())
        except Exception:
            n = 0
        from sago.tui.models import EFFORT_LEVELS

        sid = self.current_session_id[:8] if self.current_session_id else "none"
        effort = EFFORT_LEVELS.get(self.current_effort, {})
        yolo_status = "[yellow]ON[/yellow]" if self.yolo_mode else "off"
        provider = getattr(self, "current_provider", "openrouter")
        summary = getattr(self, "show_summary", False)

        lines = [
            "[bold cyan]System Status[/bold cyan]",
            f"  Agent:     [cyan]{self.current_agent}[/cyan]",
            f"  Provider:  {provider}",
            f"  Model:     [green]{self.current_model}[/green]",
            f"  Effort:    {self.current_effort} ({effort.get('desc', '')})",
            f"  YOLO:      {yolo_status}",
            f"  Summary:   {'ON' if summary else 'off'}",
            f"  Session:   [dim]{sid}[/dim]",
            f"  Agents:    {n} available",
            f"  Messages:  {len(self.messages)}",
        ]
        body = "\n".join(lines)
        container = self.query_one("#messages")
        container.mount(Collapsible(Static(body), title="System Status", collapsed=True))

    def _show_sessions(self: SagoApp) -> None:
        self._list_sessions()

    def _switch_session(self: SagoApp, sid: str) -> None:
        sid = (sid or "").strip()
        if not sid or sid.lower() in ("list", "ls"):
            self._show_sessions()
            return
        if sid.lower().startswith("switch "):
            sid = sid[7:].strip()
        if sid.lower().startswith("clean"):
            self._handle_clean_command("sessions")
            return
        if sid.lower().startswith("export "):
            self._export_session(sid[7:].strip())
            return
        if sid.lower().startswith("save"):
            self._save_session(sid[5:].strip())
            return
        try:
            from sago.database import MessageStore, Session, init_db

            init_db()
            s = Session()
            sessions = s.list_all(limit=100)
            s.close()
            for ses in sessions:
                if ses["id"].startswith(sid):
                    self._hide_welcome_screen()
                    self.current_session_id = ses["id"]
                    # CRITICAL: Reset stale _message_store so new messages go to this session
                    self._message_store = None
                    ms = MessageStore(ses["id"])
                    msgs = ms.get_history(limit=200)
                    ms.close()
                    self.messages = [
                        {
                            "role": m["role"],
                            "content": m["content"],
                            "agent_name": m.get("agent_name"),
                            "metadata": m.get("metadata", "{}"),
                            "created_at": m.get("created_at"),
                        }
                        for m in msgs
                    ]
                    # Restore session title from database
                    if ses.get("title"):
                        self.current_session_title = ses["title"]

                    # Load tool usage data for this session
                    tool_logs = []
                    try:
                        from sago.database import ToolUsageStore

                        tus = ToolUsageStore(ses["id"])
                        tool_logs = tus.get_all()
                        tus.close()
                    except Exception as e:
                        log_exception(e, "load tool usage data for session switch")

                    # Refresh the UI using ExchangeTurnCard for consistent rendering
                    self._loading_session = True
                    try:
                        import re

                        from rich.markdown import Markdown as RichMarkdown
                        from textual.widgets import Collapsible, Static

                        from sago.tui.helpers import ExchangeTurnCard
                        from sago.tui.widgets import get_agent_color

                        container = self.query_one("#messages")
                        container.remove_children()

                        # Phase 1: Mount all user cards, collect assistant responses
                        current_card = None
                        deferred_responses: list[tuple] = []
                        message_cards: list[tuple[str, object]] = []

                        for m in self.messages:
                            role = m["role"]
                            content = m["content"]
                            agent_name = m.get("agent_name") or "sago"
                            created_at = m.get("created_at", "")

                            if role == "user":
                                turn_card = ExchangeTurnCard(prompt=content, card_type="user")
                                container.mount(turn_card)
                                current_card = turn_card
                                self._active_exchange_card = turn_card
                                if created_at:
                                    message_cards.append((created_at, turn_card))

                                # Restore enhancement data if present
                                msg_metadata = {}
                                raw_meta = m.get("metadata")
                                if raw_meta:
                                    try:
                                        msg_metadata = (
                                            json.loads(raw_meta)
                                            if isinstance(raw_meta, str)
                                            else raw_meta
                                        )
                                    except (json.JSONDecodeError, TypeError):
                                        pass
                                enhancement_data = msg_metadata.get("enhancement")
                                if enhancement_data:
                                    try:
                                        from sago.engine.prompt_enhancer import (
                                            PromptEnhancementResult,
                                        )

                                        enhancement = PromptEnhancementResult(
                                            original_prompt=enhancement_data.get(
                                                "original_prompt", ""
                                            ),
                                            enhanced_prompt=enhancement_data.get(
                                                "enhanced_prompt", ""
                                            ),
                                            intent_summary=enhancement_data.get(
                                                "intent_summary", ""
                                            ),
                                            target_scope=enhancement_data.get("target_scope", []),
                                            acceptance_criteria=enhancement_data.get(
                                                "acceptance_criteria", []
                                            ),
                                            improvements=enhancement_data.get("improvements", []),
                                            was_modified=enhancement_data.get("was_modified", True),
                                        )
                                        from sago.tui.helpers import UIHelpers

                                        UIHelpers._add_prompt_enhancement_card(self, enhancement)
                                    except Exception as e:
                                        log_exception(
                                            e, "restore enhancement card on session switch"
                                        )
                            elif role == "assistant":
                                # Extract thinking blocks — per-agent, per-step (supports reload with persistence)
                                thinking_match = re.search(
                                    r"<(?:thinking|thought)>(.*?)</(?:thinking|thought)>",
                                    content,
                                    re.DOTALL,
                                )
                                display_content = content
                                thinking_blocks: list[dict] = []
                                # Check persisted thinking_blocks first (new format)
                                _meta_blocks_sw = (
                                    msg_metadata.get("thinking_blocks")
                                    if isinstance(msg_metadata, dict)
                                    else None
                                )
                                # Also handle msg.get("thinking_blocks") if stored at top level? fallback
                                if isinstance(_meta_blocks_sw, list) and _meta_blocks_sw:
                                    try:
                                        thinking_blocks = sorted(
                                            _meta_blocks_sw, key=lambda b: int(b.get("seq", 0) or 0)
                                        )
                                    except Exception:
                                        thinking_blocks = list(_meta_blocks_sw)
                                    if thinking_match:
                                        display_content = re.sub(
                                            r"<(?:thinking|thought)>.*?</(?:thinking|thought)>",
                                            "",
                                            content,
                                            flags=re.DOTALL,
                                        ).strip()
                                else:
                                    thinking_html = ""
                                    if thinking_match:
                                        thinking_content = thinking_match.group(1).strip()
                                        if thinking_content:
                                            thinking_html = thinking_content
                                        display_content = re.sub(
                                            r"<(?:thinking|thought)>.*?</(?:thinking|thought)>",
                                            "",
                                            content,
                                            flags=re.DOTALL,
                                        ).strip()
                                    # Also check legacy meta thinking
                                    meta_thinking_sw = (
                                        msg_metadata.get("thinking", "")
                                        if isinstance(msg_metadata, dict)
                                        else ""
                                    )
                                    if meta_thinking_sw and meta_thinking_sw.strip():
                                        if thinking_html:
                                            if meta_thinking_sw.strip() not in thinking_html:
                                                thinking_html = (
                                                    thinking_html
                                                    + "\n\n"
                                                    + meta_thinking_sw.strip()
                                                ).strip()
                                        else:
                                            thinking_html = meta_thinking_sw.strip()
                                        if not display_content:
                                            display_content = content.strip()
                                    if thinking_html:
                                        # Preserve legacy as single block but attempt to split by double newline per-agent?
                                        # Keep as single block with current agent
                                        thinking_blocks = [
                                            {
                                                "seq": 1,
                                                "agent": agent_name or "sago",
                                                "text": thinking_html,
                                                "timestamp": 0,
                                            }
                                        ]
                                    # Also check direct msg thinking field
                                    if not thinking_blocks:
                                        _msg_think = ""
                                        try:
                                            _msg_think = (
                                                msg.get("thinking", "")
                                                if isinstance(msg, dict)
                                                else ""
                                            )  # type: ignore[attr-defined]  # noqa: F821
                                        except Exception:
                                            _msg_think = ""
                                        if (
                                            _msg_think
                                            and isinstance(_msg_think, str)
                                            and _msg_think.strip()
                                        ):
                                            thinking_blocks = [
                                                {
                                                    "seq": 1,
                                                    "agent": agent_name or "sago",
                                                    "text": _msg_think.strip(),
                                                    "timestamp": 0,
                                                }
                                            ]

                                # Defer mounting until after compose() has run
                                deferred_responses.append(
                                    (
                                        current_card,
                                        thinking_blocks,
                                        display_content,
                                        agent_name,
                                    )
                                )

                                if created_at:
                                    message_cards.append((created_at, current_card))

                        # Phase 2: Mount all deferred responses after compose() has run
                        last_card_switch = current_card  # capture for closure

                        def _mount_deferred_switch() -> None:
                            def _build_tool_widget(tl: dict) -> Collapsible:
                                from rich.markup import escape as _esc

                                tool_name = tl.get("tool_name", "unknown")
                                success = bool(tl.get("success", True))
                                result_str = tl.get("result") or ""

                                raw_args = tl.get("arguments") or ""
                                if isinstance(raw_args, str):
                                    try:
                                        parsed_args = json.loads(raw_args) if raw_args else {}
                                    except (json.JSONDecodeError, TypeError):
                                        parsed_args = {}
                                elif isinstance(raw_args, dict):
                                    parsed_args = raw_args
                                else:
                                    parsed_args = {}

                                status_tag = (
                                    "[bold green]● OK[/bold green]"
                                    if success
                                    else "[bold red]✗ FAILED[/bold red]"
                                )
                                _tool_agent = tl.get("agent") or tl.get("agent_name") or ""
                                _agent_suffix = (
                                    f" [dim]by @{_esc(_tool_agent)}[/dim]" if _tool_agent else ""
                                )
                                title = f"{status_tag} Tool: [bold cyan]{_esc(tool_name)}[/bold cyan]{_agent_suffix}"

                                param_lines = []
                                for k, v in parsed_args.items():
                                    val_str = str(v)
                                    if len(val_str) > 300:
                                        val_str = val_str[:300] + "..."
                                    param_lines.append(
                                        f"  [bold cyan]{_esc(k)}[/bold cyan]: [white]{_esc(val_str)}[/white]"
                                    )
                                args_str = (
                                    "\n".join(param_lines)
                                    if param_lines
                                    else "  [dim](no parameters)[/dim]"
                                )

                                from sago.tui.helpers import _summarize_tool_result

                                preview_res = _summarize_tool_result(result_str)

                                body = (
                                    f"[bold yellow]Parameters:[/bold yellow]\n{args_str}\n\n"
                                    f"[bold green]Result Output:[/bold green]\n{preview_res}"
                                )

                                return Collapsible(
                                    Static(body, classes="msg-system", markup=True),
                                    title=title,
                                    collapsed=True,
                                )

                            # PHASE A: Mount tool usage cards FIRST (above response text)
                            if tool_logs and message_cards:
                                sorted_cards = sorted(message_cards, key=lambda x: x[0])

                                for tl in tool_logs:
                                    tool_time = tl.get("created_at", "")
                                    if not tool_time:
                                        continue

                                    target_card = None
                                    for msg_time, card in reversed(sorted_cards):
                                        if msg_time <= tool_time:
                                            target_card = card
                                            break

                                    if target_card is None:
                                        target_card = last_card_switch

                                    if target_card is None:
                                        continue

                                    tool_widget = _build_tool_widget(tl)
                                    try:
                                        body_widget = target_card.query_one(".exchange-body")
                                        try:
                                            resp = target_card.query_one(".exchange-response")
                                            body_widget.mount(tool_widget, before=resp)
                                        except Exception:
                                            body_widget.mount(tool_widget)
                                    except Exception:
                                        try:
                                            resp = target_card.query_one(".exchange-response")
                                            try:
                                                first_child = (
                                                    resp.children[0] if resp.children else None
                                                )
                                                if first_child is not None:
                                                    resp.mount(tool_widget, before=first_child)
                                                else:
                                                    resp.mount(tool_widget)
                                            except Exception:
                                                resp.mount(tool_widget)
                                        except Exception as e:
                                            log_exception(
                                                e, "mount tool call during session switch"
                                            )

                            # PHASE B: Mount text content AFTER tool calls — per-agent, per-step thinking in order
                            for (
                                card,
                                thinking_blocks,
                                display_content,
                                agent_name,
                            ) in deferred_responses:
                                if card is None:
                                    continue
                                try:
                                    resp = card.query_one(".exchange-response")
                                except Exception:
                                    resp = None
                                target = resp if resp is not None else card

                                if thinking_blocks:
                                    # Ensure sorted by seq
                                    try:
                                        _sorted_blocks = sorted(
                                            thinking_blocks, key=lambda b: int(b.get("seq", 0) or 0)
                                        )
                                    except Exception:
                                        _sorted_blocks = thinking_blocks
                                    for _tb in _sorted_blocks:
                                        _t_text = (_tb.get("text") or "").strip()
                                        if not _t_text:
                                            continue
                                        _t_agent = (
                                            _tb.get("agent") or agent_name or "sago"
                                        ).strip()
                                        _t_title = (
                                            f"● {_t_agent} — Technical Reasoning"
                                            if _t_agent
                                            else "● Technical Reasoning & Analysis"
                                        )
                                        # For sequential reconstruction, mount before response if inside ExchangeTurnCard body
                                        # But deferred target is response container; we mount there preserving order.
                                        # To keep thinking interleaved before tools when possible, try body mount.
                                        try:
                                            # If target is response container, try mount before it via body if available
                                            if card is not None and hasattr(
                                                card, "mount_sequential"
                                            ):
                                                # Create card-like widget for sequential mount
                                                _tb_card = Collapsible(
                                                    Static(
                                                        _t_text,
                                                        classes="thinking-text",
                                                        markup=False,
                                                    ),
                                                    title=_t_title,
                                                    collapsed=True,
                                                )
                                                # Use sequential mount if card is ExchangeTurnCard
                                                try:
                                                    card.mount_sequential(_tb_card)  # type: ignore
                                                    continue
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                                        target.mount(
                                            Collapsible(
                                                Static(
                                                    _t_text, classes="thinking-text", markup=False
                                                ),
                                                title=_t_title,
                                                collapsed=True,
                                            )
                                        )

                                color = get_agent_color(agent_name)
                                target.mount(
                                    Static(
                                        f"[{color}][{agent_name.upper()}][/{color}]",
                                        classes="exchange-assistant agent-tag",
                                        markup=True,
                                    )
                                )
                                target.mount(
                                    Static(
                                        RichMarkdown(display_content),
                                        classes="exchange-assistant markdown-body",
                                    )
                                )

                            # Set active exchange card so new messages attach here
                            if last_card_switch is not None:
                                self._active_exchange_card = last_card_switch

                        self.call_after_refresh(_mount_deferred_switch)
                    finally:
                        self._loading_session = False

                    container.scroll_end(animate=False)
                    self._add_system_message(
                        f"Loaded session: {ses.get('title', 'Untitled')} ({len(msgs)} messages)"
                    )
                    return
            self._add_system_message(f"Session not found: {sid}")
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _show_history(self: SagoApp) -> None:
        if not self.command_history:
            self._add_system_message("No history")
            return
        lines = [
            f"  [dim]{i + 1}.[/dim] [cyan]{cmd}[/cyan]"
            for i, cmd in enumerate(self.command_history[-20:])
        ]
        body = "[bold]History:[/bold]\n" + "\n".join(lines)
        container = self.query_one("#messages")
        container.mount(Collapsible(Static(body), title="History", collapsed=True))

    def _change_model(self: SagoApp, m: str) -> None:
        from sago.tui.models import (
            add_custom_model,
            get_all_models,
            refresh_models_from_openrouter,
            remove_custom_model,
        )

        parts = m.split(None, 2) if m else []

        # /model — show all cleanly in a single consolidated panel
        if not parts:
            models = get_all_models()
            providers: dict[str, list[str]] = {}
            for model in models:
                provider = model.split("/")[0] if "/" in model else "other"
                providers.setdefault(provider, []).append(model)
            cur = getattr(self, "current_model", "?")
            prov = getattr(self, "current_provider", "?")

            container = self.query_one("#messages")
            lines = [
                f"[bold green]● Active Model:[/] [bold white]{cur}[/]  ([cyan]Provider: {prov}[/])\n",
                "[dim]Switch model: /model <name>  |  Add: /model add <id>  |  Refresh: /model refresh[/dim]\n",
            ]

            for provider, pmodels in sorted(providers.items()):
                lines.append(
                    f"[bold cyan]▼ Provider: {provider.upper()} ({len(pmodels)} models)[/]"
                )
                # Display in clean bulleted list
                for m in pmodels[:10]:
                    marker = "[bold green]▶[/]" if m == cur else " "
                    lines.append(f"  {marker} [yellow]{m}[/]")
                if len(pmodels) > 10:
                    lines.append(f"    [dim]... +{len(pmodels) - 10} more[/dim]")
                lines.append("")

            body = "\n".join(lines)
            container.mount(
                Collapsible(
                    Static(body),
                    title=f"Models (Active: {cur})",
                    collapsed=True,
                )
            )
            container.scroll_end()
            return

        # /model refresh
        if parts[0] == "refresh":
            import os

            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            msg = refresh_models_from_openrouter(api_key)
            self._add_system_message(msg)
            return

        # /model add <model>
        if parts[0] == "add" and len(parts) >= 2:
            model_id = parts[1]
            msg = add_custom_model(model_id)
            self._add_system_message(msg)
            return

        # /model remove <model>
        if parts[0] == "remove" and len(parts) >= 2:
            model_id = parts[1]
            msg = remove_custom_model(model_id)
            self._add_system_message(msg)
            return

        # Known providers for smart parsing (registry-driven, aliases included)
        from sago.llm.registry import (
            get_provider_spec,
            guess_provider_from_model,
            infer_provider_for_model,
            known_provider_keys,
            normalize_provider,
        )

        valid_names = set(known_provider_keys())

        # /model <provider> <model> — explicit syntax (e.g. /model google gemini-2.0-pro or /model openrouter deepseek/deepseek-r1)
        if len(parts) >= 2 and parts[0].lower() in valid_names:
            provider = normalize_provider(parts[0])
            model_name = " ".join(parts[1:])
            self.current_provider = provider
            self.current_model = model_name
            self._add_system_message(
                f"Provider: [bold cyan]{provider}[/] | Model: [bold green]{model_name}[/]"
            )
            return

        # /model provider/model or general string
        search = parts[0]
        if "/" in search:
            prefix, rest = search.split("/", 1)
            if prefix.lower() in valid_names:
                provider = normalize_provider(prefix)
                self.current_provider = provider
                self.current_model = rest if provider == "google" else search
                self._add_system_message(
                    f"Provider: [bold cyan]{self.current_provider}[/] | Model: [bold green]{self.current_model}[/]"
                )
                return

        models = get_all_models()
        for model in models:
            if search.lower() in model.lower():
                self.current_model = model
                guessed = guess_provider_from_model(model)
                if guessed and get_provider_spec(guessed):
                    self.current_provider = guessed
                else:
                    inferred = infer_provider_for_model(model)
                    if inferred:
                        self.current_provider = inferred
                self._add_system_message(
                    f"Model: [bold green]{model}[/] (Provider: [bold cyan]{self.current_provider}[/])"
                )
                return

        # Not in list — allow custom model
        self.current_model = search
        guessed = guess_provider_from_model(search)
        if guessed and get_provider_spec(guessed):
            self.current_provider = guessed
        else:
            # Unknown 'vendor/model' ids (e.g. stealth/ox-alpha) route via OpenRouter
            inferred = infer_provider_for_model(search)
            if inferred:
                self.current_provider = inferred
        provider_label = (
            f"(Provider: [bold cyan]{self.current_provider}[/])" if "/" in search else "(custom)"
        )
        self._add_system_message(f"Model: [bold green]{search}[/] {provider_label}")

    def _change_provider(self: SagoApp, p: str) -> None:
        from sago.llm.registry import get_provider_spec, known_providers, normalize_provider

        if not p:
            from rich.markup import escape as _escape

            from sago.llm.registry import fallback_order

            current = normalize_provider(self.current_provider)
            lines = ["[bold]Providers[/bold]", f"  Current: {current}", ""]
            for name in fallback_order():
                spec = get_provider_spec(name)
                if not spec:
                    continue
                marker = " ←" if name == current else ""
                key_hint = "no key needed" if spec.local else spec.api_key_env
                lines.append(
                    f"  • [cyan]{name:<12}[/cyan] [dim]{_escape(key_hint)}[/dim] default={_escape(spec.default_model)}{marker}"
                )
            lines.append("")
            lines.append("[dim]Switch with: /provider <name>[/dim]")
            self._add_system_message("\n".join(lines))
            return

        canonical = normalize_provider(p)
        spec = get_provider_spec(canonical)
        if spec is None:
            self._add_system_message(
                f"[red]Unknown provider:[/] {p}\nKnown: {', '.join(known_providers())}"
            )
            return
        self.current_provider = canonical
        # Keep the user's explicit model if it already belongs to this provider;
        # otherwise seed the provider default.
        if "/" not in self.current_model or self.current_model.split("/", 1)[0] != canonical:
            self.current_model = spec.default_model
        key_status = (
            "local"
            if spec.local or not spec.api_key_env
            else ("key ✓" if os.environ.get(spec.api_key_env) else f"{spec.api_key_env} NOT set")
        )
        self._add_system_message(
            f"Provider: [bold cyan]{canonical}[/] | Model: [bold green]{self.current_model}[/] | {key_status}"
        )

    def _set_effort(self: SagoApp, level: str) -> None:
        from sago.tui.models import EFFORT_LEVELS

        if not level:
            current = EFFORT_LEVELS.get(self.current_effort, {})
            lines = [f"Current: {self.current_effort} - {current.get('desc', '')}"]
            for k, v in EFFORT_LEVELS.items():
                marker = " *" if k == self.current_effort else ""
                lines.append(f"  {marker} {k:<8} {v['desc']}")
            body = "\n".join(lines)
            container = self.query_one("#messages")
            container.mount(
                Collapsible(
                    Static(body, markup=False),
                    title="Effort Levels",
                    collapsed=True,
                )
            )
            container.scroll_end()
            return
        if level in EFFORT_LEVELS:
            self.current_effort = level
            self._add_system_message(f"Effort: {level}")
        else:
            self._add_system_message(f"Unknown: {level}\nAvailable: low, medium, high, max")

    def _show_version(self: SagoApp) -> None:
        from sago import __version__

        self._add_system_message(f"Sago v{__version__} — Multi-agent orchestration system")

    def _show_cost(self: SagoApp) -> None:
        from sago.tui.models import get_model_costs

        costs = get_model_costs().get(self.current_model, {"input": 0, "output": 0})
        total_in = self.total_input_tokens
        total_out = self.total_output_tokens
        cache_hit = self.total_cache_hit_tokens
        cache_miss = self.total_cache_miss_tokens

        # Calculate cost
        cost_in = (total_in / 1_000_000) * costs.get("input", 0)
        cost_out = (total_out / 1_000_000) * costs.get("output", 0)
        total_cost = cost_in + cost_out

        lines = [
            f"[bold]Model:[/bold] [cyan]{self.current_model}[/cyan]",
            f"[bold]Input:[/bold]  {total_in:,} tokens [green](${cost_in:.4f})[/green]",
            f"[bold]Output:[/bold] {total_out:,} tokens [green](${cost_out:.4f})[/green]",
            f"[bold]Total:[/bold]  [green]${total_cost:.4f}[/green]",
        ]
        if cache_hit > 0:
            lines.append(f"[dim]Cache: {cache_hit:,} hit, {cache_miss:,} miss[/dim]")
        body = "\n".join(lines)
        container = self.query_one("#messages")
        container.mount(Collapsible(Static(body), title="Token Usage", collapsed=True))

    def _compact(self: SagoApp) -> None:
        """Compact conversation history and update TUI cards."""
        if len(self.messages) < 3:
            self._add_system_message("Not enough messages to compact (minimum 3 required)")
            return

        try:
            from sago.memory.compaction import SessionCompactor

            compactor = SessionCompactor(max_context_tokens=1000)
            compacted = compactor.compact_messages(self.messages, preserve_recent=2)

            orig_count = len(self.messages)
            # Keep first turn if available and last 2 messages
            first = self.messages[:1]
            last = self.messages[-2:]
            middle_count = max(0, orig_count - len(first) - len(last))

            summary_text = (
                f"📋 **Compacted Context Summary ({middle_count} messages condensed):**\n"
                f"{compacted.summary}"
            )
            if compacted.key_points:
                summary_text += "\n\n**Key Points:**\n" + "\n".join(
                    f"- {kp}" for kp in compacted.key_points[:5]
                )
            if compacted.decisions:
                summary_text += "\n\n**Decisions:**\n" + "\n".join(
                    f"- {d}" for d in compacted.decisions[:3]
                )

            summary_msg = {"role": "system", "content": summary_text}
            self.messages = first + [summary_msg] + last

            # Update database if active session exists
            if getattr(self, "current_session_id", None) and self.current_session_id != "local":
                try:
                    from sago.database import MessageStore

                    ms = MessageStore(self.current_session_id)
                    ms.add_message(
                        role="system",
                        content=summary_text,
                        agent_name="system",
                        metadata={"type": "compaction_summary", "compacted_count": middle_count},
                    )
                    ms.flush()
                    ms.close()
                except Exception as e:
                    logger.debug("Failed to persist compaction message to DB: %s", e)

            # Collapse older rendered exchange cards in UI to keep UI responsive
            try:
                container = self.query_one("#messages")
                exchange_cards = [c for c in container.children if c.has_class("exchange-box")]
                # Collapse all but the last exchange card
                for card in exchange_cards[:-1]:
                    if hasattr(card, "is_turn_collapsed") and not card.is_turn_collapsed:
                        card.toggle_collapse()
            except Exception as e:
                logger.debug("Failed to auto-collapse cards during compaction: %s", e)

            from rich.markdown import Markdown as RichMarkdown

            compaction_card = Collapsible(
                Static(RichMarkdown(summary_text), classes="markdown-body msg-system"),
                title=f"⚡ Session Compacted ({middle_count} messages condensed)",
                collapsed=False,
            )
            container = self.query_one("#messages")
            container.mount(compaction_card)
            self._add_system_message(
                f"✓ Session compacted: {orig_count} messages reduced to {len(self.messages)}."
            )
            self._smart_scroll_end(animate=False)
        except Exception as err:
            self._add_system_message(f"Compaction failed: {err}")

    def _retry_last(self: SagoApp) -> None:
        """Retry last user prompt, cleaning trailing failed assistant turn from memory."""
        if self.messages:
            last_user = None
            last_user_idx = None
            for idx in range(len(self.messages) - 1, -1, -1):
                if self.messages[idx].get("role") == "user":
                    last_user = self.messages[idx].get("content")
                    last_user_idx = idx
                    break
            if last_user and last_user_idx is not None:
                # Remove everything after the last user message to prevent accumulating failed turns
                self.messages = self.messages[:last_user_idx]
                self._add_system_message(f"Retrying prompt: '{last_user[:60]}...'")
                self._process_message(last_user)
            else:
                self._add_system_message("No user message to retry")
        else:
            self._add_system_message("No messages to retry")

    def _continue_last(self: SagoApp) -> None:
        """Resume interrupted task from last executed tool state without wasting past tokens."""
        if not self.messages:
            self._add_system_message("No previous message to continue.")
            return

        # Fetch recently executed tools from ToolUsageStore if available
        recent_tools_summary = ""
        try:
            from sago.database import ToolUsageStore

            if self.current_session_id and self.current_session_id != "local":
                tus = ToolUsageStore(self.current_session_id)
                recent = tus.get_all()
                if recent:
                    last_entries = recent[-5:]
                    formatted_tools = []
                    for t in last_entries:
                        t_name = t.get("tool_name", "")
                        t_args = t.get("arguments", "")
                        t_res = (t.get("result") or "")[:200]
                        formatted_tools.append(f"- {t_name}({t_args}) -> {t_res}")
                    recent_tools_summary = (
                        "\n\nRecently executed tools in this turn:\n" + "\n".join(formatted_tools)
                    )
        except Exception:
            recent_tools_summary = ""

        interrupted_prompt = (
            "Please continue and finish the previous task from where it was interrupted. "
            "Do not repeat already executed steps or duplicate tool calls. Proceed with the next steps."
            + recent_tools_summary
        )
        # Use a dedicated command turn container like /chain (not a plain user card)
        # so it doesn't show duplicate "USER /continue" + "User Prompt: continue"
        self._add_command_turn(
            "continue",
            interrupted_prompt[:120] + ("..." if len(interrupted_prompt) > 120 else ""),
            meta=f"resuming {len(recent_tools_summary.splitlines()) if recent_tools_summary else 0} prior tool calls",
            tag_label="CONTINUE",
            tag_color="#3fb950",
        )
        self._process_message(interrupted_prompt)

    def _reset(self: SagoApp) -> None:
        self.messages.clear()
        self.query_one("#messages").remove_children()
        self._add_system_message("Session reset")

    def _save_session(self: SagoApp, name: str) -> None:
        try:
            from sago.database import Session, init_db

            init_db()
            title = name or f"Session {self.current_session_id[:8]}"
            s = Session(self.current_session_id)
            s.update(title=title)
            s.close()
            self._add_system_message(
                f"Session saved: {self.current_session_id[:8]} — {title}\n"
                f"Resume with: sago tui --resume {self.current_session_id[:8]}"
            )
        except Exception as e:
            self._add_system_message(f"Save error: {e}")

    def _load_session(self: SagoApp, sid: str) -> None:
        """Load a previous session's messages."""
        try:
            from sago.database import MessageStore, Session, ToolUsageStore, init_db

            init_db()
            s = Session()
            matched = s.find_by_prefix(sid)
            s.close()
            if matched:
                actual_sid = matched["id"]
                ms = MessageStore(actual_sid)
                history = ms.get_history(limit=50)
                ms.close()
                if history:
                    self._hide_welcome_screen()
                    self.messages.clear()
                    self.query_one("#messages").remove_children()
                    self.current_session_id = actual_sid
                    # CRITICAL: Reset stale _message_store so new messages go to this session
                    self._message_store = None

                    # Restore session title from database
                    try:
                        s2 = Session(actual_sid)
                        session_data = s2.get()
                        s2.close()
                        if session_data and session_data.get("title"):
                            self.current_session_title = session_data["title"]
                    except Exception as e:
                        log_exception(e, "restore session title from database")

                    # Load tool usage data for this session
                    tool_logs = []
                    try:
                        tus = ToolUsageStore(actual_sid)
                        tool_logs = tus.get_all()
                        tus.close()
                    except Exception as e:
                        log_exception(e, "load tool usage data for session")

                    # Hydrate DevTracer from saved trace.json if present
                    try:
                        from sago.tracking.dev_tracer import get_dev_tracer

                        tracer = get_dev_tracer()
                        loaded_traces = tracer.load_session_traces(actual_sid)
                        if loaded_traces:
                            logger.debug(
                                "Hydrated %d trace events from session %s",
                                loaded_traces,
                                actual_sid,
                            )
                    except Exception as e:
                        logger.debug("Trace hydration failed for %s: %s", actual_sid, e)

                    self._add_system_message(
                        f"Loaded session {actual_sid[:8]} ({len(history)} messages)"
                    )

                    # Use a flag to prevent re-saving messages to DB during load
                    self._loading_session = True
                    try:
                        import re

                        from rich.markdown import Markdown as RichMarkdown
                        from textual.widgets import Collapsible, Static

                        from sago.tui.helpers import ExchangeTurnCard
                        from sago.tui.widgets import get_agent_color

                        container = self.query_one("#messages")

                        # Group history and tools per turn
                        # We will associate each turn card with its intermediate thinking blocks,
                        # tool calls, and final assistant response in chronological order.
                        current_card = None
                        # Structure per turn: {card, user_time, items: [('thinking', block), ('tool', tl)], response: (display_content, agent_name)}
                        turns_data: list[dict[str, Any]] = []

                        # Pre-sort tool logs chronologically
                        def _parse_ts(val: Any) -> float:
                            if not val:
                                return 0.0
                            if isinstance(val, (int, float)):
                                return float(val)
                            try:
                                from datetime import datetime

                                return datetime.fromisoformat(str(val)).timestamp()
                            except Exception:
                                return 0.0

                        sorted_tools = sorted(
                            tool_logs,
                            key=lambda t: _parse_ts(t.get("created_at") or t.get("timestamp")),
                        )

                        for msg in history:
                            role = msg["role"]
                            content = msg["content"]
                            agent_name = msg.get("agent_name") or "sago"
                            created_at = msg.get("created_at", "")
                            msg_ts = _parse_ts(created_at)

                            # Parse metadata
                            msg_metadata = {}
                            raw_meta = msg.get("metadata")
                            if raw_meta:
                                try:
                                    msg_metadata = (
                                        json.loads(raw_meta)
                                        if isinstance(raw_meta, str)
                                        else raw_meta
                                    )
                                except (json.JSONDecodeError, TypeError):
                                    pass

                            if role == "user":
                                turn_card = ExchangeTurnCard(prompt=content, card_type="user")
                                container.mount(turn_card)
                                current_card = turn_card
                                self._active_exchange_card = turn_card

                                current_turn = {
                                    "card": turn_card,
                                    "user_ts": msg_ts,
                                    "items": [],
                                    "response": None,
                                }
                                turns_data.append(current_turn)

                                user_msg_dict = {
                                    "role": "user",
                                    "content": content,
                                    "agent_name": agent_name,
                                }
                                enhancement_data = msg_metadata.get("enhancement")
                                if enhancement_data:
                                    user_msg_dict["enhancement"] = enhancement_data
                                    try:
                                        from sago.engine.prompt_enhancer import (
                                            PromptEnhancementResult,
                                        )

                                        enhancement = PromptEnhancementResult(
                                            original_prompt=enhancement_data.get(
                                                "original_prompt", ""
                                            ),
                                            enhanced_prompt=enhancement_data.get(
                                                "enhanced_prompt", ""
                                            ),
                                            intent_summary=enhancement_data.get(
                                                "intent_summary", ""
                                            ),
                                            target_scope=enhancement_data.get("target_scope", []),
                                            acceptance_criteria=enhancement_data.get(
                                                "acceptance_criteria", []
                                            ),
                                            improvements=enhancement_data.get("improvements", []),
                                            was_modified=enhancement_data.get("was_modified", True),
                                        )
                                        from sago.tui.helpers import UIHelpers

                                        UIHelpers._add_prompt_enhancement_card(self, enhancement)
                                    except Exception as e:
                                        log_exception(e, "restore enhancement card on session load")

                                self.messages.append(user_msg_dict)

                            elif role == "assistant":
                                thinking_match = re.search(
                                    r"<(?:thinking|thought)>(.*?)</(?:thinking|thought)>",
                                    content,
                                    re.DOTALL,
                                )
                                display_content = content
                                thinking_blocks: list[dict] = []
                                meta_blocks = msg_metadata.get("thinking_blocks")
                                if isinstance(meta_blocks, list) and meta_blocks:
                                    try:
                                        thinking_blocks = sorted(
                                            meta_blocks, key=lambda b: int(b.get("seq", 0) or 0)
                                        )
                                    except Exception:
                                        thinking_blocks = list(meta_blocks)
                                    try:
                                        thinking_html = "\n\n".join(
                                            str(b.get("text", "") or "").strip()
                                            for b in thinking_blocks
                                            if b.get("text")
                                        )
                                    except Exception:
                                        thinking_html = ""
                                    if thinking_match:
                                        display_content = re.sub(
                                            r"<(?:thinking|thought)>.*?</(?:thinking|thought)>",
                                            "",
                                            content,
                                            flags=re.DOTALL,
                                        ).strip()
                                else:
                                    thinking_html = ""
                                    if thinking_match:
                                        thinking_content = thinking_match.group(1).strip()
                                        if thinking_content:
                                            thinking_html = thinking_content
                                        display_content = re.sub(
                                            r"<(?:thinking|thought)>.*?</(?:thinking|thought)>",
                                            "",
                                            content,
                                            flags=re.DOTALL,
                                        ).strip()
                                    meta_thinking = msg_metadata.get("thinking", "")
                                    if meta_thinking and meta_thinking.strip():
                                        if thinking_html:
                                            if meta_thinking.strip() not in thinking_html:
                                                thinking_html = (
                                                    thinking_html + "\n\n" + meta_thinking.strip()
                                                ).strip()
                                        else:
                                            thinking_html = meta_thinking.strip()
                                        if not display_content:
                                            display_content = content.strip()
                                    if thinking_html:
                                        thinking_blocks = [
                                            {
                                                "seq": 1,
                                                "agent": agent_name or "sago",
                                                "text": thinking_html,
                                                "timestamp": msg_ts,
                                            }
                                        ]

                                # Assign thinking blocks to current turn
                                target_turn = turns_data[-1] if turns_data else None
                                if target_turn is not None:
                                    for tb in thinking_blocks:
                                        tb_ts = _parse_ts(tb.get("timestamp")) or msg_ts
                                        target_turn["items"].append(("thinking", tb_ts, tb))
                                    target_turn["response"] = (display_content, agent_name)

                                self.messages.append(
                                    {
                                        "role": "assistant",
                                        "content": content,
                                        "agent_name": agent_name,
                                        "thinking": thinking_html,
                                        "metadata": msg_metadata,
                                    }
                                )

                        # Correlate tool calls into the appropriate turn
                        for tl in sorted_tools:
                            t_ts = _parse_ts(tl.get("created_at") or tl.get("timestamp"))
                            target_turn = None
                            for turn in reversed(turns_data):
                                if turn["user_ts"] <= t_ts:
                                    target_turn = turn
                                    break
                            if target_turn is None and turns_data:
                                target_turn = turns_data[-1]
                            if target_turn is not None:
                                target_turn["items"].append(("tool", t_ts, tl))

                        last_card = current_card

                        def _mount_deferred() -> None:
                            def _build_tool_widget(tl: dict) -> Collapsible:
                                from rich.markup import escape as _esc

                                tool_name = tl.get("tool_name", "unknown")
                                success = bool(tl.get("success", True))
                                result_str = tl.get("result") or ""

                                raw_args = tl.get("arguments") or ""
                                if isinstance(raw_args, str):
                                    try:
                                        parsed_args = json.loads(raw_args) if raw_args else {}
                                    except (json.JSONDecodeError, TypeError):
                                        parsed_args = {}
                                elif isinstance(raw_args, dict):
                                    parsed_args = raw_args
                                else:
                                    parsed_args = {}

                                status_tag = (
                                    "[bold green]● OK[/bold green]"
                                    if success
                                    else "[bold red]✗ FAILED[/bold red]"
                                )
                                _tool_agent = tl.get("agent") or tl.get("agent_name") or ""
                                _agent_suffix = (
                                    f" [dim]by @{_esc(_tool_agent)}[/dim]" if _tool_agent else ""
                                )
                                title = f"{status_tag} Tool: [bold cyan]{_esc(tool_name)}[/bold cyan]{_agent_suffix}"

                                param_lines = []
                                for k, v in parsed_args.items():
                                    val_str = str(v)
                                    if len(val_str) > 300:
                                        val_str = val_str[:300] + "..."
                                    param_lines.append(
                                        f"  [bold cyan]{_esc(k)}[/bold cyan]: [white]{_esc(val_str)}[/white]"
                                    )
                                args_str = (
                                    "\n".join(param_lines)
                                    if param_lines
                                    else "  [dim](no parameters)[/dim]"
                                )

                                from sago.tui.helpers import _summarize_tool_result

                                preview_res = _summarize_tool_result(result_str)

                                body = (
                                    f"[bold yellow]Parameters:[/bold yellow]\n{args_str}\n\n"
                                    f"[bold green]Result Output:[/bold green]\n{preview_res}"
                                )

                                return Collapsible(
                                    Static(body, classes="msg-system", markup=True),
                                    title=title,
                                    collapsed=True,
                                )

                            for turn in turns_data:
                                card = turn["card"]
                                if card is None:
                                    continue

                                # Sort all items in this turn chronologically (or by seq for equal ts)
                                sorted_items = sorted(
                                    turn["items"],
                                    key=lambda it: (
                                        it[1],
                                        int(it[2].get("seq", 0)) if it[0] == "thinking" else 0,
                                    ),
                                )

                                for item_type, _, data in sorted_items:
                                    if item_type == "thinking":
                                        _t_text = (data.get("text") or "").strip()
                                        if not _t_text:
                                            continue
                                        _t_agent = (data.get("agent") or "sago").strip()
                                        _t_title = (
                                            f"● {_t_agent} — Technical Reasoning"
                                            if _t_agent
                                            else "● Technical Reasoning & Analysis"
                                        )
                                        _tb_card = Collapsible(
                                            Static(_t_text, classes="thinking-text", markup=False),
                                            title=_t_title,
                                            collapsed=True,
                                        )
                                        if hasattr(card, "mount_sequential"):
                                            try:
                                                card.mount_sequential(_tb_card)
                                                continue
                                            except Exception:
                                                pass
                                        try:
                                            body_w = card.query_one(".exchange-body")
                                            body_w.mount(_tb_card)
                                        except Exception:
                                            card.mount(_tb_card)

                                    elif item_type == "tool":
                                        tool_w = _build_tool_widget(data)
                                        if hasattr(card, "mount_sequential"):
                                            try:
                                                card.mount_sequential(tool_w)
                                                continue
                                            except Exception:
                                                pass
                                        try:
                                            body_w = card.query_one(".exchange-body")
                                            body_w.mount(tool_w)
                                        except Exception:
                                            card.mount(tool_w)

                                # Finally mount the assistant response text in the response container
                                if turn.get("response"):
                                    display_content, agent_name = turn["response"]
                                    try:
                                        resp = card.query_one(".exchange-response")
                                    except Exception:
                                        resp = card
                                    color = get_agent_color(agent_name)
                                    resp.mount(
                                        Static(
                                            f"[{color}][{agent_name.upper()}][/{color}]",
                                            classes="exchange-assistant agent-tag",
                                            markup=True,
                                        )
                                    )
                                    resp.mount(
                                        Static(
                                            RichMarkdown(display_content),
                                            classes="exchange-assistant markdown-body",
                                        )
                                    )

                            if last_card is not None:
                                self._active_exchange_card = last_card

                        self.call_after_refresh(_mount_deferred)
                    finally:
                        self._loading_session = False

                    container.scroll_end(animate=False)
                    return
            self._add_system_message(
                f"Session not found: {sid}\nUse /sessions to list available sessions"
            )
        except Exception as e:
            self._add_system_message(f"Load error: {e}")

    def _exit_session(self: SagoApp) -> None:
        """Save session and exit, or auto-delete if no human messages exist."""
        # Flush any pending batched DB writes (messages + tool usage) so the
        # dev artifacts export below sees complete data
        if hasattr(self, "_message_store") and self._message_store:
            try:
                self._message_store.flush()
            except Exception as e:
                log_exception(e, "flush message store on exit")
        try:
            from sago.database import ToolUsageStore

            if self.current_session_id and self.current_session_id != "local":
                ToolUsageStore(self.current_session_id).flush()
        except Exception as e:
            log_exception(e, "flush tool usage store on exit")

        # Safety net: persist all settings to disk before exit
        try:
            self._save_settings()
        except Exception as e:
            log_exception(e, "save settings before exit")
        from sago.engine.prompt_enhancer import generate_session_title

        current_title = getattr(self, "current_session_title", "")
        if not current_title or current_title in ("TUI Session", "Interactive Session"):
            self.current_session_title = generate_session_title(self.messages)

        try:
            from sago.database import Session, init_db

            init_db()
            s = Session(self.current_session_id)
            # If session has no real human user messages, auto-delete it
            if not s.has_human_messages(self.current_session_id):
                s.delete()
                s.close()
                self.exit()
                return

            # Save current session with smart title
            s.update(title=self.current_session_title, status="closed")
            s.close()
        except Exception as e:
            log_exception(e, "save/update session on exit")
        # Auto-export developer mode session artifacts if dev mode is enabled
        dev_artifacts_info: list[str] = []
        if getattr(self, "developer_mode", False):
            try:
                import os
                from pathlib import Path

                from sago.tracking.dev_tracer import export_session_dev_artifacts

                artifacts = export_session_dev_artifacts(
                    session_id=self.current_session_id,
                    messages=self.messages,
                    cwd=Path.cwd(),
                    tool_calls=getattr(self, "session_tool_calls", None),
                )
                if artifacts:
                    dev_artifacts_info.append("📁 [Dev Mode] Session artifacts generated:")
                    for _, p in artifacts.items():
                        rel = os.path.relpath(p, os.getcwd()) if os.path.exists(p) else p
                        dev_artifacts_info.append(f"   ↳ {rel}")
            except Exception as e:
                log_exception(e, "export dev artifacts on exit")

        # Build comprehensive session highlights summary banner
        sid = self.current_session_id[:8]
        messages = list(getattr(self, "messages", []))
        user_queries = sum(1 for m in messages if m.get("role") == "user")
        total_messages = len(messages)

        # Tool calls stats
        tool_calls = getattr(self, "session_tool_calls", [])
        total_tools = len(tool_calls)
        tool_counts: dict[str, int] = {}
        for tc in tool_calls:
            t_name = tc.get("tool", "tool")
            tool_counts[t_name] = tool_counts.get(t_name, 0) + 1

        if not tool_counts:
            try:
                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                events = get_dev_tracer().get_recent_traces()
                for e in events:
                    if e.event_type == TraceEventType.TOOL_DISPATCH:
                        t_name = e.data.get("tool_name", e.action)
                        tool_counts[t_name] = tool_counts.get(t_name, 0) + 1
                total_tools = sum(tool_counts.values())
            except Exception as e:
                log_exception(e, "get dev tracer events for summary")

        # Token stats
        t_in = getattr(self, "total_input_tokens", 0)
        t_out = getattr(self, "total_output_tokens", 0)
        total_tokens = t_in + t_out

        # Engaged agents
        agents = sorted({m.get("agent_name") for m in messages if m.get("agent_name")})
        agents_str = (
            ", ".join(f"@{a}" for a in agents)
            if agents
            else f"@{getattr(self, 'current_agent', 'sago')}"
        )

        # Tool breakdown
        if tool_counts:
            sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:4]
            tools_breakdown = ", ".join(f"{t} ({cnt})" for t, cnt in sorted_tools)
            if len(tool_counts) > 4:
                tools_breakdown += f", +{len(tool_counts) - 4} more"
        else:
            tools_breakdown = "0 calls"

        import sys

        print("\n" + "━" * 60, file=sys.stderr)
        print(f"📊 SAGO SESSION SUMMARY ({sid})", file=sys.stderr)
        print("━" * 60, file=sys.stderr)
        print(
            f"• Total Queries  : {user_queries} user turns ({total_messages} messages)",
            file=sys.stderr,
        )
        print(f"• Specialist(s)  : {agents_str}", file=sys.stderr)
        print(f"• Tool Calls     : {total_tools} total [{tools_breakdown}]", file=sys.stderr)
        print(
            f"• Token Usage    : {total_tokens:,} tokens ({t_in:,} in, {t_out:,} out)",
            file=sys.stderr,
        )
        print(f"• Resume Command : sago tui --resume {sid}  (or /load {sid})", file=sys.stderr)

        if dev_artifacts_info:
            print("━" * 60, file=sys.stderr)
            print("\n".join(dev_artifacts_info), file=sys.stderr)

        print("━" * 60 + "\n", file=sys.stderr)
        self.exit()

    def _detach_session(self: SagoApp) -> None:
        """Detach from session cleanly without stopping background tasks."""
        if hasattr(self, "_message_store") and self._message_store:
            try:
                self._message_store.flush()
            except Exception as e:
                log_exception(e, "flush message store on detach")
        try:
            from sago.database import ToolUsageStore

            if self.current_session_id and self.current_session_id != "local":
                ToolUsageStore(self.current_session_id).flush()
        except Exception as e:
            log_exception(e, "flush tool usage store on detach")
        from sago.engine.prompt_enhancer import generate_session_title

        current_title = getattr(self, "current_session_title", "")
        if not current_title or current_title in ("TUI Session", "Interactive Session"):
            self.current_session_title = generate_session_title(self.messages)

        try:
            from sago.database import Session, init_db

            init_db()
            s = Session(self.current_session_id)
            s.update(title=self.current_session_title, status="detached")
            s.close()
        except Exception as e:
            log_exception(e, "update session status to detached")

        # Auto-export developer mode session artifacts if dev mode is enabled
        dev_artifacts_info: list[str] = []
        if getattr(self, "developer_mode", False):
            try:
                import os
                from pathlib import Path

                from sago.tracking.dev_tracer import export_session_dev_artifacts

                artifacts = export_session_dev_artifacts(
                    session_id=self.current_session_id,
                    messages=self.messages,
                    cwd=Path.cwd(),
                    tool_calls=getattr(self, "session_tool_calls", None),
                )
                if artifacts:
                    dev_artifacts_info.append("📁 [Dev Mode] Session artifacts generated:")
                    for _, p in artifacts.items():
                        rel = os.path.relpath(p, os.getcwd()) if os.path.exists(p) else p
                        dev_artifacts_info.append(f"   ↳ {rel}")
            except Exception as e:
                log_exception(e, "export dev artifacts on detach")

        sid = self.current_session_id[:8]
        messages = list(getattr(self, "messages", []))
        user_queries = sum(1 for m in messages if m.get("role") == "user")
        total_messages = len(messages)
        t_in = getattr(self, "total_input_tokens", 0)
        t_out = getattr(self, "total_output_tokens", 0)
        total_tokens = t_in + t_out

        import sys

        print("\n" + "=" * 60, file=sys.stderr)
        print(f"✓ SAGO DETACHED SUCCESSFULLY (Session: {sid})", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(
            f"• Total Queries  : {user_queries} user turns ({total_messages} messages)",
            file=sys.stderr,
        )
        print(
            f"• Token Usage    : {total_tokens:,} tokens ({t_in:,} in, {t_out:,} out)",
            file=sys.stderr,
        )
        print("All background agent tasks and processes remain running.", file=sys.stderr)
        print("-" * 60, file=sys.stderr)
        print(f"To reattach anytime, run:  sago attach {sid}", file=sys.stderr)
        print(f"                      or:  sago tui --resume {sid}", file=sys.stderr)
        if dev_artifacts_info:
            print("-" * 60, file=sys.stderr)
            print("\n".join(dev_artifacts_info), file=sys.stderr)
        print("=" * 60 + "\n", file=sys.stderr)
        self.exit()

    def _list_sessions(self: SagoApp) -> None:
        """List recent sessions for easy resume."""
        try:
            from sago.database import MessageStore, Session, init_db

            init_db()
            s = Session()
            sessions = s.list_all(limit=15)
            s.close()
            if not sessions:
                self._add_system_message("No saved sessions")
                return
            lines = ["[bold]Recent sessions:[/bold]"]
            for ses in sessions:
                sid = ses["id"][:8]
                title = (ses.get("title") or "Untitled")[:30]
                date = (ses.get("created_at") or "?")[:16]
                # Get message count
                try:
                    ms = MessageStore(ses["id"])
                    msgs = ms.get_history(limit=1000)
                    count = len(msgs)
                    ms.close()
                except Exception:
                    count = "?"
                current = " [green]*[/green]" if ses["id"] == self.current_session_id else ""
                lines.append(
                    f"  [cyan]{sid}[/cyan]{current}  [yellow]{title:<30}[/yellow] [dim]{count} msgs  {date}[/dim]"
                )
            lines.append(
                f"\n[dim]Resume: /load <id>  |  Current: {self.current_session_id[:8]}[/dim]"
            )
            body = "\n".join(lines)
            container = self.query_one("#messages")
            container.mount(
                Collapsible(
                    Static(body),
                    title="Sessions",
                    collapsed=True,
                )
            )
        except Exception as e:
            self._add_system_message(f"Sessions error: {e}")

    def _export_session(self: SagoApp, output_path: str = "") -> None:
        """Export session to comprehensive markdown file.

        Usage: /export [output_path]
        Default: {session_id}_export.md in current directory
        """

        from sago.database import MessageStore, ToolUsageStore, init_db

        init_db()
        sid = self.current_session_id

        # Build header
        lines = [
            f"# Session Export: {sid[:12]}",
            "",
            f"- **Session ID:** {sid}",
            f"- **Agent:** {self.current_agent}",
            f"- **Model:** {self.current_provider}/{self.current_model}",
            f"- **Exported:** {__import__('datetime').datetime.now().isoformat()[:19]}",
            f"- **Messages:** {len(self.messages)}",
            "",
            "---",
            "",
            "## Conversation",
            "",
        ]

        # Add messages with timestamps and metadata from DB
        try:
            ms = MessageStore(sid)
            db_msgs = ms.get_history(limit=10000)
            ms.close()
        except Exception:
            db_msgs = []

        # Build lookup by content for timestamp matching
        db_by_content: dict[str, dict] = {}
        for dm in db_msgs:
            key = dm.get("content", "")[:100]
            db_by_content[key] = dm

        for msg in self.messages:
            role = msg["role"].upper()
            content = msg.get("content", "")

            # Try to find matching DB record for timestamp/metadata
            db_match = db_by_content.get(content[:100], {})
            timestamp = db_match.get("created_at", "")
            agent = db_match.get("agent_name", "")
            meta_str = db_match.get("metadata", "{}")

            try:
                meta = __import__("json").loads(meta_str) if isinstance(meta_str, str) else meta_str
            except Exception:
                meta = {}

            # Format header line
            header_parts = [f"### {role}"]
            if agent:
                header_parts.append(f"Agent: {agent}")
            if timestamp:
                header_parts.append(f"Time: {timestamp[:19]}")
            if meta:
                meta_items = [f"{k}={v}" for k, v in meta.items() if k not in ("session_id",)]
                if meta_items:
                    header_parts.append(", ".join(meta_items[:3]))

            lines.append(" | ".join(header_parts))
            lines.append("")
            lines.append(content)
            # Add tool usage and subagent execution section
        lines.extend(["---", "", "## ⚙️ Tool Executions & Sub-Agent Delegations", ""])
        try:
            tus = ToolUsageStore(sid)
            tool_logs = tus.get_all()
            tus.close()
        except Exception:
            tool_logs = []

        # Fallback to dev tracer in case DB was local or not yet flushed
        if not tool_logs:
            try:
                from sago.tracking.dev_tracer import get_dev_tracer

                traces = get_dev_tracer().get_recent_traces(limit=500)
                for t in traces:
                    if t.event_type.value == "TOOL_DISPATCH":
                        tool_logs.append(
                            {
                                "tool_name": t.data.get("tool_name", t.action),
                                "arguments": t.data.get("arguments", {}),
                                "result": t.data.get("result_preview", ""),
                                "duration_ms": int(t.duration_ms),
                                "success": 1 if t.status == "OK" else 0,
                            }
                        )
            except Exception as e:
                log_exception(e, "build tool logs from dev tracer")

        subagent_calls = []
        error_logs = []
        if tool_logs:
            lines.append("| # | Tool / Action | Duration | Status | Key Arguments / Target |")
            lines.append("|---|---------------|----------|--------|------------------------|")
            for i, log in enumerate(tool_logs, 1):
                tool = log.get("tool_name", "?")
                dur = f"{log.get('duration_ms', 0)}ms"
                success = bool(log.get("success", 1))
                ok = "✓ OK" if success else "✗ FAIL"
                args_raw = log.get("arguments", "{}")
                try:
                    args = (
                        __import__("json").loads(args_raw)
                        if isinstance(args_raw, str)
                        else args_raw
                    )
                except Exception:
                    args = {}

                res_str = str(log.get("result", ""))
                is_actual_err = (
                    not success
                    or res_str.lower().startswith("error")
                    or res_str.lower().startswith("traceback")
                    or "exception:" in res_str.lower()
                    or "failed:" in res_str.lower()
                )
                if is_actual_err:
                    error_logs.append((i, tool, args, res_str))

                if tool == "spawn_agent":
                    subagent_calls.append((i, args, res_str))

                args_str = str(args)
                if len(args_str) > 120:
                    args_str = args_str[:120] + "..."
                lines.append(f"| {i} | `{tool}` | {dur} | {ok} | `{args_str}` |")
            lines.append("")
        else:
            lines.append("_No tool usage recorded._")
            lines.append("")

        # Sub-Agent Delegations Section
        if subagent_calls:
            lines.extend(["---", "", "## 🤖 Sub-Agent Delegations", ""])
            for idx, args, result in subagent_calls:
                target_agent = args.get("agent_name") or args.get("agent") or "Specialist Agent"
                task_desc = args.get("task", "(No task description)")
                lines.append(f"### Sub-Agent Delegation #{idx}: `{target_agent}`")
                lines.append(f"- **Target Agent:** `{target_agent}`")
                lines.append(f"- **Delegated Task:** {task_desc}")
                lines.append(
                    f"- **Arguments & Parameters:** `{__import__('json').dumps(args, indent=2)}`"
                )
                if result:
                    lines.append("- **Execution Output:**")
                    lines.append("```markdown")
                    lines.append(result)
                    lines.append("```")
                lines.append("")

        # Execution Errors & Diagnostics
        if error_logs:
            lines.extend(["---", "", "## ❌ Execution Errors & Issues", ""])
            for idx, tool, args, result in error_logs:
                lines.append(f"### Error in Tool #{idx} (`{tool}`)")
                lines.append(f"- **Parameters:** `{args}`")
                lines.append("- **Failure Diagnostics:**")
                lines.append("```")
                lines.append(str(result))
                lines.append("```")
                lines.append("")

        # Interaction Flowchart & Execution Tree
        from sago.tracking.dev_tracer import get_tracer

        tracer = get_tracer()
        events = tracer.get_events()
        if events:
            lines.extend(["---", "", "## 🗺️ Interaction Graph & Hierarchy", ""])
            lines.append(tracer._generate_mermaid_graph(events))
            lines.append("")
            lines.append(tracer._generate_ascii_tree(events))
            lines.append("")
        else:
            lines.extend(["---", "", "## 🗺️ Interaction Flowchart", "", "```mermaid", "graph TD"])
            lines.append(f"  User([User Request]) --> Orch[{self.current_agent}]")
            for i, log in enumerate(tool_logs[:20], 1):
                t_name = log.get("tool_name", "tool")
                stat = "✓" if log.get("success", 1) else "✗"
                if t_name == "spawn_agent":
                    lines.append(f"  Orch -->|Delegate| Sub_{i}[🤖 Subagent ({stat})]")
                else:
                    lines.append(f"  Orch -->|Call| Tool_{i}[⚙️ {t_name} ({stat})]")
            lines.extend(["```", ""])

        # Add token usage summary if available
        lines.extend(["---", "", "## Token Usage", ""])
        try:
            from sago.tracking.token_tracker import get_token_tracker

            tracker = get_token_tracker()
            session_usages = tracker.get_for_session(sid)
            if session_usages:
                total_in = sum(u.get("input_tokens", 0) for u in session_usages)
                total_out = sum(u.get("output_tokens", 0) for u in session_usages)
                total_cost = sum(u.get("cost_usd", 0) for u in session_usages)
                lines.extend(
                    [
                        f"- **Total Requests:** {len(session_usages)}",
                        f"- **Input Tokens:** {total_in:,}",
                        f"- **Output Tokens:** {total_out:,}",
                        f"- **Total Cost:** ${total_cost:.4f}",
                    ]
                )
            else:
                lines.append("_No token usage data for this session._")
        except Exception:
            lines.append("_Token tracking unavailable._")
        lines.append("")

        # Write file
        if output_path:
            path = Path(output_path)
        else:
            path = Path(f"{sid[:12]}_export.md")
        try:
            path.write_text("\n".join(lines), encoding="utf-8")
            self._add_system_message(
                f"Exported to {path} ({len(self.messages)} messages, {len(tool_logs)} tool calls, {len(subagent_calls)} subagents)"
            )
        except Exception as e:
            self._add_system_message(f"Export failed: {e}")

    def _handle_git_command(self: SagoApp, args: str = "") -> None:
        """Handle /git [status|diff|log|branch|checkout|commit|...] commands."""
        parts = args.strip().split(None, 1)
        subcmd = parts[0].lower() if parts else "status"
        subargs = parts[1] if len(parts) > 1 else ""

        if subcmd == "status":
            self._git_status()
        elif subcmd == "diff":
            self._git_diff(subargs)
        elif subcmd == "commit":
            self._git_commit(subargs)
        else:
            try:
                cwd = str(Path.cwd())
                cmd = ["git", "-C", cwd, subcmd] + (subargs.split() if subargs else [])
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                out = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
                display = out.strip() or "(no output)"
                from rich.markup import escape

                body = f"[bold]git {args}:[/bold]\n{escape(display[:8000])}"
                container = self.query_one("#messages")
                container.mount(
                    Collapsible(
                        Static(body),
                        title=f"Git {subcmd.capitalize()}",
                        collapsed=False,
                    )
                )
                container.scroll_end()
            except Exception as e:
                self._add_system_message(f"Git error: {e}")

    def _git_status(self: SagoApp) -> None:
        try:
            cwd = str(Path.cwd())
            r = subprocess.run(
                ["git", "-C", cwd, "status", "--short", "--branch"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            from rich.markup import escape

            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            container = self.query_one("#messages")
            if r.returncode != 0:
                body = f"[bold]Git status:[/bold]\n[red]{escape(err or out or 'Unknown git error')}[/red]"
                title = "Git Status — Error"
            elif not out:
                body = "[bold]Git status:[/bold]\n[green]Working tree clean[/green] [dim](no changes)[/dim]"
                if err:
                    body += f"\n[dim]{escape(err[:500])}[/dim]"
                title = "Git Status — Clean"
            else:
                body = f"[bold]Git status:[/bold]\n{escape(out[:8000])}"
                title = "Git Status"
            container.mount(Collapsible(Static(body), title=title, collapsed=False))
            container.scroll_end()
        except Exception as e:
            self._add_system_message(f"Git error: {e}")

    def _git_diff(self: SagoApp, file: str) -> None:
        try:
            cwd = str(Path.cwd())
            cmd = ["git", "-C", cwd, "diff", "HEAD"]
            if file:
                cmd.extend(["--", file])
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            from rich.markup import escape

            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            container = self.query_one("#messages")
            if r.returncode != 0:
                body = f"[bold]Diff:[/bold]\n[red]{escape(err or out or 'git diff failed')}[/red]"
                title = "Git Diff — Error"
            elif not out:
                # No diff vs HEAD — check if truly clean or just show empty
                body = "[bold]Diff:[/bold]\n[green]No changes vs HEAD[/green] [dim](working tree clean)[/dim]"
                if err:
                    body += f"\n[dim]{escape(err[:500])}[/dim]"
                title = "Git Diff — No Changes"
            else:
                # Truncate large diffs but keep useful portion
                truncated = out[:20000] + ("\n… [truncated]" if len(out) > 20000 else "")
                body = f"[bold]Diff:[/bold]\n{escape(truncated)}"
                title = "Git Diff"
            container.mount(Collapsible(Static(body), title=title, collapsed=False))
            container.scroll_end()
        except Exception as e:
            self._add_system_message(f"Git error: {e}")

    def _git_commit(self: SagoApp, msg: str) -> None:
        if not msg:
            self._add_system_message("Usage: /commit <message>")
            return
        self.pending_action = {"type": "git_commit", "message": msg}
        self._show_approval_bar(f'Commit: "{msg}"?  Press [Y] Approve or [N] Deny')

    def _approve_action(self: SagoApp) -> None:
        import threading

        self._hide_approval_bar()

        # 1. Check if executor is paused waiting for tool permission confirmation
        if self._executor_pause_event and isinstance(self._executor_pause_event, threading.Event):
            # Silent resume — no "Approved ..." banner (user says it breaks immersion / alignment)
            self._tool_approved = True  # Mark tool as approved
            self._executor_pause_event.set()  # Resume executor (unblock wait)
            return

        # 2. Check for pending orchestration plan
        if hasattr(self, "pending_orchestration") and self.pending_orchestration:
            plan = self.pending_orchestration.get("plan")
            if plan:
                self.pending_orchestration = None
                self._execute_orchestration_plan(plan)
                return

        # 3. Check for pending git commit or user input
        action = getattr(self, "pending_action", None) or {}
        if action.get("type") == "git_commit":
            try:
                cwd = str(Path.cwd())
                subprocess.run(["git", "-C", cwd, "add", "-A"], capture_output=True, timeout=5)
                r = subprocess.run(
                    ["git", "-C", cwd, "commit", "-m", action["message"]],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                out = (r.stdout or r.stderr or "").strip()[:500] or "Committed"
                self._add_system_message(f"Committed: {out}")
            except Exception as e:
                self._add_system_message(f"Failed: {e}")
        elif action.get("type") == "user_input":
            plan_id = action.get("plan_id")
            todo_id = action.get("todo_id")
            if plan_id and todo_id:
                from sago.tasks import get_task_manager

                tm = get_task_manager()
                user_input = action.get("input", "")
                if user_input:
                    tm.provide_input(plan_id, todo_id, user_input)
                    self._add_system_message(f"Input provided for todo {todo_id}")
        self.pending_action = {}

    def _deny_action(self: SagoApp) -> None:
        import threading

        self._hide_approval_bar()

        # 1. Check if executor is paused waiting for tool permission confirmation
        if self._executor_pause_event and isinstance(self._executor_pause_event, threading.Event):
            self._tool_approved = False  # Mark tool as denied
            self._executor_pause_event.set()  # Resume executor (unblock wait)
            # Silent — no banner
            return

        # 2. Check for pending orchestration plan
        if hasattr(self, "pending_orchestration") and self.pending_orchestration:
            self.pending_orchestration = None
            self._add_system_message("Orchestration plan denied")
            return

        self.pending_action = {}
        self._add_system_message("Denied")

    def _toggle_yolo(self: SagoApp) -> None:
        """Toggle YOLO mode - auto-approve all tool calls."""
        self.yolo_mode = not self.yolo_mode
        # Update permission manager YOLO state
        try:
            from sago.permissions import get_permission_manager

            pm = get_permission_manager()
            pm.set_yolo_mode(self.current_session_id, self.yolo_mode)
            pm.set_global_yolo(self.yolo_mode)
        except Exception as e:
            log_exception(e, "set yolo mode on permission manager")
        if self.yolo_mode:
            self._add_system_message(
                "YOLO MODE ON - All tools will be auto-approved without asking\n"
                "Use with caution! Type /yolo again to disable"
            )
        else:
            self._add_system_message("YOLO MODE OFF - Permissions restored")

    def _handle_perms_command(self: SagoApp, args: str = "") -> None:
        """Handle /perms subcommand dispatch."""
        parts = args.strip().split(None, 1)
        action = parts[0].lower() if parts else "list"
        param = parts[1].strip() if len(parts) > 1 else ""

        if action in ("allow", "unblock"):
            self._allow_tool(param)
        elif action in ("block", "deny"):
            self._block_tool(param)
        elif action == "blocked":
            self._show_permissions("blocked")
        elif action == "allowed":
            self._show_permissions("allowed")
        elif action == "reset":
            from sago.permissions import get_permission_manager

            pm = get_permission_manager()
            pm.config.blocked_tools.clear()
            pm.config.allowed_tools.clear()
            pm._save_config()
            self._add_system_message("Tool permissions reset to default.")
        else:
            self._show_permissions("")

    def _handle_todo_command(self: SagoApp, args: str = "") -> None:
        """Handle /todo subcommand dispatch."""
        parts = args.strip().split(None, 1)
        action = parts[0].lower() if parts else "list"
        param = parts[1].strip() if len(parts) > 1 else ""

        if action == "done" and param:
            self._mark_todo_done(param)
        elif action == "show" and param:
            self._show_todo(param)
        elif action == "done" and not param:
            self._add_system_message("Usage: /todo done <id>")
        elif action and action not in ("list", "all"):
            self._show_todo(action)
        else:
            self._show_plan("")

    def _handle_tasks_command(self: SagoApp, args: str = "") -> None:
        """Handle /tasks subcommand dispatch."""
        parts = args.strip().split(None, 1)
        action = parts[0].lower() if parts else "list"
        param = parts[1].strip() if len(parts) > 1 else ""

        if action == "cancel":
            self._cancel_task(param)
        else:
            self._show_tasks()

    def _show_permissions(self: SagoApp, args: str) -> None:
        from sago.permissions import TOOL_RISK_LEVELS, get_permission_manager

        pm = get_permission_manager()

        if args == "blocked":
            if pm.config.blocked_tools:
                lines = "\n".join(f"  [red]✗[/red] {t}" for t in pm.config.blocked_tools)
                body = f"[bold]Blocked tools:[/bold]\n{lines}"
                container = self.query_one("#messages")
                container.mount(Collapsible(Static(body), title="Blocked Tools", collapsed=True))
            else:
                self._add_system_message("No blocked tools")
        elif args == "allowed":
            if pm.config.allowed_tools:
                lines = "\n".join(f"  [green]✓[/green] {t}" for t in pm.config.allowed_tools)
                body = f"[bold]Allowed tools:[/bold]\n{lines}"
                container = self.query_one("#messages")
                container.mount(Collapsible(Static(body), title="Allowed Tools", collapsed=True))
            else:
                self._add_system_message(
                    "[dim]No explicit allowed list (all tools available)[/dim]"
                )
        else:
            lines = []
            for name, risk in sorted(TOOL_RISK_LEVELS.items()):
                blocked = pm.is_blocked(name)
                status = "[red]BLOCKED[/red]" if blocked else "[green]ok[/green]"
                risk_colors = {
                    "safe": "green",
                    "low": "green",
                    "medium": "yellow",
                    "high": "red",
                    "critical": "red",
                }
                risk_color = risk_colors.get(risk.value, "white")
                lines.append(f"  {name:<25} [{risk_color}]{risk.value:<10}[/{risk_color}] {status}")
            body = "\n".join(lines)
            container = self.query_one("#messages")
            container.mount(
                Collapsible(
                    Static(f"[bold]Tool permissions:[/bold]\n{body}"),
                    title="Permissions",
                    collapsed=True,
                )
            )

    def _allow_tool(self: SagoApp, tool_name: str) -> None:
        if not tool_name:
            self._add_system_message("Usage: /allow <tool_name>")
            return
        from sago.permissions import get_permission_manager

        pm = get_permission_manager()
        if tool_name in pm.config.blocked_tools:
            pm.config.blocked_tools.remove(tool_name)
            pm._save_config()
            self._add_system_message(f"Unblocked: {tool_name}")
        else:
            self._add_system_message(f"Not blocked: {tool_name}")

    def _block_tool(self: SagoApp, tool_name: str) -> None:
        if not tool_name:
            self._add_system_message("Usage: /block <tool_name>")
            return
        from sago.permissions import get_permission_manager

        pm = get_permission_manager()
        if tool_name not in pm.config.blocked_tools:
            pm.config.blocked_tools.append(tool_name)
            pm._save_config()
            self._add_system_message(f"Blocked: {tool_name}")
        else:
            self._add_system_message(f"Already blocked: {tool_name}")

    def _show_plan(self: SagoApp, args: str) -> None:
        try:
            self._show_plan_inner(args)
        except Exception as e:
            import logging

            logging.getLogger("sago.tui.commands").exception("_show_plan crashed")
            self._add_system_message(f"Plan display error: {e}")

    def _show_plan_inner(self: SagoApp, args: str) -> None:
        raw = args.strip()
        if raw and raw.lower() not in ("status", "list", "show"):
            # Interactive planning mode for user task!
            self._hide_welcome_screen()
            self._add_to_history(f"/plan {raw}")
            self._add_user_message(f"/plan {raw}")

            planning_prompt = (
                f"You are operating in rigorous PLANNING MODE. Create a comprehensive implementation plan for the following task before making any changes:\n\n"
                f"**Task**: {raw}\n\n"
                f"Please research the codebase thoroughly and format the plan as follows:\n"
                f"### 1. Goal & Requirements\n"
                f"- Clear summary of what will be implemented or resolved.\n\n"
                f"### 2. Architecture & Proposed File Changes\n"
                f"- Specific files to create, modify, or delete, including key functions, classes, and logic flow.\n\n"
                f"### 3. Step-by-Step Execution Plan\n"
                f"- Numbered, ordered implementation checklist.\n\n"
                f"### 4. Verification & Testing Plan\n"
                f"- Exact commands and automated tests to run to verify the solution.\n\n"
                f"---\n"
                f"**CRITICAL INSTRUCTION**: Do NOT make code changes or run modifying commands yet. "
                f"Conclude by asking for the user's review and explicit confirmation (e.g. `Type 'y' or 'proceed' to execute this plan, or provide feedback to refine.`)."
            )
            self._process_message(planning_prompt)
            return

        from sago.tasks import TaskStatus, get_task_manager

        tm = get_task_manager()
        plan = tm.get_active_plan()
        if not plan:
            self._add_system_message(
                "No active plan in memory.\nUsage: `/plan <task description>` — Researches codebase and generates a step-by-step implementation plan for your review before executing."
            )
            return

        container = self.query_one("#messages")

        # Build status counts
        done = sum(1 for t in plan.todos if t.status == TaskStatus.COMPLETED)
        total = len(plan.todos)
        in_progress = sum(1 for t in plan.todos if t.status == TaskStatus.IN_PROGRESS)
        pending = sum(1 for t in plan.todos if t.status == TaskStatus.PENDING)

        plan_title = getattr(plan, "description", None) or getattr(plan, "goal", "Untitled")
        header = f"Plan: {plan_title[:60]}\nProgress: {done}/{total} done"
        if in_progress:
            header += f" | {in_progress} in progress"
        if pending:
            header += f" | {pending} pending"

        # Build step list with status icons
        step_lines = []
        for i, todo in enumerate(plan.todos):
            status_icon = {
                TaskStatus.COMPLETED: "\033[32m✓\033[0m",
                TaskStatus.IN_PROGRESS: "\033[33m⟳\033[0m",
                TaskStatus.FAILED: "\033[31m✗\033[0m",
                TaskStatus.WAITING: "\033[36m◎\033[0m",
                TaskStatus.SKIPPED: "\033[90m⊘\033[0m",
            }.get(todo.status, "\033[90m○\033[0m")
            step_lines.append(f"  {status_icon} {i + 1}. {todo.description[:70]}")

        body = "\n".join(step_lines)

        from rich.text import Text

        body_text = Text.from_ansi(body)

        container.mount(
            Collapsible(
                Static(body_text),
                title=header,
                collapsed=True,
            )
        )
        container.scroll_end()

    def _show_todo(self: SagoApp, args: str) -> None:
        try:
            from sago.tasks import get_task_manager

            tm = get_task_manager()
            plan = tm.get_active_plan()
            if plan:
                for todo in plan.todos:
                    if todo.id == args or args in todo.description:
                        self._add_system_message(
                            f"[{todo.id}] {todo.description}\nStatus: {todo.status.value}"
                        )
                        return
                self._add_system_message(f"Todo not found: {args}")
            else:
                self._add_system_message("No active plan")
        except Exception as e:
            import logging

            logging.getLogger("sago.tui.commands").exception("_show_todo crashed")
            self._add_system_message(f"Todo display error: {e}")

    def _show_all_todos(self: SagoApp) -> None:
        self._show_plan("")

    def _mark_todo_done(self: SagoApp, todo_id: str) -> None:
        try:
            from sago.tasks import get_task_manager

            tm = get_task_manager()
            plan = tm.get_active_plan()
            if plan:
                tm.complete_todo(plan.id, todo_id, result="Marked done by user")
                next_todo = plan.current_todo
                if next_todo:
                    self._add_system_message(f"Next: [{next_todo.id}] {next_todo.description}")
                else:
                    self._add_system_message("All todos completed! 🎉")
            else:
                self._add_system_message(f"Todo {todo_id} not found")
        except Exception as e:
            import logging

            logging.getLogger("sago.tui.commands").exception("_mark_todo_done crashed")
            self._add_system_message(f"Todo update error: {e}")

    def _ask_user(self: SagoApp, message: str) -> None:
        try:
            if not message:
                self._add_system_message("Usage: /ask <question for user>")
                return
            from sago.tasks import get_task_manager

            tm = get_task_manager()
            plan = tm.get_active_plan()
            if plan:
                current = plan.current_todo
                if current:
                    tm.wait_for_input(plan.id, current.id, message)
                    self.pending_action = {
                        "type": "user_input",
                        "plan_id": plan.id,
                        "todo_id": current.id,
                    }
                    self._show_approval_bar(f"Input needed: {message}")
            else:
                self._add_system_message(f"❓ {message}")
        except Exception as e:
            import logging

            logging.getLogger("sago.tui.commands").exception("_ask_user crashed")
            self._add_system_message(f"Ask error: {e}")

    def _undo_change(self: SagoApp) -> None:
        """Undo the last file change."""
        try:
            from sago.memory.change_tracker import get_change_tracker

            tracker = get_change_tracker()
            undone_path = tracker.undo_last()
            if undone_path:
                self._add_system_message(f"Undid change to: {undone_path}")
            else:
                self._add_system_message("No changes to undo")
        except Exception as e:
            import logging

            logging.getLogger("sago.tui.commands").exception("_undo_change crashed")
            self._add_system_message(f"Undo error: {e}")

    def _show_changes(self: SagoApp) -> None:
        """Show all file changes this session."""
        try:
            from sago.memory.change_tracker import get_change_tracker

            tracker = get_change_tracker()
            summary = tracker.get_diff_summary()
            self._add_system_message(summary)
        except Exception as e:
            import logging

            logging.getLogger("sago.tui.commands").exception("_show_changes crashed")
            self._add_system_message(f"Changes display error: {e}")

    # ========================================================================
    # PARALLEL EXECUTION COMMANDS
    # ========================================================================

    def _run_parallel(self: SagoApp, args: str) -> None:
        """Run multiple agents in parallel, each with its own task or a shared task.

        Formats:
          /parallel agent1: task1, agent2: task2    — per-agent tasks
          /parallel agent1,agent2 shared task        — same task for all
        """
        agent_tasks: list[tuple[str, str]] = []
        shared_task = ""

        # Try per-agent format first: "agent1: task1, agent2: task2"
        # Split on comma followed by optional space and a word-: pattern
        segments = re.split(r",\s*(?=\w[\w-]*\s*:)", args)
        for seg in segments:
            seg = seg.strip()
            if ":" in seg:
                colon_idx = seg.index(":")
                agent_part = seg[:colon_idx].strip()
                task_part = seg[colon_idx + 1 :].strip()
                if (
                    agent_part
                    and task_part
                    and re.match(r"^[\w-]+$", agent_part)
                    and len(agent_part) < 40
                ):
                    agent_name = agent_part.lower().replace("_", "-")
                    agent_tasks.append((agent_name, task_part))

        if not agent_tasks:
            # Fall back to shared-task format: "agent1,agent2,... shared task"
            parts = args.split(None, 1)
            if len(parts) < 2:
                self._add_system_message(
                    "Usage:\n"
                    "  /parallel agent1: task1, agent2: task2\n"
                    "  /parallel agent1,agent2 shared task"
                )
                return
            agent_list_str, shared_task = parts
            agents = [a.strip() for a in agent_list_str.split(",") if a.strip()]
            if len(agents) < 2:
                self._add_system_message(
                    f"Need at least 2 agents. Got: {agents[0] if agents else 'none'}\n"
                    "Example: /parallel python-engineer,go-engineer build a web page"
                )
                return
            agent_tasks = [(a, shared_task) for a in agents]

        if len(agent_tasks) < 2:
            self._add_system_message(
                "Need at least 2 agents.\n"
                "Example: /parallel python-engineer: build api, reviewer: review code"
            )
            return

        agents = [a for a, _ in agent_tasks]
        task_display = " | ".join(f"@{a}: {t[:40]}" for a, t in agent_tasks)

        self._add_command_turn(
            "parallel",
            task_display,
            meta=",".join(agents),
            tag_label="PARALLEL",
            tag_color="#f09483",
        )

        self._process_parallel(agent_tasks)

    def _toggle_dashboard(self: SagoApp) -> None:
        """Toggle the agent dashboard sidebar safely."""
        try:
            if hasattr(self, "_dashboard_visible"):
                self._dashboard_visible = not self._dashboard_visible
            else:
                self._dashboard_visible = True

            dashboards = self.query("#agent-dashboard")
            if not dashboards:
                return
            dashboard = dashboards[0]

            if self._dashboard_visible:
                dashboard.remove_class("hidden")
                self._update_dashboard()
                self._add_system_message("Dashboard: ON")
            else:
                dashboard.add_class("hidden")
                self._add_system_message("Dashboard: OFF")
        except Exception as e:
            self._add_system_message(f"Dashboard toggle note: {e}")

    def _show_tasks(self: SagoApp) -> None:
        """Show all background tasks."""
        from sago.tui.widgets import AgentStatus, get_task_manager

        tm = get_task_manager()
        tasks = tm.get_all_tasks()
        if not tasks:
            self._add_system_message("No background tasks")
            return

        status_icons = {
            AgentStatus.IDLE: "○",
            AgentStatus.RUNNING: "⟳",
            AgentStatus.WAITING: "◎",
            AgentStatus.COMPLETED: "✓",
            AgentStatus.FAILED: "✗",
            AgentStatus.CANCELLED: "⊘",
        }

        lines = [f"Background Tasks ({len(tasks)}):"]
        for t in tasks:
            icon = status_icons.get(t.status, "?")
            elapsed = f"{t.elapsed:.1f}s" if t.elapsed > 0 else "..."
            tool_info = f" | {t.current_tool}" if t.current_tool else ""
            lines.append(
                f"  {icon} {t.agent_id} [{t.agent_name}] {t.status.value} {elapsed}{tool_info}"
            )
            lines.append(f"    Task: {t.task[:60]}")
        self._add_system_message("\n".join(lines))

    def _cancel_task(self: SagoApp, args: str) -> None:
        """Cancel a background task."""
        from sago.tui.widgets import get_task_manager

        tm = get_task_manager()
        if not args or args.strip() == "":
            self._add_system_message("Usage: /cancel <task-id> or /cancel all")
            return

        if args.strip() == "all":
            count = tm.cancel_all()
            self._add_system_message(f"Cancelled {count} tasks")
            return

        task_id = args.strip()
        if tm.cancel_task(task_id):
            self._add_system_message(f"Cancelled: {task_id}")
        else:
            self._add_system_message(f"Task not found or not running: {task_id}")

    def _show_handoff(self: SagoApp) -> None:
        """Show handoff graph for current agent chain."""
        from sago.agents.registry import get_agent

        agent = get_agent(self.current_agent)
        if agent and agent.handoff_to:
            lines = [f"Handoff targets for {self.current_agent}:"]
            for target in agent.handoff_to:
                lines.append(f"  → {target}")
            self._add_system_message("\n".join(lines))
        else:
            self._add_system_message(f"No handoff targets for {self.current_agent}")

    def _list_agents_color(self: SagoApp) -> None:
        """List agents with their assigned colors."""
        from sago.tui.widgets import get_agent_color

        try:
            from sago.agents.registry import list_agents

            agents = list_agents()
            lines = [f"[bold]Agents ({len(agents)}):[/bold]"]
            for a in agents[:50]:
                color = get_agent_color(a["name"])
                lines.append(f"  [{color}]●[/{color}] [cyan]{a['name']}[/cyan]")
            if len(agents) > 50:
                lines.append(f"  [dim]... and {len(agents) - 50} more[/dim]")
            body = "\n".join(lines)
            container = self.query_one("#messages")
            container.mount(
                Collapsible(
                    Static(body),
                    title=f"Agents ({len(agents)})",
                    collapsed=True,
                )
            )
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _toggle_summary(self: SagoApp) -> None:
        """Toggle summary display after each task."""
        self.show_summary = not self.show_summary
        if self.show_summary:
            self._add_system_message("Summary: ON — tool usage summary will appear after each task")
        else:
            self._add_system_message("Summary: OFF")

    def _show_repo_map(self: SagoApp, query: str = "") -> None:
        """Generate and display compact, structured AST symbol repo map."""
        from rich.markdown import Markdown

        from sago.memory.symbol_graph import SymbolGraph
        from sago.tui.helpers import create_collapsible

        try:
            graph = SymbolGraph()
            clean_map = graph.generate_clean_tui_map(filter_query=query.strip() or None)

            container = self.query_one("#messages")
            md_widget = Markdown(clean_map, code_theme="monokai")
            title = (
                f"Symbol Repo Map ({graph.root_dir.name})"
                if not query
                else f"Symbol Repo Map (filter: {query})"
            )
            container.mount(
                create_collapsible(
                    Static(md_widget),
                    title=title,
                    collapsed=False,
                )
            )
            container.scroll_end(animate=False)
        except Exception as e:
            self._add_system_message(f"Error generating repo map: {e}")

    def _show_project_graph(self: SagoApp, args: str = "") -> None:
        """Generate and display comprehensive architecture, process map & data graph asynchronously."""
        import threading

        from sago.memory.project_graph import get_cached_project_graph

        try:
            parts = args.strip().split()
            view = "dashboard"
            focus = None
            target_dir = None

            for p in parts:
                p_lower = p.lower()
                if p_lower in (
                    "dashboard",
                    "all",
                    "arch",
                    "architecture",
                    "process",
                    "pipeline",
                    "er",
                    "data",
                    "models",
                    "tree",
                    "ascii",
                    "flow",
                    "flowchart",
                    "mermaid",
                    "json",
                    "llm",
                    "ai",
                    "review",
                    "analysis",
                    "summary",
                ):
                    view = p_lower
                else:
                    expanded = Path(p).expanduser().resolve()
                    if expanded.is_dir():
                        target_dir = expanded
                    else:
                        focus = p

            root_path = target_dir or Path.cwd()
            self._add_system_message(
                f"⚡ Analyzing codebase architecture & topology in background for '{root_path.name}' (view: {view})..."
            )
            self.is_thinking = True

            def _worker() -> None:
                try:
                    pg = get_cached_project_graph(root_dir=root_path, max_files=1500)

                    if view in ("ai", "review", "analysis", "summary"):
                        content = pg.to_ai_architectural_analysis(
                            provider=getattr(self, "current_provider", "openrouter"),
                            model=getattr(self, "current_model", "openrouter/auto"),
                        )
                        title = f"AI Architectural Analysis & Review: {root_path.name}"
                        render_text = content
                    elif view in ("arch", "architecture"):
                        content = pg.to_architecture_diagram()
                        title = f"System Architecture Map — Layered Box Diagram ({len(pg.nodes)} components)"
                        render_text = f"```text\n{content}\n```"
                    elif view in ("process", "pipeline"):
                        content = pg.to_process_map()
                        title = f"Execution & Lifecycle Pipeline ({len(pg.nodes)} components)"
                        render_text = f"```text\n{content}\n```"
                    elif view in ("er", "data", "models"):
                        content = pg.to_er_diagram()
                        title = f"Entity Relationship & Data Model Map ({len(pg.data_models)} models/schemas)"
                        render_text = f"```text\n{content}\n```"
                    elif view in ("flow", "flowchart"):
                        content = pg.to_visual_flowchart(focus_filter=focus)
                        title = (
                            f"Component Dependency & Data Flow Pipeline ({len(pg.edges)} relations)"
                        )
                        render_text = f"```text\n{content}\n```"
                    elif view in ("tree", "ascii"):
                        content = pg.to_ascii_tree()
                        title = f"File Dependency & Data Model Tree ({len(pg.nodes)} nodes, {len(pg.edges)} relations)"
                        render_text = f"```text\n{content}\n```"
                    elif view == "mermaid":
                        render_text = pg.to_mermaid(focus_filter=focus)
                        title = f"Project Graph (Mermaid Flowchart - {len(pg.nodes)} components)"
                    elif view == "json":
                        import json

                        raw_json = json.dumps(pg.to_dict(), indent=2)
                        render_text = f"```json\n{raw_json}\n```"
                        title = (
                            f"Project Graph (JSON - {len(pg.nodes)} nodes, {len(pg.edges)} edges)"
                        )
                    elif view == "llm":
                        render_text = pg.to_llm_context()
                        title = "Project Topology & Hub Summary"
                    else:
                        # Curated Consolidated Dashboard
                        render_text = pg.to_curated_dashboard(
                            focus_filter=focus,
                            provider=getattr(self, "current_provider", "openrouter"),
                            model=getattr(self, "current_model", "openrouter/auto"),
                        )
                        title = f"SAGO Architecture & Process Graph Dashboard ({len(pg.nodes)} components)"

                    def _mount_result() -> None:
                        from rich.markdown import Markdown

                        from sago.tui.helpers import create_collapsible

                        container = self.query_one("#messages")
                        md_widget = Markdown(render_text, code_theme="monokai")
                        c = create_collapsible(
                            Static(md_widget),
                            title=title,
                            collapsed=True,
                        )
                        container.mount(c)
                        try:
                            container.scroll_end(animate=False)
                            self.query_one("#msg-input").focus()
                        except Exception as e:
                            logger.debug("scroll/focus after graph mount failed: %s", e)
                        self.is_thinking = False

                    self.call_from_thread(_mount_result)
                except Exception as ex:
                    err_msg = str(ex)

                    def _mount_error() -> None:
                        self._add_system_message(f"Error generating graph: {err_msg}")
                        try:
                            self.query_one("#msg-input").focus()
                        except Exception as e:
                            logger.debug("focus msg-input on graph error failed: %s", e)
                        self.is_thinking = False

                    self.call_from_thread(_mount_error)

            threading.Thread(target=_worker, daemon=True).start()
        except Exception as e:
            self.is_thinking = False
            try:
                self.query_one("#msg-input").focus()
            except Exception as e:
                logger.debug("focus msg-input after graph error failed: %s", e)
            self._add_system_message(f"Error generating project graph: {e}")

    def _run_verify(self: SagoApp) -> None:
        """Run automated multi-language verifier."""
        from sago.engine.verifier import ProjectVerifier

        try:
            self._add_system_message("Running linters, type checks, and tests...")
            verifier = ProjectVerifier()
            report = verifier.verify_project()
            container = self.query_one("#messages")
            if report.passed:
                container.mount(
                    Collapsible(
                        Static("[bold green]✓ ALL CHECKS PASSED[/bold green]\n" + report.summary),
                        title="Verification Passed",
                        collapsed=True,
                    )
                )
            else:
                container.mount(
                    Collapsible(
                        Static(report.to_prompt_feedback()),
                        title="[bold red]Verification Failed[/bold red]",
                        collapsed=True,
                    )
                )
        except Exception as e:
            self._add_system_message(f"Error running verification: {e}")

    def _show_skills(self: SagoApp, filter_query: str = "") -> None:
        """Display available built-in and workspace skills."""
        from sago.skills.loader import SkillLoader
        from sago.skills.registry import list_skills

        try:
            builtin = list_skills()
            custom = SkillLoader.discover_skills()
            lines = [f"[bold]Available Skills ({len(builtin) + len(custom)}):[/bold]\n"]

            if custom:
                lines.append("[bold cyan]Workspace & Custom Skills:[/bold cyan]")
                for name, sk in sorted(custom.items()):
                    if (
                        filter_query
                        and filter_query.lower() not in name.lower()
                        and filter_query.lower() not in sk.description.lower()
                    ):
                        continue
                    tools_str = f" [dim](tools: {', '.join(sk.tools)})[/dim]" if sk.tools else ""
                    lines.append(
                        f"  • [bold yellow]{name:<18}[/bold yellow] {sk.description}{tools_str}"
                    )
                lines.append("")

            lines.append("[bold cyan]Built-in Capabilities:[/bold cyan]")
            for sk in builtin:
                if (
                    filter_query
                    and filter_query.lower() not in sk.name.lower()
                    and filter_query.lower() not in sk.description.lower()
                ):
                    continue
                tools_str = f" [dim](tools: {', '.join(sk.tools[:4])})[/dim]" if sk.tools else ""
                lines.append(
                    f"  • [bold green]{sk.name:<18}[/bold green] {sk.description}{tools_str}"
                )

            container = self.query_one("#messages")
            container.mount(
                Collapsible(
                    Static("\n".join(lines)),
                    title=f"Skills ({len(builtin) + len(custom)})",
                    collapsed=True,
                )
            )
            container.scroll_end()
        except Exception as e:
            self._add_system_message(f"Error listing skills: {e}")

    def _show_plugins(self: SagoApp) -> None:
        """Display installed third-party plugins."""
        from sago.plugins.base import get_plugin_manager

        try:
            pm = get_plugin_manager()
            plugins = pm.list_plugins()
            if not plugins:
                self._add_system_message(
                    "No external plugins loaded. Place Python plugins in .sago/plugins/ or ~/.sago/plugins/"
                )
                return

            lines = [f"[bold]Installed Plugins ({len(plugins)}):[/bold]\n"]
            for p in plugins:
                status = "[green]ENABLED[/green]" if p.enabled else "[dim]DISABLED[/dim]"
                lines.append(
                    f"• [bold cyan]{p.name}[/bold cyan] v{p.version} ({p.author}) - {status}\n  {p.description}"
                )

            container = self.query_one("#messages")
            container.mount(
                Collapsible(
                    Static("\n".join(lines)),
                    title=f"Plugins ({len(plugins)})",
                    collapsed=True,
                )
            )
            container.scroll_end()
        except Exception as e:
            self._add_system_message(f"Error listing plugins: {e}")

    def _handle_mcp_command(self: SagoApp, args: str = "") -> None:
        """Handle /mcp [list|test|reload] command."""
        from sago.mcp.manager import get_mcp_manager

        mgr = get_mcp_manager()
        parts = args.strip().split(None, 1)
        subcmd = parts[0].lower() if parts else "list"
        subargs = parts[1].strip() if len(parts) > 1 else ""

        if subcmd in ("reload", "refresh"):
            mgr._servers.clear()
            mgr._load_configurations()
            tools = mgr.get_mcp_tools()
            self._add_system_message(
                f"🔄 MCP Servers reloaded: {len(mgr.list_servers())} servers configured, {len(tools)} remote tools bridged."
            )
        elif subcmd == "test":
            if not subargs:
                self._add_system_message("Usage: `/mcp test <server_name>`")
                return
            res = mgr.test_server(subargs)
            if res.get("success"):
                t_list = ", ".join(res.get("tools", [])) or "none"
                self._add_system_message(
                    f"✅ [bold green]MCP Server '{subargs}' Connected[/bold green]\n"
                    f"Exposed {res.get('tool_count', 0)} tools: {t_list}"
                )
            else:
                self._add_system_message(
                    f"❌ [bold red]MCP Server '{subargs}' Connection Failed[/bold red]: {res.get('error')}"
                )
        else:
            servers = mgr.list_servers()
            tools = mgr.get_mcp_tools()
            if not servers:
                self._add_system_message(
                    "No MCP servers configured.\n"
                    "Define servers in `.sago/mcp_servers.json` or `~/.sago/mcp_servers.json`:\n"
                    '```json\n{\n  "mcpServers": {\n    "sqlite": {\n      "command": "uvx",\n      "args": ["mcp-server-sqlite", "--db-path", "test.db"]\n    }\n  }\n}\n```'
                )
                return
            lines = [f"[bold]Configured MCP Servers ({len(servers)}):[/bold]\n"]
            for s in servers:
                target = s.url if s.url else f"{s.command} {' '.join(s.args)}"
                status = "[green]ENABLED[/green]" if s.enabled else "[dim]DISABLED[/dim]"
                lines.append(
                    f"  • [bold cyan]{s.name:<16}[/bold cyan] {status} - [dim]{target}[/dim]"
                )

            if tools:
                lines.append(f"\n[bold green]Bridged MCP Tools ({len(tools)}):[/bold green]")
                for t in tools:
                    lines.append(f"  • [bold yellow]{t.name:<24}[/bold yellow] {t.description}")

            lines.append("\n[dim]Commands: /mcp test <server> | /mcp reload[/dim]")
            container = self.query_one("#messages")
            container.mount(
                Collapsible(
                    Static("\n".join(lines)),
                    title=f"MCP Servers ({len(servers)} configured, {len(tools)} tools)",
                    collapsed=False,
                )
            )
            container.scroll_end()

    def _set_theme(self: SagoApp, name: str) -> None:
        """Switch or list available TUI color themes."""
        from sago.tui.models import THEMES as themes

        name = name.strip().lower()
        if not name or name == "list":
            current = getattr(self, "sago_theme", "obsidian")
            lines = [
                f"[bold]Active Theme:[/bold] [cyan]{current}[/cyan]\n",
                "[bold]Available Themes:[/bold]",
            ]
            for k, desc in themes.items():
                marker = " [bold green]● (active)[/bold green]" if k == current else ""
                lines.append(f"  • [bold cyan]/theme {k:<15}[/bold cyan] {desc}{marker}")
            self._add_system_message("\n".join(lines))
            return

        if name not in themes:
            self._add_system_message(
                f"Unknown theme '{name}'. Available options: {', '.join(themes.keys())}"
            )
            return

        try:
            # Remove previous theme classes
            for t in themes:
                self.screen.remove_class(f"theme-{t}")

            self.sago_theme = name
            self.screen.add_class(f"theme-{name}")
            self._add_system_message(f"Switched theme to {themes[name]}")
        except Exception as e:
            self._add_system_message(f"Failed to switch theme: {e}")

    def _collapse_chats(self: SagoApp, action: str = "") -> None:
        """Collapse or expand all chat turns in the message pane."""
        from textual.widgets import Collapsible

        from sago.tui.helpers import ExchangeTurnCard

        action = action.strip().lower()
        messages_container = self.query_one("#messages")
        turn_cards = list(messages_container.query(ExchangeTurnCard))
        collapsibles = list(messages_container.query(Collapsible))

        if not turn_cards and not collapsibles:
            self._add_system_message("No chat turns to collapse.")
            return

        if action in ("expand", "all-open", "open"):
            for card in turn_cards:
                if card.is_turn_collapsed:
                    card.toggle_collapse()
            for c in collapsibles:
                c.collapsed = False
            self._add_system_message("Expanded all chat turns and cards.")
        else:
            for card in turn_cards:
                if not card.is_turn_collapsed:
                    card.toggle_collapse()
            for c in collapsibles:
                c.collapsed = True
            self._add_system_message("Collapsed all chat turns and cards.")

    def _handle_developer_command(self: SagoApp, args: str = "") -> None:
        """Handle /developer or /dev command."""
        from sago.tracking.dev_tracer import get_dev_tracer

        tracer = get_dev_tracer()
        parts = args.strip().split(None, 1)
        action = parts[0].lower() if parts else ""
        subarg = parts[1] if len(parts) > 1 else ""

        if action in ("on", "enable", "1", "true"):
            self.developer_mode = True
            tracer.set_enabled(True)
            msg = (
                "[bold red] ⚡ SAGO DEVELOPER MODE ACTIVATED                             [/bold red]\n"
                "  • [bold cyan]Deep Tracing[/bold cyan]: LLM payloads, token metrics, exact tool parameters\n"
                "  • [bold magenta]Telemetry[/bold magenta]: Microsecond function duration & state transitions\n"
                "  • [bold yellow]Commands[/bold yellow]: `/dev logs` | `/dev traces` | `/dev export <file>` | `/dev off`"
            )
            self._add_system_message(msg)
        elif action in ("off", "disable", "0", "false"):
            self.developer_mode = False
            tracer.set_enabled(False)
            self._add_system_message("⚡ (DEV MODE OFF) Developer diagnostics disabled.")
        elif action in ("export", "save"):
            parts_export = subarg.split()
            export_type = parts_export[0].lower() if parts_export else "json"
            target_path = parts_export[1] if len(parts_export) > 1 else None

            if export_type in ("otel", "opentelemetry"):
                import json

                from sago.tracking.otel_exporter import OTelExporter

                payload = OTelExporter().export_traces(tracer.get_events())
                out_path = Path(target_path or "sago_otel_traces.json").resolve()
                out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                self._add_system_message(
                    f"● [bold green]OpenTelemetry Traces Exported[/bold green]:\n  `{out_path}`"
                )
            elif export_type in ("prometheus", "metrics", "prom"):
                from sago.tracking.otel_exporter import PrometheusExporter

                metrics_text = PrometheusExporter().export_metrics(tracer.get_events())
                out_path = Path(target_path or "sago_metrics.prom").resolve()
                out_path.write_text(metrics_text, encoding="utf-8")
                self._add_system_message(
                    f"● [bold green]Prometheus Metrics Exported[/bold green]:\n  `{out_path}`"
                )
            else:
                fmt = "md" if subarg.endswith(".md") else "json"
                success, res = tracer.export_traces(file_path=subarg or None, format=fmt)
                if success:
                    from rich.markup import escape

                    self._add_system_message(
                        f"● [bold green]Traces Exported Successfully[/bold green]:\n  `{escape(str(res))}`"
                    )
                else:
                    from rich.markup import escape

                    self._add_system_message(
                        f"● [bold red]Export Failed[/bold red]: {escape(str(res))}"
                    )
        elif action in ("clear", "reset"):
            tracer.clear()
            self._add_system_message("⚡ Developer trace telemetry buffer cleared.")
        elif action in ("view", "popup", "deep", "debug"):
            # Open the deep trace viewer popup
            events = tracer.get_recent_traces(limit=500)
            if not events:
                self._add_system_message(
                    "⚡ No traces to view. Run some tasks first with `/dev on`."
                )
                return
            try:
                from sago.tui.trace_viewer import TraceViewerScreen

                self.push_screen(TraceViewerScreen(events))
            except Exception as e:
                self._add_system_message(f"⚡ Trace viewer error: {e}")
        elif action in ("logs", "log", "traces", "trace"):
            traces = tracer.get_recent_traces(limit=25)
            if not traces:
                self._add_system_message("⚡ No developer traces recorded yet.")
                return

            from rich.markup import escape

            lines = ["[bold red]═══ SAGO DEVELOPER EXECUTION TRACES ═══[/bold red]"]
            for t in traces:
                lines.append(f"  {escape(t.format_line())}")
                if t.data:
                    data_str = ", ".join(f"{k}={escape(str(v)[:80])}" for k, v in t.data.items())
                    lines.append(f"    [dim]↳ data: {data_str}[/dim]")
            lines.append("\n[dim]To export to file: /dev export <filepath.json|filepath.md>[/dim]")
            self._add_system_message("\n".join(lines))
        else:
            # Toggle mode
            current = getattr(self, "developer_mode", False)
            self.developer_mode = not current
            tracer.set_enabled(self.developer_mode)
            state_str = (
                "[bold red]ENABLED[/bold red]" if self.developer_mode else "[dim]DISABLED[/dim]"
            )
            self._add_system_message(
                f"⚡ Developer Mode is now {state_str}.\nUsage: `/dev <on|off|logs|traces|export|clear>`"
            )

    def _handle_checkpoint_command(self: SagoApp, args: str = "") -> None:
        """Handle /checkpoint [create|list|restore] command."""
        from sago.engine.checkpoint import get_checkpoint_manager

        mgr = get_checkpoint_manager()
        parts = args.strip().split(None, 1)
        subcmd = parts[0].lower() if parts else "list"
        subargs = parts[1] if len(parts) > 1 else ""

        if subcmd == "create":
            cp = mgr.create_checkpoint(description=subargs or "TUI Manual Snapshot")
            self._add_system_message(
                f"● [bold green]Checkpoint Created[/bold green]: `{cp.checkpoint_id}` ({len(cp.file_paths)} files snapshot)\n[dim]{cp.description}[/dim]"
            )
        elif subcmd == "restore":
            if not subargs:
                self._add_system_message("Usage: /checkpoint restore <checkpoint-id>")
                return
            res = mgr.restore_checkpoint(subargs.strip())
            if res.get("success"):
                self._add_system_message(
                    f"● [bold green]Restored[/bold green]: Successfully restored {res.get('restored_count', 0)} files from {subargs.strip()}"
                )
            else:
                self._add_system_message(
                    f"● [bold red]Restore Failed[/bold red]: {res.get('error')}"
                )
        elif subcmd in ("prune", "clean"):
            keep = 3
            if subargs and subargs.strip().isdigit():
                keep = int(subargs.strip())
            deleted = mgr.prune_checkpoints(keep_latest=keep)
            self._add_system_message(
                f"● [bold green]Checkpoints Pruned[/bold green]: Removed {len(deleted)} old snapshots (retaining newest {keep})"
            )
        else:
            import time

            cps = mgr.list_checkpoints(limit=10)
            if not cps:
                self._add_system_message(
                    "No checkpoints found. Create one with: `/checkpoint create <description>`"
                )
                return
            lines = ["[bold cyan]═══ WORKSPACE CHECKPOINTS ═══[/bold cyan]"]
            for cp in cps:
                t_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(cp.timestamp))
                lines.append(
                    f"  • `{cp.checkpoint_id}` - [dim]{t_str}[/dim] ({len(cp.file_paths)} files) - {cp.description}"
                )
            lines.append(
                "\n[dim]To restore: /checkpoint restore <id> | To prune: /checkpoint prune <keep>[/dim]"
            )
            self._add_system_message("\n".join(lines))

    def _handle_clean_command(self: SagoApp, args: str = "") -> None:
        """Handle /clean and /gc garbage collection command.

        Usage: /clean [mode] [--confirm]
        Modes: all, cache, backups, checkpoints, db, logs
        Default: dry-run showing what would be deleted
        Add --confirm to actually delete
        """
        from sago.cleanup import run_cleanup

        args_lower = args.strip().lower() if args else ""
        confirm = "--confirm" in args_lower
        mode = args_lower.replace("--confirm", "").strip() or "all"

        clean_cache = mode in ("all", "cache", "caches")
        clean_backup = mode in ("all", "backups", "backup")
        clean_chkpt = mode in ("all", "checkpoints", "checkpoint")
        clean_db = mode in ("all", "db", "database", "sessions")
        clean_log = mode in ("all", "logs", "log")

        if not any([clean_cache, clean_backup, clean_chkpt, clean_db, clean_log]):
            clean_cache = clean_backup = clean_chkpt = clean_db = clean_log = True

        # Always do dry-run first to show what would be deleted
        dry_run_results = run_cleanup(
            clean_cache=clean_cache,
            clean_backup=clean_backup,
            clean_chkpt=clean_chkpt,
            clean_db=clean_db,
            clean_log=clean_log,
            dry_run=True,
        )

        total_would_delete = sum(r.items_deleted for r in dry_run_results)
        total_would_reclaim = sum(r.bytes_reclaimed for r in dry_run_results)

        lines = ["[bold cyan]═══ SAGO GARBAGE COLLECTION (DRY RUN) ═══[/bold cyan]"]
        for r in dry_run_results:
            if r.items_deleted > 0:
                lines.append(
                    f"  • [bold]{r.category}:[/bold] {', '.join(r.details) if r.details else 'No items to clean'}"
                )

        if total_would_reclaim < 1024 * 1024:
            rec_str = f"{total_would_reclaim / 1024:.1f} KB"
        else:
            rec_str = f"{total_would_reclaim / (1024 * 1024):.2f} MB"

        if total_would_delete == 0:
            lines.append("\n[bold green]✓ Nothing to clean[/] - database is already optimized.")
            self._add_system_message("\n".join(lines))
            return

        lines.append(
            f"\n[bold yellow]Would delete:[/] {total_would_delete} items, {rec_str} disk space"
        )

        if not confirm:
            lines.append("\n[bold]To execute cleanup:[/] /clean {mode} --confirm")
            self._add_system_message("\n".join(lines))
            return

        # Execute actual cleanup
        results = run_cleanup(
            clean_cache=clean_cache,
            clean_backup=clean_backup,
            clean_chkpt=clean_chkpt,
            clean_db=clean_db,
            clean_log=clean_log,
            dry_run=False,
        )

        total_reclaimed = sum(r.bytes_reclaimed for r in results)
        total_items = sum(r.items_deleted for r in results)

        lines = ["[bold cyan]═══ SAGO GARBAGE COLLECTION ═══[/bold cyan]"]
        for r in results:
            lines.append(
                f"  • [bold]{r.category}:[/bold] {', '.join(r.details) if r.details else 'Cleaned'}"
            )

        if total_reclaimed < 1024 * 1024:
            rec_str = f"{total_reclaimed / 1024:.1f} KB"
        else:
            rec_str = f"{total_reclaimed / (1024 * 1024):.2f} MB"

        lines.append(
            f"\n[bold green]✓ Cleanup complete:[/] {total_items} items purged, [bold cyan]{rec_str}[/bold cyan] disk space reclaimed."
        )
        self._add_system_message("\n".join(lines))

    def _handle_shortcuts_command(self: SagoApp, args: str = "") -> None:
        """Handle ? / /? / /shortcuts command."""
        try:
            from sago.tui.screens.shortcuts import ShortcutsScreen

            self.push_screen(ShortcutsScreen())
        except Exception:
            msg = (
                "[bold cyan]╔════════════════════════════════════════════════════════════════╗[/bold cyan]\n"
                "[bold cyan]║  ⌨️  SAGO SHORTCUTS & POWER COMMANDS                           ║[/bold cyan]\n"
                "[bold cyan]╚════════════════════════════════════════════════════════════════╝[/bold cyan]\n"
                "  [bold yellow]Keyboard Shortcuts:[/bold yellow]\n"
                "  • [bold white]F1[/bold white] or [bold white]?[/bold white]         : Open Shortcuts & Reference Sheet\n"
                "  • [bold white]Ctrl + D[/bold white]       : Toggle Agent Dashboard sidebar\n"
                "  • [bold white]Ctrl + T[/bold white]       : Show background tasks\n"
                "  • [bold white]Ctrl + C[/bold white]       : Cancel running task or agent execution\n"
                "  • [bold white]Ctrl + L[/bold white]       : Clear conversation chat log\n"
                "  • [bold white]Ctrl + Q[/bold white]       : Quit Sago\n"
                "  • [bold white]Tab / Enter[/bold white]    : Accept autocomplete suggestion\n"
                "  • [bold white]y / n[/bold white]          : Approve or Deny permission requests\n\n"
                "  [bold magenta]Core Commands:[/bold magenta]\n"
                "  • `/search <query>`    : Hybrid BM25 & dense vector semantic code search\n"
                "  • `/dev on|off|export`  : Developer mode & OTel/Prometheus trace exporter\n"
                "  • `/theme <name>`      : Switch between 11 terminal themes\n"
                "  • `/collapse all`      : Collapse or expand conversational cards\n"
                "  • `/checkpoint`        : Instant project snapshots & rollback\n"
                "  • `/model <id>`        : Switch active AI model\n"
                "  • `/effort <level>`    : Adjust reasoning depth (low, med, high, max)\n"
                "  • `@agent / #file`     : Mention agent or reference file"
            )
            self._add_system_message(msg)

    def _handle_search_command(self: SagoApp, args: str = "") -> None:
        """Handle /search or /semantic codebase natural language search."""
        if not args.strip():
            self._add_system_message("Usage: `/search <natural language query or symbol>`")
            return

        from sago.memory.hybrid_indexer import get_hybrid_code_indexer
        from sago.tui.helpers import create_collapsible

        try:
            indexer = get_hybrid_code_indexer()
            results = indexer.search(query=args.strip(), limit=6)
            if not results:
                self._add_system_message(f"No semantic code matches found for: '{args}'")
                return

            lines = [
                f"[bold cyan]═══ HYBRID SEMANTIC SEARCH RESULTS for '{args}' ═══[/bold cyan]\n"
            ]
            for i, r in enumerate(results, 1):
                chunk = r.chunk
                title = f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
                if chunk.name:
                    title += f" ({chunk.chunk_type} {chunk.name})"
                lines.append(
                    f"[bold yellow]#{i} {title}[/bold yellow] "
                    f"[dim](Score: {r.combined_score:.2f} | BM25: {r.bm25_score:.2f} | Vec: {r.semantic_score:.2f})[/dim]\n"
                    f"```{chunk.language}\n{chunk.content[:400]}\n```\n"
                )

            container = self.query_one("#messages")
            container.mount(
                create_collapsible(
                    Static("\n".join(lines)),
                    title=f"Search: {args.strip()[:30]} ({len(results)} matches)",
                    collapsed=True,
                )
            )
            container.scroll_end()
        except Exception as e:
            self._add_system_message(f"Error during search: {e}")

    def _handle_copy_command(self: SagoApp, args: str = "") -> None:
        """Copy last assistant response, code block, or full conversation to system clipboard."""
        import re

        from sago.tools.session.clipboard import ClipboardTool

        arg = args.strip().lower()
        tool = ClipboardTool()

        if arg in ("code", "snippet"):
            for msg in reversed(self.messages):
                content = msg.get("content", "")
                if "```" in content:
                    parts = content.split("```")
                    if len(parts) >= 3:
                        code_chunk = parts[-2]
                        lines = code_chunk.split("\n", 1)
                        code = lines[1] if len(lines) > 1 else lines[0]
                        tool._write_clipboard(code.strip())
                        self._add_system_message(
                            f"📋 Copied last code block to clipboard ({len(code.strip())} chars)"
                        )
                        return
            self._add_system_message("No code blocks found in recent conversation to copy.")

        elif arg in ("all", "chat", "history"):
            chat_text = []
            for msg in self.messages:
                role = msg.get("role", "user").upper()
                content = msg.get("content", "")
                chat_text.append(f"[{role}]:\n{content}\n")
            full_text = "\n".join(chat_text)
            tool._write_clipboard(full_text)
            self._add_system_message(
                f"📋 Copied entire chat history ({len(self.messages)} messages, {len(full_text)} chars) to clipboard"
            )

        else:
            for msg in reversed(self.messages):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    clean = re.sub(
                        r"<(?:thinking|thought)>.*?</(?:thinking|thought)>",
                        "",
                        content,
                        flags=re.DOTALL,
                    ).strip()
                    tool._write_clipboard(clean)
                    self._add_system_message(
                        f"📋 Copied last assistant response to clipboard ({len(clean)} chars)"
                    )
                    return
            self._add_system_message("No assistant messages found to copy.")

    def _handle_buttons_command(self: SagoApp, args: str = "") -> None:
        """Toggle or set visibility of the bottom quick actions button bar (/show, /hide, /buttons [on|off|toggle])."""
        arg = (args or "").strip().lower()
        if arg in ("hide", "off", "0", "false", "disable"):
            self.show_action_bar = False
            self._add_system_message(
                "🔘 Bottom action bar [bold red]hidden[/bold red]. (Type /show or /buttons on to restore)"
            )
        elif arg in ("show", "on", "1", "true", "enable"):
            self.show_action_bar = True
            self._add_system_message(
                "🔘 Bottom action bar [bold green]visible[/bold green]. (Type /hide to hide)"
            )
        else:
            # Toggle
            self.show_action_bar = not self.show_action_bar
            state = (
                "[bold green]visible[/bold green]"
                if self.show_action_bar
                else "[bold red]hidden[/bold red]"
            )
            self._add_system_message(f"🔘 Bottom action bar is now {state}. (Settings persisted)")

    def _handle_pr_command(self: SagoApp, args: str = "") -> None:
        """Handle /pr command for automated branch creation and Pull Requests."""
        title = args.strip() or "Feature updates and verified code changes"
        self._show_spinner(f"Creating PR: {title}...")
        try:
            from sago.tools.vcs.pr_workflow import create_pr_workflow

            res = create_pr_workflow(title=title)
            self._hide_spinner()
            if res["success"]:
                msg = res.get("pr_url") or res.get("message")
                md_content = res.get("pr_markdown", "")
                self._add_system_message(f"✓ {msg}\n\n{md_content}")
            else:
                self._add_system_message(f"✗ PR workflow failed: {res.get('error')}")
        except Exception as e:
            self._hide_spinner()
            self._add_system_message(f"PR creation error: {e}")
