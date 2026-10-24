"""Exhaustive tests for Smart Input Processor."""

from __future__ import annotations

import pytest

from sago.tui.smart_input import (
    InputAnalysis,
    SmartInputProcessor,
    get_smart_processor,
)


def test_input_analysis_to_dict() -> None:
    analysis = InputAnalysis(
        original_length=150,
        word_count=25,
        needs_summarization=False,
        keywords=["critical", "security", "bug"],
        error_lines=["Error: file not found"],
        stack_frames=["main:42"],
        file_references=["sago/app.py"],
        code_blocks=["```python\nprint(1)\n```"],
        urls=["https://example.com"],
        numbers=["1", "2.5"],
        importance_score=0.85,
    )
    d = analysis.to_dict()
    assert d["original_length"] == 150
    assert d["word_count"] == 25
    assert d["needs_summarization"] is False
    assert "critical" in d["keywords"]
    assert d["error_count"] == 1
    assert d["stack_frame_count"] == 1
    assert d["file_count"] == 1
    assert d["code_block_count"] == 1
    assert d["url_count"] == 1
    assert d["importance_score"] == 0.85


def test_short_input_processing() -> None:
    processor = SmartInputProcessor()
    text = "Hello world, please check the status."
    processed_text, analysis = processor.process_input(text)

    assert processed_text == text
    assert analysis.needs_summarization is False
    assert analysis.original_length == len(text)
    assert analysis.word_count == 6


def test_long_input_with_errors_stacks_files_code() -> None:
    processor = SmartInputProcessor()
    # Create input with > 500 words
    lorem = "word " * 450
    text = f"""
{lorem}
Critical vulnerability and bug detected in authentication!
Traceback (most recent call last):
  File "/usr/local/lib/sago/auth.py", line 123, in authenticate
    raise ValueError("Invalid auth credentials")
Error: authentication failed with status 401
at Module.login(user.js:55)
in verify_token at line 89
Referenced file: /var/log/sago/audit.log
Windows file: C:\\sago\\config\\settings.toml
Code block:
```python
def login():
    return False
```
Documentation link: https://docs.sago.dev/security/auth?id=999
Count: 42 items and 3.14 ratio.
Can we fix and deploy this immediately?
"""
    processed_text, analysis = processor.process_input(text)

    assert analysis.needs_summarization is True
    assert len(analysis.error_lines) > 0
    assert len(analysis.stack_frames) > 0
    assert len(analysis.file_references) > 0
    assert len(analysis.code_blocks) > 0
    assert len(analysis.urls) > 0
    assert len(analysis.numbers) > 0
    assert analysis.importance_score >= 0.8
    assert "Task:" in analysis.summary
    assert len(analysis.selective_content) > 0
    assert processed_text == analysis.selective_content


@pytest.mark.parametrize(
    ("task_type", "sample_prompt"),
    [
        ("debug", "We have an issue and crash error traceback in login module"),
        ("implement", "Please create and develop a new feature to build user profiles"),
        ("fix", "Please repair, patch and correct the broken link"),
        ("refactor", "Let's clean and restructure the module to improve clarity"),
        ("test", "Run tests and assert verify validate the output"),
        ("deploy", "We need to release and ship the new build to publish it"),
        ("review", "Please audit inspect and analyze the security policy"),
        ("optimize", "Speed up the cache performance to make it fast"),
        ("security", "Check auth token encryption for any vulnerability"),
    ],
)
def test_task_classification_variants(task_type: str, sample_prompt: str) -> None:
    processor = SmartInputProcessor()
    classified = processor._classify_task(sample_prompt)
    assert classified == task_type


def test_classify_task_empty_or_no_keywords() -> None:
    processor = SmartInputProcessor()
    assert processor._classify_task("ordinary words without trigger") is None


def test_get_smart_processor_factory() -> None:
    p1 = get_smart_processor()
    assert isinstance(p1, SmartInputProcessor)
