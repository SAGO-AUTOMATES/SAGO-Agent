"""Tests for IntentClassifier semantic intent detection and caching."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sago.engine.intent_classifier import IntentClassifier


def test_intent_classifier_heuristic_chat() -> None:
    classifier = IntentClassifier()

    r1 = classifier.classify("Tell me a funny joke", use_llm=False)
    assert r1.task_type == "chat"
    assert r1.needs_tools is False

    r2 = classifier.classify("10-20 more", use_llm=False)
    assert r2.task_type == "chat"
    assert r2.needs_tools is False

    r3 = classifier.classify("hi there how are you", use_llm=False)
    assert r3.task_type == "chat"
    assert r3.needs_tools is False


def test_intent_classifier_heuristic_code_tasks() -> None:
    classifier = IntentClassifier()

    fix_res = classifier.classify("Fix the broken authentication loop", use_llm=False)
    assert fix_res.task_type == "fix"
    assert fix_res.needs_tools is True
    assert fix_res.suggested_agent == "debugger"

    test_res = classifier.classify("Run pytest on unit test suite", use_llm=False)
    assert test_res.task_type == "test"
    assert test_res.needs_tools is True

    create_res = classifier.classify("Build a FastAPI REST API server", use_llm=False)
    assert create_res.task_type == "create"
    assert create_res.needs_tools is True


def test_intent_classifier_caching() -> None:
    classifier = IntentClassifier(cache_size=2)

    res1 = classifier.classify("explain the database architecture", use_llm=False)
    assert res1.source == "heuristic"

    # Second call must hit cache
    res2 = classifier.classify("explain the database architecture", use_llm=False)
    assert res2.source == "cache"
    assert res2.task_type == "analyze"


def test_intent_classifier_llm_flow() -> None:
    classifier = IntentClassifier()

    mock_cfg = MagicMock()
    mock_cfg.llm.api_key = "test_api_key"
    mock_cfg.llm.provider = "openrouter"
    mock_cfg.llm.model = "openrouter/free"

    mock_provider = MagicMock()
    mock_provider.generate.return_value = '{"type": "chat", "needs_tools": false, "suggested_agent": "general-assistant", "confidence": 0.99}'

    with (
        patch("sago.engine.intent_classifier.get_config", return_value=mock_cfg),
        patch("sago.engine.intent_classifier.create_provider", return_value=mock_provider),
    ):
        res = classifier.classify("write 5 more jokes please", use_llm=True)
        assert res.task_type == "chat"
        assert res.needs_tools is False
        assert res.source == "llm"
        assert res.confidence == 0.99
