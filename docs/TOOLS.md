# Sago - Tools Reference

> Complete documentation for all 45 tools with usage examples and error handling.

## Permission System

All tools are protected by a risk-based permission system. Tools are categorized by risk level:

| Risk Level | Tools | Default Behavior |
|------------|-------|------------------|
| **Safe** | read_file, glob_files, grep_content, env_info, os_detector | Auto-approved |
| **Low** | write_file, edit_file, file_operations, archive | Auto-approved |
| **Medium** | execute_shell, background_process, docker_ops | Requires approval |
| **High** | ssh_connect, ssh_command, sudo_executor | Requires approval |
| **Critical** | spawn_agent | Requires approval |

### Managing Permissions

```python
from sago.permissions import get_permission_manager

pm = get_permission_manager()

# Check if a tool can be executed
allowed, reason = pm.check_permission("execute_shell")
# allowed = False, reason = "Tool 'execute_shell' requires approval (risk: medium)"

# Approve a tool for a session
pm.approve_tool("execute_shell", session_id="my-session")

# Block a tool globally
pm.config.blocked_tools.append("sudo_executor")
```

### Risk Level Assignment

```python
from sago.permissions import TOOL_RISK_LEVELS, RiskLevel

# Check risk level
risk = TOOL_RISK_LEVELS["execute_shell"]  # RiskLevel.MEDIUM
risk = TOOL_RISK_LEVELS["sudo_executor"]  # RiskLevel.HIGH
```

---

## Tool Categories

### File Operations (15 tools)

#### `read_file`
Read file contents with encoding detection.

```python
from sago.tools.file.read_file import ReadFileTool

tool = ReadFileTool()
result = tool.execute(path="main.py", encoding="utf-8")
```

**Parameters:**
- `path` (str): File path
- `encoding` (str, optional): File encoding

**Errors:**
- `FileNotFoundError`: File doesn't exist
- `PermissionError`: No read access
- `UnicodeDecodeError`: Encoding mismatch

---

#### `write_file`
Write content to file, creating directories if needed.

```python
from sago.tools.file.write_file import WriteFileTool

tool = WriteFileTool()
result = tool.execute(path="output.txt", content="Hello")
```

**Parameters:**
- `path` (str): File path
- `content` (str): Content to write
- `append` (bool, optional): Append mode

**Errors:**
- `PermissionError`: No write access
- `IsADirectoryError`: Path is directory

---

#### `edit_file`
Edit file with exact string replacement.

```python
from sago.tools.file.edit_file import EditFileTool

tool = EditFileTool()
result = tool.execute(
    path="main.py",
    old_string="def foo():",
    new_string="def bar():"
)
```

**Parameters:**
- `path` (str): File path
- `old_string` (str): Text to replace
- `new_string` (str): Replacement text
- `replaceAll` (bool, optional): Replace all occurrences

**Errors:**
- `ValueError`: old_string not found
- `ValueError`: Multiple matches found

---

#### `glob_files`
Find files matching patterns.

```python
from sago.tools.file.glob_files import GlobFilesTool

tool = GlobFilesTool()
result = tool.execute(pattern="**/*.py", path="src/")
```

**Parameters:**
- `pattern` (str): Glob pattern
- `path` (str, optional): Directory to search

---

#### `grep_content`
Search file contents with regex.

```python
from sago.tools.file.grep_content import GrepContentTool

tool = GrepContentTool()
result = tool.execute(pattern="def \w+\(", include="*.py")
```

**Parameters:**
- `pattern` (str): Regex pattern
- `include` (str, optional): File pattern
- `path` (str, optional): Directory to search

---

#### `file_ops`
Move, copy, delete, rename files.

```python
from sago.tools.file.file_ops import FileOpsTool

tool = FileOpsTool()
result = tool.execute(operation="copy", source="a.txt", dest="b.txt")
```

**Parameters:**
- `operation` (str): move|copy|delete|rename
- `source` (str): Source path
- `dest` (str, optional): Destination path

---

#### `directory_scanner` (NEW)
Smart directory scanning with language detection.

```python
from sago.tools.file.directory_scanner import DirectoryScanner

scanner = DirectoryScanner(max_files=10000)
result = scanner.scan("/path/to/project")

print(result.languages)  # {'python': 50, 'javascript': 30}
print(result.frameworks)  # ['node', 'docker']
print(result.categories)  # {'backend': 50, 'frontend': 30}
```

