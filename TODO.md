# SAGO-Agent Development TODO

> **Status:** Last Updated - 2026-08-17  
> **Branch:** feature/cleanup-and-gc (v0.1.7)  
> **Next Release Target:** v0.1.8  

---

## 📋 Table of Contents

1. [Critical Security Issues (High Priority)](#1-critical-security-issues-high-priority)
2. [Code Quality & Reliability Issues (Medium Priority)](#2-code-quality--reliability-issues-medium-priority)
3. [Test Infrastructure (Medium Priority)](#3-test-infrastructure-medium-priority)
4. [Documentation Tasks (Medium Priority)](#4-documentation-tasks-medium-priority)
5. [Future Features & Enhancements (Low Priority)](#5-future-features--enhancements-low-priority)
6. [Technical Debt & Refactoring (Low Priority)](#6-technical-debt--refactoring-low-priority)
7. [Dependency & Environment Issues](#7-dependency--environment-issues)

---

## 🚨 Priority Legend

| Icon | Priority | Description | Target Resolution |
|------|----------|-------------|-------------------|
| 🔴 | **Critical** | Must fix before next release. Security issues, data loss risks, crashes. | v0.1.8 |
| 🟡 | **High** | Important fixes that should be in next release. | v0.1.8 |
| 🟢 | **Medium** | Nice to have, improvements, minor bugs. | v0.1.8 or v0.1.9 |
| 🔵 | **Low** | Future enhancements, technical debt. | v0.1.9+ |

---

# 1. 🔴 Critical Security Issues (High Priority)

> **Owner:** @CrimsonDevil333333  
> **Review Source:** PR #4 Security Audit  
> **Impact:** Security vulnerabilities, potential privilege escalation, data leakage

### 1.1 Namespace Support Detection is Incomplete

**File:** `sago/tools/system/sandbox.py:46-56`  
**Function:** `_check_namespace_support()`  
**Severity:** 🔴 CRITICAL  
**Status:** ⬜ Not Started  

**Problem:**
The current implementation only checks if `unshare` command exists, but does NOT verify:
1. If user namespaces are enabled (`/proc/sys/kernel/unprivileged_userns_clone`)
2. If the current user has CAP_SYS_ADMIN capability
3. If the process is running in a container with restricted permissions
4. If AppArmor/SELinux prevents namespace usage

This gives a **false sense of security** - the code thinks namespaces are available when they're not actually usable.

**Expected Behavior:**
- Return `False` if namespaces cannot actually be used
- Log warnings when falling back to non-namespace mode
- Provide clear feedback to users about why namespaces aren't available

**Solution:**
```python
def _check_namespace_support() -> tuple[bool, str]:
    """Check if Linux namespace isolation is available.
    
    Returns:
        tuple[bool, str]: (is_available, reason_if_not)
    """
    import os
    
    # 1. Check if unshare command exists
    try:
        result = subprocess.run(
            ["unshare", "--help"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False, "unshare command not found or not executable"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "unshare command not found"
    
    # 2. Check if user namespaces are enabled
    try:
        with open("/proc/sys/kernel/unprivileged_userns_clone") as f:
            if f.read().strip() != "1":
                return False, "User namespaces disabled (unprivileged_userns_clone=0)"
    except (FileNotFoundError, PermissionError):
        return False, "Cannot check user namespace support (permission denied)"
    
    # 3. Try to actually use unshare to verify it works
    try:
        result = subprocess.run(
            ["unshare", "--mount", "--pid", "--", "true"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False, f"unshare test failed: {result.stderr.decode()}"
    except Exception as e:
        return False, f"unshare test error: {e}"
    
    return True, "All namespace checks passed"
```

**Files to Modify:**
- `sago/tools/system/sandbox.py`

**Test Files to Add/Modify:**
- `tests/unit/test_sandbox.py::test_namespace_support_detection`

**Estimated Effort:** 2-3 hours  
**Dependencies:** None  

---

### 1.2 Resource Limits Can Be Bypassed by Child Processes

**File:** `sago/tools/system/sandbox.py:146-180`  
**Function:** `_build_resource_limited_cmd()`  
**Severity:** 🔴 CRITICAL  
**Status:** ⬜ Not Started  

**Problem:**
The current implementation uses a bash wrapper script with `ulimit` commands:
```bash
ulimit -v {max_memory_mb * 1024}
ulimit -u {max_processes}
ulimit -t {max_cpu_seconds}
exec "$@"
```

Issues:
1. `ulimit` only applies to the shell process and its direct children
2. Some applications (Java JVM, Go runtime, Node.js) may reset their own limits
3. Child processes spawned by the executed command **do not inherit** these limits
4. No verification that limits were actually applied

**Expected Behavior:**
- Resource limits should apply to ALL processes in the sandbox
- Limits should be verified before execution
- Hard limits should be enforced at the kernel level

**Solution:**
Use `prlimit` command (available on modern Linux) which can set limits on running processes:

```python
def _build_resource_limited_cmd(
    self, cmd_args: list[str] | str, sandbox_path: Path
) -> list[str]:
    """Build command with resource limits applied.
    
    Uses prlimit for more reliable limit enforcement.
    """
    # Use prlimit to set hard limits on the command process
    # prlimit --pid=0 sets limits on the current process (which will be the command)
    
    limits = []
    
    # Memory limit (in bytes) - soft and hard
    mem_limit_bytes = self.config.max_memory_mb * 1024 * 1024
    limits.append(f"--as={mem_limit_bytes}")  # Address space limit
    
    # CPU time limit (in seconds)
    limits.append(f"--cpu={self.config.max_cpu_seconds}")
    
    # Process limit
    limits.append(f"--nproc={self.config.max_processes}")
    
    # Build the command
    if isinstance(cmd_args, str):
        # For string commands, use shell
        return ["prlimit", "--pid=0"] + limits + ["bash", "-c", cmd_args]
    else:
        # For list commands, exec directly
        return ["prlimit", "--pid=0"] + limits + ["exec"] + cmd_args
```

Alternative: Use `systemd-run` with resource limits if available:
```python
def _build_systemd_run_cmd(self, cmd_args, sandbox_path):
    """Use systemd-run for maximum isolation (if available)."""
    mem_limit = f"{self.config.max_memory_mb}M"
    cpu_limit = f"{self.config.max_cpu_seconds}s"
    
    cmd = [
        "systemd-run",
        "--scope",
        "--slice=sago-sandbox.slice",
        f"--memory={mem_limit}",
        f"--CPUQuota=100%",  # Limit to 100% of one CPU
        f"--TasksMax={self.config.max_processes}",
        "--",
    ]
    if isinstance(cmd_args, str):
        cmd.extend(["bash", "-c", cmd_args])
    else:
        cmd.extend(cmd_args)
    return cmd
```

**Files to Modify:**
- `sago/tools/system/sandbox.py`

**Test Files to Add/Modify:**
- `tests/unit/test_sandbox.py::test_resource_limits_enforced`
- `tests/unit/test_sandbox.py::test_resource_limits_bypass_attempts`

**Estimated Effort:** 3-4 hours  
**Dependencies:** prlimit (available in util-linux >= 2.23)

---

### 1.3 PATH Environment Variable Security Risk

**File:** `sago/mcp/client.py:75-92`  
**Function:** `_build_subprocess_env()`  
**Severity:** 🔴 CRITICAL  
**Status:** ⬜ Not Started  

**Problem:**
The current implementation copies `PATH` from the parent environment:
```python
essential_vars = ["PATH", "LANG", "LC_ALL", "HOME", "TMPDIR", "USER"]
for var in essential_vars:
    if var in os.environ:
        safe_vars[var] = os.environ[var]  # Copies PATH as-is
```

**Security Risk:**
- Parent's PATH may contain malicious directories (e.g., `~/malicious/bin`)
- MCP servers could execute binaries from untrusted locations
- This defeats the purpose of environment isolation

**Expected Behavior:**
- Use a known-safe PATH
- Validate PATH entries before including them
- Never trust parent's PATH in security-sensitive contexts

**Solution:**
```python
def _build_subprocess_env(self) -> dict[str, str]:
    """Build isolated environment for subprocess execution.
    
    Uses a safe, minimal PATH and only essential system variables.
    """
    import os
    
    if self._isolated_env is not None:
        # Build minimal safe environment with only essential vars + server-specific env
        safe_vars = {}
        
        # Use a known-safe PATH
        safe_path = "/usr/local/bin:/usr/bin:/bin"
        # On most systems, these are safe
        if os.path.exists("/usr/local/sbin"):
            safe_path = "/usr/local/sbin:" + safe_path
        if os.path.exists("/sbin"):
            safe_path = safe_path + ":/sbin"
        
        safe_vars["PATH"] = safe_path
        
        # Copy other essential, non-dangerous variables
        essential_vars = ["LANG", "LC_ALL", "HOME", "TMPDIR", "USER"]
        for var in essential_vars:
            if var in os.environ:
                safe_vars[var] = os.environ[var]
        
        # Add server-specific environment variables
        safe_vars.update(self._isolated_env)
        return safe_vars
    else:
        # Even when not isolated, sanitize PATH
        env = os.environ.copy()
        safe_path = "/usr/local/bin:/usr/bin:/bin"
        if os.path.exists("/usr/local/sbin"):
            safe_path = "/usr/local/sbin:" + safe_path
        if os.path.exists("/sbin"):
            safe_path = safe_path + ":/sbin"
        env["PATH"] = safe_path
        return env
```

**Files to Modify:**
- `sago/mcp/client.py`

**Test Files to Add/Modify:**
- `tests/unit/test_mcp_manager.py::test_path_isolation`

**Estimated Effort:** 1-2 hours  
**Dependencies:** None

---

### 1.4 Checkpoint Path Traversal Vulnerability

**File:** `sago/engine/checkpoint.py:262-280`  
**Function:** `restore_checkpoint()` - path validation  
**Severity:** 🔴 CRITICAL  
**Status:** ⬜ Not Started  

**Problem:**
The current path validation can be bypassed:

1. **Symlink Attack:** An attacker could create a checkpoint with a symlink pointing outside the workspace
2. **Path Normalization:** Paths like `../../../etc/passwd` might not be properly normalized
3. **Validation Only at Restore Time:** Malicious checkpoints can be created and validated later

Current validation:
```python
def _validate_restore_path(self, target_path: Path) -> bool:
    resolved = target_path.resolve()
    try:
        resolved.relative_to(self.root.resolve())
        return True
    except ValueError:
        pass
    for allowed in self._allowed_restore_paths:
        try:
            resolved.relative_to(allowed)
            return True
        except ValueError:
            continue
    return False
```

**Issues:**
- `resolve()` follows symlinks, which could point anywhere
- No check for `..` in the path
- No validation at checkpoint creation time

**Expected Behavior:**
- Validate paths at BOTH creation and restore time
- Reject paths containing `..` or other traversal patterns
- Resolve symlinks and validate the final destination
- Reject absolute paths outside workspace (unless in allowed list)

**Solution:**
```python
def _validate_restore_path(self, target_path: Path) -> bool:
    """Validate that a restore target path is allowed.
    
    Returns True if the path is safe to restore to.
    """
    import re
    
    # Convert to Path if string
    target_path = Path(target_path)
    
    # 1. Check for path traversal patterns in string representation
    path_str = str(target_path)
    if re.search(r'(^|[/\\])\.\.([/\\]|$)', path_str):
        logger.warning("Path traversal attempt detected: %s", path_str)
        return False
    
    # 2. Resolve symlinks
    try:
        resolved = target_path.resolve()
    except (OSError, RuntimeError) as e:
        logger.warning("Failed to resolve path %s: %s", target_path, e)
        return False
    
    # 3. Check if within workspace root
    try:
        self.root.resolve()
        resolved.relative_to(self.root.resolve())
        return True
    except ValueError:
        pass
    
    # 4. Check if in allowed restore paths
    for allowed in self._allowed_restore_paths:
        try:
            resolved.relative_to(allowed.resolve())
            return True
        except ValueError:
            continue
    
    logger.warning("Restore path %s resolves to %s which is outside allowed locations", 
                   target_path, resolved)
    return False

# Also validate at checkpoint creation time
def create_checkpoint(
    self, description: str, files: list[str | Path] | None = None
) -> dict[str, Any]:
    """Create a checkpoint snapshot."""
    # ... existing code ...
    
    # Validate all file paths at creation time
    for file_path in files:
        fp = Path(file_path)
        if fp.is_absolute():
            # For absolute paths (external files), validate they're safe to snapshot
            if not self._validate_external_path(fp):
                raise ValueError(f"External path not allowed: {fp}")
        # Relative paths are fine as they're within workspace
    
    # ... rest of existing code ...

def _validate_external_path(self, path: Path) -> bool:
    """Validate that an external path is safe to include in checkpoint."""
    # Check for traversal
    path_str = str(path)
    if re.search(r'(^|[/\\])\.\.([/\\]|$)', path_str):
        return False
    
    # Check if path is readable
    if not path.exists():
        return False
    
    # Check if we can read it
    try:
        path.stat()
    except PermissionError:
        return False
    
    return True
```

**Files to Modify:**
- `sago/engine/checkpoint.py`

**Test Files to Add/Modify:**
- `tests/unit/test_scale_index_and_checkpoint.py::test_checkpoint_path_traversal`
- `tests/unit/test_scale_index_and_checkpoint.py::test_checkpoint_symlink_attack`

**Estimated Effort:** 2-3 hours  
**Dependencies:** None

---

### 1.5 MCP Initialization Handshake Not Implemented

**File:** `sago/mcp/client.py:65-67`  
**Severity:** 🔴 CRITICAL  
**Status:** ⬜ Not Started  

**Problem:**
The commit message states: "Add proper initialization handshake per MCP protocol spec"

But the code has:
```python
self._initialized = False
self._request_id = 0
self._isolated_env: dict[str, str] | None = None
```

And `_initialized` is never set to `True` or checked.

**Expected Behavior:**
- Implement MCP protocol initialization handshake
- Send `initialize` request with client info
- Wait for server's `initialized` response
- Verify server capabilities
- Mark as initialized only after successful handshake

**Solution:**
```python
class MCPClient:
    # ... existing code ...
    
    def connect(self) -> bool:
        """Connect to the MCP server endpoint and perform initialization handshake."""
        # ... existing connection code ...
        
        # Perform MCP protocol initialization handshake
        if not self._perform_handshake():
            self.close()
            return False
        
        self._initialized = True
        logger.info("MCP client initialized: %s", self.server_url)
        return True
    
    def _perform_handshake(self) -> bool:
        """Perform MCP protocol initialization handshake.
        
        According to MCP spec:
        1. Client sends initialize request with clientInfo
        2. Server responds with initialized result or error
        3. Client can then send requests
        """
        import json
        
        client_info = {
            "protocolVersion": "2024-11-05",  # Current MCP protocol version
            "capabilities": {
                "tools": {},
                "prompts": {},
                "resources": {},
            },
            "clientInfo": {
                "name": "SAGO-Agent",
                "version": self._get_sago_version(),
            }
        }
        
        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": client_info["capabilities"],
                    "clientInfo": client_info["clientInfo"],
                }
            }
            
            # Send request
            if not self._send_request(request):
                logger.error("Failed to send initialize request")
                return False
            
            # Wait for response
            response = self._wait_for_response(request["id"])
            if not response:
                logger.error("No response to initialize request")
                return False
            
            if response.get("error"):
                logger.error("MCP initialization error: %s", response["error"])
                return False
            
            # Server should send notification, then we're good
            logger.debug("MCP handshake completed successfully")
            return True
            
        except Exception as e:
            logger.error("MCP handshake failed: %s", e)
            return False
    
    def _get_sago_version(self) -> str:
        """Get SAGO version."""
        try:
            from sago.version import __version__
            return __version__
        except ImportError:
            return "0.0.0-dev"
```

**Files to Modify:**
- `sago/mcp/client.py`

**Test Files to Add/Modify:**
- `tests/unit/test_mcp_manager.py::test_mcp_handshake`

**Estimated Effort:** 3-4 hours  
**Dependencies:** MCP protocol specification compliance

---

# 2. 🟡 Code Quality & Reliability Issues (Medium Priority)

### 2.1 Cleanup Defaults Could Be More Conservative

**File:** `sago/cleanup.py:389-391`  
**Function:** `clean_database()` - `min_session_age_days` parameter  
**Severity:** 🟡 HIGH  
**Status:** ⬜ Not Started  

**Problem:**
Current default is 7 days, which might be too aggressive:
```python
def clean_database(
    ...
    min_session_age_days: float = 7.0,  # Only delete sessions older than this
)
```

**Issues:**
- Users might accidentally delete recent sessions they still need
- No persistent configuration (must pass parameter each time)
- No warning for sessions < 7 days

**Expected Behavior:**
- More conservative default (e.g., 30 days)
- Configurable via configuration file
- Clear warnings when deleting any sessions

**Solution:**
```python
# In sago/cleanup.py

# Add configuration loading
CLEANUP_CONFIG_PATHS = [
    Path.home() / ".sago" / "cleanup.json",
    Path.home() / ".sago" / "config.json",  # Check for cleanup section
]

@dataclass
class CleanupConfig:
    """Configuration for cleanup operations."""
    min_session_age_days: float = 30.0  # More conservative default
    max_age_days: float | None = None
    keep_recent_sessions: int = 10
    dry_run_default: bool = True
    
    @classmethod
    def load(cls) -> "CleanupConfig":
        """Load configuration from file or use defaults."""
        for config_path in CLEANUP_CONFIG_PATHS:
            if config_path.exists():
                try:
                    data = json.loads(config_path.read_text())
                    # Support both cleanup section and flat config
                    cleanup_data = data.get("cleanup", data)
                    return cls(**cleanup_data)
                except Exception as e:
                    logger.warning("Failed to load cleanup config from %s: %s", config_path, e)
        return cls()

def clean_database(
    ...
    min_session_age_days: float | None = None,  # None means use config default
    ...
) -> CleanResult:
    """Clean empty and stale test sessions from SQLite database."""
    # Load config
    config = CleanupConfig.load()
    
    # Use parameter if provided, else config, else default
    if min_session_age_days is None:
        min_session_age_days = config.min_session_age_days
    
    # Warn if deleting sessions younger than 7 days
    if min_session_age_days < 7.0:
        logger.warning(
            "Deleting sessions younger than 7 days (min_session_age_days=%.1f). "
            "Consider increasing this value to avoid accidental data loss.",
            min_session_age_days
        )
    
    # ... rest of function ...
```

**Files to Modify:**
- `sago/cleanup.py`

**Configuration File Example:**
```json
{
  "cleanup": {
    "min_session_age_days": 30,
    "keep_recent_sessions": 20,
    "dry_run_default": true
  }
}
```

**Test Files to Add/Modify:**
- `tests/unit/test_cleanup_and_gc.py::test_cleanup_config_loading`

**Estimated Effort:** 2-3 hours  
**Dependencies:** None

---

### 2.2 Silent Error Swallowing in Sandbox Workspace Copy

**File:** `sago/tools/system/sandbox.py:118-129`  
**Severity:** 🟡 HIGH  
**Status:** ⬜ Not Started  

**Problem:**
```python
for item in self.workspace_root.iterdir():
    if item.name.startswith((".", "venv", ".venv", "__pycache__", "node_modules")):
        continue
    try:
        dest = sandbox_path / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    except Exception:
        pass  # SILENT FAILURE!
```

**Issues:**
1. **Silent exception swallowing** - no logging of failures
2. **TOCTOU race condition** - workspace can change during copy
3. **No atomicity** - partial copies leave sandbox inconsistent
4. **No timeout** - could hang on large files

**Expected Behavior:**
- Log all copy failures with details
- Use atomic operations where possible
- Add timeout for copy operations
- Provide partial success information

**Solution:**
```python
def run_command(
    self,
    command: str | list[str],
    timeout: int | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a command in an isolated temporary directory sandbox."""
    timeout = timeout or self.config.max_cpu_seconds
    use_namespaces = self.config.use_namespaces and _check_namespace_support()
    
    with tempfile.TemporaryDirectory(prefix="sago_sandbox_") as temp_dir:
        sandbox_path = Path(temp_dir)
        copied_files = []
        copy_errors = []
        
        # Mirror current workspace if requested
        if self.config.copy_workspace and self.workspace_root.exists():
            for item in self.workspace_root.iterdir():
                if item.name.startswith((".", "venv", ".venv", "__pycache__", "node_modules")):
                    continue
                
                try:
                    dest = sandbox_path / item.name
                    start_time = time.time()
                    
                    if item.is_dir():
                        # Use copytree with timeout
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    else:
                        # Check file size and timeout
                        file_size = item.stat().st_size
                        if file_size > 100 * 1024 * 1024:  # 100MB limit
                            logger.warning("Skipping large file: %s (%s)", item, format_size(file_size))
                            copy_errors.append(f"Skipped large file: {item}")
                            continue
                        
                        # Use copy2 with timeout via shutil.copy2 (no built-in timeout)
                        # Implement timeout using threading or signal
                        shutil.copy2(item, dest)
                    
                    copied_files.append(str(item))
                    
                    # Check if we're taking too long
                    if time.time() - start_time > (timeout or 30):
                        logger.warning("Workspace copy taking too long, continuing with partial copy")
                        break
                        
                except PermissionError as e:
                    logger.warning("Permission denied copying %s: %s", item, e)
                    copy_errors.append(f"Permission denied: {item}")
                except FileNotFoundError as e:
                    logger.warning("File not found during copy: %s", e)
                    copy_errors.append(f"File not found: {item}")
                except shutil.Error as e:
                    logger.warning("Error copying %s: %s", item, e)
                    copy_errors.append(f"Copy error: {item}")
                except Exception as e:
                    logger.error("Unexpected error copying %s: %s", item, e, exc_info=True)
                    copy_errors.append(f"Unexpected error: {item}")
        
        # Log summary
        if copy_errors:
            logger.info(
                "Sandbox workspace copy: %d files copied, %d errors",
                len(copied_files), len(copy_errors)
            )
        
        # ... rest of function ...
        
        result = {
            "success": exit_code == 0,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "sandbox_dir": str(sandbox_path),
            "isolated": use_namespaces,
        }
        
        if copy_errors:
            result["copy_errors"] = copy_errors
        if copied_files:
            result["copied_files"] = copied_files
        
        return result
```

**Files to Modify:**
- `sago/tools/system/sandbox.py`

**Test Files to Add/Modify:**
- `tests/unit/test_sandbox.py::test_workspace_copy_errors_logged`

**Estimated Effort:** 2-3 hours  
**Dependencies:** None

---

### 2.3 Inconsistent Null Checks for cutoff_ts

**Files:** Multiple (`sago/cleanup.py`, `sago/engine/checkpoint.py`)  
**Severity:** 🟡 HIGH  
**Status:** ⬜ Not Started  

**Problem:**
Pattern appears in multiple places:
```python
if max_age_days is not None and cutoff_ts is not None:
    for snap in snapshots:
        if snap.stat().st_mtime <= cutoff_ts:
            to_delete.append(snap)
```

**Issue:**
- `cutoff_ts` is only calculated when `max_age_days is not None`
- But the check requires both to be not None
- This is redundant - if `max_age_days` is None, the code path wouldn't reach this check
- Creates potential for bugs if `cutoff_ts` is not properly initialized

**Expected Behavior:**
- Consistent pattern for age-based filtering
- Single source of truth for cutoff calculation
- Clear separation of concerns

**Solution:**
Create a helper function:
```python
# In sago/cleanup.py or a utilities module

def calculate_age_cutoff(max_age_days: float | None) -> float | None:
    """Calculate timestamp cutoff for age-based filtering.
    
    Args:
        max_age_days: Maximum age in days, or None for no limit
        
    Returns:
        Timestamp (seconds since epoch) or None if no limit
    """
    if max_age_days is None:
        return None
    return time.time() - (max_age_days * 86400)

# Then use it consistently:
def clean_backups(
    backup_root: Path | None = None,
    max_age_days: float | None = None,
    dry_run: bool = True,
) -> CleanResult:
    """Clean up old backup directories."""
    # ...
    cutoff_ts = calculate_age_cutoff(max_age_days)
    
    to_delete: list[Path] = []
    if cutoff_ts is not None:
        for sdir in session_dirs:
            if sdir.stat().st_mtime <= cutoff_ts:
                to_delete.append(sdir)
    # ...
```

**Files to Modify:**
- `sago/cleanup.py`
- `sago/engine/checkpoint.py`

**Test Files to Add/Modify:**
- Add tests for the helper function

**Estimated Effort:** 1-2 hours  
**Dependencies:** None

---

# 3. 🟡 Test Infrastructure (Medium Priority)

### 3.1 Install Missing Test Dependencies

**Severity:** 🟡 HIGH  
**Status:** ⬜ Not Started  

**Problem:**
Several test files cannot run due to missing dependencies:
- `textual` - Required by:
  - `test_trace_viewer.py`
  - `test_tui_agent_delegation_autocomplete.py`
  - `test_tui_turn_container.py`
  - `test_delegation_dev_trace.py`
  - `test_langgraph_engine.py`

**Expected Behavior:**
- All tests should be runnable
- Missing dependencies should be clearly documented
- Optional dependencies should have graceful fallbacks

**Solution:**

**Option A: Add to pyproject.toml (Recommended)**
```toml
[project.optional-dependencies]
test = [
    "pytest>=7.0",
    "pytest-asyncio>=0.23",
    "textual>=0.50",
    # ... other test dependencies
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

**Option B: Mock TUI Components**
Create mock modules for textual that allow tests to run:
```python
# tests/mocks/textual.py
"""Mock textual module for tests."""

class App:
    pass

class ComposeResult:
    pass

def on(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

# Export what's needed
__all__ = ["App", "ComposeResult", "on"]
```

Then in tests, mock the imports:
```python
import sys
sys.modules["textual"] = mock_textual
sys.modules["textual.app"] = mock_textual
sys.modules["textual.widgets"] = mock_textual
```

**Option C: Skip TUI Tests When Dependencies Missing**
```python
# conftest.py
import pytest

def pytest_configure(config):
    """Skip tests requiring textual if not installed."""
    try:
        import textual
    except ImportError:
        config.addinivalue_line(
            "markers",
            "requires_textual: mark test as requiring textual"
        )

@pytest.fixture
def requires_textual():
    """Skip test if textual not available."""
    try:
        import textual
        return True
    except ImportError:
        pytest.skip("textual not installed")
```

**Files to Modify:**
- `pyproject.toml`
- Possibly `conftest.py`

**Estimated Effort:** 1-2 hours  

---

### 3.2 Fix Async Test Configuration

**Severity:** 🟡 HIGH  
**Status:** ⬜ Not Started  

**Problem:**
Warning messages:
```
Unknown pytest.mark.asyncio - is this a typo?
```

**Files affected:**
- `test_comprehensive_coverage_and_edge_cases.py`
- `test_next_gen_features.py`

**Cause:**
`pytest-asyncio` plugin not installed or not configured.

**Solution:**

**Option A: Install pytest-asyncio**
```bash
pip install pytest-asyncio
```

**Option B: Remove async markers if not needed**
If tests don't actually use async, remove the markers:
```python
# Before
@pytest.mark.asyncio
async def test_something():
    pass

# After
def test_something():
    pass
```

**Option C: Configure pytest-asyncio**
```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

**Files to Modify:**
- `pyproject.toml`
- Possibly test files

**Estimated Effort:** 1 hour  

---

### 3.3 Add Security Regression Tests

**Severity:** 🟡 HIGH  
**Status:** ⬜ Not Started  

**Problem:**
No explicit tests for security-critical functionality:
- Sandbox actually blocks network
- Sandbox actually limits resources
- MCP environment isolation actually works
- Checkpoint path validation prevents traversal

**Solution:**
Create comprehensive security tests:

```python
# tests/unit/test_sandbox_security.py

import pytest
import subprocess
import tempfile
from pathlib import Path

from sago.tools.system.sandbox import SandboxedExecutor, SandboxConfig


class TestSandboxNetworkIsolation:
    """Test that sandbox blocks network access."""
    
    def test_network_blocked_by_default(self):
        """Verify network is blocked when allow_network=False."""
        executor = SandboxedExecutor(config=SandboxConfig(allow_network=False))
        
        # Try to access network
        result = executor.run_command(
            ["curl", "--max-time", "2", "https://example.com"],
            timeout=5
        )
        
        # Should fail (network blocked or timeout)
        assert not result["success"]
        assert result["exit_code"] != 0
    
    def test_network_allowed_when_enabled(self):
        """Verify network works when allow_network=True."""
        executor = SandboxedExecutor(config=SandboxConfig(allow_network=True))
        
        result = executor.run_command(
            ["curl", "--max-time", "2", "https://example.com"],
            timeout=5
        )
        
        # Should succeed (or at least not be blocked by sandbox)
        # Note: This test may fail in environments without network
        # Can mock curl for more reliable testing
    
    def test_dns_resolution_blocked(self):
        """Verify DNS resolution is blocked."""
        executor = SandboxedExecutor(config=SandboxConfig(allow_network=False))
        
        result = executor.run_command(
            ["ping", "-c", "1", "-W", "1", "google.com"],
            timeout=3
        )
        
        assert not result["success"]


class TestSandboxResourceLimits:
    """Test that sandbox enforces resource limits."""
    
    def test_memory_limit_enforced(self):
        """Verify memory limit is enforced."""
        executor = SandboxedExecutor(
            config=SandboxConfig(max_memory_mb=10)  # 10MB limit
        )
        
        # Try to allocate more memory than limit
        result = executor.run_command(
            ["python3", "-c", "data = 'x' * 100 * 1024 * 1024; print('allocated')"],
            timeout=5
        )
        
        # Should be killed by OOM killer or ulimit
        assert not result["success"]
    
    def test_cpu_time_limit_enforced(self):
        """Verify CPU time limit is enforced."""
        executor = SandboxedExecutor(
            config=SandboxConfig(max_cpu_seconds=1)
        )
        
        # Infinite loop should be killed
        result = executor.run_command(
            ["python3", "-c", "while True: pass"],
            timeout=5
        )
        
        assert not result["success"]
        assert result["exit_code"] != 0
    
    def test_process_limit_enforced(self):
        """Verify process limit is enforced."""
        executor = SandboxedExecutor(
            config=SandboxConfig(max_processes=5)
        )
        
        # Try to spawn many processes
        result = executor.run_command(
            ["bash", "-c", "for i in $(seq 1 100); do sleep 10 & done; wait"],
            timeout=5
        )
        
        # Should fail due to process limit
        assert not result["success"]


class TestSandboxFilesystemIsolation:
    """Test that sandbox isolates filesystem."""
    
    def test_workspace_copy_isolated(self):
        """Verify workspace copy doesn't affect host."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            
            # Create a test file in workspace
            test_file = workspace / "test.txt"
            test_file.write_text("original content")
            
            # Run sandbox with workspace copy
            executor = SandboxedExecutor(
                workspace_root=str(workspace),
                config=SandboxConfig(copy_workspace=True)
            )
            
            result = executor.run_command(
                ["bash", "-c", "echo 'modified' > test.txt"],
                timeout=5
            )
            
            # Original file should be unchanged
            assert test_file.read_text() == "original content"
            
            # Sandbox directory should have modified file
            assert result["sandbox_dir"]
            sandbox_file = Path(result["sandbox_dir"]) / "test.txt"
            assert sandbox_file.exists()
            assert sandbox_file.read_text().strip() == "modified"
    
    def test_cannot_access_outside_sandbox(self):
        """Verify sandbox cannot access files outside sandbox directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_file = Path(temp_dir) / "secret.txt"
            secret_file.write_text("secret data")
            
            executor = SandboxedExecutor(config=SandboxConfig())
            
            # Try to read the secret file
            result = executor.run_command(
                ["cat", str(secret_file)],
                timeout=5
            )
            
            # Should fail - cannot access files outside sandbox
            assert not result["success"] or "No such file" in result["stderr"]


class TestMCPEnvironmentIsolation:
    """Test that MCP environment isolation works."""
    
    def test_env_vars_not_leaked(self):
        """Verify MCP server env vars don't leak to parent process."""
        import os
        
        # Set a test env var in parent
        os.environ["TEST_PARENT_VAR"] = "parent_value"
        
        # Create MCP client with isolated env
        from sago.mcp.client import MCPClient
        
        client = MCPClient(server_url="stdio://echo")
        client._isolated_env = {"SERVER_VAR": "server_value"}
        
        # Build subprocess env
        subprocess_env = client._build_subprocess_env()
        
        # Parent var should not be in subprocess env
        assert "TEST_PARENT_VAR" not in subprocess_env
        
        # Server var should be in subprocess env
        assert subprocess_env.get("SERVER_VAR") == "server_value"
        
        # Safe vars should be present
        assert "PATH" in subprocess_env
        assert "HOME" in subprocess_env
    
    def test_path_is_safe(self):
        """Verify PATH is sanitized in subprocess env."""
        import os
        
        # Set malicious PATH in parent
        original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = "/malicious/bin:/evil/path:" + original_path
        
        try:
            from sago.mcp.client import MCPClient
            
            client = MCPClient(server_url="stdio://echo")
            subprocess_env = client._build_subprocess_env()
            
            # PATH should not contain malicious entries
            assert "/malicious/bin" not in subprocess_env["PATH"]
            assert "/evil/path" not in subprocess_env["PATH"]
            
            # PATH should contain safe entries
            assert "/usr/bin" in subprocess_env["PATH"] or "/bin" in subprocess_env["PATH"]
        finally:
            os.environ["PATH"] = original_path


class TestCheckpointPathValidation:
    """Test that checkpoint path validation works."""
    
    def test_path_traversal_rejected(self):
        """Verify path traversal attempts are rejected."""
        from sago.engine.checkpoint import CheckpointManager
        import tempfile
        
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            
            manager = CheckpointManager(workspace_root=workspace)
            
            # Try to add path with traversal
            test_path = workspace / ".." / "etc" / "passwd"
            
            # Should not be valid
            assert not manager._validate_restore_path(test_path)
    
    def test_symlink_traversal_rejected(self):
        """Verify symlink traversal is rejected."""
        from sago.engine.checkpoint import CheckpointManager
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            
            # Create a symlink pointing outside
            outside_file = Path(temp_dir) / "outside.txt"
            outside_file.write_text("outside")
            
            symlink = workspace / "link.txt"
            symlink.symlink_to(outside_file)
            
            manager = CheckpointManager(workspace_root=workspace)
            
            # Symlink should not be valid for restore
            assert not manager._validate_restore_path(symlink)
    
    def test_within_workspace_allowed(self):
        """Verify paths within workspace are allowed."""
        from sago.engine.checkpoint import CheckpointManager
        import tempfile
        
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            
            manager = CheckpointManager(workspace_root=workspace)
            
            # Path within workspace should be valid
            test_path = workspace / "subdir" / "file.txt"
            assert manager._validate_restore_path(test_path)
    
    def test_allowed_path_works(self):
        """Verify allowed paths are accepted."""
        from sago.engine.checkpoint import CheckpointManager
        import tempfile
        
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            allowed = Path(temp_dir) / "allowed"
            allowed.mkdir()
            
            manager = CheckpointManager(workspace_root=workspace)
            manager.add_allowed_restore_path(allowed)
            
            # Path in allowed directory should be valid
            test_path = allowed / "file.txt"
            assert manager._validate_restore_path(test_path)
```

**Files to Add:**
- `tests/unit/test_sandbox_security.py`

**Estimated Effort:** 4-6 hours  
**Dependencies:** pytest, tempfile, subprocess

---

# 4. 🟡 Documentation Tasks (Medium Priority)

### 4.1 Document Security Model and Limitations

**Severity:** 🟡 HIGH  
**Status:** ⬜ Not Started  

**Problem:**
No comprehensive documentation of:
- What security guarantees are provided
- What the limitations are
- When sandbox isolation is effective
- What threats are NOT protected against

**Solution:**
Create `docs/SECURITY.md`:

```markdown
# SAGO-Agent Security Model

## Overview

SAGO-Agent provides multiple layers of security to protect your system when running untrusted code or connecting to external services.

## Security Features

### 1. Sandboxed Execution

**Protection:** Linux namespace isolation, resource limits, restricted environment  
**Scope:** `sandbox_run` tool and internal sandboxed operations  
**Platform:** Linux only (with namespace support)

#### Linux Namespace Isolation

When available, SAGO uses the following Linux namespaces:

| Namespace | Purpose | Protection |
|-----------|---------|------------|
| Mount (--mount) | Filesystem isolation | Prevents access to host filesystem |
| PID (--pid) | Process isolation | Limits process visibility |
| IPC (--ipc) | Shared memory isolation | Prevents shared memory attacks |
| UTS (--uts) | Hostname isolation | Prevents hostname spoofing |
| Network (--net) | Network isolation | Blocks all network access |
| User (--user) | Privilege de-escalation | Reduces privileges |

**Note:** User namespace is only used if `/proc/sys/kernel/unprivileged_userns_clone == 1`

#### Resource Limits

| Resource | Limit | Purpose |
|----------|-------|---------|
| Virtual Memory | Configurable (default 512MB) | Prevent OOM attacks |
| CPU Time | Configurable (default 30s) | Prevent CPU exhaustion |
| Processes | Configurable (default 16) | Prevent fork bombs |

#### Environment Restrictions

The sandbox provides a minimal, sanitized environment:
- Only essential variables are copied (PATH, LANG, LC_ALL, HOME, TMPDIR, USER)
- Dangerous variables are removed (PYTHONPATH, LD_PRELOAD, LD_LIBRARY_PATH)
- PATH is sanitized to only safe directories

### 2. MCP Server Isolation

**Protection:** Environment variable isolation, credential separation  
**Scope:** All MCP server connections  

Each MCP server runs with:
- Its own isolated environment variables
- No access to parent process environment
- Sanitized PATH
- Only variables explicitly configured for that server

**Warning:** Environment isolation is NOT the same as process isolation. MCP servers can still:
- Access the same files as the parent process (unless running in sandbox)
- Use the same network (unless network sandboxing is enabled)
- Consume system resources (unless resource limits are applied)

### 3. Checkpoint Path Validation

**Protection:** Path traversal prevention, symlink resolution  
**Scope:** Checkpoint restore operations  

When restoring checkpoints:
- All paths are resolved to absolute paths
- Symlinks are followed and validated
- Paths must be within the workspace root OR in the allowed paths list
- Paths containing `..` are rejected

## Limitations and Threats NOT Protected Against

### ⚠️ Not Protected: Running as Root

**Threat:** If SAGO runs as root, sandbox isolation provides limited protection  
**Mitigation:** Always run SAGO as a non-root user

### ⚠️ Not Protected: Container Escape

**Threat:** If SAGO runs in a container, namespace isolation inside the container may not prevent container escape  
**Mitigation:** Use container-level security (seccomp, AppArmor, etc.)

### ⚠️ Not Protected: Kernel Vulnerabilities

**Threat:** Linux kernel vulnerabilities can bypass all isolation mechanisms  
**Mitigation:** Keep your system updated with security patches

### ⚠️ Not Protected: Physical Access

**Threat:** Users with physical access to the machine can bypass all software-based protections  
**Mitigation:** Physical security is required

### ⚠️ Not Protected: Malicious MCP Servers

**Threat:** MCP servers you connect to can perform malicious actions within their environment  
**Mitigation:** Only connect to trusted MCP servers

### ⚠️ Not Protected: Checkpoint Tampering

**Threat:** If an attacker can modify checkpoint files, they may be able to inject malicious paths  
**Mitigation:** Store checkpoints in secure locations, verify checkpoint integrity

## Configuration

### Sandbox Configuration

```python
from sago.tools.system.sandbox import SandboxConfig

config = SandboxConfig(
    max_cpu_seconds=30,        # CPU time limit in seconds
    max_memory_mb=512,         # Memory limit in MB
    max_processes=16,          # Maximum number of processes
    allow_network=False,       # Block network access
    read_only_root=True,       # Make root filesystem read-only
    copy_workspace=True,       # Copy workspace files to sandbox
    use_namespaces=True,       # Use Linux namespaces for isolation
    allowed_env_vars=["PATH", "LANG", "LC_ALL", "HOME", "TMPDIR", "USER"]
)
```

### MCP Configuration

```json
{
  "mcpServers": {
    "my-server": {
      "command": "python3",
      "args": ["-m", "my_mcp_server"],
      "env": {
        "MY_API_KEY": "secret-value"
      },
      "isolate_env": true,
      "timeout": 30.0
    }
  }
}
```

## Reporting Security Issues

If you discover a security vulnerability in SAGO-Agent, please report it responsibly:

1. **DO NOT** open a public GitHub issue
2. Email security concerns to: [SECURITY_EMAIL]
3. Include steps to reproduce the vulnerability
4. Allow reasonable time for a fix to be developed

## Security Checklist for Developers

- [ ] All user-provided paths are validated
- [ ] All file operations use safe functions (not eval, not shell=True)
- [ ] All subprocess calls have timeouts
- [ ] All network operations have timeouts
- [ ] All external inputs are sanitized
- [ ] All errors are logged (not silently swallowed)
- [ ] All security-critical code has tests
```

**Files to Add:**
- `docs/SECURITY.md`

**Estimated Effort:** 2-3 hours  

---

### 4.2 Document MCP Server Configuration

**Severity:** 🟢 MEDIUM  
**Status:** ⬜ Not Started  

**Problem:**
MCP server configuration format not clearly documented.

**Solution:**
Expand `docs/MCP.md` with:
- Configuration file locations
- Configuration format (Claude/Anthropic compatible)
- Environment isolation options
- Security considerations
- Example configurations

**Estimated Effort:** 1-2 hours

---

### 4.3 Update README with New Features

**Severity:** 🟢 MEDIUM  
**Status:** ⬜ Not Started  

**Problem:**
README doesn't mention:
- Comprehensive cleanup system
- SQLite checkpoint persistence
- Dynamic MCP tool bridging
- Sandbox isolation

**Solution:**
Update README.md with:
- New features in v0.1.7
- Usage examples for new commands
- Links to detailed documentation

**Estimated Effort:** 1-2 hours

---

# 5. 🔵 Future Features & Enhancements (Low Priority)

### 5.1 Add Atomic Checkpoint Operations

**Severity:** 🔵 LOW  
**Status:** ⬜ Not Started  

**Idea:**
- Implement atomic checkpoint creation (all or nothing)
- Add checkpoint verification (checksums)
- Support checkpoint signing for integrity

**Estimated Effort:** 3-5 hours

---

### 5.2 Add Sandbox Logging and Auditing

**Severity:** 🔵 LOW  
**Status:** ⬜ Not Started  

**Idea:**
- Log all sandboxed command executions
- Audit trail of what was run and by whom
- Optional: Log to syslog or external system

**Estimated Effort:** 2-3 hours

---

### 5.3 Add Windows Support for Sandbox

**Severity:** 🔵 LOW  
**Status:** ⬜ Not Started  

**Idea:**
- Implement Windows-compatible sandbox using:
  - Job Objects for process limits
  - AppLocker for execution control
  - Windows Containers for isolation

**Estimated Effort:** 5-8 hours

---

### 5.4 Add macOS Support for Sandbox

**Severity:** 🔵 LOW  
**Status:** ⬜ Not Started  

**Idea:**
- Implement macOS-compatible sandbox using:
  - sandbox-exec
  - seatbelt profiles
  - macOS resource limits

**Estimated Effort:** 3-5 hours

---

### 5.5 Add Rate Limiting for MCP Servers

**Severity:** 🔵 LOW  
**Status:** ⬜ Not Started  

**Idea:**
- Rate limit MCP server requests
- Prevent DoS attacks via MCP
- Configurable rate limits per server

**Estimated Effort:** 2-3 hours

---

### 5.6 Add MCP Server Health Checks

**Severity:** 🔵 LOW  
**Status:** ⬜ Not Started  

**Idea:**
- Periodic health checks for MCP servers
- Automatic reconnection on failure
- Circuit breaker pattern for failing servers

**Estimated Effort:** 2-3 hours

---

# 6. 🔵 Technical Debt & Refactoring (Low Priority)

### 6.1 Refactor Cleanup Module

**Severity:** 🔵 LOW  
**Status:** ⬜ Not Started  

**Problem:**
Cleanup code has duplicated patterns for age-based filtering.

**Solution:**
- Extract common patterns into utility functions
- Reduce code duplication
- Improve testability

**Estimated Effort:** 2-3 hours

---

### 6.2 Improve Error Messages

**Severity:** 🔵 LOW  
**Status:** ⬜ Not Started  

**Problem:**
Some error messages lack context or are unclear.

**Solution:**
- Review all error messages
- Add context to error messages
- Use consistent error message format

**Estimated Effort:** 2-3 hours

---

### 6.3 Add Type Hints for All Functions

**Severity:** 🔵 LOW  
**Status:** ⬜ Not Started  

**Problem:**
Some functions lack type hints.

**Solution:**
- Add type hints to all public functions
- Use `typing` module for complex types
- Add return type annotations

**Estimated Effort:** 3-5 hours

---

# 7. 📦 Dependency & Environment Issues

### 7.1 Update Dependencies

**Severity:** 🟡 HIGH  
**Status:** ⬜ Not Started  

**Problem:**
Some dependencies may be outdated or have known vulnerabilities.

**Solution:**
Run dependency updates:
```bash
# Check for outdated dependencies
pip list --outdated

# Update pyproject.toml with new versions
# Run tests to ensure compatibility

# Check for security vulnerabilities
pip install safety
safety check
```

**Estimated Effort:** 1-2 hours

---

### 7.2 Python 3.13 Compatibility

**Severity:** 🟢 MEDIUM  
**Status:** ⬜ Not Started  

**Problem:**
Some type annotations may not be fully compatible with Python 3.13.

**Solution:**
- Test with Python 3.13
- Fix any compatibility issues
- Update type annotations as needed

**Estimated Effort:** 1-2 hours

---

## 📊 Summary Statistics

| Category | Total | Not Started | In Progress | Completed |
|----------|-------|-------------|------------|-----------|
| Critical Security | 5 | 5 | 0 | 0 |
| Code Quality | 5 | 5 | 0 | 0 |
| Test Infrastructure | 3 | 3 | 0 | 0 |
| Documentation | 3 | 3 | 0 | 0 |
| Future Features | 6 | 6 | 0 | 0 |
| Technical Debt | 3 | 3 | 0 | 0 |
| Dependencies | 2 | 2 | 0 | 0 |
| **Total** | **27** | **27** | **0** | **0** |

---

## 🎯 Recommended Work Order

### Phase 1: Critical Security (v0.1.8 - Must Ship)
1. Fix namespace support detection (1.1)
2. Fix resource limits enforcement (1.2)
3. Fix PATH security issue (1.3)
4. Fix checkpoint path traversal (1.4)
5. Implement MCP handshake (1.5)

**Estimated Time:** 10-14 hours  
**Target:** 1-2 weeks

### Phase 2: Infrastructure (v0.1.8 - Should Ship)
1. Add cleanup configuration (2.1)
2. Fix silent error swallowing (2.2)
3. Fix inconsistent null checks (2.3)
4. Install test dependencies (3.1)
5. Fix async test configuration (3.2)
6. Add security regression tests (3.3)

**Estimated Time:** 10-12 hours  
**Target:** 2-3 weeks

### Phase 3: Documentation (v0.1.8 - Nice to Have)
1. Document security model (4.1)
2. Document MCP configuration (4.2)
3. Update README (4.3)

**Estimated Time:** 5-7 hours  
**Target:** 3-4 weeks

### Phase 4: Future Enhancements (v0.1.9+)
All items in sections 5 and 6.

**Estimated Time:** 20-30 hours  
**Target:** v0.1.9 or later

---

## 🚀 Release Checklist

Before releasing v0.1.8:

- [ ] All critical security issues (1.1-1.5) are fixed
- [ ] All existing tests pass
- [ ] Security regression tests are added and passing
- [ ] Documentation is updated
- [ ] CHANGELOG.md is updated
- [ ] Dependencies are up to date
- [ ] Code has been reviewed

---

## 📝 Changelog Template

Use this template for updating CHANGELOG.md:

```markdown
## [0.1.8] - YYYY-MM-DD

### Security
- Fixed namespace support detection to actually verify namespace availability
- Fixed resource limits to properly apply to all child processes
- Fixed PATH sanitization in MCP client to prevent malicious directory access
- Fixed checkpoint path validation to prevent symlink and path traversal attacks
- Implemented proper MCP protocol initialization handshake

### Fixed
- Fixed silent error swallowing in sandbox workspace copy
- Fixed inconsistent null checks for cutoff_ts parameter
- Added cleanup configuration file support

### Added
- Added comprehensive security regression tests
- Added security documentation (docs/SECURITY.md)
- Added MCP environment isolation tests
- Added sandbox resource limit enforcement tests

### Changed
- Increased default min_session_age_days from 7 to 30 days
- Improved error messages and logging throughout
```

---

## 💬 Communication

- **Slack/Discord:** #sago-dev
- **Email:** [TEAM_EMAIL]
- **GitHub Discussions:** [REPO]/discussions

---

## 📅 Timeline

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| Phase 1 Complete | 2026-08-24 | ⬜ Not Started |
| Phase 2 Complete | 2026-08-31 | ⬜ Not Started |
| Phase 3 Complete | 2026-09-07 | ⬜ Not Started |
| v0.1.8 Release | 2026-09-14 | ⬜ Not Started |

---

**Note:** This TODO document is a living document. Update it as work progresses, new issues are discovered, or priorities change.
