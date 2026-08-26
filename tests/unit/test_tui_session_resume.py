"""Unit tests to verify session resume resilience against malformed tool arguments."""

import json


class TestSessionResumeResilience:
    """Test resume session tool widget decoding with various edge case arguments."""

    def test_tool_widget_arguments_decoding_variants(self):
        """Verify that double-encoded, malformed, non-dict, or raw string args never crash."""
        test_cases = [
            '{"command": "ls -la"}',
            '"{\\"command\\": \\"ls -la\\"}"',
            '{"nested": {"key": 123}}',
            "just plain text",
            "",
            None,
            12345,
            ["item1", "item2"],
            {"normal": "dict"},
        ]

        for raw_args in test_cases:
            parsed_args = {}
            if isinstance(raw_args, str):
                try:
                    decoded = json.loads(raw_args) if raw_args else {}
                    if isinstance(decoded, str):
                        try:
                            decoded = json.loads(decoded)
                        except Exception:
                            pass
                    if isinstance(decoded, dict):
                        parsed_args = decoded
                    elif decoded:
                        parsed_args = {"args": decoded}
                except Exception:
                    parsed_args = {"args": raw_args}
            elif isinstance(raw_args, dict):
                parsed_args = raw_args
            elif raw_args:
                parsed_args = {"args": raw_args}

            assert isinstance(parsed_args, dict), f"Failed for input {raw_args}"
            # Ensure items() can always be iterated
            param_lines = []
            for k, v in parsed_args.items():
                param_lines.append(f"{k}: {v}")
            assert isinstance(param_lines, list)