**Features:**
- Detects 40+ languages
- Detects 20+ frameworks
- Categorizes files
- Skips node_modules, __pycache__, etc.

---

#### `agent_delegator` (NEW)
Smart agent routing based on context.

```python
from sago.tools.file.agent_delegator import get_delegator

delegator = get_delegator()
result = delegator.delegate(
    task="fix python bug",
    language="python"
)

print(result.primary_agent)  # "debugger"
print(result.confidence)     # 0.5
print(result.reason)         # "language:python + task:bug"
```

---

#### `data_processor`
Parse and transform JSON/YAML data.

```python
from sago.tools.file.data_processor import DataProcessorTool

tool = DataProcessorTool()
result = tool.execute(operation="parse", content='{"key": "value"}')
```

**Operations:** parse, validate, format, query, merge

---

#### `database_query`
Execute SQL queries on SQLite databases.

```python
from sago.tools.file.database_query import DatabaseQueryTool

tool = DatabaseQueryTool()
result = tool.execute(db_path="data.db", query="SELECT * FROM users")
```

---

#### `hash_checksum`
Calculate file/text hashes.

```python
from sago.tools.file.hash_checksum import HashChecksumTool

tool = HashChecksumTool()
result = tool.execute(path="file.txt", algorithm="sha256")
```

**Algorithms:** md5, sha1, sha256, sha512

---

#### `archive`
Create/extract archives.

```python
from sago.tools.file.archive import ArchiveTool

tool = ArchiveTool()
result = tool.execute(operation="create", path="archive.zip", files=["a.txt", "b.txt"])
```

**Formats:** zip, tar, tar.gz, tar.bz2

---

#### `pdf_reader`
Extract text from PDF files.

```python
from sago.tools.file.pdf_reader import PdfReaderTool

tool = PdfReaderTool()
result = tool.execute(path="document.pdf")
```

---

#### `regex_tester`
Test and debug regular expressions.

```python
from sago.tools.file.regex_tester import RegexTesterTool

tool = RegexTesterTool()
result = tool.execute(pattern=r"\d+", text="abc123def456")
```

---

#### `diff_tool`
Compare files or text.

```python
from sago.tools.file.diff_tool import DiffTool

tool = DiffTool()
result = tool.execute(file1="old.py", file2="new.py")
```

---

### Shell Operations (2 tools)

#### `execute_shell`
Execute shell commands.

```python
from sago.tools.shell.execute import ExecuteShellTool

tool = ExecuteShellTool()
result = tool.execute(command="ls -la", timeout=30)
```

**Parameters:**
- `command` (str): Shell command
- `timeout` (int, optional): Timeout in seconds
- `cwd` (str, optional): Working directory

**Errors:**
- `TimeoutError`: Command timed out
- `subprocess.CalledProcessError`: Non-zero exit code

---

#### `background_process`
Run commands in background.

```python
from sago.tools.shell.background import BackgroundProcessTool

tool = BackgroundProcessTool()
result = tool.execute(command="python server.py", name="server")
```

---

### SSH Operations (3 tools)

#### `ssh_connect`
Establish SSH connection.

```python
from sago.tools.ssh.ssh_connect import SSHConnectTool

tool = SSHConnectTool()
result = tool.execute(host="example.com", user="root", key_path="~/.ssh/id_rsa")
```

---

#### `ssh_command`
Execute remote commands.

```python
from sago.tools.ssh.ssh_command import SSHCommandTool

tool = SSHCommandTool()
result = tool.execute(connection_id="conn1", command="df -h")
```

---

#### `ssh_transfer`
Transfer files via SCP/SFTP.

```python
from sago.tools.ssh.ssh_transfer import SSHTransferTool

tool = SSHTransferTool()
result = tool.execute(connection_id="conn1", local="file.txt", remote="/tmp/file.txt")
```

---

### Coding Tools (7 tools)

#### `code_analyzer`
Analyze code structure and complexity.

```python
from sago.tools.coding.code_analyzer import CodeAnalyzerTool

tool = CodeAnalyzerTool()
result = tool.execute(path="main.py", language="python")
```

**Output:** functions, classes, complexity, imports, dependencies

---

#### `linter`
Lint code for errors.

