"""TUI Commands - All command handler methods."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from textual.widgets import Collapsible, Static

if TYPE_CHECKING:
    from sago.tui.app import SagoApp


class CommandHandlers:
    """Mixin class providing command handlers for SagoApp."""

    def _show_help(self: SagoApp) -> None:
        from sago.tui.models import COMMANDS

        container = self.query_one("#messages")

        categories = {
            "CORE": ["/help", "/map", "/verify", "/plan", "/todos", "/done", "/compact", "/reset"],
            "AGENT ORCHESTRATION": [
                "/agents",
                "/agent",
                "/delegate",
                "/chain",
                "/orchestrate",
                "/parallel",
                "/handoff",
            ],
            "MODEL & RUNTIME": ["/model", "/provider", "/effort", "/cost", "/yolo", "/dashboard"],
            "VERSION CONTROL": ["/git", "/diff", "/commit", "/changes", "/undo"],
            "SESSION & SECURITY": [
                "/sessions",
                "/save",
                "/load",
                "/export",
                "/permissions",
                "/allow",
                "/block",
            ],
        }

        lines = ["[bold white on #21262d]  COMMAND REFERENCE  [/bold white on #21262d]\n"]
        for cat, cmds in categories.items():
            lines.append(f"[bold cyan]{cat}[/bold cyan]")
            for cmd in cmds:
                desc = COMMANDS.get(cmd, "")
                lines.append(f"  [bold yellow]{cmd:<16}[/bold yellow] [white]{desc}[/white]")
            lines.append("")

        lines.append(
            "[dim]Shortcuts: Ctrl+D Dashboard | Ctrl+T Tasks | Ctrl+C Cancel | @agent | #file[/dim]"
        )

        body = "\n".join(lines)
        container.mount(
            Collapsible(
                Static(body),
                title="Command Reference",
                collapsed=False,
            )
        )
        container.scroll_end()

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
                    collapsed=False,
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
        self._add_user_message(f"/delegate {args}")
        self._process_delegation(agent_name, task)

    def _chain_agents(self: SagoApp, args: str) -> None:
        parts = args.split(None, 1)
        if len(parts) < 2:
            self._add_system_message("Usage: /chain <agent1,agent2> <task>")
            return
        agent_chain, task = parts
        agents = [a.strip() for a in agent_chain.split(",")]
        self._add_user_message(f"/chain {args}")
        self._process_chain(agents, task)

    def _orchestrate_task(self: SagoApp, task: str) -> None:
        if not task:
            self._add_system_message("Usage: /orchestrate <task>")
            return
        self._add_user_message(f"/orchestrate {task}")
        self._process_orchestration(task)

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
        container.mount(Collapsible(Static(body), title="System Status", collapsed=False))

    def _show_sessions(self: SagoApp) -> None:
        self._list_sessions()

    def _switch_session(self: SagoApp, sid: str) -> None:
        if not sid:
            self._add_system_message("Usage: /session <id>")
            return
        try:
            from sago.database import MessageStore, Session, init_db

            init_db()
            s = Session()
            sessions = s.list_all(limit=100)
            s.close()
            for ses in sessions:
                if ses["id"].startswith(sid):
                    self.current_session_id = ses["id"]
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
                    # Refresh the UI
                    container = self.query_one("#messages")
                    container.remove_children()
                    for m in self.messages:
                        if m["role"] == "user":
                            container.mount(
                                Static(f"> {m['content']}", classes="msg-user", markup=False)
                            )
                        elif m["role"] == "assistant":
                            agent = m.get("agent_name") or ""
                            prefix = f"[{agent}] " if agent else ""
                            container.mount(
                                Static(
                                    f"{prefix}{m['content']}", classes="msg-assistant", markup=False
                                )
                            )
                    container.scroll_end()
                    self._add_system_message(
                        f"Loaded session: {ses.get('title', 'Untitled')} ({len(msgs)} messages)"
                    )
                    return
            self._add_system_message(f"Session not found: {sid}")
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _show_history(self: SagoApp) -> None:
        if not self.command_history:
            self._add_system_message("[dim]No history[/dim]")
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
                    collapsed=False,
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

        # /model <provider> <model> — set provider + model
        if len(parts) >= 2:
            provider = parts[0]
            model_name = parts[1]
            self.current_provider = provider
            self.current_model = model_name
            self._add_system_message(f"Provider: {provider} | Model: {model_name}")
            return

        # /model <name> — fuzzy match (legacy compat)
        search = parts[0]
        models = get_all_models()
        for model in models:
            if search.lower() in model.lower():
                self.current_model = model
                self._add_system_message(f"Model: {model}")
                return
        # Not in list — allow it
        self.current_model = search
        self._add_system_message(f"Model: {search} (custom)")

    def _change_provider(self: SagoApp, p: str) -> None:
        self.current_model = f"{p}/free" if "/" not in p else p
        self._add_system_message(f"Provider: {self.current_model}")

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
        self._add_system_message("Sago v0.1.1 — Multi-agent orchestration system")

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
        if len(self.messages) < 5:
            self._add_system_message("Not enough messages to compact")
            return
        # Keep first and last 2 messages, summarize middle
        first = self.messages[:2]
        last = self.messages[-2:]
        middle = self.messages[2:-2]
        summary = f"[{len(middle)} messages compacted]"
        self.messages = first + [{"role": "system", "content": summary}] + last
        self._add_system_message(f"Compacted {len(middle)} messages")

    def _retry_last(self: SagoApp) -> None:
        if self.messages:
            last_user = None
            for msg in reversed(self.messages):
                if msg["role"] == "user":
                    last_user = msg["content"]
                    break
            if last_user:
                self._process_message(last_user)
            else:
                self._add_system_message("No user message to retry")
        else:
            self._add_system_message("No messages to retry")

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
        self._hide_welcome_screen()
        if not sid:
            self._add_system_message("Usage: /load <session-id>")
            return
        try:
            from sago.database import MessageStore, Session, init_db

            init_db()
            s = Session()
            sessions = s.list_all(limit=100)
            s.close()
            for ses in sessions:
                if ses["id"].startswith(sid):
                    self.current_session_id = ses["id"]
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
                    # Refresh the UI
                    container = self.query_one("#messages")
                    container.remove_children()
                    for m in self.messages:
                        if m["role"] == "user":
                            container.mount(
                                Static(f"> {m['content']}", classes="msg-user", markup=False)
                            )
                        elif m["role"] == "assistant":
                            agent = m.get("agent_name") or ""
                            prefix = f"[{agent}] " if agent else ""
                            container.mount(
                                Static(
                                    f"{prefix}{m['content']}", classes="msg-assistant", markup=False
                                )
                            )
                    container.scroll_end()
                    self._add_system_message(
                        f"Loaded: {ses.get('title', 'Untitled')} ({len(msgs)} messages)"
                    )
                    return
            self._add_system_message(
                f"Session not found: {sid}\nUse /sessions to list available sessions"
            )
        except Exception as e:
            self._add_system_message(f"Load error: {e}")

    def _exit_session(self: SagoApp) -> None:
        """Save session and exit, showing resume info."""
        # Flush any pending messages
        if hasattr(self, "_message_store") and self._message_store:
            try:
                self._message_store.flush()
            except Exception:
                pass
        try:
            from sago.database import Session, init_db

            init_db()
            # Save current session
            s = Session(self.current_session_id)
            s.update(title=f"Session {self.current_session_id[:8]}", status="closed")
            s.close()
        except Exception:
            pass
        sid = self.current_session_id[:8]
        msg_count = len(self.messages)
        # Print to stdout before exit so user sees the info
        import sys

        print(f"\nSession saved: {sid} ({msg_count} messages)", file=sys.stderr)
        print(f"Resume: sago tui --resume {sid}", file=sys.stderr)
        print(f"Or: /load {sid}", file=sys.stderr)
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
        from pathlib import Path

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
            lines.append("")

        # Add tool usage section
        lines.extend(["---", "", "## Tool Usage", ""])
        try:
            tus = ToolUsageStore(sid)
            tool_logs = tus.get_all()
            tus.close()
        except Exception:
            tool_logs = []

        if tool_logs:
            lines.append("| # | Tool | Duration | Status | Arguments |")
            lines.append("|---|------|----------|--------|-----------|")
            for i, log in enumerate(tool_logs, 1):
                tool = log.get("tool_name", "?")
                dur = f"{log.get('duration_ms', 0)}ms"
                ok = "OK" if log.get("success", 1) else "FAIL"
                args_raw = log.get("arguments", "{}")
                try:
                    args = (
                        __import__("json").loads(args_raw)
                        if isinstance(args_raw, str)
                        else args_raw
                    )
                except Exception:
                    args = {}
                # Truncate long args
                args_str = str(args)[:80]
                lines.append(f"| {i} | {tool} | {dur} | {ok} | `{args_str}` |")
            lines.append("")
        else:
            lines.append("_No tool usage recorded._")
            lines.append("")

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
            path.write_text("\n".join(lines))
            self._add_system_message(
                f"Exported to {path} ({len(self.messages)} messages, {len(tool_logs)} tool calls)"
            )
        except Exception as e:
            self._add_system_message(f"Export failed: {e}")

    def _git_status(self: SagoApp) -> None:
        try:
            r = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            from rich.markup import escape

            body = f"[bold]Git status:[/bold]\n{escape(r.stdout[:500])}"
            container = self.query_one("#messages")
            container.mount(Collapsible(Static(body), title="Git Status", collapsed=True))
        except Exception as e:
            self._add_system_message(f"Git error: {e}")

    def _git_diff(self: SagoApp, file: str) -> None:
        try:
            cmd = ["git", "diff"]
            if file:
                cmd.append(file)
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            from rich.markup import escape

            body = f"[bold]Diff:[/bold]\n{escape(r.stdout[:1000])}"
            container = self.query_one("#messages")
            container.mount(Collapsible(Static(body), title="Git Diff", collapsed=True))
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
        action = self.pending_action
        if not action:
            # Check for pending orchestration plan
            if hasattr(self, "pending_orchestration") and self.pending_orchestration:
                plan = self.pending_orchestration.get("plan")
                if plan:
                    self.pending_orchestration = None
                    self._execute_orchestration_plan(plan)
                    return
            # Check if executor is paused (waiting for user confirmation)
            if self._executor_pause_event and isinstance(
                self._executor_pause_event, threading.Event
            ):
                self._tool_approved = True  # Mark tool as approved
                self._executor_pause_event.set()  # Resume executor (unblock wait)
                self._add_system_message("Approved - continuing execution")
                return
            self._add_system_message("Nothing to approve")
            return
        if action["type"] == "git_commit":
            try:
                subprocess.run(["git", "add", "-A"], capture_output=True, timeout=5)
                r = subprocess.run(
                    ["git", "commit", "-m", action["message"]],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self._add_system_message(f"Committed: {r.stdout.strip()[:100]}")
            except Exception as e:
                self._add_system_message(f"Failed: {e}")
        elif action["type"] == "user_input":
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
        # Check for pending orchestration plan
        if hasattr(self, "pending_orchestration") and self.pending_orchestration:
            self.pending_orchestration = None
            self._add_system_message("Orchestration plan denied")
            return
        # Check if executor is paused - resume with skip
        if self._executor_pause_event and isinstance(self._executor_pause_event, threading.Event):
            self._tool_approved = False  # Mark tool as denied
            self._executor_pause_event.set()  # Resume executor (unblock wait)
            self._add_system_message("Skipped - continuing execution")
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
        except Exception:
            pass
        if self.yolo_mode:
            self._add_system_message(
                "YOLO MODE ON - All tools will be auto-approved without asking\n"
                "Use with caution! Type /yolo again to disable"
            )
        else:
            self._add_system_message("YOLO MODE OFF - Permissions restored")

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
                self._add_system_message("[dim]No blocked tools[/dim]")
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
        from sago.tasks import TaskStatus, get_task_manager

        tm = get_task_manager()
        plan = tm.get_active_plan()
        if not plan:
            self._add_system_message("No active plan")
            return

        container = self.query_one("#messages")

        # Build status counts
        done = sum(1 for t in plan.todos if t.status == TaskStatus.COMPLETED)
        total = len(plan.todos)
        in_progress = sum(1 for t in plan.todos if t.status == TaskStatus.IN_PROGRESS)
        pending = sum(1 for t in plan.todos if t.status == TaskStatus.PENDING)

        header = f"Plan: {plan.description[:60]}\nProgress: {done}/{total} done"
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
                collapsed=False,
            )
        )
        container.scroll_end()

    def _show_todo(self: SagoApp, args: str) -> None:
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

    def _show_all_todos(self: SagoApp) -> None:
        self._show_plan("")

    def _mark_todo_done(self: SagoApp, todo_id: str) -> None:
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

    def _ask_user(self: SagoApp, message: str) -> None:
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

    def _undo_change(self: SagoApp) -> None:
        """Undo the last file change."""
        from sago.memory.change_tracker import get_change_tracker

        tracker = get_change_tracker()
        undone_path = tracker.undo_last()
        if undone_path:
            self._add_system_message(f"Undid change to: {undone_path}")
        else:
            self._add_system_message("No changes to undo")

    def _show_changes(self: SagoApp) -> None:
        """Show all file changes this session."""
        from sago.memory.change_tracker import get_change_tracker

        tracker = get_change_tracker()
        summary = tracker.get_diff_summary()
        self._add_system_message(summary)

    # ========================================================================
    # PARALLEL EXECUTION COMMANDS
    # ========================================================================

    def _run_parallel(self: SagoApp, args: str) -> None:
        """Run multiple agents in parallel on the same task."""
        parts = args.split(None, 1)
        if len(parts) < 2:
            self._add_system_message("Usage: /parallel <agent1,agent2,...> <task>")
            return
        agent_list, task = parts
        agents = [a.strip() for a in agent_list.split(",")]
        if len(agents) < 2:
            self._add_system_message("Need at least 2 agents for /parallel")
            return
        self._add_user_message(f"/parallel {args}")
        self._process_parallel(agents, task)

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
        """Generate and display compact AST symbol repo map."""
        from sago.memory.symbol_graph import SymbolGraph

        try:
            graph = SymbolGraph()
            rmap = graph.generate_repo_map(filter_query=query.strip() or None)
            container = self.query_one("#messages")
            container.mount(
                Collapsible(
                    Static(f"```text\n{rmap}\n```"),
                    title="Symbol Repo Map",
                    collapsed=False,
                )
            )
        except Exception as e:
            self._add_system_message(f"Error generating repo map: {e}")

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
                        collapsed=False,
                    )
                )
            else:
                container.mount(
                    Collapsible(
                        Static(report.to_prompt_feedback()),
                        title="[bold red]Verification Failed[/bold red]",
                        collapsed=False,
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
                    collapsed=False,
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
                    collapsed=False,
                )
            )
            container.scroll_end()
        except Exception as e:
            self._add_system_message(f"Error listing plugins: {e}")

    def _set_theme(self: SagoApp, name: str) -> None:
        """Switch or list available TUI color themes."""
        themes = {
            "obsidian": "Obsidian Deep Dark (Default)",
            "nord": "Nord Arctic Cold Blue",
            "dracula": "Dracula Vampire Dark",
            "monokai": "Monokai Pro High Contrast",
            "solarized-dark": "Solarized Precision Teal",
            "tokyo-night": "Tokyo Night Indigo",
            "light": "Clean Day Light Mode",
        }
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
            self._add_system_message(f"Switched theme to [bold cyan]{themes[name]}[/bold cyan]")
        except Exception as e:
            self._add_system_message(f"Failed to switch theme: {e}")

    def _collapse_chats(self: SagoApp, action: str = "") -> None:
        """Collapse or expand all chat turns in the message pane."""
        from textual.widgets import Collapsible

        action = action.strip().lower()
        messages_container = self.query_one("#messages")
        turn_cards = messages_container.query(Collapsible)

        if not turn_cards:
            self._add_system_message("No chat turns to collapse.")
            return

        if action in ("expand", "all-open", "open"):
            for card in turn_cards:
                card.collapsed = False
            self._add_system_message(f"Expanded all ({len(turn_cards)}) cards in chat.")
        else:
            for card in turn_cards:
                card.collapsed = True
            self._add_system_message(f"Collapsed all ({len(turn_cards)}) cards in chat.")
