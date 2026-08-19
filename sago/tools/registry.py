"""Dynamic Tool Registry for SAGO.

Discovers, categorizes, inspects, and manages all SAGO tools dynamically.
Includes built-in tools across all domains, third-party plugin tools, and
MCP (Model Context Protocol) bridged tools.
"""

from __future__ import annotations

import importlib
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.registry")


@dataclass
class ToolDefinition:
    """Rich metadata definition for a dynamically discovered tool."""

    name: str
    description: str
    category: str
    tool_class: type[BaseTool]
    source: str = "builtin"  # builtin, plugin, mcp
    args_model: type[BaseModel] | None = None
    args_schema: dict[str, Any] = field(default_factory=dict)
    module_path: str = ""
    is_safe: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert tool definition to JSON-serializable dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "source": self.source,
            "module_path": self.module_path,
            "args_schema": self.args_schema,
            "is_safe": self.is_safe,
        }


# Cache storage
_TOOLS_CACHE: dict[str, ToolDefinition] = {}
_TOOLS_LOCK = threading.Lock()


def _infer_category_from_path(file_path: Path, tools_root: Path, tool_cls: type[BaseTool]) -> str:
    """Infer category from class attribute or folder hierarchy."""
    # 1. Subclass attribute if explicitly defined
    if "category" in tool_cls.__dict__ and getattr(tool_cls, "category"):
        cat = getattr(tool_cls, "category")
        return str(cat.value if hasattr(cat, "value") else cat).lower().strip()

    # 2. Relative folder under tools/ (e.g. sago/tools/file/read_file.py -> 'file')
    try:
        resolved_file = file_path.resolve()
        resolved_root = tools_root.resolve()
        rel_parts = resolved_file.relative_to(resolved_root).parts
        if len(rel_parts) > 1:
            return rel_parts[0].lower().strip()
    except Exception as e:
        logger.debug("Failed to infer category from path %s: %s", file_path, e)

    return "general"


def _extract_args_schema(args_model: type[BaseModel] | None) -> dict[str, Any]:
    """Extract human-readable schema dictionary from args_model."""
    if not args_model or not issubclass(args_model, BaseModel):
        return {}
    schema: dict[str, Any] = {}
    try:
        # Pydantic v2
        if hasattr(args_model, "model_fields"):
            for fname, fval in args_model.model_fields.items():
                annotation_str = (
                    str(fval.annotation)
                    .replace("typing.", "")
                    .replace("<class '", "")
                    .replace("'>", "")
                )
                desc = fval.description or ""
                default = (
                    fval.default
                    if fval.default is not None and str(fval.default) != "PydanticUndefined"
                    else None
                )
                schema[fname] = {
                    "type": annotation_str,
                    "description": desc,
                    "default": default,
                    "required": fval.is_required(),
                }
        # Pydantic v1 fallback
        elif hasattr(args_model, "__fields__"):
            for fname, fval in args_model.__fields__.items():
                schema[fname] = {
                    "type": str(fval.outer_type_),
                    "description": fval.field_info.description or "",
                    "required": fval.required,
                }
    except Exception as exc:
        logger.debug(f"Failed to parse args schema for {args_model}: {exc}")
    return schema