```python
from sago.tools.coding.linter import LinterTool

tool = LinterTool()
result = tool.execute(path="main.py", linter="ruff")
```

---

#### `formatter`
Format code.

```python
from sago.tools.coding.formatter import FormatterTool

tool = FormatterTool()
result = tool.execute(path="main.py", formatter="black")
```

---

#### `test_runner`
Run tests.

```python
from sago.tools.coding.test_runner import TestRunnerTool

tool = TestRunnerTool()
result = tool.execute(path="tests/", framework="pytest")
```

---

#### `debugger`
Debug code issues.

```python
from sago.tools.coding.debugger import DebuggerTool

tool = DebuggerTool()
result = tool.execute(path="main.py", error="NameError: name 'x' is not defined")
```

---

#### `log_analyzer`
Analyze log files.

```python
from sago.tools.coding.log_analyzer import LogAnalyzerTool

tool = LogAnalyzerTool()
result = tool.execute(path="app.log", pattern="ERROR")
```

---

#### `text_summarizer`
Summarize text.

```python
from sago.tools.coding.text_summarizer import TextSummarizerTool

tool = TextSummarizerTool()
result = tool.execute(text="Long text...", max_length=100)
```

---

### Network Tools (5 tools)

#### `http_client`
Make HTTP requests.

```python
from sago.tools.network.http_client import HttpClientTool

tool = HttpClientTool()
result = tool.execute(url="https://api.example.com", method="GET")
```

---

#### `web_crawler`
Crawl websites.

```python
from sago.tools.network.web_crawler import WebCrawlerTool

tool = WebCrawlerTool()
result = tool.execute(url="https://example.com", depth=2)
```

---

#### `dns_lookup`
DNS resolution.

```python
from sago.tools.network.dns_lookup import DnsLookupTool

tool = DnsLookupTool()
result = tool.execute(domain="example.com", record_type="A")
```

---

#### `port_scan`
Scan ports.

```python
from sago.tools.network.port_scan import PortScanTool

tool = PortScanTool()
result = tool.execute(host="example.com", ports="80,443,8080")
```

---

#### `config_manager`
Manage network configurations.

```python
from sago.tools.network.config_manager import ConfigManagerTool

tool = ConfigManagerTool()
result = tool.execute(operation="get", key="proxy")
```

---

### Admin Tools (4 tools)

#### `software_install`
Install software packages.

```python
from sago.tools.admin.software_install import SoftwareInstallTool

tool = SoftwareInstallTool()
result = tool.execute(package="nginx", manager="apt")
```

---

#### `permission_manager`
Manage file permissions.

```python
from sago.tools.admin.permission_manager import PermissionManagerTool

tool = PermissionManagerTool()
result = tool.execute(path="script.sh", mode="755")
```

---

#### `sudo_executor`
Execute with sudo.

```python
from sago.tools.admin.sudo_executor import SudoExecutorTool

tool = SudoExecutorTool()
result = tool.execute(command="systemctl restart nginx")
```

---

#### `prompt_generator`
Generate prompts.

```python
from sago.tools.admin.prompt_generator import PromptGeneratorTool

tool = PromptGeneratorTool()
result = tool.execute(template="code_review", context={"file": "main.py"})
```

---

### System Tools (8 tools)

#### `os_detector`
Detect operating system.

```python
from sago.tools.system.os_detector import OSDetectorTool

tool = OSDetectorTool()
result = tool.execute()
# {'os': 'linux', 'distro': 'ubuntu', 'version': '22.04'}
```

---

#### `process_manager`
Manage processes.

```python
from sago.tools.system.process_manager import ProcessManagerTool

tool = ProcessManagerTool()
result = tool.execute(operation="list", pattern="python")
```

---

#### `env_manager`
Manage environment variables.

```python
from sago.tools.system.env_manager import EnvManagerTool

tool = EnvManagerTool()
result = tool.execute(operation="get", key="PATH")
```

---

#### `git_ops`
Git operations.

```python
from sago.tools.system.git_ops import GitOpsTool

tool = GitOpsTool()
result = tool.execute(operation="status")
```

**Operations:** status, log, diff, commit, push, pull, branch

---

#### `docker_ops`
Docker operations.

```python
from sago.tools.system.docker_ops import DockerOpsTool

tool = DockerOpsTool()
result = tool.execute(operation="ps")
```

