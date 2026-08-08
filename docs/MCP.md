# Sago - MCP Server Support

> Model Context Protocol integration for external tool exposure and integration.

## Overview

Sago supports the Model Context Protocol (MCP) for:
1. Exposing Sago tools to external MCP clients
2. Integrating external MCP tools into Sago

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Sago MCP                             │
├─────────────────────────────────────────────────────────────┤
│  MCP Server                    MCP Client                   │
│  ┌─────────────────┐          ┌─────────────────┐          │
│  │ Expose Tools     │          │ Connect Servers  │          │
│  │ - read_file      │          │ - filesystem     │          │
│  │ - write_file     │          │ - github         │          │
│  │ - scan_directory │          │ - postgres       │          │
│  │ - execute_shell  │          │ - custom servers │          │
│  └─────────────────┘          └─────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## MCP Server (Expose Sago Tools)

### Create Server

```python
from sago.mcp.server import MCPServer, MCPTool

server = MCPServer(name="sago", version="0.1.0")

# Register tools
server.register_function(
    name="read_file",
    description="Read file contents",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
        },
        "required": ["path"],
    },
    handler=read_file_handler,
)
```

### List Tools

```python
tools = server.list_tools()
# [{'name': 'read_file', 'description': '...', 'inputSchema': {...}}]
```

### Call Tool

```python
result = server.call_tool("read_file", {"path": "main.py"})
```

### MCP Protocol Response

```python
response = server.to_mcp_response()
# {
#     'protocolVersion': '2024-11-05',
#     'capabilities': {'tools': {'listChanged': False}},
#     'serverInfo': {'name': 'sago', 'version': '0.1.0'}
# }
```

## MCP Client (Connect to External Servers)

### Connect to Server

```python
from sago.mcp.client import MCPClient

client = MCPClient(server_url="stdio://path/to/server")
client.connect()
```

### List Remote Tools

```python
tools = client.list_tools()
```

### Call Remote Tool

```python
result = client.call_tool("remote_tool", {"arg": "value"})
```

## Built-in MCP Tools

Sago registers these tools by default:

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents |
| `write_file` | Write to file |
| `scan_directory` | Scan directory structure |
| `execute_shell` | Execute shell commands |
| `list_agents` | List available agents |
| `delegate_task` | Delegate task to agent |

## Integration Examples

### With Claude Desktop

```json
{
  "mcpServers": {
    "sago": {
      "command": "python",
      "args": ["-m", "sago.mcp.server"],
      "env": {
        "GEMINI_API_KEY": "your-key"
      }
    }
  }
}
```

### With VS Code

```json
{
  "mcp.servers": {
    "sago": {
      "command": "python",
      "args": ["-m", "sago.mcp.server"]
    }
  }
}
```

### Custom MCP Server

```python
from sago.mcp.server import MCPServer

# Create custom server
server = MCPServer(name="custom-sago")

# Register custom tools
server.register_function(
    name="analyze_project",
    description="Analyze project structure",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
    },
    handler=analyze_project_handler,
)

# Run server (stdio transport)
import sys
import json

for line in sys.stdin:
    request = json.loads(line)
    if request["method"] == "tools/list":
        response = {"tools": server.list_tools()}
    elif request["method"] == "tools/call":
        response = server.call_tool(
            request["params"]["name"],
            request["params"]["arguments"],
        )
    print(json.dumps(response))
```

## Error Handling

```python
from sago.mcp.server import MCPServer

server = MCPServer(name="sago")

# Tools raise specific exceptions
class MCPToolError(Exception):
    pass

class MCPToolNotFound(MCPToolError):
    pass

class MCPToolExecutionError(MCPToolError):
    pass
```

## Configuration

### Environment Variables

```bash
# MCP server port (for HTTP transport)
SAGO_MCP_PORT=8080

# MCP log level
SAGO_MCP_LOG_LEVEL=INFO

# Disable MCP
SAGO_MCP_ENABLED=0
```

### Project Config

```json
{
  "mcp": {
    "enabled": true,
    "port": 8080,
    "tools": ["read_file", "write_file", "scan_directory"],
    "external_servers": []
  }
}
```

## Limitations

- Current implementation uses stdio transport
- HTTP/SSE transport planned for future
- External tool integration requires custom handler
