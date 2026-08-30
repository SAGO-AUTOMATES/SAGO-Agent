"""Comprehensive tests for sago.skills.loader and sago.skills.registry."""

from __future__ import annotations

from pathlib import Path

from sago.skills.loader import CustomSkill, SkillLoader
from sago.skills.registry import SKILLS, Skill


class TestCustomSkill:
    def test_to_prompt_context_minimal(self) -> None:
        skill = CustomSkill(name="test-skill", description="A test skill")
        ctx = skill.to_prompt_context()
        assert "test-skill" in ctx
        assert "A test skill" in ctx

    def test_to_prompt_context_with_tools(self) -> None:
        skill = CustomSkill(name="deploy", description="Deploy stuff", tools=["kubectl", "helm"])
        ctx = skill.to_prompt_context()
        assert "kubectl" in ctx
        assert "helm" in ctx

    def test_to_prompt_context_with_steps(self) -> None:
        skill = CustomSkill(
            name="review", description="Review code", steps=["Read file", "Check style"]
        )
        ctx = skill.to_prompt_context()
        assert "1. Read file" in ctx
        assert "2. Check style" in ctx

    def test_to_prompt_context_with_instructions(self) -> None:
        skill = CustomSkill(
            name="doc", description="Document", instructions="Always add docstrings."
        )
        ctx = skill.to_prompt_context()
        assert "Always add docstrings" in ctx

    def test_to_prompt_context_all_fields(self) -> None:
        skill = CustomSkill(
            name="full",
            description="Full skill",
            tools=["tool_a"],
            steps=["Step 1", "Step 2"],
            instructions="Do it well.",
        )
        ctx = skill.to_prompt_context()
        assert "full" in ctx
        assert "tool_a" in ctx
        assert "Step 1" in ctx
        assert "Do it well" in ctx


class TestSkillLoader:
    def test_parse_skill_with_yaml_frontmatter(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: my-skill\ndescription: Does things\ntools:\n  - read_file\nsteps:\n  - Read\n  - Act\ntags:\n  - utility\n---\n\nFull instructions here.\n"
        )
        skill = SkillLoader.parse_markdown_skill(skill_file)
        assert skill is not None
        assert skill.name == "my-skill"
        assert skill.description == "Does things"
        assert "read_file" in skill.tools
        assert "Read" in skill.steps
        assert "utility" in skill.tags
        assert "Full instructions" in skill.instructions

    def test_parse_skill_without_frontmatter(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# My Fallback Skill\n\nThis skill does something useful.")
        skill = SkillLoader.parse_markdown_skill(skill_file)
        assert skill is not None
        # Name falls back to directory/stem
        assert skill.description  # extracted from first line

    def test_parse_skill_malformed_yaml_fallback(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\nname: [bad yaml\n---\n\nInstructions")
        # Should not raise, should return a skill using fallback
        skill = SkillLoader.parse_markdown_skill(skill_file)
        assert skill is not None  # name falls back to stem

    def test_parse_skill_tools_as_string(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: single-tool\ndescription: Uses one tool\ntools: read_file\n---\n\nInstructions"
        )
        skill = SkillLoader.parse_markdown_skill(skill_file)
        assert skill is not None
        assert "read_file" in skill.tools

    def test_discover_skills_finds_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\nname: discoverable\ndescription: Found via discover\n---\n\nInstructions"
        )
        found = SkillLoader.discover_skills(extra_dirs=[tmp_path])
        assert "discoverable" in found

    def test_discover_skills_finds_direct_md(self, tmp_path: Path) -> None:
        md = tmp_path / "special.md"
        md.write_text(
            "---\nname: special\ndescription: A special skill\n---\n\nDo something special."
        )
        found = SkillLoader.discover_skills(extra_dirs=[tmp_path])
        assert "special" in found

    def test_discover_skills_skips_readme(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("---\nname: readme\ndescription: Should be skipped\n---\n\nNot a skill.")
        found = SkillLoader.discover_skills(extra_dirs=[tmp_path])
        assert "readme" not in found

    def test_discover_skills_empty_dir(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        found = SkillLoader.discover_skills(extra_dirs=[empty_dir])
        assert isinstance(found, dict)


class TestSkillRegistry:
    def test_skills_dict_not_empty(self) -> None:
        assert len(SKILLS) > 0

    def test_known_skill_code_review(self) -> None:
        assert "code_review" in SKILLS
        skill = SKILLS["code_review"]
        assert isinstance(skill, Skill)
        assert skill.name == "code_review"
        assert skill.tools
        assert skill.steps

    def test_skill_to_dict(self) -> None:
        skill = SKILLS["code_review"]
        d = skill.to_dict()
        assert d["name"] == "code_review"
        assert "tools" in d
        assert "steps" in d
        assert "examples" in d

    def test_all_skills_valid(self) -> None:
        for name, skill in SKILLS.items():
            assert skill.name
            assert skill.description
            assert isinstance(skill.tools, list)
            assert isinstance(skill.steps, list)
