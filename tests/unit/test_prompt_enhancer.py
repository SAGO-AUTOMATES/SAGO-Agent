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
    assert "fix" in res.intent_summary.lower() or "bug" in res.intent_summary.lower()
    assert len(res.acceptance_criteria) > 0
    assert len(res.operational_constraints) > 0
    assert "fix memory leak" in res.enhanced_prompt
    assert len(res.enhanced_prompt) > len("fix memory leak in cache")


def test_prompt_enhancer_target_detection(tmp_path):
    (tmp_path / "auth_service.py").write_text("def login(): pass", encoding="utf-8")

    res = enhance_prompt(
        task="refactor auth_service.py to support JWT tokens",
        agent_role="security-engineer",
        cwd=tmp_path,
    )

    assert "auth_service.py" in res.target_scope
    assert len(res.operational_constraints) > 0


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

    for chat_query in [
        "hello",
        "hoi",
        "how are you today?",
        "what's the weather today?",
        "tell me a joke",
    ]:
        intent = classifier.classify(chat_query)
        assert intent.task_type == "chat", (
            f"Query '{chat_query}' was classified as {intent.task_type}, expected 'chat'"
        )

        res = enhance_prompt(chat_query, agent_role="python-engineer", cwd=tmp_path)
        assert res.was_modified is False, (
            f"Query '{chat_query}' should not be modified with code templates"
        )
        assert res.enhanced_prompt == chat_query


def test_mixed_greeting_with_engineering_task(tmp_path):
    from sago.engine.intent_classifier import get_intent_classifier

    (tmp_path / "auth.py").write_text("def authenticate(): pass", encoding="utf-8")

    classifier = get_intent_classifier()
    task = "Hey there! Can you fix the auth bug in auth.py?"

    intent = classifier.classify(task)
    assert intent.task_type == "fix"

    res = enhance_prompt(task, agent_role="security-engineer", cwd=tmp_path)
    assert res.was_modified is True
    assert "auth.py" in res.target_scope
    assert "bug" in res.intent_summary.lower() or "fix" in res.intent_summary.lower()


def test_comprehensive_trigger_scenarios(tmp_path):
    from sago.engine.intent_classifier import get_intent_classifier

    classifier = get_intent_classifier()

    # Troubleshooting
    res = classifier.classify("why is this not working")
    assert res.task_type == "fix"

    res = classifier.classify("it crashes when I click login")
    assert res.task_type == "fix"

    # Exploration
    res = classifier.classify("projects in this repository")
    assert res.task_type == "analyze"

    res = classifier.classify("how does the session manager work")
    assert res.task_type == "analyze"

    # DevOps
    res = classifier.classify("how do I run this with docker")
    assert res.task_type == "devops"

    # QA / Testing
    res = classifier.classify("why is pytest failing on auth")
    assert res.task_type == "test"

    # Performance
    enh = enhance_prompt("this feels slow, optimize memory usage", cwd=tmp_path)
    assert enh.was_modified is True
    assert "optimize" in enh.intent_summary.lower() or "profile" in enh.intent_summary.lower()


def test_prompt_generator_tool_integration(tmp_path):
    from sago.tools.admin.prompt_generator import PromptGeneratorTool

    tool = PromptGeneratorTool()

    # Template retrieval
    tmpl_res = tool._run(operation="template", template_type="coding")
    assert "software engineer" in tmpl_res.lower()

    # Enhanced custom generation
    gen_res = tool._run(
        operation="generate",
        template_type="debugger",
        content="fix broken JWT authentication loop in auth.py",
    )
    assert "Generated Enhanced Prompt" in gen_res
    assert "JWT authentication" in gen_res


def test_zero_token_local_execution(tmp_path):
    """Verify that enhance_prompt runs completely locally without external network or LLM calls."""
    import time

    start = time.perf_counter()
    res = enhance_prompt(
        "refactor database connection pool for high concurrency",
        agent_role="python-engineer",
        cwd=tmp_path,
    )
    duration = time.perf_counter() - start

    assert res.was_modified is True
    assert duration < 0.05  # Sub-50ms local execution
    assert "refactor" in res.intent_summary.lower()


def test_generate_session_title():
    from sago.engine.prompt_enhancer import generate_session_title

    # Coding task
    t1 = generate_session_title(
        [{"role": "user", "content": "Fix the authentication token refresh bug in auth.py"}]
    )
    assert len(t1) > 0

    # Architecture query
    t2 = generate_session_title("explain the multi-agent orchestration architecture")
    assert len(t2) > 0

    # Greeting & capability query
    t3 = generate_session_title("hellos wehta can yiu do ?>")
    assert len(t3) > 0
    assert not t3.startswith("Empty")


def test_typo_greeting_and_capabilities_queries():
    from sago.engine.intent_classifier import get_intent_classifier

    classifier = get_intent_classifier()

    # User typos and greeting capability questions
    queries = [
        "hellos wehta can yiu do ?>",
        "hello what can you do",
        "heyy what are your capabilities",
        "howdy what skills do you have",
        "yo what can u do",
        "whats up today",
    ]
    for q in queries:
        enh = enhance_prompt(q)
        assert enh.was_modified is False

        intent = classifier.classify(q, use_llm=False)
        assert intent.task_type == "chat"
        assert intent.needs_tools is False
