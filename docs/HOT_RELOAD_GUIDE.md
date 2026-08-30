# SAGO-Agent Hot-Reload Developer Guide

## Overview

This guide explains the hot-reload and config watching system for SAGO-Agent. When
the `config.yaml` execution mode or any other configuration setting changes, the
system automatically detects the change and applies it without requiring a full
server restart.

## Architecture

### Configuration Watching

The system uses a two-tier approach for config watching:

1. **Watchdog (preferred)**: Uses the `watchdog` library to receive filesystem
   notifications when `config.yaml` is modified. Provides instant detection.

2. **Polling (fallback)**: If watchdog is unavailable, uses a background thread
   that checks `config.yaml` modification time every 2 seconds. Slightly delayed
   but works on all platforms.

Both approaches call `invalidate_config_cache()` which forces the next `get_config()`
call to reload from disk.

### Execution Mode Configuration

The `config.yaml` file has an `execution.mode` setting with two possible values:

- `"native"` (default): TUI/CLI executes tasks directly using local agents and tools
- `"api"`: Tasks are executed via the FastAPI + WebSocket server

When the mode changes, the following happens:

1. Config cache is invalidated
2. Config watching is restarted with new settings
3. TUI receives signal and switches mode
4. API server rereads config on next request
5. Ongoing tasks continue in their original mode

### SIGHUP Signal Handling

The TUI handles SIGHUP signal to trigger config reload:

```bash
# Send SIGHUP to the TUI process
kill -HUP $(pgrep -f "sago tui")

# Or use the /reload command within TUI
# Press: /reload
```

### /reload TUI Command

Users can hot-reload the config from within the TUI:

1. Press inside the TUI: `/reload`
2. The system invalidates the config cache
3. Restarts config watching
4. Reads new execution mode
5. Displays message: "Config reloaded: execution mode is now [mode]"

### API Server /reload Endpoint

The API server also has a `/reload` endpoint for programmatic config reloading:

```bash
curl -X POST http://localhost:8000/reload
# Returns: {"status": "ok", "execution_mode": "native"}
```

This triggers:
1. `invalidate_config_cache()`
2. `stop_config_watching()`
3. `start_config_watching()`
4. Returns new execution mode

### Config File Location

The config file is loaded from this priority order:

1. `.sago.yaml` in current working directory (project-level)
2. `~/.sago/config/sago.yaml` (user-level)
3. `sago/config/sago.yaml` (default bundled config)

### Watchdog vs Polling

| Feature | Watchdog | Polling |
|---------|-----------|---------|
| Detection time | Instant (file system event) | ~2 seconds (check interval) |
| CPU usage | Very low (event-driven) | Low (2s interval) |
| Platform support | Linux, macOS, Windows | All platforms |
| Dependency | `watchdog` package | None (built-in) |
| Fallback | Falls back to polling if unavailable | N/A |

### Development Setup

To develop with hot-reload:

1. Ensure `watchdog` is installed: `pip install watchdog`
2. Make changes to `~/.sago/config/sago.yaml` or `./.sago.yaml`
3. The TUI will detect changes via SIGHUP or `/reload` command
4. Or send `kill -HUP <pid>` to the TUI process
5. API server: `curl -X POST http://localhost:8000/reload`

### Testing Hot-Reload

The test suite includes a hot-reload test:

```python
def test_config_reload_changes_mode():
    """Test that config can be modified and reloaded."""
    import yaml
    from pathlib import Path
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # Get current config
    cfg = get_config()
    assert cfg.execution.mode == "native"

    # Modify config to api mode
    config_path = Path.home() / ".sago" / "config" / "sago.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Change mode
    config["execution"]["mode"] = "api"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    # Reload config
    invalidate_config_cache()
    cfg = get_config()
    assert cfg.execution.mode == "api"

    # Reset config back to native
    config["execution"]["mode"] = "native"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    invalidate_config_cache()
```

### Troubleshooting

#### Config Changes Not Detected

1. Ensure `hot_reload: true` is set in `config.yaml`
2. Ensure the config file path is correct (check priority order above)
3. Try sending SIGHUP manually: `kill -HUP <tui-pid>`
4. Or use `/reload` command in TUI
5. Or call `POST /reload` on the API server

#### Watchdog Not Available

If watchdog is not installed or not working, the system automatically falls back
to polling mode. This is indicated in the logs:

```
WARNING: watchdog not available, falling back to polling-based config watching
```

To fix: `pip install watchdog`

#### Changes Not Applying

1. Check that the YAML is valid (no syntax errors)
2. Ensure the new setting names match the `ExecutionConfig` model
3. Verify `invalidate_config_cache()` was called
4. Check that `stop_config_watching()` and `start_config_watching()` were called
5. Review the logger output for any errors during the reload process