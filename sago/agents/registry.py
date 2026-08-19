"""Specialist Agent Definitions for Sago.

Loads agent profiles from individual .py files in agents/profiles/.
Each profile file exports a get_profile() function returning an AgentProfile.

For customization:
- Edit profiles in agents/profiles/ to modify default prompts
- Use config.sago.json to enable/disable agents per project
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("sago.agents.registry")


@dataclass
class AgentDefinition:
    """Definition of a specialist agent."""

    name: str
    codename: str
    role: str
    description: str
    system_prompt: str
    skills: list[str]
    tools: list[str]
    category: str = "general"
    handoff_to: list[str] = field(default_factory=list)
    model_preference: str | None = None
    max_iterations: int = 15
    temperature: float = 0.7


# ============================================================================
# LOAD AGENTS FROM PROFILE FILES
# ============================================================================

AGENTS: dict[str, AgentDefinition] = {}


def _load_profiles() -> None:
    """Load all agent profiles from the profiles directory."""
    profiles_dir = Path(__file__).parent / "profiles"

    if not profiles_dir.exists():
        logger.debug("Profiles directory does not exist: %s", profiles_dir)
        return

    logger.info("Loading agent profiles from %s", profiles_dir)
    loaded = 0
    for py_file in sorted(profiles_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        try:
            from importlib.util import module_from_spec, spec_from_file_location

            module_name = f"sago.agents.profiles.{py_file.stem}"
            spec = spec_from_file_location(module_name, py_file)

            if spec is None or spec.loader is None:
                continue

            module = module_from_spec(spec)
            spec.loader.exec_module(module)

            # Determine category from docstring
            category = "general"
            doc = getattr(module, "__doc__", "") or ""
            if "Category:" in doc:
                category = doc.split("Category:")[1].splitlines()[0].strip()

            # Get profile from module
            profile = None
            if hasattr(module, "get_profile"):
                profile = module.get_profile()
            elif hasattr(module, "PROFILE"):
                profile = module.PROFILE

            if profile and hasattr(profile, "name"):
                final_category = getattr(profile, "category", category)
                temp = getattr(profile, "temperature", 0.7)

                # Domain-aware hyperparameter tuning when default temperature (0.7) is used
                if temp == 0.7:
                    cat_lower = final_category.lower()
                    name_lower = profile.name.lower()
                    if any(
                        k in cat_lower or k in name_lower
                        for k in (
                            "security",
                            "database",
                            "compliance",
                            "legal",
                            "finance",
                            "testing",
                            "qa",
                            "audit",
                            "crypto",
                        )
                    ):
                        temp = 0.2
                    elif any(
                        k in cat_lower or k in name_lower
                        for k in ("language", "engineering-dev", "infra", "devops", "backend")
                    ):
                        temp = 0.3
                    elif any(
                        k in cat_lower or k in name_lower
                        for k in ("architecture", "orchestration", "planning", "design")
                    ):
                        temp = 0.5

                agent = AgentDefinition(
                    name=profile.name,
                    codename=profile.codename,
                    role=profile.role,
                    description=profile.description,
                    system_prompt=profile.system_prompt,
                    skills=profile.skills,
                    tools=profile.tools,
                    category=final_category,
                    handoff_to=profile.handoff_to,
                    model_preference=getattr(profile, "model_preference", None),
                    max_iterations=getattr(profile, "max_iterations", 15),
                    temperature=temp,
                )
                AGENTS[agent.name] = agent
                loaded += 1
                logger.debug(
                    "Loaded agent: %s (category=%s, temp=%.2f)", agent.name, agent.category, temp
                )

        except Exception as e:
            logger.warning("Failed to load profile %s: %s", py_file.name, e)

    logger.info("Loaded %d agent profiles", loaded)


# Load profiles on module import
_load_profiles()


# Load plugin-provided agents
def _load_plugin_agents() -> None:
    """Load agent profiles provided by plugins."""
    try:
        from sago.plugins.base import get_plugin_manager

        pm = get_plugin_manager()
        loaded = 0
        for plugin in pm.discover_plugins():
            if not plugin.meta.enabled:
                continue
            try:
                for agent_data in plugin.provide_agents():
                    if not isinstance(agent_data, dict) or "name" not in agent_data:
                        continue
                    name = agent_data["name"]
                    if name in AGENTS:
                        logger.debug("Skipping plugin agent %s (already registered)", name)
                        continue  # Don't override built-in agents
                    agent = AgentDefinition(
                        name=name,
                        codename=agent_data.get("codename", name),
                        role=agent_data.get("role", "Plugin Agent"),
                        description=agent_data.get("description", ""),
                        system_prompt=agent_data.get("system_prompt", ""),
                        skills=agent_data.get("skills", []),
                        tools=agent_data.get("tools", []),
                        category=agent_data.get("category", "plugin"),
                        handoff_to=agent_data.get("handoff_to", []),
                        model_preference=agent_data.get("model_preference"),
                        max_iterations=agent_data.get("max_iterations", 15),
                        temperature=agent_data.get("temperature", 0.7),
                    )
                    AGENTS[agent.name] = agent
                    loaded += 1
                    logger.info(
                        "Registered plugin agent: %s from plugin %s", name, plugin.meta.name
                    )
            except Exception as e:
                logger.error("Plugin %s failed to provide agents: %s", plugin.meta.name, e)
        if loaded:
            logger.info("Loaded %d plugin agents", loaded)
    except Exception as e:
        logger.debug("Plugin system not available: %s", e)


_load_plugin_agents()


AGENT_ALIASES: dict[str, str] = {
    "system-architect": "architect",
    "test-runner": "tester",
    "ui-designer": "frontend-engineer",
    "python-pro": "python-engineer",
    "fullstack-dev": "backend-engineer",
    "rust-systems": "rust-engineer",
    "go-backend": "go-engineer",
    "debugger": "python-engineer",
    "security-debugger": "security-engineer",
    "code-reviewer": "reviewer",
    "security-reviewer": "security-engineer",
    "db-optimizer": "database-administrator",
    "api-designer": "api-engineer",
    "frontend-expert": "frontend-engineer",
    "tech-writer": "documentation-updater",
    "devops-engineer": "devops",
    "cloud-engineer": "cloud-architect",
    "sre-engineer": "devops",
}


def get_agent(name: str) -> AgentDefinition | None:
    """Get an agent definition by name or alias."""
    resolved_name = AGENT_ALIASES.get(name, name)
    agent = AGENTS.get(resolved_name)
    if agent:
        logger.debug("Agent lookup: %s -> %s (found)", name, resolved_name)
    else:
        logger.debug("Agent lookup: %s -> %s (not found)", name, resolved_name)
    return agent


def list_agents() -> list[dict[str, Any]]:
    """List all available agents."""
    return [
        {
            "name": a.name,
            "codename": a.codename,
            "role": a.role,
            "description": a.description,
            "skills": a.skills,
            "category": a.category,
        }
        for a in AGENTS.values()
    ]


def list_categories() -> dict[str, list[AgentDefinition]]:
    """Get all agents grouped by category."""
    cats: dict[str, list[AgentDefinition]] = {}
    for a in sorted(AGENTS.values(), key=lambda x: (x.category, x.name)):
        cats.setdefault(a.category, []).append(a)
    return cats


def get_agents_by_category(category: str) -> list[AgentDefinition]:
    """Find agents in a specific category (case-insensitive fuzzy match)."""
    target = category.lower().strip()
    return [
        a
        for a in AGENTS.values()
        if target in a.category.lower() or target in a.name.lower() or target in a.role.lower()
    ]


def get_agents_by_skill(skill: str) -> list[AgentDefinition]:
    """Find agents with a specific skill."""
    return [a for a in AGENTS.values() if skill.lower() in [s.lower() for s in a.skills]]


def get_handoff_targets(agent_name: str) -> list[AgentDefinition]:
    """Get agents that a given agent can hand off to."""
    agent = get_agent(agent_name)
    if not agent:
        return []
    targets: list[AgentDefinition] = []
    for name in agent.handoff_to:
        target_agent = get_agent(name)
        if target_agent and target_agent not in targets:
            targets.append(target_agent)
    return targets


def reload_agents() -> None:
    """Reload all agent profiles from disk."""
    logger.info("Reloading all agent profiles")
    AGENTS.clear()
    _load_profiles()


def resolve_specialist_agent(
    task: str = "",
    cwd: str | None = None,
    referenced_files: list[str] | None = None,
    default_agent: str = "general-assistant",
) -> str:
    """Smartly resolve the best specialist agent for a given task, workspace, and referenced files.

    Cascades across:
    1. Direct agent mentions in prompt (@agent-name)
    2. Explicit technology / stack / framework keywords in task
    3. Referenced file extensions (e.g. .tsx, .java, .rs, .go, .tf, .cs, .sql)
    4. Auto-detected workspace language, framework, and config indicators
    5. Action type (debug, qa, devops, security)
    """
    import os
    import re

    task_lower = task.lower().strip() if task else ""

    # 1. Direct explicit agent mention (e.g. @nextjs-engineer, @azure-engineer)
    mention_match = re.search(r"@([a-zA-Z0-9_\-]+)", task)
    if mention_match:
        cand = mention_match.group(1).lower().replace("_", "-")
        if get_agent(cand):
            return cand

    # 2. Technology & Framework Keyword Detection in Task
    tech_agent_map: list[tuple[tuple[str, ...], str]] = [
        # Frontend & Modern Web
        (
            (
                "nextjs",
                "next.js",
                "next 14",
                "next 15",
                "app router",
                "page router",
                "next auth",
                "app/",
                "pages/",
            ),
            "nextjs-engineer",
        ),
        (("react", "reactjs", "react-native", "jsx", "tsx", "redux", "zustand"), "react-engineer"),
        (("vue", "vuejs", "vue3", "pinia", "vite"), "vue-engineer"),
        (("nuxt", "nuxtjs"), "nuxt-engineer"),
        (("svelte", "sveltekit"), "svelte-engineer"),
        (("angular", "angularjs", "rxjs", "ngrx"), "angular-engineer"),
        (("solidjs", "solid.js"), "solidjs-engineer"),
        (
            (
                "tailwind",
                "tailwindcss",
                "css",
                "scss",
                "sass",
                "styling",
                "frontend",
                "ui component",
            ),
            "frontend-engineer",
        ),
        (("typescript", "tsc", "type-check", "interface", "generics"), "typescript-engineer"),
        (("node", "nodejs", "npm", "express", "expressjs", "nestjs", "fastify"), "node-engineer"),
        # Java & JVM Stack
        (
            ("spring", "spring boot", "springboot", "spring-boot", "jpa", "hibernate"),
            "spring-boot-engineer",
        ),
        (("java", "maven", "gradle", "pom.xml", "build.gradle", "jvm", "openjdk"), "java-engineer"),
        (("kotlin", "android", "coroutine", "coroutines"), "kotlin-engineer"),
        (("scala", "sbt", "akka"), "scala-engineer"),
        # Cloud & Platforms
        (
            (
                "azure",
                "aks",
                "bicep",
                "arm template",
                "azure devops",
                "azure function",
                "blob storage",
            ),
            "azure-engineer",
        ),
        (
            ("aws", "lambda", "s3", "ec2", "dynamodb", "cloudformation", "cdk", "fargate"),
            "aws-engineer",
        ),
        (
            ("gcp", "google cloud", "bigquery", "cloud run", "gke", "pubsub", "app engine"),
            "gcp-engineer",
        ),
        (("cloudflare", "workers", "pages", "r2", "d1"), "cloudflare-engineer"),
        (("vercel", "vercel edge"), "vercel-engineer"),
        # Systems & Compiled Languages
        (("rust", "cargo", "tokio", "axum", "actix", "serde", "crates.io"), "rust-engineer"),
        (("golang", "golang", "go mod", "goroutine", "gin", "gorm"), "go-engineer"),
        (
            ("c#", "csharp", "dotnet", ".net", "asp.net", "entity framework", "nuget", "unity"),
            "dotnet-engineer",
        ),
        (("c++", "cpp", "cmake", "clang", "g++", "boost"), "cpp-engineer"),
        (("c language", "embedded", "firmware", "makefile", "rtos"), "embedded-engineer"),
        (("zig", "ziglang"), "zig-engineer"),
        (("swift", "swiftui", "ios", "xcode"), "swift-engineer"),
        # Web & Scripting
        (("ruby", "rails", "rubyonrails", "gemfile", "bundler"), "rails-engineer"),
        (("php", "laravel", "composer", "symfony", "wordpress"), "laravel-engineer"),
        (("elixir", "phoenix", "mix", "erlang"), "elixir-engineer"),
        (
            ("python", "fastapi", "django", "flask", "pytorch", "pandas", "numpy", "pip"),
            "python-engineer",
        ),
        # Databases & Search
        (("postgres", "postgresql", "psql", "pg_"), "postgresql-engineer"),
        (("mysql", "mariadb"), "mysql-engineer"),
        (("sqlite", "sqlite3"), "sqlite-engineer"),
        (("mongodb", "mongo", "mongoose"), "mongodb-engineer"),
        (("redis", "valkey", "keydb"), "redis-engineer"),
        (("elasticsearch", "opensearch", "kibana"), "elasticsearch-engineer"),
        (("snowflake", "data warehouse"), "snowflake-engineer"),
        (("neo4j", "cypher", "graph database"), "neo4j-engineer"),
        (("kafka", "eventstream", "streaming pipeline"), "kafka-engineer"),
        # Infrastructure & DevOps
        (("terraform", "opentofu", "hcl", "tfvars"), "terraform-engineer"),
        (
            ("docker", "dockerfile", "docker-compose", "containerize", "containerization"),
            "docker-engineer",
        ),
        (("k8s", "kubernetes", "helm", "argocd", "kubectl", "ingress"), "kubernetes-engineer"),
        (("ci/cd", "github actions", "gitlab ci", "jenkins", "pipeline"), "cicd-engineer"),
        # Security & QA
        (
            (
                "security",
                "vulnerability",
                "auth",
                "jwt",
                "oauth",
                "penetration",
                "xss",
                "csrf",
                "sanitize",
            ),
            "security-engineer",
        ),
        (
            (
                "pytest",
                "unittest",
                "jest",
                "vitest",
                "cypress",
                "playwright",
                "test coverage",
                "qa",
            ),
            "qa-engineer",
        ),
        (
            ("debugger", "debug", "crash", "segfault", "memory leak", "traceback", "infinite loop"),
            "debugger",
        ),
    ]

    for keywords, agent_name in tech_agent_map:
        if any(
            re.search(r"\b" + re.escape(kw) + r"\b", task_lower) or kw in task_lower
            for kw in keywords
            if "/" in kw or re.search(r"\b" + re.escape(kw) + r"\b", task_lower)
        ):
            if get_agent(agent_name):
                return agent_name

    # 3. Referenced Files / File Extension Inspection
    all_files: list[str] = list(referenced_files or [])
    # Also extract file paths mentioned directly in task text
    file_matches = re.findall(
        r"\b[\w\-\./]+\.(?:tsx|jsx|ts|js|java|rs|go|cs|cpp|c|h|rb|php|py|tf|sql|json|yml|yaml|md)\b",
        task,
    )
    all_files.extend(file_matches)

    for f in all_files:
        f_lower = f.lower()
        if "app/" in f_lower or "pages/" in f_lower or f_lower.endswith((".tsx", ".jsx")):
            return "nextjs-engineer" if get_agent("nextjs-engineer") else "react-engineer"
        elif f_lower.endswith(".java") or "pom.xml" in f_lower or "build.gradle" in f_lower:
            return "spring-boot-engineer" if get_agent("spring-boot-engineer") else "java-engineer"
        elif f_lower.endswith(".rs") or "cargo.toml" in f_lower:
            return "rust-engineer"
        elif f_lower.endswith(".go") or "go.mod" in f_lower:
            return "go-engineer"
        elif f_lower.endswith((".cs", ".csproj", ".sln")):
            return "dotnet-engineer"
        elif f_lower.endswith(".tf") or f_lower.endswith(".tfvars"):
            return "terraform-engineer"
        elif f_lower.endswith(".rb") or "gemfile" in f_lower:
            return "rails-engineer" if get_agent("rails-engineer") else "ruby-engineer"
        elif f_lower.endswith(".php") or "composer.json" in f_lower:
            return "laravel-engineer" if get_agent("laravel-engineer") else "php-engineer"
        elif f_lower.endswith(".sql"):
            return "postgresql-engineer"
        elif "dockerfile" in f_lower or "docker-compose" in f_lower:
            return "docker-engineer"
        elif f_lower.endswith(".ts") or f_lower.endswith(".js"):
            return "typescript-engineer" if get_agent("typescript-engineer") else "node-engineer"
        elif f_lower.endswith(".py"):
            return "python-engineer"

    # 4. Auto-detected Workspace Language & Framework (from config files)
    if cwd and os.path.isdir(cwd):
        pkg_path = os.path.join(cwd, "package.json")
        if os.path.exists(pkg_path):
            try:
                import json

                with open(pkg_path, encoding="utf-8") as f:
                    pkg_data = json.load(f)
                all_deps = {
                    **pkg_data.get("dependencies", {}),
                    **pkg_data.get("devDependencies", {}),
                }
                if "next" in all_deps:
                    return "nextjs-engineer"
                elif "react" in all_deps or "react-dom" in all_deps:
                    return "react-engineer"
                elif "vue" in all_deps or "nuxt" in all_deps:
                    return "vue-engineer" if "vue" in all_deps else "nuxt-engineer"
                elif "svelte" in all_deps or "@sveltejs/kit" in all_deps:
                    return "svelte-engineer"
                elif "@angular/core" in all_deps:
                    return "angular-engineer"
                elif "express" in all_deps or "fastify" in all_deps or "nestjs" in all_deps:
                    return "node-engineer"
            except Exception:
                pass

        if os.path.exists(os.path.join(cwd, "pom.xml")) or os.path.exists(
            os.path.join(cwd, "build.gradle")
        ):
            return "spring-boot-engineer" if get_agent("spring-boot-engineer") else "java-engineer"
        elif os.path.exists(os.path.join(cwd, "Cargo.toml")):
            return "rust-engineer"
        elif os.path.exists(os.path.join(cwd, "go.mod")):
            return "go-engineer"
        elif os.path.exists(os.path.join(cwd, "Gemfile")):
            return "rails-engineer" if get_agent("rails-engineer") else "ruby-engineer"
        elif os.path.exists(os.path.join(cwd, "composer.json")):
            return "laravel-engineer" if get_agent("laravel-engineer") else "php-engineer"
        elif os.path.exists(os.path.join(cwd, "tsconfig.json")):
            return "typescript-engineer"
        elif os.path.exists(os.path.join(cwd, "pyproject.toml")) or os.path.exists(
            os.path.join(cwd, "requirements.txt")
        ):
            return "python-engineer"

    # 5. Default fallback based on task classification
    greetings = ("hello", "hi", "hoi", "hey", "weather", "forecast", "joke", "who are you")
    if not task_lower or any(
        re.search(r"\b" + re.escape(kw) + r"\b", task_lower) for kw in greetings
    ):
        return "general-assistant"

    return default_agent or "full-stack-engineer"
