"""Directory Scanner Tool

Recursively scans directories, detects languages, analyzes project structure,
and provides smart file routing to appropriate agents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("sago.tools.file.directory_scanner")


# Language detection by file extension
LANGUAGE_MAP: dict[str, str] = {
    # Python
    ".py": "python",
    ".pyi": "python",
    ".pyx": "python",
    # JavaScript/TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    # Web
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".vue": "vue",
    ".svelte": "svelte",
    # Systems
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".zig": "zig",
    # Java/JVM
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    ".groovy": "groovy",
    # Scripting
    ".rb": "ruby",
    ".php": "php",
    ".pl": "perl",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    # Data
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".csv": "data",
    ".tsv": "data",
    # Config
    ".ini": "config",
    ".cfg": "config",
    ".conf": "config",
    ".env": "config",
    ".env.local": "config",
    # Docs
    ".md": "markdown",
    ".rst": "markdown",
    ".txt": "text",
    # Shell
    ".ps1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    # SQL
    ".sql": "sql",
    ".pgsql": "sql",
    ".mysql": "sql",
    # Mobile
    ".swift": "swift",
    ".m": "objc",
    ".mm": "objc",
    # Other
    ".r": "r",
    ".R": "r",
    ".dart": "dart",
    ".lua": "lua",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".fs": "fsharp",
}

# Framework detection by config files
FRAMEWORK_MAP: dict[str, list[str]] = {
    "package.json": ["node", "npm"],
    "yarn.lock": ["node", "yarn"],
    "pnpm-lock.yaml": ["node", "pnpm"],
    "Cargo.toml": ["rust", "cargo"],
    "go.mod": ["go"],
    "requirements.txt": ["python", "pip"],
    "pyproject.toml": ["python", "pip"],
    "setup.py": ["python", "pip"],
    "Pipfile": ["python", "pipenv"],
    "poetry.lock": ["python", "poetry"],
    "Gemfile": ["ruby", "bundler"],
    "composer.json": ["php", "composer"],
    "pom.xml": ["java", "maven"],
    "build.gradle": ["java", "gradle"],
    "build.gradle.kts": ["kotlin", "gradle"],
    "CMakeLists.txt": ["c", "cmake"],
    "Makefile": ["make"],
    "Dockerfile": ["docker"],
    "docker-compose.yml": ["docker"],
    "docker-compose.yaml": ["docker"],
    "terraform.tf": ["terraform"],
    "main.tf": ["terraform"],
    ".github/workflows": ["github-actions"],
    "kubernetes": ["kubernetes", "k8s"],
    "helm": ["helm"],
}

# File categories for agent routing
FILE_CATEGORIES: dict[str, list[str]] = {
    "frontend": [".html", ".css", ".scss", ".less", ".jsx", ".tsx", ".vue", ".svelte"],
    "backend": [".py", ".java", ".go", ".rs", ".php", ".rb"],
    "mobile": [".swift", ".kt", ".dart", ".m", ".mm"],
    "data": [".sql", ".csv", ".json", ".yaml", ".yml", ".toml"],
    "devops": ["Dockerfile", "docker-compose.yml", ".tf", ".yaml"],
    "testing": ["test_", "_test.py", ".test.js", ".spec.js", ".test.ts", ".spec.ts"],
    "documentation": [".md", ".rst", ".txt"],
    "config": [".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env"],
}


@dataclass
class FileEntry:
    """A single file entry."""

    path: str
    name: str
    extension: str
    language: str
    size: int
    category: str
    last_modified: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "extension": self.extension,
            "language": self.language,
            "size": self.size,
            "category": self.category,
        }


@dataclass
class ScanResult:
    """Result of a directory scan."""

    root_path: str
    total_files: int
    total_directories: int
    files: list[FileEntry] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    categories: dict[str, int] = field(default_factory=dict)
    largest_files: list[FileEntry] = field(default_factory=list)
    recent_files: list[FileEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_path": self.root_path,
            "total_files": self.total_files,
            "total_directories": self.total_directories,
            "languages": self.languages,
            "frameworks": self.frameworks,
            "categories": self.categories,
            "file_count": len(self.files),
        }


# Directories to skip
SKIP_DIRS = {
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    "dist",
    "build",
    "target",
    "out",
    ".idea",
    ".vscode",
    ".eclipse",
    "coverage",
    ".nyc_output",
    "vendor",
    "packages",
}

# File extensions to skip
SKIP_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".obj",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".rar",
    ".7z",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
}


class DirectoryScanner:
    """Smart directory scanner with language detection."""

    def __init__(self, max_files: int = 10000, max_depth: int = 20) -> None:
        self.max_files = max_files
        self.max_depth = max_depth

    def scan(
        self,
        path: str | Path,
        include_hidden: bool = False,
        include_empty: bool = False,
    ) -> ScanResult:
        """Scan a directory recursively."""
        root = Path(path).resolve()
        result = ScanResult(
            root_path=str(root),
            total_files=0,
            total_directories=0,
        )

        if not root.exists():
            return result

        self._scan_recursive(root, result, 0, include_hidden, include_empty)

        # Compute summary stats
        result.languages = self._count_languages(result.files)
        result.frameworks = self._detect_frameworks(root)
        result.categories = self._count_categories(result.files)
        result.largest_files = sorted(result.files, key=lambda f: f.size, reverse=True)[:10]
        result.recent_files = sorted(result.files, key=lambda f: f.last_modified, reverse=True)[:10]

        return result

    def _scan_recursive(
        self,
        path: Path,
        result: ScanResult,
        depth: int,
        include_hidden: bool,
        include_empty: bool,
    ) -> None:
        """Recursively scan directory."""
        if depth > self.max_depth:
            return
        if result.total_files >= self.max_files:
            return

        try:
            entries = list(path.iterdir())
        except (PermissionError, OSError):
            return

        for entry in sorted(entries):
            if result.total_files >= self.max_files:
                break

            # Skip hidden files
            if not include_hidden and entry.name.startswith("."):
                continue

            # Skip directories
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                result.total_directories += 1
                self._scan_recursive(entry, result, depth + 1, include_hidden, include_empty)
                continue

            # Skip binary/unnecessary files
            if entry.suffix.lower() in SKIP_EXTENSIONS:
                continue

            # Get file info
            try:
                stat = entry.stat()
            except (PermissionError, OSError):
                continue

            # Skip empty files unless requested
            if not include_empty and stat.st_size == 0:
                continue

            # Determine language and category
            language = LANGUAGE_MAP.get(entry.suffix.lower(), "unknown")
            category = self._get_category(entry)

            file_entry = FileEntry(
                path=str(entry),
                name=entry.name,
                extension=entry.suffix.lower(),
                language=language,
                size=stat.st_size,
                category=category,
                last_modified=stat.st_mtime,
            )

            result.files.append(file_entry)
            result.total_files += 1

    def _get_category(self, path: Path) -> str:
        """Determine file category."""
        name = path.name.lower()
        suffix = path.suffix.lower()

        # Check by name patterns
        if name.startswith("test") or name.endswith(("_test.py", ".test.js", ".spec.js")):
            return "testing"
        if name in ("dockerfile", "docker-compose.yml", "docker-compose.yaml"):
            return "devops"
        if name in ("makefile", "cmakelists.txt"):
            return "build"
        if name.endswith((".md", ".rst", ".txt")) and "readme" in name:
            return "documentation"

        # Check by extension
        for category, extensions in FILE_CATEGORIES.items():
            if suffix in extensions:
                return category

        return "other"

    def _count_languages(self, files: list[FileEntry]) -> dict[str, int]:
        """Count files by language."""
        counts: dict[str, int] = {}
        for f in files:
            if f.language != "unknown":
                counts[f.language] = counts.get(f.language, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def _detect_frameworks(self, root: Path) -> list[str]:
        """Detect frameworks from config files."""
        frameworks = []
        for filename, fw_list in FRAMEWORK_MAP.items():
            if "/" in filename:
                # Check directory
                if (root / filename).exists() or any(root.rglob(filename)):
                    frameworks.extend(fw_list)
            else:
                if (root / filename).exists():
                    frameworks.extend(fw_list)
        return list(set(frameworks))

    def _count_categories(self, files: list[FileEntry]) -> dict[str, int]:
        """Count files by category."""
        counts: dict[str, int] = {}
        for f in files:
            counts[f.category] = counts.get(f.category, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def scan_single(self, path: str | Path) -> FileEntry | None:
        """Scan a single file."""
        p = Path(path).resolve()
        if not p.exists() or not p.is_file():
            return None

        try:
            stat = p.stat()
        except (PermissionError, OSError):
            return None

        language = LANGUAGE_MAP.get(p.suffix.lower(), "unknown")
        category = self._get_category(p)

        return FileEntry(
            path=str(p),
            name=p.name,
            extension=p.suffix.lower(),
            language=language,
            size=stat.st_size,
            category=category,
            last_modified=stat.st_mtime,
        )


def scan_directory(path: str, **kwargs: Any) -> ScanResult:
    """Quick directory scan."""
    scanner = DirectoryScanner()
    return scanner.scan(path, **kwargs)


def get_project_summary(path: str) -> dict[str, Any]:
    """Get a quick project summary."""
    result = scan_directory(path)
    return {
        "path": result.root_path,
        "files": result.total_files,
        "directories": result.total_directories,
        "languages": result.languages,
        "frameworks": result.frameworks,
        "categories": result.categories,
        "main_language": list(result.languages.keys())[0] if result.languages else "unknown",
    }
