# Sago - Error Handling Guide

> Complete guide to error handling, recovery, and troubleshooting.

## Error Types

### Tool Errors

| Error | Cause | Recovery |
|-------|-------|----------|
| `ToolNotFoundError` | Tool doesn't exist | Check tool name |
| `ToolExecutionError` | Tool failed | Check parameters |
| `ToolTimeoutError` | Tool timed out | Increase timeout |
| `ToolPermissionError` | No permission | Check permissions |

### Agent Errors

| Error | Cause | Recovery |
|-------|-------|----------|
| `AgentNotFoundError` | Agent doesn't exist | Check agent name |
| `AgentExecutionError` | Agent failed | Check task description |
| `AgentTimeoutError` | Agent timed out | Increase timeout |
| `AgentDelegationError` | Delegation failed | Try different agent |

### LLM Errors

| Error | Cause | Recovery |
|-------|-------|----------|
| `ProviderNotFoundError` | Provider doesn't exist | Check provider name |
| `APIKeyError` | Invalid/missing API key | Set environment variable |
| `RateLimitError` | Rate limit hit | Wait or use different provider |
| `ModelNotFoundError` | Model doesn't exist | Check model name |

### System Errors

| Error | Cause | Recovery |
|-------|-------|----------|
| `DatabaseError` | SQLite error | Check database path |
| `CacheError` | Cache error | Clear cache |
| `ConfigError` | Config error | Reinitialize |

## Automatic Recovery

### Retry Strategy

```python
from sago.errors.handler import get_recovery_manager

recovery = get_recovery_manager()

# Automatically retries transient errors
result = recovery.execute_with_recovery(
    tool_name="execute_shell",
    func=lambda: risky_operation(),
    max_retries=3,
)
```

### Fallback Strategy

```python
# Set fallback tools
recovery.set_fallbacks(
    "primary_tool",
    ["fallback_tool_1", "fallback_tool_2"],
)

# Tries fallbacks if primary fails
result = recovery.execute_with_fallbacks(
    primary_tool="primary_tool",
    func=lambda: risky_operation(),
)
```

### Error Classification

Errors are automatically classified:

- **Transient**: Timeout, Connection, OSError → Retried
- **Permanent**: FileNotFound, Permission, Value → Not retried
- **Critical**: Runtime, System → Immediate attention

## Manual Error Handling

### Try/Except Pattern

```python
from sago.errors.exceptions import ToolExecutionError

try:
    result = tool.execute(params)
except ToolExecutionError as e:
    print(f"Tool failed: {e}")
    # Handle error
except Exception as e:
    print(f"Unexpected error: {e}")
    # Log and re-raise
```

### Error Callbacks

```python
from sago.errors.handler import get_error_handler

handler = get_error_handler()

def on_error(context):
    print(f"Error in {context.tool_name}: {context.error}")
    print(f"Attempt {context.attempt}/{context.max_attempts}")

handler.on_error = on_error
```

## Common Issues & Solutions

### 1. Module Not Found

```bash
# Error: ModuleNotFoundError: No module named 'sago'
# Solution:
uv sync
# or
pip install -e .
```

### 2. API Key Not Set

```bash
# Error: APIKeyError: GEMINI_API_KEY not set
# Solution:
export GEMINI_API_KEY="AIza..."
```

### 3. Database Locked

```bash
# Error: DatabaseError: database is locked
# Solution:
rm ~/.sago/data/sago.db
sago status  # Recreates
```

### 4. Cache Issues

```bash
# Error: CacheError: invalid cache
# Solution:
rm ~/.sago/cache.json
```

### 5. Permission Denied

```bash
# Error: PermissionError: [Errno 13] Permission denied
# Solution:
chmod +x script.sh
# or
sudo command
```

### 6. File Not Found

```bash
# Error: FileNotFoundError: [Errno 2] No such file
# Solution:
ls -la path/to/file  # Check if exists
pwd  # Check current directory
```

### 7. Timeout Error

```bash
# Error: TimeoutError: Operation timed out
# Solution:
# Increase timeout
tool.execute(command="long-running", timeout=300)
```

### 8. Import Errors (LSP)

```
# Error: Import "pydantic" could not be resolved
# This is a FALSE POSITIVE
# LSP doesn't use uv virtualenv
# Verify with:
uv run python -c "import sago; print('OK')"
```

## Debug Mode

### Enable Debug Logging

```bash
export SAGO_DEBUG=1
sago smart "task"
```

### Python Debugger

```bash
uv run python -m pdb -m sago --help
```

### Verbose Output

```bash
uv run python -m sago --verbose smart "task"
```

## Error Logging

### Log Location

```bash
# Default: ~/.sago/logs/sago.log
ls ~/.sago/logs/
```

### Log Levels

```bash
# Set log level
export SAGO_LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

### View Logs

```bash
tail -f ~/.sago/logs/sago.log
```

## Troubleshooting Checklist

1. **Check Python version**: `python --version` (need 3.11+)
2. **Check dependencies**: `uv sync` or `pip install -e .`
3. **Check API keys**: `env | grep API`
4. **Check database**: `ls ~/.sago/data/`
5. **Check cache**: `ls ~/.sago/cache.json`
6. **Check logs**: `cat ~/.sago/logs/sago.log`
7. **Reset state**: `rm -rf ~/.sago/`
8. **Reinitialize**: `sago setup`

## Getting Help

```bash
# CLI help
sago --help
sago <command> --help

# TUI help
sago tui
/help

# Status
sago status
sago usage
```
