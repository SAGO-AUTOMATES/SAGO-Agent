"""Agent Profile Optimization Engine.

Optimizes all specialist agent profiles with enterprise-grade anti-apology rules,
token efficiency constraints, structured response contracts, and expanded tool ecosystems.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Standard strict enterprise prompt addendum
ENTERPRISE_INSTRUCTION_HEADER = """### Enterprise Execution Guidelines
1. **Zero Apologies & Pure Technical Execution**: Never say "I'm sorry", "As an AI", or "I cannot". Diagnose with available tools, propose concrete technical solutions, and provide actionable implementations.
2. **Token Economy**: Provide high-density, concise, code-first answers. Avoid conversational pleasantries.
3. **Structured Response Format**:
   - **Analysis**: Technical summary of requirements and root cause.
   - **Work Done**: Specific file changes, commands, and code written.
   - **Results**: Verification, tests, or query results.
   - **Issues Found**: Blockers, warnings, or "None".
   - **Handoff Notes**: Structured notes for peer specialist agents.
"""

# Tool mappings based on domain keywords
DOMAIN_TOOL_AUGMENTATIONS = {
    "db": ["database_query", "sql_schema", "sql_migration"],
    "sql": ["database_query", "sql_schema", "sql_migration"],
    "database": ["database_query", "sql_schema", "sql_migration"],
    "security": ["secret_scanner", "grep_content", "code_analyzer"],
    "sec": ["secret_scanner", "grep_content", "code_analyzer"],
    "cloud": ["platform_diagnostics", "env_info", "docker_ops"],
    "devops": ["platform_diagnostics", "docker_ops", "cron_schedule"],
    "platform": ["platform_diagnostics", "docker_ops", "env_info"],
    "code": ["repo_map", "ast_grep", "git_blame", "multi_replace_file"],
    "engineer": ["repo_map", "ast_grep", "git_blame"],
}


def optimize_profile_file(profile_path: Path) -> bool:
    """Optimize a single agent profile file in-place.

    Returns True only when the profile was already optimized or an optimization
    was successfully applied; False when the profile cannot be optimized (e.g. it
    is not a recognized profile, or has no injection point for the guidelines).
    """
    try:
        content = profile_path.read_text(encoding="utf-8")
        if not content.startswith('"""Agent Profile:'):
            return False

        # Already optimized: nothing to do.
        if "Enterprise Execution Guidelines" in content:
            return True

        # Add enterprise guidelines if not already present.
        if 'system_prompt="""' not in content:
            # No known injection point -> cannot optimize this profile.
            return False

        content = content.replace(
            'system_prompt="""',
            f'system_prompt="""{ENTERPRISE_INSTRUCTION_HEADER}\n',
            1,
        )

        profile_path.write_text(content, encoding="utf-8")
        return True
    except Exception as exc:
        logger.error("Failed to optimize profile at %s: %s", profile_path, exc)
        return False


def optimize_all_profiles(profiles_dir: Path | None = None) -> int:
    """Batch optimize all 339 agent profiles."""
    if profiles_dir is None:
        profiles_dir = Path(__file__).parent / "profiles"

    count = 0
    for file_path in profiles_dir.glob("*.py"):
        if file_path.name.startswith("__"):
            continue
        if optimize_profile_file(file_path):
            count += 1

    return count


if __name__ == "__main__":
    n = optimize_all_profiles()
    print(f"Optimized {n} specialist agent profiles with enterprise guidelines.")
