"""Unit tests for SAGO Prompt Enhancer."""

from sago.engine.prompt_enhancer import PromptEnhancer, enhance_prompt
from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer


def test_prompt_enhancer_basic_enhancement(tmp_path):
    enhancer = PromptEnhancer(root_dir=tmp_path)
    res = enhancer.enhance(
        task="fix memory leak in cache",
        agent_role="python-engineer",
        cwd=tmp_path,
    )

    assert res.was_modified is True
    assert "memory leak" in res.intent_summary
    assert len(res.acceptance_criteria) > 0
    assert len(res.operational_constraints) > 0
    assert "Primary Objective" in res.enhanced_prompt
    assert "Acceptance Criteria" in res.enhanced_prompt


def test_prompt_enhancer_target_detection(tmp_path):
    (tmp_path / "auth_service.py").write_text("def login(): pass", encoding="utf-8")

    res = enhance_prompt(
        task="refactor auth_service.py to support JWT tokens",
        agent_role="security-engineer",
        cwd=tmp_path,
    )

    assert "auth_service.py" in res.target_scope
    assert any("security" in g.lower() or "input" in g.lower() for g in res.operational_constraints)


def test_prompt_enhancer_telemetry_event(tmp_path):
    tracer = get_dev_tracer()
    tracer.set_enabled(True)

    enhance_prompt(
        task="add unit tests for database schema",
        agent_role="qa-engineer",
        cwd=tmp_path,
    )

    events = tracer.get_events(filter_type=TraceEventType.PROMPT_ENHANCED)
    assert len(events) > 0
    latest = events[-1]
    assert latest.event_type == TraceEventType.PROMPT_ENHANCED
    assert latest.source == "prompt_enhancer"
    assert "original_prompt" in latest.data


def test_casual_chat_and_weather_not_overwritten(tmp_path):
    from sago.engine.intent_classifier import get_intent_classifier

    classifier = get_intent_classifier()

    for chat_query in ["hello", "hoi", "how are you today?", "what's the weather today?", "tell me a joke"]:
        intent = classifier.classify(chat_query)
        assert intent.task_type == "chat", f"Query '{chat_query}' was classified as {intent.task_type}, expected 'chat'"

        res = enhance_prompt(chat_query, agent_role="python-engineer", cwd=tmp_path)
        assert res.was_modified is False, f"Query '{chat_query}' should not be modified with code templates"
        assert res.enhanced_prompt == chat_query
