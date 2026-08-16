# Sago Skills, Plugins & MCP Extensibility Guide

> Comprehensive guide for authoring custom skills, Python plugins, and integrating external Model Context Protocol (MCP) servers.

---

## 1. Custom Skills (`SKILL.md`)

Skills define specialized, repeatable operational workflows that agents can activate to accomplish complex domain tasks.

### Directory Locations
Sago automatically scans and loads skills from:
- **Workspace-specific**: `.sago/skills/<skill_name>/SKILL.md` or `skills/<skill_name>/SKILL.md`
- **Global / User-wide**: `~/.sago/skills/<skill_name>/SKILL.md`

### SKILL.md Structure & Specification
A skill document begins with YAML frontmatter followed by markdown instructions:

```markdown
---
name: database-migration
description: Safely plans, tests, and executes database schema migrations with rollback checkpoints.
tools:
  - execute_shell
  - read_file
  - write_file
  - checkpoint_ops
steps:
  - Create atomic workspace snapshot with checkpoint_ops
  - Verify existing database schema and generate migration script
  - Run test suite against temporary database
  - Apply migration and verify table consistency
tags:
  - database
  - migration
  - devops
---

# Database Migration Procedure

When performing database migrations:
1. Always create a pre-migration snapshot before touching any schema files.
2. Inspect models and verify foreign key constraints.
3. Generate reversible UP/DOWN migration scripts.
4. Execute test suites to ensure zero regression before committing.
```

### Inspecting Skills in TUI & CLI
- **TUI Command**: `/skills` or `/skill [query]`
- **Reloading**: `/skill reload`
- **Agent Activation**: Mention `@database-specialist` or instruct the agent to use the `database-migration` skill.

---

## 2. Python Plugins (`BasePlugin`)

Plugins provide full lifecycle hooks and enable registering custom tools and agents without modifying the core Sago codebase.

### Plugin Drop-in Locations
- **Workspace Plugins**: `.sago/plugins/<plugin_name>.py`
- **User Global Plugins**: `~/.sago/plugins/<plugin_name>.py`
- **Python Entry Points**: Package `sago.plugins` in `pyproject.toml`

### Authoring a Custom Plugin
Create `.sago/plugins/my_custom_plugin.py`:

```python
from typing import Any
from sago.plugins.base import BasePlugin, PluginMetadata
from sago.tools.base import BaseTool
from pydantic import BaseModel, Field


class SlackNotifyArgs(BaseModel):
    message: str = Field(..., description="Message text to post to Slack")
    channel: str = Field(default="#dev", description="Target Slack channel")


class SlackNotifyTool(BaseTool):
    name: str = "slack_notify"
    description: str = "Send alert notification to team Slack channel"
    args_model: type[BaseModel] = SlackNotifyArgs

    def _run(self, message: str, channel: str = "#dev", **kwargs: Any) -> str:
        # Custom execution logic
        return f"Message posted to {channel}: {message}"


class MyTeamPlugin(BasePlugin):
    meta = PluginMetadata(
        name="team_notifier",
        version="1.0.0",
        author="DevOps Team",
        description="Integrates internal Slack alerting and custom audit hooks",
        enabled=True,
    )

    def on_init(self, context: dict[str, Any]) -> None:
        print("[Plugin] Team Notifier initialized.")

    def on_user_message(self, message: str, context: dict[str, Any]) -> str:
        # Pre-process or enrich user prompts
        return message

    def on_tool_call(self, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        # Intercept tool arguments before execution
        return tool_args

    def on_tool_result(self, tool_name: str, result: Any) -> Any:
        # Inspect or transform tool execution outputs
        return result

    def provide_tools(self) -> list[Any]:
        # Expose custom tools to Sago's tool registry
        return [SlackNotifyTool()]
```

### Inspecting Plugins
- **TUI Command**: `/plugins`

---

## 3. Model Context Protocol (MCP) Server Integration

Sago seamlessly connects to external MCP servers running via **stdio**, **HTTP**, or **SSE**, discovering their remote tools and bridging them as native Sago tools.

### MCP Configuration File
Define servers in `.sago/mcp_servers.json` (workspace) or `~/.sago/mcp_servers.json` (global). Sago supports standard Claude/Anthropic format:

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "app.db"],
      "env": {}
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxxxxxxxxxx"
      }
    },
    "remote_api": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer sago_secret_key"
      }
    }
  }
}
```

### Managing MCP Servers in TUI
| Command | Action |
| :--- | :--- |
| `/mcp` or `/mcp list` | Lists all configured servers and all bridged remote tools |
| `/mcp test <name>` | Tests connectivity and schema discovery for `<name>` |
| `/mcp reload` | Re-reads configuration files and reconnects clients |

### How Agents Use MCP Tools
When an MCP server is configured:
1. Sago connects and extracts JSON schemas for all exposed tools.
2. Tools are bridged as `mcp_<server>_<tool_name>` (e.g. `mcp_sqlite_query`).
3. Agents can invoke them autonomously through standard function-calling loops.
