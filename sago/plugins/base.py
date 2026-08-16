"""SAGO Plugin Architecture

Enables third-party plugins, custom tools, and lifecycle hooks
without modifying core codebase.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sago.paths import get_sago_home

logger = logging.getLogger(__name__)


@dataclass
class PluginMetadata:
    """Metadata describing a Sago plugin."""

    name: str
    version: str = "0.1.0"
    author: str = "Community"
    description: str = ""
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


class BasePlugin(ABC):
    """Abstract base class for all SAGO plugins."""

    meta: PluginMetadata

    def __init__(self) -> None:
        if not hasattr(self, "meta"):
            self.meta = PluginMetadata(
                name=self.__class__.__name__.lower(),
                description=self.__doc__ or "",
            )

    def on_init(self, context: dict[str, Any]) -> None:
        """Called when Sago initializes."""
        pass

    def on_user_message(self, message: str, context: dict[str, Any]) -> str:
        """Called before a user message is processed by agents.

        Can transform or enrich the prompt.
        """
        return message

    def on_tool_call(self, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        """Called right before a tool is executed. Can inspect or modify args."""
        return tool_args

    def on_tool_result(self, tool_name: str, result: Any) -> Any:
        """Called immediately after a tool finishes execution."""
        return result

    def on_response(self, response: str, context: dict[str, Any]) -> str:
        """Called before the assistant response is returned to the user."""
        return response

    def provide_tools(self) -> list[Any]:
        """Return a list of custom tool instances to register in SAGO."""
        return []

    def provide_agents(self) -> list[dict[str, Any]]:
        """Return custom specialist agent profiles to register in SAGO."""
        return []


class PluginManager:
    """Discovers, loads, and manages SAGO plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, BasePlugin] = {}
        self._disabled: set[str] = set()

    def discover_plugins(self, custom_dirs: list[Path] | None = None) -> list[BasePlugin]:
        """Discover plugins from standard paths, entry points, and custom directories."""
        dirs = [
            get_sago_home() / "plugins",
            Path.cwd() / ".sago" / "plugins",
        ]
        if custom_dirs:
            dirs.extend(custom_dirs)

        # 1. Load directory plugins
        for plugin_dir in dirs:
            if not plugin_dir.exists() or not plugin_dir.is_dir():
                continue
            for file_path in plugin_dir.glob("*.py"):
                if file_path.name.startswith("__"):
                    continue
                self.load_from_file(file_path)

        # 2. Load Python entry_points if available
        try:
            from importlib.metadata import entry_points

            eps = entry_points(group="sago.plugins")
            for ep in eps:
                try:
                    plugin_cls = ep.load()
                    if issubclass(plugin_cls, BasePlugin):
                        instance = plugin_cls()
                        self.register_plugin(instance)
                except Exception as exc:
                    logger.warning("Failed to load plugin entry point %s: %s", ep.name, exc)
        except Exception:
            pass

        return list(self._plugins.values())

    def register_plugin(self, plugin: BasePlugin) -> None:
        """Register a plugin instance."""
        name = plugin.meta.name.lower()
        self._plugins[name] = plugin
        logger.info("Registered plugin: %s v%s", name, plugin.meta.version)

    def unregister_plugin(self, name: str) -> None:
        """Unregister a plugin."""
        self._plugins.pop(name.lower(), None)

    def enable_plugin(self, name: str) -> bool:
        name = name.lower()
        if name in self._plugins:
            self._disabled.discard(name)
            self._plugins[name].meta.enabled = True
            return True
        return False

    def disable_plugin(self, name: str) -> bool:
        name = name.lower()
        if name in self._plugins:
            self._disabled.add(name)
            self._plugins[name].meta.enabled = False
            return True
        return False

    def get_plugin(self, name: str) -> BasePlugin | None:
        return self._plugins.get(name.lower())

    def list_plugins(self) -> list[PluginMetadata]:
        return [p.meta for p in self._plugins.values()]

    def load_from_file(self, file_path: Path) -> BasePlugin | None:
        """Dynamically load a plugin from a Python file."""
        try:
            module_name = f"sago_plugin_{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find BasePlugin subclass
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePlugin)
                    and attr is not BasePlugin
                ):
                    instance = attr()
                    self.register_plugin(instance)
                    return instance
        except Exception as exc:
            logger.error("Failed to load plugin from %s: %s", file_path, exc)
        return None

    # Lifecycle dispatchers
    def hook_user_message(self, message: str, context: dict[str, Any]) -> str:
        for p in self._plugins.values():
            if p.meta.enabled and p.meta.name not in self._disabled:
                try:
                    message = p.on_user_message(message, context)
                except Exception as exc:
                    logger.error("Plugin %s failed in on_user_message: %s", p.meta.name, exc)
        return message

    def hook_tool_call(self, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        for p in self._plugins.values():
            if p.meta.enabled and p.meta.name not in self._disabled:
                try:
                    tool_args = p.on_tool_call(tool_name, tool_args)
                except Exception as exc:
                    logger.error("Plugin %s failed in on_tool_call: %s", p.meta.name, exc)
        return tool_args

    def hook_tool_result(self, tool_name: str, result: Any) -> Any:
        for p in self._plugins.values():
            if p.meta.enabled and p.meta.name not in self._disabled:
                try:
                    result = p.on_tool_result(tool_name, result)
                except Exception as exc:
                    logger.error("Plugin %s failed in on_tool_result: %s", p.meta.name, exc)
        return result

    def hook_response(self, response: str, context: dict[str, Any]) -> str:
        for p in self._plugins.values():
            if p.meta.enabled and p.meta.name not in self._disabled:
                try:
                    response = p.on_response(response, context)
                except Exception as exc:
                    logger.error("Plugin %s failed in on_response: %s", p.meta.name, exc)
        return response


# Global singleton instance
_plugin_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager singleton."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
        _plugin_manager.discover_plugins()
    return _plugin_manager
