"""Agent Profile Loader

Loads agent profiles from individual .py files in the profiles/ directory.
Each profile file exports a get_profile() function returning an AgentProfile.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any


def load_all_profiles(profiles_dir: Path | None = None) -> dict[str, Any]:
    """Load all agent profiles from the profiles directory."""
    if profiles_dir is None:
        profiles_dir = Path(__file__).parent / "profiles"

    profiles = {}
    for py_file in sorted(profiles_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        try:
            profile = load_profile(py_file)
            if profile and hasattr(profile, "name"):
                profiles[profile.name] = profile
        except Exception as e:
            print(f"Warning: Failed to load {py_file.name}: {e}")

    return profiles


def load_profile(file_path: Path) -> Any | None:
    """Load a single profile from a .py file."""
    module_name = f"sago.agents.profiles.{file_path.stem}"
    spec = spec_from_file_location(module_name, file_path)

    if spec is None or spec.loader is None:
        return None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "get_profile"):
        return module.get_profile()

    if hasattr(module, "PROFILE"):
        return module.PROFILE

    return None


def get_profile_by_name(name: str, profiles_dir: Path | None = None) -> Any | None:
    """Get a specific profile by name."""
    # Convert name to file name: "python-pro" -> "python_pro.py"
    file_name = f"{name.replace('-', '_')}.py"
    profiles_dir = profiles_dir or Path(__file__).parent / "profiles"
    file_path = profiles_dir / file_name

    if file_path.exists():
        return load_profile(file_path)

    # Try to find by scanning all profiles
    profiles = load_all_profiles(profiles_dir)
    return profiles.get(name)


def list_profile_names(profiles_dir: Path | None = None) -> list[str]:
    """List all available profile names."""
    profiles = load_all_profiles(profiles_dir)
    return sorted(profiles.keys())
