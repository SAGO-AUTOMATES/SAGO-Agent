"""Unit tests for SAGO Plugins, Custom Skills, and New Production Tools."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sago.plugins.base import BasePlugin, PluginManager, PluginMetadata
from sago.skills.loader import SkillLoader
from sago.tools.coding.ast_grep import AstGrepTool
from sago.tools.coding.git_blame import GitBlameTool
from sago.tools.security.secret_scanner import SecretScannerTool
from sago.tools.web.search import WebSearchTool


class SampleTestPlugin(BasePlugin):
    def __init__(self):
        self.meta = PluginMetadata(
            name="test_plugin",
            version="1.0.0",
            author="Tester",
            description="A test plugin",
        )

    def on_user_message(self, message: str, context: dict) -> str:
        return f"[PROCESSED] {message}"


def test_plugin_lifecycle():
    pm = PluginManager()
    plugin = SampleTestPlugin()
    pm.register_plugin(plugin)

    assert len(pm.list_plugins()) == 1
    assert pm.get_plugin("test_plugin") is not None

    # Test hook
    processed = pm.hook_user_message("hello", {})
    assert processed == "[PROCESSED] hello"

    # Disable plugin
    pm.disable_plugin("test_plugin")
    unprocessed = pm.hook_user_message("hello", {})
    assert unprocessed == "hello"


def test_skill_loader_markdown_parsing():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "test-skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"

        skill_file.write_text(
            """---
name: security-audit
description: Comprehensive security and vulnerability analysis
tools: [grep_content, secret_scanner, linter]
steps:
  - Run secret scanner
  - Check dependency vulnerabilities
  - Review authentication endpoints
---
## Security Instructions
Always follow OWASP Top 10 guidelines when reviewing code.
""",
            encoding="utf-8",
        )

        skill = SkillLoader.parse_markdown_skill(skill_file)
        assert skill is not None
        assert skill.name == "security-audit"
        assert "secret_scanner" in skill.tools
        assert len(skill.steps) == 3

        prompt = skill.to_prompt_context()
        assert "Active Skill: security-audit" in prompt
        assert "OWASP Top 10" in prompt


def test_secret_scanner_detection():
    scanner = SecretScannerTool()
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "config.py"
        test_file.write_text(
            'OPENAI_KEY = "sk-abcdef1234567890abcdef1234567890"\n', encoding="utf-8"
        )

        result = scanner.run(directory=tmpdir)
        assert "OpenAI API Key" in result or "secret" in result.lower()


def test_ast_grep_tool():
    tool = AstGrepTool()
    with tempfile.TemporaryDirectory() as tmpdir:
        code_file = Path(tmpdir) / "service.py"
        code_file.write_text(
            """
class UserService:
    def authenticate(self, username, password):
        return True

def create_user(name):
    pass
""",
            encoding="utf-8",
        )

        class_res = tool.run(pattern_type="class", name_pattern="UserService", directory=tmpdir)
        assert "UserService" in class_res

        func_res = tool.run(pattern_type="function", name_pattern="create_user", directory=tmpdir)
        assert "create_user" in func_res


def test_web_search_tool_graceful():
    tool = WebSearchTool()
    res = tool.run(query="Python asyncio")
    assert isinstance(res, str)
    assert len(res) > 0


def test_git_blame_tool_nonexistent():
    tool = GitBlameTool()
    res = tool.run(path="/nonexistent/file/path.py")
    assert "does not exist" in res
