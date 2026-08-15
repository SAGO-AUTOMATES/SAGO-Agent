"""Smart Agent Profile Optimizer.

Analyzes each agent profile file, cleans up generic boilerplate,
and enriches tools, handoff chains, and domain-specific technical capabilities.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

# Category-based rich tool suites
CATEGORY_TOOLS = {
    "database-specialists": [
        "database_query",
        "sql_schema",
        "sql_migration",
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "execute_shell",
        "grep_content",
        "diff_tool",
    ],
    "cloud-infra-architecture": [
        "platform_diagnostics",
        "docker_ops",
        "cron_schedule",
        "env_info",
        "env_manager",
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "execute_shell",
        "git_ops",
    ],
    "cloud-providers": [
        "platform_diagnostics",
        "env_info",
        "env_manager",
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "execute_shell",
        "git_ops",
        "secret_scanner",
    ],
    "infrastructure-ops": [
        "platform_diagnostics",
        "docker_ops",
        "process_manager",
        "cron_schedule",
        "env_info",
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "execute_shell",
        "git_ops",
    ],
    "compliance-legal-finance": [
        "secret_scanner",
        "grep_content",
        "code_analyzer",
        "read_file",
        "write_file",
        "edit_file",
        "diff_tool",
        "git_blame",
    ],
    "language-specific": [
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "repo_map",
        "ast_grep",
        "git_blame",
        "code_analyzer",
        "linter",
        "formatter",
        "test_runner",
        "execute_shell",
        "diff_tool",
    ],
    "engineering-dev": [
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "repo_map",
        "ast_grep",
        "git_blame",
        "code_analyzer",
        "linter",
        "formatter",
        "test_runner",
        "execute_shell",
        "diff_tool",
    ],
    "frontend-frameworks": [
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "repo_map",
        "git_blame",
        "code_analyzer",
        "linter",
        "formatter",
        "test_runner",
        "execute_shell",
        "diff_tool",
    ],
    "testing-quality": [
        "test_runner",
        "debugger",
        "linter",
        "code_analyzer",
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "ast_grep",
        "execute_shell",
        "diff_tool",
    ],
    "data-intelligence": [
        "database_query",
        "sql_schema",
        "data_processor",
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "repo_map",
        "ast_grep",
        "web_search",
        "execute_shell",
    ],
    "specialized-engineering": [
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "repo_map",
        "ast_grep",
        "git_blame",
        "code_analyzer",
        "execute_shell",
        "diff_tool",
    ],
    "design-architecture": [
        "read_file",
        "write_file",
        "edit_file",
        "multi_replace_file",
        "repo_map",
        "ast_grep",
        "code_analyzer",
        "diff_tool",
    ],
}

DEFAULT_DEV_TOOLS = [
    "read_file",
    "write_file",
    "edit_file",
    "multi_replace_file",
    "repo_map",
    "grep_content",
    "execute_shell",
]

# Domain-tailored handoff targets
CATEGORY_HANDOFFS = {
    "database-specialists": [
        "backend-engineer",
        "python-engineer",
        "dbre-engineer",
        "db-migration-tools-engineer",
        "security-engineer",
        "reviewer",
    ],
    "cloud-infra-architecture": [
        "devops",
        "kubernetes-engineer",
        "terraform-engineer",
        "security-engineer",
        "cloud-architect",
        "reviewer",
    ],
    "cloud-providers": [
        "cloud-architect",
        "devops",
        "security-engineer",
        "terraform-engineer",
        "reviewer",
    ],
    "infrastructure-ops": [
        "devops",
        "site-reliability-engineer",
        "kubernetes-engineer",
        "docker-engineer",
        "security-engineer",
        "reviewer",
    ],
    "compliance-legal-finance": [
        "security-engineer",
        "appsec-engineer",
        "audit-engineer",
        "reviewer",
    ],
    "language-specific": [
        "reviewer",
        "qa-engineer",
        "tester",
        "test-runner",
        "security-engineer",
        "backend-engineer",
    ],
    "engineering-dev": [
        "reviewer",
        "qa-engineer",
        "tester",
        "security-engineer",
        "system-architect",
    ],
    "frontend-frameworks": [
        "designer",
        "ui-designer",
        "reviewer",
        "e2e-automation-engineer",
        "backend-engineer",
    ],
    "testing-quality": [
        "python-engineer",
        "backend-engineer",
        "frontend-engineer",
        "reviewer",
        "security-engineer",
    ],
    "data-intelligence": [
        "data-engineer",
        "mlops-engineer",
        "backend-engineer",
        "reviewer",
        "python-engineer",
    ],
    "specialized-engineering": ["system-architect", "reviewer", "qa-engineer", "devops"],
    "design-architecture": [
        "system-architect",
        "backend-engineer",
        "frontend-engineer",
        "reviewer",
    ],
}


def clean_and_enrich_profile(file_path: Path) -> bool:
    """Clean static boilerplate and enrich tools & handoffs."""
    content = file_path.read_text(encoding="utf-8")

    # 1. Strip out the static boilerplate if present
    content = re.sub(
        r"### Enterprise Execution Guidelines\n(?:1\..*?\n2\..*?\n3\..*?\n(?:   -.*?\n)*\n)?",
        "",
        content,
    )

    # 2. Extract Category
    cat_match = re.search(r"Category:\s*([\w\-]+)", content)
    cat = cat_match.group(1).strip() if cat_match else "general"

    # 3. Determine optimal tools
    tools = CATEGORY_TOOLS.get(cat, DEFAULT_DEV_TOOLS)
    tools_repr = str(tools)

    # 4. Determine optimal handoffs
    handoffs = CATEGORY_HANDOFFS.get(cat, ["reviewer", "qa-engineer", "security-engineer"])
    handoffs_repr = str(handoffs)

    # 5. Update tools in file
    content = re.sub(
        r"tools=\[.*?\]",
        f"tools={tools_repr}",
        content,
        flags=re.DOTALL,
    )

    # 6. Update handoff_to in file
    content = re.sub(
        r"handoff_to=\[.*?\]",
        f"handoff_to={handoffs_repr}",
        content,
        flags=re.DOTALL,
    )

    file_path.write_text(content, encoding="utf-8")
    return True


def run():
    profiles = glob.glob("sago/agents/profiles/*.py")
    count = 0
    for p in profiles:
        if Path(p).name.startswith("__"):
            continue
        if clean_and_enrich_profile(Path(p)):
            count += 1
    print(f"Successfully processed and enriched {count} agent profile files.")


if __name__ == "__main__":
    run()
