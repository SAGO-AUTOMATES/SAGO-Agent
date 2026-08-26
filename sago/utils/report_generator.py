"""Report generator for SAGO execution sessions, traces, and metrics."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("sago.utils.report_generator")


def generate_html_report(
    session_data: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
) -> str:
    """Generate a clean, standalone, responsive HTML report."""
    events = events or []
    task = session_data.get("task", "SAGO Execution Task")
    model = session_data.get("model", "Default Model")
    elapsed = session_data.get("elapsed", 0.0)
    success = session_data.get("success", True)
    tokens_in = session_data.get("tokens_in", 0)
    tokens_out = session_data.get("tokens_out", 0)
    output = session_data.get("output", "No output recorded.")
    tool_calls = session_data.get("tool_calls", [])

    status_badge = (
        '<span style="background:#10b981;color:#fff;padding:4px 12px;border-radius:999px;font-weight:bold;">PASSED</span>'
        if success
        else '<span style="background:#ef4444;color:#fff;padding:4px 12px;border-radius:999px;font-weight:bold;">FAILED</span>'
    )

    tools_rows = ""
    for i, tc in enumerate(tool_calls, 1):
        t_name = tc.get("tool") or tc.get("name", "tool")
        t_args = json.dumps(tc.get("args", {}), indent=2)
        t_res = str(tc.get("result", ""))[:300]
        tools_rows += f"""
        <tr>
            <td style="padding:10px;border-bottom:1px solid #334155;">{i}</td>
            <td style="padding:10px;border-bottom:1px solid #334155;font-weight:bold;color:#38bdf8;"><code>{t_name}</code></td>
            <td style="padding:10px;border-bottom:1px solid #334155;"><pre style="margin:0;font-size:12px;">{t_args}</pre></td>
            <td style="padding:10px;border-bottom:1px solid #334155;"><pre style="margin:0;font-size:12px;">{t_res}</pre></td>
        </tr>
        """

    if not tools_rows:
        tools_rows = '<tr><td colspan="4" style="padding:15px;text-align:center;color:#94a3b8;">No tool calls executed during this session.</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SAGO Run Report - {task[:40]}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 28px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        h1, h2, h3 {{ color: #f1f5f9; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 20px 0; }}
        .card {{ background: #0f172a; border-radius: 8px; padding: 16px; border: 1px solid #334155; }}
        .card-val {{ font-size: 24px; font-weight: bold; color: #38bdf8; margin-top: 6px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th {{ background: #0f172a; padding: 10px; text-align: left; border-bottom: 2px solid #475569; }}
        pre {{ background: #0f172a; padding: 16px; border-radius: 8px; overflow-x: auto; color: #e2e8f0; }}
        code {{ color: #38bdf8; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="container">
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #334155;padding-bottom:16px;">
            <div>
                <h1 style="margin:0 0 6px 0;">⚡ SAGO Run Execution Report</h1>
                <div style="color:#94a3b8;">Generated at {time.strftime("%Y-%m-%d %H:%M:%S")}</div>
            </div>
            <div>{status_badge}</div>
        </div>

        <div class="grid">
            <div class="card"><div>Model</div><div class="card-val" style="font-size:18px;">{model}</div></div>
            <div class="card"><div>Elapsed Time</div><div class="card-val">{elapsed:.2f}s</div></div>
            <div class="card"><div>Total Tokens</div><div class="card-val">{tokens_in + tokens_out:,}</div></div>
            <div class="card"><div>Tool Calls</div><div class="card-val">{len(tool_calls)}</div></div>
        </div>

        <h2>📋 Task Specification</h2>
        <pre>{task}</pre>

        <h2>🛠️ Tool Execution Trace</h2>
        <table>
            <thead>
                <tr><th>#</th><th>Tool Name</th><th>Arguments</th><th>Output Preview</th></tr>
            </thead>
            <tbody>
                {tools_rows}
            </tbody>
        </table>

        <h2>💬 Final Agent Output</h2>
        <pre>{output}</pre>
    </div>
</body>
</html>
"""


def generate_markdown_report(session_data: dict[str, Any]) -> str:
    """Generate a clean Markdown summary report."""
    task = session_data.get("task", "SAGO Execution")
    model = session_data.get("model", "Default Model")
    elapsed = session_data.get("elapsed", 0.0)
    success = session_data.get("success", True)
    tool_calls = session_data.get("tool_calls", [])
    output = session_data.get("output", "")

    status = "✅ PASSED" if success else "❌ FAILED"

    lines = [
        f"# ⚡ SAGO Execution Report: {status}",
        "",
        f"- **Task:** `{task}`",
        f"- **Model:** `{model}`",
        f"- **Duration:** `{elapsed:.2f}s`",
        f"- **Tools Used:** `{len(tool_calls)}`",
        "",
        "## 🛠️ Tool Calls",
    ]

    for i, tc in enumerate(tool_calls, 1):
        t_name = tc.get("tool") or tc.get("name", "tool")
        lines.append(f"{i}. **`{t_name}`**")

    lines.extend(["", "## 💬 Agent Output", "```text", output, "```"])
    return "\n".join(lines)
