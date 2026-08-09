"""CrewAI Tool Wrappers - Auto-discover ALL Sago tools for CrewAI."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from crewai.tools import tool as crewai_tool


def create_crewai_tool(sago_tool_class: type) -> Any:
    """Create a CrewAI tool from a Sago tool class.

    Args:
        sago_tool_class: A Sago tool class that inherits from BaseTool.

    Returns:
        A CrewAI-compatible tool instance.
    """
    tool_instance = sago_tool_class()

    @crewai_tool(tool_instance.name)
    def wrapped_tool(**kwargs: Any) -> str:
        """Wrapped Sago tool."""
        return tool_instance.run(**kwargs)

    wrapped_tool.description = tool_instance.description
    return wrapped_tool


def _discover_all_tools() -> dict[str, Any]:
    """Auto-discover ALL BaseTool subclasses and wrap them for CrewAI."""
    import logging
    _log = logging.getLogger("sago.tools")

    tools_dir = Path(__file__).parent.parent / "tools"
    crewai_tools: dict[str, Any] = {}

    for py_file in tools_dir.rglob("*.py"):
        if py_file.name.startswith("_") or py_file.name == "base.py":
            continue
        if py_file.name == "crewai_wrappers.py":
            continue

        rel = py_file.relative_to(tools_dir)
        parts = list(rel.with_suffix("").parts)
        module_name = ".".join(["sago", "tools"] + list(parts))

        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            _log.debug(f"Failed to import {module_name}: {e}")
            continue

        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if (
                isinstance(obj, type)
                and hasattr(obj, "name")
                and obj.__name__ != "BaseTool"
                and obj is not getattr(sys.modules.get("sago.tools.base", None), "BaseTool", None)
            ):
                try:
                    from sago.tools.base import BaseTool
                    if issubclass(obj, BaseTool) and obj.name:
                        crewai_tools[obj.name] = create_crewai_tool(obj)
                except Exception as e:
                    _log.debug(f"Failed to wrap tool {obj.__name__}: {e}")

    return crewai_tools


# Lazy-loaded registry
_CREWAI_TOOLS: dict[str, Any] | None = None


def _get_registry() -> dict[str, Any]:
    global _CREWAI_TOOLS
    if _CREWAI_TOOLS is None:
        _CREWAI_TOOLS = _discover_all_tools()
    return _CREWAI_TOOLS


def get_crewai_tool(tool_name: str) -> Any | None:
    """Get a CrewAI tool by name.

    Args:
        tool_name: Name of the tool.

    Returns:
        CrewAI tool or None if not found.
    """
    return _get_registry().get(tool_name)


def list_crewai_tools() -> list[str]:
    """List all available CrewAI tool names."""
    return sorted(_get_registry().keys())


# Also export the full registry for direct access
CREWAI_TOOLS = property(lambda self: _get_registry())
