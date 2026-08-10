"""JSON/YAML Processor Tool - Parse and transform structured data."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class DataProcessorArgs(BaseModel):
    """Arguments for data processing."""

    operation: str = Field(
        description="Operation: parse, validate, format, query, merge, diff, convert"
    )
    data: str = Field(description="JSON or YAML string to process")
    target_format: str = Field(default="json", description="Target format: json, yaml")
    query_path: str = Field(default="", description="JSONPath query for query operation")
    extra_data: str = Field(default="", description="Extra data for merge/diff operations")


class DataProcessor(BaseTool):
    """Tool for processing JSON/YAML data."""

    name: str = "data_processor"
    description: str = (
        "Process JSON/YAML data: parse, validate, format, query, merge, diff, convert."
    )
    args_model: type[BaseModel] = DataProcessorArgs

    def _run(
        self,
        operation: str,
        data: str,
        target_format: str = "json",
        query_path: str = "",
        extra_data: str = "",
        **kwargs: Any,
    ) -> str:
        """Process structured data."""
        try:
            import yaml
        except ImportError:
            # Fallback if pyyaml not installed
            yaml = None  # type: ignore

        def parse_data(text: str) -> Any:
            text = text.strip()
            if text.startswith(("{", "[")):
                return json.loads(text)
            elif yaml:
                return yaml.safe_load(text)
            else:
                return json.loads(text)

        def format_data(obj: Any, fmt: str) -> str:
            if fmt == "yaml" and yaml:
                return yaml.dump(obj, default_flow_style=False, sort_keys=False)
            return json.dumps(obj, indent=2, default=str)

        try:
            if operation == "parse":
                parsed = parse_data(data)
                return f"Parsed successfully:\nType: {type(parsed).__name__}\nValue: {json.dumps(parsed, indent=2, default=str)[:2000]}"

            elif operation == "validate":
                parsed = parse_data(data)
                return f"Valid JSON/YAML. Type: {type(parsed).__name__}"

            elif operation == "format":
                parsed = parse_data(data)
                return format_data(parsed, target_format)

            elif operation == "query":
                parsed = parse_data(data)
                if not query_path:
                    return "Error: query_path required for query operation"
                # Simple JSONPath-like query
                parts = query_path.strip(".").split(".")
                current = parsed
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    elif isinstance(current, list) and part.isdigit():
                        current = current[int(part)]
                    else:
                        return f"Path not found: {query_path}"
                return f"Query result:\n{json.dumps(current, indent=2, default=str)[:2000]}"

            elif operation == "merge":
                parsed = parse_data(data)
                extra = parse_data(extra_data) if extra_data else {}
                if isinstance(parsed, dict) and isinstance(extra, dict):
                    parsed.update(extra)
                    return f"Merged:\n{format_data(parsed, target_format)[:2000]}"
                return "Error: Both inputs must be objects for merge"

            elif operation == "diff":
                parsed = parse_data(data)
                extra = parse_data(extra_data) if extra_data else {}
                diffs = []
                if isinstance(parsed, dict) and isinstance(extra, dict):
                    all_keys = set(list(parsed.keys()) + list(extra.keys()))
                    for key in sorted(all_keys):
                        if key not in parsed:
                            diffs.append(f"+ {key}: {extra[key]}")
                        elif key not in extra:
                            diffs.append(f"- {key}: {parsed[key]}")
                        elif parsed[key] != extra[key]:
                            diffs.append(f"~ {key}: {parsed[key]} -> {extra[key]}")
                return "Differences:\n" + "\n".join(diffs) if diffs else "No differences"

            elif operation == "convert":
                parsed = parse_data(data)
                return format_data(parsed, target_format)

            else:
                return f"Error: Invalid operation '{operation}'"

        except json.JSONDecodeError as e:
            return f"JSON parse error: {e}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"


def get_tool() -> type[DataProcessor]:
    """Get the tool class."""
    return DataProcessor
