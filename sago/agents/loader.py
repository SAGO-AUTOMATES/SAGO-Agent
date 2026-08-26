"""Agent Profile Loader

Loads agent profiles from individual .py files in the profiles/ directory.
Each profile file exports a get_profile() function returning an AgentProfile.
"""

import logging
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

logger = logging.getLogger("sago.agents.loader")


def load_all_profiles(profiles_dir: Path | None = None) -> dict[str, Any]:
    """Load all agent profiles from the profiles directory."""
    if profiles_dir is None:
        profiles_dir = Path(__file__).parent / "profiles"

    logger.info("Loading all profiles from %s", profiles_dir)
    profiles = {}
    skipped = 0
    failed = 0

    for py_file in sorted(profiles_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            logger.debug("Skipping private file: %s", py_file.name)
            skipped += 1
            continue

        try:
            profile = load_profile(py_file)
            if profile and hasattr(profile, "name"):
                profiles[profile.name] = profile
                logger.info("Loaded profile: name=%s, file=%s", profile.name, py_file.name)
            else:
                logger.debug("No valid profile in %s (no name attribute)", py_file.name)
        except Exception as e:
            failed += 1
            logger.error("Failed to load %s: %s (full_path=%s)", py_file.name, e, py_file)

    logger.info(
        "Profile loading complete: loaded=%d, skipped=%d, failed=%d, dir=%s",
        len(profiles),
        skipped,
        failed,
        profiles_dir,
    )
    return profiles


def load_profile(file_path: Path) -> Any | None:
    """Load a single profile from a .py file."""
    logger.debug("Loading profile from file: %s", file_path)
    module_name = f"sago.agents.profiles.{file_path.stem}"
    spec = spec_from_file_location(module_name, file_path)

    if spec is None or spec.loader is None:
        logger.warning(
            "Could not create module spec for %s (module_name=%s)", file_path, module_name
        )
        return None

    module = module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        logger.debug("Successfully executed module: %s", file_path)
    except Exception as e:
        logger.error("Failed to execute module %s: %s", file_path, e)
        return None

    if hasattr(module, "get_profile"):
        profile = module.get_profile()
        logger.debug("Loaded profile via get_profile() from %s", file_path)
        return profile

    if hasattr(module, "PROFILE"):
        profile = module.PROFILE
        logger.debug("Loaded profile via PROFILE constant from %s", file_path)
        return profile

    logger.warning("No profile found in %s (missing get_profile/PROFILE)", file_path)
    return None


def get_profile_by_name(name: str, profiles_dir: Path | None = None) -> Any | None:
    """Get a specific profile by name."""
    logger.debug("Looking up profile by name: %s", name)
    # Convert name to file name: "python-pro" -> "python_pro.py"
    file_name = f"{name.replace('-', '_')}.py"
    profiles_dir = profiles_dir or Path(__file__).parent / "profiles"
    file_path = profiles_dir / file_name

    if file_path.exists():
        logger.info("Direct file match for profile %s: %s", name, file_path)
        return load_profile(file_path)

    # Try to find by scanning all profiles
    logger.debug("No direct file match for %s, scanning all profiles", name)
    profiles = load_all_profiles(profiles_dir)
    profile = profiles.get(name)
    if profile:
        logger.info("Found profile %s via scan (file=%s)", name, file_path)
    else:
        logger.warning("Profile not found: name=%s, attempted_file=%s", name, file_path)
    return profile


def list_profile_names(profiles_dir: Path | None = None) -> list[str]:
    """List all available profile names."""
    logger.debug("Listing all profile names from %s", profiles_dir)
    profiles = load_all_profiles(profiles_dir)
    names = sorted(profiles.keys())
    logger.info("Available profiles (%d): %s", len(names), names[:10])
    return names
