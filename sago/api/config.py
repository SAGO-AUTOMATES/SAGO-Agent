from __future__ import annotations

from typing import Any

from sago.config.loader import get_config as _get_sago_config
from sago.config.loader import is_dev_mode_enabled


def get_execution_mode() -> str:
    """Return configured execution mode ('native' or 'api')."""
    try:
        cfg = _get_sago_config()
        return getattr(cfg.execution, "mode", "native")
    except Exception:
        return "native"


def is_dev_mode() -> bool:
    """Return if dev mode is enabled."""
    return is_dev_mode_enabled()


def get_config(key: str, default: Any = None) -> Any:
    """Get a configuration value by dot-separated path."""
    try:
        cfg = _get_sago_config()
        data = cfg.model_dump()
        keys = key.split(".")
        value: Any = data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default
    except Exception:
        return default