**Operations:** ps, build, run, stop, compose

---

#### `cron_schedule`
Manage cron jobs.

```python
from sago.tools.system.cron_schedule import CronScheduleTool

tool = CronScheduleTool()
result = tool.execute(operation="add", schedule="0 * * * *", command="backup.sh")
```

---

#### `screenshot`
Capture screenshots.

```python
from sago.tools.system.screenshot import ScreenshotTool

tool = ScreenshotTool()
result = tool.execute(output="screenshot.png")
```

---

#### `env_info`
System information.

```python
from sago.tools.system.env_info import EnvInfoTool

tool = EnvInfoTool()
result = tool.execute(info_type="system")
```

**Types:** system, disk, memory, network

---

## Error Handling

### Tool Errors

All tools raise specific exceptions:

```python
from sago.errors.exceptions import (
    ToolError,
    ToolNotFoundError,
    ToolExecutionError,
    ToolTimeoutError,
    ToolPermissionError,
)
```

### Recovery Strategies

```python
from sago.errors.recovery import RecoveryManager

recovery = RecoveryManager()

# Automatic recovery
result = recovery.execute_with_recovery(
    tool=my_tool,
    params={},
    max_retries=3,
    fallback_tools=[alternative_tool1, alternative_tool2],
)
```

### Error Callbacks

```python
def on_error(tool_name: str, error: Exception, context: dict):
    """Handle tool errors."""
    print(f"Tool {tool_name} failed: {error}")
    # Log, notify, retry, etc.

recovery.on_error = on_error
```

---

## Agent Handoff Tool

### `spawn_agent`

Delegate tasks to specialized agents with recursion protection and structured handoffs.

**Parameters:**
- `task` (str): The task to delegate
- `agent_name` (str): Target agent name (e.g., "python-engineer")
- `context` (dict): Optional context to pass to the agent
- `feedback` (FeedbackRequest): Optional feedback request

**Features:**
- **RecursionGuard**: Prevents infinite loops with depth limit (5), visit limit (15), cycle detection
- **HandoffContext**: Structured context passing between agents
- **FeedbackRequest**: Agent-to-agent feedback requests
- **Error Propagation**: Breaks on failure instead of propagating error strings

**Usage:**

```python
from sago.tools.file.spawn_agent import SpawnAgentTool

tool = SpawnAgentTool()

# Simple delegation
result = tool.execute({
    "task": "Fix the authentication bug",
    "agent_name": "python-engineer"
})

# With context
result = tool.execute({
    "task": "Review this code",
    "agent_name": "code-reviewer",
    "context": {
        "codebase": {...},
        "previous_results": [...]
    }
})

# With feedback request
from sago.agents.handoff import FeedbackRequest

feedback = FeedbackRequest(
    from_agent="python-engineer",
    to_agent="code-reviewer",
    question="Review this code for security issues",
    context={"file": "auth.py"}
)

result = tool.execute({
    "task": "Review code for security",
    "agent_name": "code-reviewer",
    "feedback": feedback
})
```

**Response Format:**

```python
{
    "status": "success",
    "agent": "python-engineer",
    "agent_role": "Senior Python Engineer",
    "result": "Fixed authentication bug...",
    "handoff_to": "code-reviewer",
    "context_sent": ["codebase", "previous_results"],
    "recursion_depth": 2,
    "visited_agents": ["python-engineer", "code-reviewer"],
    "timestamp": "2025-01-15T10:30:00"
}
```

**Recursion Protection:**

The tool uses a `RecursionGuard` to prevent infinite loops:

```python
from sago.agents.handoff import RecursionGuard

# Default limits
guard = RecursionGuard(
    depth_limit=5,        # Max chain depth
    visits_limit=15,      # Max total agent visits
    same_agent_limit=2    # Max visits to same agent
)

# Check before visiting
if guard.can_visit("code-reviewer"):
    guard.record_visit("code-reviewer")
    # Execute agent
else:
    # Return error - recursion limit reached
```

**Error Handling:**

```python
# Catches and reports:
# - Recursion limit exceeded
# - Cycle detection (A->B->A)
# - Same agent visited too many times
# - Agent not found
# - Execution timeout

result = tool.execute({
    "task": "Complex task",
    "agent_name": "python-engineer"
})

if result.get("status") == "error":
    print(f"Error: {result.get('error')}")
```
