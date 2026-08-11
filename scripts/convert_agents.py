#!/usr/bin/env python3
"""Convert agent markdown files from agents-readme to sago profile files.

This script reads all .md agent files from the reference repo and converts them
to Python profile files that sago can load.
"""

import re
from pathlib import Path
from typing import Any


def parse_agent_md(file_path: Path) -> dict[str, Any] | None:
    """Parse an agent markdown file and extract key information."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    result = {
        "name": file_path.stem,  # e.g., "security-engineer"
        "codename": "Specialist",
        "role": "Specialist",
        "description": "",
        "system_prompt": "",
        "skills": [],
        "tools": [],
        "handoff_to": [],
    }

    # Extract title/role from first line
    # Format: # Role Name — Description
    title_match = re.match(r"^#\s+(.+?)(?:\s*—\s*(.+))?$", content, re.MULTILINE)
    if title_match:
        result["role"] = title_match.group(1).strip()
        if title_match.group(2):
            result["description"] = title_match.group(2).strip()

    # Extract codename
    codename_match = re.search(r"\*\*Codename:\*\*\s*(.+)", content)
    if codename_match:
        result["codename"] = codename_match.group(1).strip()

    # Extract core mandate as description fallback
    mandate_match = re.search(r"\*\*Core Mandate:\*\*\s*(.+)", content)
    if mandate_match and not result["description"]:
        result["description"] = mandate_match.group(1).strip()

    # Extract skills from sections
    skills_section = re.search(r"## \d+\.\s*Core (?:Competencies|Responsibilities)(.*?)(?=##|\Z)", content, re.DOTALL)
    if skills_section:
        # Extract bullet points
        bullets = re.findall(r"[-*]\s*\*\*(.+?)\*\*", skills_section.group(1))
        result["skills"] = [b.strip().lower().replace(" ", "-") for b in bullets[:8]]

    # If no skills found, extract from filename
    if not result["skills"]:
        name_parts = result["name"].replace("_", "-").split("-")
        result["skills"] = [p for p in name_parts if len(p) > 2][:5]

    # Extract core section content for system prompt
    core_sections = []
    for match in re.finditer(r"## \d+\.\s*(.+?)(?=## \d+|\Z)", content, re.DOTALL):
        section_title = match.group(1).split("\n")[0].strip()
        section_content = match.group(0)[:1500]  # Limit length
        core_sections.append(f"### {section_title}\n{section_content}")

    if core_sections:
        result["system_prompt"] = "\n\n".join(core_sections[:5])
    else:
        # Use first 1000 chars as system prompt
        result["system_prompt"] = content[:1500]

    return result


def convert_to_profile(agent_data: dict[str, Any], category: str) -> str:
    """Convert parsed agent data to a Python profile file."""
    name = agent_data["name"]
    codename = agent_data["codename"]
    role = agent_data["role"]
    description = agent_data["description"] or f"Specialist in {role}"
    skills = agent_data["skills"]
    system_prompt = agent_data["system_prompt"]

    # Escape triple quotes in system prompt
    escaped_prompt = system_prompt.replace('"""', '\\"\\"\\"')

    # Determine tools based on category/skills
    tools = ["read_file", "write_file", "edit_file", "execute_shell"]
    if any(s in str(skills) for s in ["test", "quality", "review"]):
        tools.extend(["linter", "test_runner"])
    if any(s in str(skills) for s in ["debug", "trace", "log"]):
        tools.extend(["debugger", "log_analyzer"])
    if any(s in str(skills) for s in ["security", "auth", "vulnerability"]):
        tools.extend(["code_analyzer"])

    # Determine handoffs based on category
    handoffs = []
    if category not in ["testing-quality", "compliance-legal-finance"]:
        handoffs.append("code-reviewer")

    return f'''"""Agent Profile: {role}

Category: {category}
Auto-generated from agents-readme reference repo.
"""

from dataclasses import dataclass, field


@dataclass
class AgentProfile:
    """Agent profile definition."""

    name: str
    codename: str
    role: str
    description: str
    system_prompt: str
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    handoff_to: list[str] = field(default_factory=list)
    model_preference: str | None = None
    max_iterations: int = 15
    temperature: float = 0.7


PROFILE = AgentProfile(
    name="{name}",
    codename="{codename}",
    role="{role}",
    description="{description}",
    system_prompt="""{escaped_prompt}""",
    skills={skills},
    tools={tools},
    handoff_to={handoffs},
)


def get_profile() -> AgentProfile:
    """Get this agent's profile."""
    return PROFILE
'''


def convert_all_agents(
    source_dir: Path,
    output_dir: Path,
    max_agents: int | None = None,
) -> int:
    """Convert all agent markdown files to sago profiles.

    Args:
        source_dir: Path to agents-readme directory
        output_dir: Path to sago/agents/profiles/
        max_agents: Maximum number of agents to convert (None = all)

    Returns:
        Number of agents converted
    """
    converted = 0
    skipped = 0

    # Categories to process
    categories = [
        "specialized-engineering",
        "engineering-dev",
        "language-specific",
        "data-intelligence",
        "infrastructure-ops",
        "database-specialists",
        "compliance-legal-finance",
        "planning-oversight",
        "design-architecture",
        "testing-quality",
        "orchestration",
        "content-communication",
        "cloud-infra-architecture",
        "system-extensibility",
        "frontend-frameworks",
        "business-revenue",
        "people-culture",
        "executive",
        "cloud-providers",
        "business-analysis",
        "it-support",
        "game-development",
    ]

    for category in categories:
        category_dir = source_dir / category
        if not category_dir.exists():
            continue

        for md_file in sorted(category_dir.glob("*.md")):
            if md_file.name == "README.md":
                continue

            if max_agents and converted >= max_agents:
                return converted

            # Parse the markdown
            agent_data = parse_agent_md(md_file)
            if not agent_data:
                skipped += 1
                continue

            # Convert to profile
            profile_code = convert_to_profile(agent_data, category)

            # Write to output
            output_file = output_dir / f"{agent_data['name']}.py"
            try:
                output_file.write_text(profile_code, encoding="utf-8")
                converted += 1
                print(f"  [{category}] {agent_data['name']}")
            except Exception as e:
                print(f"  ERROR writing {agent_data['name']}: {e}")
                skipped += 1

    print(f"\nConverted: {converted}, Skipped: {skipped}")
    return converted


if __name__ == "__main__":
    source = Path("/mnt/ramdisk/agents-readme")
    output = Path("/mnt/ramdisk/sago/sago/agents/profiles")

    # Clear existing profiles
    for f in output.glob("*.py"):
        if f.name not in ["__init__.py"]:
            f.unlink()

    print("Converting agents from agents-readme...")
    count = convert_all_agents(source, output)
    print(f"\nDone! {count} agents converted.")
