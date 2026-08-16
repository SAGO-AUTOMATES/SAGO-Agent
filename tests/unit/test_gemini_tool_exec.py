"""Tests for Gemini tool execution in the simple executor.

The bug: the gemini branch in ``execute_agent_task`` returned early (with a
``pending_gemini_tools`` payload) the moment Gemini emitted a function call,
instead of executing the tool via the shared registry and feeding the result
back into the next model turn. These tests mock the Google ``genai`` SDK at the
import boundary so no network call is made, and assert that:
  1. a gemini-requested tool is actually executed, and
  2. its result is included in the follow-up model call.
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import sago.engine.simple_executor as se
from sago.tools.base import BaseTool


# --------------------------------------------------------------------------- #
# Fake Google genai SDK (injected into sys.modules at the call boundary)      #
# --------------------------------------------------------------------------- #
class _FakeType:
    STRING = "STRING"
    OBJECT = "OBJECT"


class _FakeSchema:
    def __init__(self, type=None, description="", properties=None, required=None):
        self.type = type
        self.description = description
        self.properties = properties
        self.required = required


class _FakeFunctionDeclaration:
    def __init__(self, name, description="", parameters=None):
        self.name = name
        self.description = description
        self.parameters = parameters


class _FakeTool:
    def __init__(self, function_declarations=None):
        self.function_declarations = function_declarations


class _FakeConfig:
    def __init__(
        self,
        system_instruction=None,
        max_output_tokens=None,
        temperature=None,
        tools=None,
    ):
        self.system_instruction = system_instruction
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.tools = tools


class _FakePart:
    def __init__(self, text=None, function_call=None, function_response=None):
        self.text = text
        self.function_call = function_call
        self.function_response = function_response


class _FakeContent:
    def __init__(self, role=None, parts=None):
        self.role = role
        self.parts = parts


class _FakeFunctionCall:
    def __init__(self, name=None, args=None):
        self.name = name
        self.args = args


class _FakeFunctionResponse:
    def __init__(self, name=None, response=None):
        self.name = name
        self.response = response


def _build_fake_google():
    """Return (google_pkg, genai_module) fakes and install them in sys.modules."""
    types_mod = ModuleType("google.genai.types")
    types_mod.Type = _FakeType
    types_mod.Schema = _FakeSchema
    types_mod.FunctionDeclaration = _FakeFunctionDeclaration
    types_mod.Tool = _FakeTool
    types_mod.GenerateContentConfig = _FakeConfig
    types_mod.Part = _FakePart
    types_mod.Content = _FakeContent
    types_mod.FunctionCall = _FakeFunctionCall
    types_mod.FunctionResponse = _FakeFunctionResponse

    genai_mod = ModuleType("google.genai")
    genai_mod.types = types_mod

    google_pkg = ModuleType("google")
    google_pkg.genai = genai_mod

    return google_pkg, genai_mod, types_mod


# --------------------------------------------------------------------------- #
# Fake tool registry                                                          #
# --------------------------------------------------------------------------- #
class _FakeWeatherTool(BaseTool):
    name = "get_weather"
    description = "Get the weather for a city"

    def _run(self, **kwargs):
        return f"Weather in {kwargs.get('city')}: sunny"


def _install_fakes(monkeypatch):
    google_pkg, genai_mod, types_mod = _build_fake_google()
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_mod)

    # Single shared "models" mock so the side_effect spans both turns.
    models = MagicMock()

    def _client_factory(api_key=None):
        return SimpleNamespace(models=models)

    genai_mod.Client = _client_factory

    # Replace the discovered tool registry with just our fake tool.
    monkeypatch.setattr(se, "_discover_tools", lambda: {"get_weather": _FakeWeatherTool})

    # The OpenAI client is built unconditionally but unused on the gemini path.
    # Stub it so no real credentials / network are needed.
    monkeypatch.setattr("openai.OpenAI", MagicMock())

    # Allow every tool call without prompting (mirrors YOLO mode for the test).
    class _FakePM:
        def get_risk_level(self, name):
            return "LOW"

        def check_permission(self, name, args, session_id=None):
            return True, "allowed"

        def approve_tool(self, name, session_id=None):
            pass

    import sago.permissions as perms

    monkeypatch.setattr(perms, "get_permission_manager", lambda: _FakePM())

    return models


def _make_response(text, parts):
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))],
        usage=None,
    )


class _RaisingTextResponse:
    """Mirrors the real Gemini SDK, which raises when a response has no text."""

    def __init__(self, candidates):
        self.candidates = candidates
        self.usage = None

    @property
    def text(self):
        raise ValueError("response.text failed: not an answer")


def test_gemini_tool_executed_and_result_fed_back(monkeypatch):
    models = _install_fakes(monkeypatch)

    fc_part = _FakePart(function_call=_FakeFunctionCall(name="get_weather", args={"city": "Paris"}))
    # Real SDK raises when a response contains only function calls; exercise guard.
    first = _RaisingTextResponse(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[fc_part]))]
    )

    second = _make_response(
        "The weather in Paris is sunny.", [_FakePart(text="The weather in Paris is sunny.")]
    )

    models.generate_content.side_effect = [first, second]

    tool_results = []
    calls = []

    result = se.execute_agent_task(
        task="What is the weather in Paris?",
        model="gemini-1.5-flash",
        api_key="",
        max_iterations=5,
        on_tool_result=lambda name, args, res, ok: tool_results.append((name, args, res)),
        on_tool_call=lambda name, args: calls.append((name, args)),
    )

    # 1) The tool was actually executed.
    assert ("get_weather", {"city": "Paris"}) in calls, result
    assert any(name == "get_weather" for name, _, _ in tool_results), result

    # 2) The result was fed back into the follow-up model turn.
    assert models.generate_content.call_count == 2
    follow_up_contents = models.generate_content.call_args_list[1].kwargs["contents"]
    fed_back = False
    for c in follow_up_contents:
        if getattr(c, "role", None) == "user":
            for p in c.parts:
                if p.function_response is not None:
                    assert p.function_response.name == "get_weather"
                    assert "Weather in Paris: sunny" in p.function_response.response["result"]
                    fed_back = True
    assert fed_back, "tool result was not fed back to gemini"

    # 3) The final answer reflects the tool output.
    assert result["success"] is True
    assert "sunny" in result["output"]


def test_gemini_no_tool_call_completes(monkeypatch):
    models = _install_fakes(monkeypatch)
    only_text = _make_response("Hello there!", [_FakePart(text="Hello there!")])
    models.generate_content.side_effect = [only_text]

    result = se.execute_agent_task(
        task="Say hi",
        model="gemini-1.5-flash",
        api_key="",
        max_iterations=5,
    )
    assert result["success"] is True
    assert result["output"] == "Hello there!"
    assert models.generate_content.call_count == 1
