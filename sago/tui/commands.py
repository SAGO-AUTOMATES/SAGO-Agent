"""TUI Commands - All command handler methods."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from sago.tui.app import SagoApp


class CommandHandlers:
    """Mixin class providing command handlers for SagoApp."""

    def _show_help(self: SagoApp) -> None:
        from sago.tui.models import COMMANDS

        lines = ["Commands:"]
        for cmd, desc in COMMANDS.items():
            lines.append(f"  {cmd:<18} {desc}")
        self._add_system_message("\n".join(lines))

    def _show_agents(self: SagoApp, f: str = "") -> None:
        try:
            from sago.agents.registry import list_agents

            agents = list_agents()
            if f:
                agents = [a for a in agents if f.lower() in a["name"].lower()]
            lines = [f"Agents ({len(agents)}):"]
            for a in agents[:30]:
                skills = ", ".join(a.get("skills", [])[:3])
                lines.append(f"  {a['name']:<25} {skills}")
            if len(agents) > 30:
                lines.append(f"  ... and {len(agents) - 30} more")
            self._add_system_message("\n".join(lines))
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
        yolo_status = "ON" if self.yolo_mode else "off"
        provider = getattr(self, "current_provider", "openrouter")
        self._add_system_message(
            f"Sago v0.1.0\n"
            f"  Agent:    {self.current_agent}\n"
            f"  Provider: {provider}\n"
            f"  Model:    {self.current_model}\n"
            f"  Effort:   {self.current_effort} ({effort.get('desc', '')})\n"
            f"  YOLO:     {yolo_status}\n"
            f"  Session:  {sid}\n"
            f"  Agents:   {n} available\n"
            f"  Messages: {len(self.messages)}"
        )

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
                    msgs = ms.get_history(limit=50)
                    ms.close()
                    self.messages = [{"role": m["role"], "content": m["content"]} for m in msgs]
                    self._add_system_message(f"Loaded session: {ses.get('title', 'Untitled')}")
                    return
            self._add_system_message(f"Session not found: {sid}")
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _show_history(self: SagoApp) -> None:
        if not self.command_history:
            self._add_system_message("No history")
            return
        lines = [f"  {i + 1}. {cmd}" for i, cmd in enumerate(self.command_history[-20:])]
        self._add_system_message("History:\n" + "\n".join(lines))

    def _change_model(self: SagoApp, m: str) -> None:
        from sago.tui.models import (
            add_custom_model,
            get_all_models,
            refresh_models_from_openrouter,
            remove_custom_model,
        )

        parts = m.split(None, 2) if m else []

        # /model — show all grouped by provider
        if not parts:
            models = get_all_models()
            # Group by first part of model ID
            providers: dict[str, list[str]] = {}
            for model in models:
                provider = model.split("/")[0]
                providers.setdefault(provider, []).append(model)
            cur = getattr(self, "current_model", "?")
            prov = getattr(self, "current_provider", "?")
            lines = [f"Current: {prov} / {cur}\n"]
            lines.append("Usage: /model <provider> <model>")
            lines.append("  e.g. /model google gemini-2.0-flash")
            lines.append("  e.g. /model openrouter openrouter/free")
            lines.append("  e.g. /model openai gpt-4o\n")
            for provider, pmodels in sorted(providers.items()):
                lines.append(f"  [{provider}] ({len(pmodels)})")
                for model in pmodels[:10]:
                    lines.append(f"    {model}")
                if len(pmodels) > 10:
                    lines.append(f"    ... +{len(pmodels) - 10} more")
                lines.append("")
            self._add_system_message("\n".join(lines))
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
            self._add_system_message("\n".join(lines))
            return
        if level in EFFORT_LEVELS:
            self.current_effort = level
            self._add_system_message(f"Effort: {level}")
        else:
            self._add_system_message(f"Unknown: {level}\nAvailable: low, medium, high, max")

    def _show_version(self: SagoApp) -> None:
        self._add_system_message("Sago v0.1.0 — Multi-agent orchestration system")

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
            f"Model: {self.current_model}",
            f"Input:  {total_in:,} tokens (${cost_in:.4f})",
            f"Output: {total_out:,} tokens (${cost_out:.4f})",
            f"Total:  ${total_cost:.4f}",
        ]
        if cache_hit > 0:
            lines.append(f"Cache: {cache_hit:,} hit, {cache_miss:,} miss")
        self._add_system_message("\n".join(lines))

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
                    self.messages = [{"role": m["role"], "content": m["content"]} for m in msgs]
                    # Refresh the UI
                    container = self.query_one("#messages")
                    container.remove_children()
                    for m in self.messages:
                        if m["role"] == "user":
                            container.mount(Static(f"> {m['content']}", classes="msg-user"))
                        elif m["role"] == "assistant":
                            container.mount(Static(m["content"], classes="msg-assistant"))
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
        try:
            from sago.database import Session, init_db

            init_db()
            # Save current session
            s = Session(self.current_session_id)
            s.update(title=f"Session {self.current_session_id[:8]}")
            s.close()
        except Exception:
            pass
        sid = self.current_session_id[:8]
        msg_count = len(self.messages)
        self._add_system_message(
            f"\nSession saved: {sid} ({msg_count} messages)\n"
            f"Resume: sago tui --resume {sid}\n"
            f"Or: /load {sid}"
        )
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
            lines = ["Recent sessions:"]
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
                current = " *" if ses["id"] == self.current_session_id else ""
                lines.append(f"  {sid}{current}  {title:<30} {count} msgs  {date}")
            lines.append(f"\nResume: /load <id>  |  Current: {self.current_session_id[:8]}")
            self._add_system_message("\n".join(lines))
        except Exception as e:
            self._add_system_message(f"Sessions error: {e}")

    def _export_session(self: SagoApp) -> None:
        from pathlib import Path

        lines = []
        for msg in self.messages:
            role = msg["role"].upper()
            lines.append(f"[{role}]\n{msg['content']}\n")
        path = Path("session_export.md")
        path.write_text("\n".join(lines))
        self._add_system_message(f"Exported to {path}")

    def _git_status(self: SagoApp) -> None:
        try:
            r = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self._add_system_message(f"Git status:\n{r.stdout[:500]}")
        except Exception as e:
            self._add_system_message(f"Git error: {e}")

    def _git_diff(self: SagoApp, file: str) -> None:
        try:
            cmd = ["git", "diff"]
            if file:
                cmd.append(file)
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            self._add_system_message(f"Diff:\n{r.stdout[:1000]}")
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
        if self.yolo_mode:
            self._add_system_message(
                "YOLO MODE ON - All tools will be auto-approved without asking\n"
                "⚠️  Use with caution! Type /yolo again to disable"
            )
        else:
            self._add_system_message("YOLO MODE OFF - Permissions restored")

    def _show_permissions(self: SagoApp, args: str) -> None:
        from sago.permissions import TOOL_RISK_LEVELS, get_permission_manager

        pm = get_permission_manager()

        if args == "blocked":
            if pm.config.blocked_tools:
                lines = "\n".join(f"  - {t}" for t in pm.config.blocked_tools)
                self._add_system_message(f"Blocked tools:\n{lines}")
            else:
                self._add_system_message("No blocked tools")
        elif args == "allowed":
            if pm.config.allowed_tools:
                lines = "\n".join(f"  - {t}" for t in pm.config.allowed_tools)
                self._add_system_message(f"Allowed tools:\n{lines}")
            else:
                self._add_system_message("No explicit allowed list (all tools available)")
        else:
            lines = []
            for name, risk in sorted(TOOL_RISK_LEVELS.items()):
                blocked = "BLOCKED" if pm.is_blocked(name) else "ok"
                lines.append(f"  {name:<25} {risk.value:<10} {blocked}")
            self._add_system_message("Tool permissions:\n" + "\n".join(lines))

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
        from sago.tasks import get_task_manager

        tm = get_task_manager()
        plan = tm.get_active_plan()
        if plan:
            self._add_system_message(tm.format_plan(plan))
        else:
            self._add_system_message("No active plan")

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
        from sago.tasks import get_task_manager

        tm = get_task_manager()
        plan = tm.get_active_plan()
        if plan:
            self._add_system_message(tm.format_plan(plan))
        else:
            self._add_system_message("No active plan")

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
        """Toggle the agent dashboard sidebar."""
        if hasattr(self, "_dashboard_visible"):
            self._dashboard_visible = not self._dashboard_visible
        else:
            self._dashboard_visible = True

        dashboard = self.query_one("#agent-dashboard")
        if self._dashboard_visible:
            dashboard.remove_class("hidden")
            if self._dashboard is None:
                self._dashboard = dashboard
            self._update_dashboard()
            self._add_system_message("Dashboard: ON")
        else:
            dashboard.add_class("hidden")
            self._add_system_message("Dashboard: OFF")

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
            lines = [f"Agents ({len(agents)}):"]
            for a in agents[:40]:
                color = get_agent_color(a["name"])
                lines.append(f"  [{color}]●[/{color}] {a['name']}")
            if len(agents) > 40:
                lines.append(f"  ... and {len(agents) - 40} more")
            self._add_system_message("\n".join(lines))
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _toggle_summary(self: SagoApp) -> None:
        """Toggle summary display after each task."""
        self.show_summary = not self.show_summary
        if self.show_summary:
            self._add_system_message("Summary: ON — tool usage summary will appear after each task")
        else:
            self._add_system_message("Summary: OFF")
