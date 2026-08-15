"""Single Source of Truth for Sago Version.

Dynamically resolves package version from installed distribution metadata
with static fallback during local development.
"""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version("sago-agent")
except Exception:
    __version__ = "0.1.7"
