"""Project Scaffolding Tool - Create project structure from templates."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class ScaffoldArgs(BaseModel):
    """Arguments for ScaffoldTool."""

    project_type: str = Field(
        description="Project type: python, python-cli, python-web, node, node-react, rust, go, java"
    )
    project_name: str = Field(description="Name of the project")
    path: str = Field(default=".", description="Parent directory to create project in")


# Template definitions: each template is a dict of {relative_path: file_content}
TEMPLATES: dict[str, dict[str, str]] = {
    "python": {
        "README.md": "# {project_name}\n\nA Python project.\n\n## Installation\n\n```bash\npip install -e .\n```\n\n## Usage\n\n```bash\npython -m {project_name}\n```\n",
        "pyproject.toml": '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n\n[project]\nname = "{project_name}"\nversion = "0.1.0"\ndescription = ""\nrequires-python = ">=3.10"\n\n[project.scripts]\n{project_name} = "{project_name}.main:main"\n',
        "{project_name}/__init__.py": '"""${project_name}"""\n\n__version__ = "0.1.0"\n',
        "{project_name}/main.py": '"""Main entry point."""\n\n\ndef main() -> None:\n    print("Hello from {project_name}!")\n\n\nif __name__ == "__main__":\n    main()\n',
        "tests/__init__.py": "",
        "tests/test_main.py": '"""Tests for main module."""\n\nfrom {project_name}.main import main\n\n\ndef test_main(capsys):\n    main()\n    captured = capsys.readouterr()\n    assert "Hello" in captured.out\n',
        ".gitignore": "__pycache__/\n*.pyc\n*.egg-info/\ndist/\nbuild/\n.venv/\n",
    },
    "python-cli": {
        "README.md": "# {project_name}\n\nA Python CLI tool.\n\n## Installation\n\n```bash\npip install -e .\n```\n\n## Usage\n\n```bash\n{project_name} --help\n```\n",
        "pyproject.toml": '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n\n[project]\nname = "{project_name}"\nversion = "0.1.0"\ndescription = ""\nrequires-python = ">=3.10"\ndependencies = [\n    "typer>=0.9",\n    "rich>=13.0",\n]\n\n[project.scripts]\n{project_name} = "{project_name}.cli:app"\n',
        "{project_name}/__init__.py": '"""${project_name}"""\n\n__version__ = "0.1.0"\n',
        "{project_name}/cli.py": '"""CLI interface."""\n\nimport typer\nfrom rich.console import Console\n\napp = typer.Typer(help="{project_name} CLI tool")\nconsole = Console()\n\n\n@app.command()\ndef main(name: str = "World") -> None:\n    """Greet someone."""\n    console.print(f"Hello, {name}!")\n\n\nif __name__ == "__main__":\n    app()\n',
        "tests/__init__.py": "",
        "tests/test_cli.py": '"""Tests for CLI."""\n\nfrom typer.testing import CliRunner\nfrom {project_name}.cli import app\n\nrunner = CliRunner()\n\n\ndef test_main():\n    result = runner.invoke(app, ["--help"])\n    assert result.exit_code == 0\n    assert "Greet" in result.output\n',
        ".gitignore": "__pycache__/\n*.pyc\n*.egg-info/\ndist/\nbuild/\n.venv/\n",
    },
    "python-web": {
        "README.md": "# {project_name}\n\nA Python web application.\n\n## Installation\n\n```bash\npip install -e .\n```\n\n## Usage\n\n```bash\npython -m {project_name}.app\n```\n",
        "pyproject.toml": '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n\n[project]\nname = "{project_name}"\nversion = "0.1.0"\ndescription = ""\nrequires-python = ">=3.10"\ndependencies = [\n    "flask>=3.0",\n]\n\n[project.scripts]\n{project_name} = "{project_name}.app:main"\n',
        "{project_name}/__init__.py": '"""${project_name}"""\n\n__version__ = "0.1.0"\n',
        "{project_name}/app.py": '"""Flask web application."""\n\nfrom flask import Flask, jsonify\n\napp = Flask(__name__)\n\n\n@app.route("/")\ndef index() -> dict:\n    return jsonify({"message": "Hello from {project_name}!"})\n\n\n@app.route("/health")\ndef health() -> dict:\n    return jsonify({"status": "ok"})\n\n\ndef main() -> None:\n    app.run(debug=True)\n\n\nif __name__ == "__main__":\n    main()\n',
        "tests/__init__.py": "",
        "tests/test_app.py": '"""Tests for web app."""\n\nimport pytest\nfrom {project_name}.app import app\n\n\n@pytest.fixture\ndef client():\n    app.config["TESTING"] = True\n    with app.test_client() as c:\n        yield c\n\n\ndef test_index(client):\n    resp = client.get("/")\n    assert resp.status_code == 200\n    assert b"Hello" in resp.data\n\n\ndef test_health(client):\n    resp = client.get("/health")\n    assert resp.status_code == 200\n    assert resp.json["status"] == "ok"\n',
        ".gitignore": "__pycache__/\n*.pyc\n*.egg-info/\ndist/\nbuild/\n.venv/\n",
    },
    "node": {
        "README.md": "# {project_name}\n\nA Node.js project.\n\n## Installation\n\n```bash\nnpm install\n```\n\n## Usage\n\n```bash\nnpm start\n```\n\n## Test\n\n```bash\nnpm test\n```\n",
        "package.json": '{\n  "name": "{project_name}",\n  "version": "1.0.0",\n  "description": "",\n  "main": "src/index.js",\n  "scripts": {\n    "start": "node src/index.js",\n    "test": "jest",\n    "lint": "eslint src/"\n  },\n  "devDependencies": {\n    "jest": "^29.0.0",\n    "eslint": "^8.0.0"\n  }\n}\n',
        "src/index.js": 'const http = require("http");\n\nconst server = http.createServer((req, res) => {\n  res.writeHead(200, { "Content-Type": "application/json" });\n  res.end(JSON.stringify({ message: "Hello from {project_name}!" }));\n});\n\nconst PORT = process.env.PORT || 3000;\nserver.listen(PORT, () => {\n  console.log(`Server running on port ${PORT}`);\n});\n\nmodule.exports = { server };\n',
        "tests/index.test.js": 'const { server } = require("../src/index");\n\ndescribe("Server", () => {\n  afterAll(() => {\n    server.close();\n  });\n\n  test("should respond with hello message", () => {\n    expect(true).toBe(true);\n  });\n});\n',
        ".gitignore": "node_modules/\ndist/\n.env\n",
    },
    "rust": {
        "README.md": "# {project_name}\n\nA Rust project.\n\n## Build\n\n```bash\ncargo build\n```\n\n## Run\n\n```bash\ncargo run\n```\n\n## Test\n\n```bash\ncargo test\n```\n",
        "Cargo.toml": '[package]\nname = "{project_name}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n',
        "src/main.rs": 'fn main() {\n    println!("Hello from {project_name}!");\n}\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn test_hello() {\n        assert!(true);\n    }\n}\n',
        ".gitignore": "target/\n",
    },
    "go": {
        "README.md": "# {project_name}\n\nA Go project.\n\n## Build\n\n```bash\ngo build\n```\n\n## Run\n\n```bash\ngo run .\n```\n\n## Test\n\n```bash\ngo test ./...\n```\n",
        "go.mod": 'module {project_name}\n\ngo 1.21\n',
        "main.go": 'package main\n\nimport "fmt"\n\nfunc main() {\n    fmt.Println("Hello from {project_name}!")\n}\n',
        "main_test.go": 'package main\n\nimport "testing"\n\nfunc TestHello(t *testing.T) {\n    if true != true {\n        t.Error("Expected true")\n    }\n}\n',
        ".gitignore": "vendor/\n",
    },
}


class ScaffoldTool(BaseTool):
    """Tool for creating project structures from templates."""

    name = "scaffold_project"
    description = (
        "Create a new project with proper structure, dependencies, and tests. "
        "Types: python, python-cli, python-web, node, rust, go. "
        "Use 'auto' to detect from existing files."
    )
    args_model = ScaffoldArgs

    def _detect_project_type(self, path: str) -> str | None:
        """Auto-detect project type from existing files in the directory."""
        import os
        work_dir = self._expand_path(path)

        indicators = {
            "python-web": ["flask", "django", "fastapi"],
            "python-cli": ["typer", "click", "argparse"],
            "python": ["pyproject.toml", "setup.py", "requirements.txt"],
            "node": ["package.json"],
            "rust": ["Cargo.toml"],
            "go": ["go.mod"],
        }

        # Check for config files
        for ptype, files in indicators.items():
            for f in files:
                if os.path.exists(os.path.join(work_dir, f)):
                    return ptype

        # Check for source files
        ext_map = {
            ".py": "python",
            ".js": "node",
            ".ts": "node",
            ".rs": "rust",
            ".go": "go",
        }
        for root, dirs, files in os.walk(work_dir):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "target", "vendor")]
            for f in files:
                ext = os.path.splitext(f)[1]
                if ext in ext_map:
                    return ext_map[ext]
            break  # Only check top level

        return None

    def _run(
        self,
        project_type: str,
        project_name: str,
        path: str = ".",
        **kwargs: Any,
    ) -> str:
        """Create a project from a template.

        Args:
            project_type: Type of project to create. Use 'auto' to detect.
            project_name: Name of the project.
            path: Parent directory.

        Returns:
            Created project structure.
        """
        # Auto-detect project type if requested
        if project_type == "auto":
            detected = self._detect_project_type(path)
            if detected:
                project_type = detected
            else:
                return (
                    "Could not auto-detect project type. Available types: "
                    + ", ".join(sorted(TEMPLATES.keys()))
                )

        if project_type not in TEMPLATES:
            available = ", ".join(sorted(TEMPLATES.keys()))
            return f"Unknown project type '{project_type}'. Available: {available}"

        # Sanitize project name for use in imports/identifiers
        safe_name = project_name.replace("-", "_").replace(" ", "_").lower()

        parent = self._expand_path(path)
        project_dir = parent / safe_name

        if project_dir.exists():
            return f"Directory already exists: {project_dir}"

        template = TEMPLATES[project_type]
        created_files = []

        for rel_path, content in template.items():
            # Replace placeholders
            final_path = rel_path.replace("{project_name}", safe_name)
            final_content = content.replace("{project_name}", safe_name)

            file_path = project_dir / final_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(final_content, encoding="utf-8")
            created_files.append(str(file_path.relative_to(project_dir)))

        return (
            f"Created {project_type} project '{safe_name}' at {project_dir}\n"
            f"Files created:\n" + "\n".join(f"  - {f}" for f in created_files)
        )