def discover_tools(
    force_reload: bool = False,
    include_plugins: bool = True,
    include_mcp: bool = True,
) -> dict[str, ToolDefinition]:
    """Discover all tools dynamically across built-in modules, plugins, and MCP."""
    global _TOOLS_CACHE

    if _TOOLS_CACHE and not force_reload:
        return _TOOLS_CACHE

    with _TOOLS_LOCK:
        if _TOOLS_CACHE and not force_reload:
            return _TOOLS_CACHE

        discovered: dict[str, ToolDefinition] = {}
        tools_root = Path(__file__).parent

        # 1. Scan built-in tool files
        for py_file in tools_root.rglob("*.py"):
            if (
                py_file.name.startswith("_")
                or py_file.name == "base.py"
                or py_file.name == "crewai_wrappers.py"
                or py_file.name == "registry.py"
            ):
                continue

            try:
                parts = py_file.relative_to(tools_root).with_suffix("").as_posix().split("/")
                module_name = f"sago.tools.{'.'.join(parts)}"
                mod = importlib.import_module(module_name)

                for attr_name in dir(mod):
                    obj = getattr(mod, attr_name)
                    if isinstance(obj, type) and issubclass(obj, BaseTool) and obj is not BaseTool:
                        tool_name = getattr(obj, "name", None)
                        if not tool_name:
                            continue

                        # Extract docstring description if description not explicitly set
                        desc = (
                            getattr(obj, "description", "")
                            or (obj.__doc__ or "").strip().splitlines()[0]
                            if (obj.__doc__ or "").strip()
                            else f"Execute {tool_name} tool"
                        )
                        category = _infer_category_from_path(py_file, tools_root, obj)
                        args_model = getattr(obj, "args_model", None)
                        args_schema = _extract_args_schema(args_model)

                        discovered[tool_name] = ToolDefinition(
                            name=tool_name,
                            description=desc,
                            category=category,
                            tool_class=obj,
                            source="builtin",
                            args_model=args_model,
                            args_schema=args_schema,
                            module_path=module_name,
                        )
            except Exception as exc:
                logger.debug(f"Could not load tool from {py_file}: {exc}")

        # 2. Discover plugin tools
        if include_plugins:
            try:
                from sago.plugins.base import get_plugin_manager

                pm = get_plugin_manager()
                for plugin in pm.discover_plugins():
                    if getattr(plugin, "meta", None) and plugin.meta.enabled:
                        for pt in plugin.provide_tools():
                            pt_cls = pt if isinstance(pt, type) else pt.__class__
                            if issubclass(pt_cls, BaseTool):
                                name = getattr(pt, "name", None) or getattr(pt_cls, "name", "")
                                if name and name not in discovered:
                                    desc = (
                                        getattr(pt, "description", "")
                                        or getattr(pt_cls, "description", "")
                                        or "Plugin extension tool"
                                    )
                                    args_model = getattr(pt_cls, "args_model", None)
                                    discovered[name] = ToolDefinition(
                                        name=name,
                                        description=desc,
                                        category="plugin",
                                        tool_class=pt_cls,
                                        source=f"plugin:{plugin.meta.name}",
                                        args_model=args_model,
                                        args_schema=_extract_args_schema(args_model),
                                        module_path=f"plugin.{plugin.meta.name}",
                                    )
            except Exception as exc:
                logger.debug(f"Plugin tools discovery skipped: {exc}")

        # 3. Discover MCP tools
        if include_mcp:
            try:
                from sago.mcp.manager import get_mcp_manager

                mgr = get_mcp_manager()
                for mcp_tool in mgr.get_mcp_tools():
                    mcp_cls = mcp_tool if isinstance(mcp_tool, type) else mcp_tool.__class__
                    if issubclass(mcp_cls, BaseTool):
                        name = getattr(mcp_tool, "name", "") or getattr(mcp_cls, "name", "")
                        if name and name not in discovered:
                            desc = (
                                getattr(mcp_tool, "description", "")
                                or getattr(mcp_cls, "description", "")
                                or "Bridged MCP tool"
                            )
                            args_model = getattr(mcp_cls, "args_model", None)
                            discovered[name] = ToolDefinition(
                                name=name,
                                description=desc,
                                category="mcp",
                                tool_class=mcp_cls,
                                source="mcp",
                                args_model=args_model,
                                args_schema=_extract_args_schema(args_model),
                                module_path="mcp.bridge",
                            )
            except Exception as exc:
                logger.debug(f"MCP tools discovery skipped: {exc}")

        _TOOLS_CACHE = discovered
        return _TOOLS_CACHE


def get_tool(name: str) -> ToolDefinition | None:
    """Get a tool definition by name."""
    tools = discover_tools()
    return tools.get(name)


def get_tool_class(name: str) -> type[BaseTool] | None:
    """Get the BaseTool class for a given tool name."""
    tool_def = get_tool(name)
    return tool_def.tool_class if tool_def else None


def instantiate_tool(name: str) -> BaseTool | None:
    """Instantiate a tool by name."""
    cls = get_tool_class(name)
    if cls:
        try:
            return cls()
        except Exception as exc:
            logger.warning(f"Failed to instantiate tool {name}: {exc}")
    return None


def list_tools(category: str | None = None, query: str | None = None) -> list[ToolDefinition]:
    """List tools optionally filtered by category or search query."""
    tools = discover_tools()
    results = list(tools.values())

    if category:
        cat_lower = category.lower()
        results = [t for t in results if t.category.lower() == cat_lower]

    if query:
        q_lower = query.lower()
        results = [
            t
            for t in results
            if q_lower in t.name.lower()
            or q_lower in t.description.lower()
            or q_lower in t.category.lower()
        ]

    return sorted(results, key=lambda t: (t.category, t.name))


def list_categories() -> dict[str, list[ToolDefinition]]:
    """Group all discovered tools by category."""
    tools = discover_tools()
    categories: dict[str, list[ToolDefinition]] = {}
    for t in tools.values():
        categories.setdefault(t.category, []).append(t)

    for cat in categories:
        categories[cat].sort(key=lambda t: t.name)

    return dict(sorted(categories.items()))


def get_total_tools_count() -> int:
    """Return the total number of dynamically discovered tools."""
    return len(discover_tools())
