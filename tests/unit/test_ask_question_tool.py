"""Unit tests for AskQuestionTool with MCQ and decision support."""

from __future__ import annotations

import os

from sago.tools.interactive.ask_question import (
    AskQuestionTool,
    QuestionItem,
    create_ask_question_tool,
)


def test_ask_question_headless_mode():
    """Verify AskQuestionTool automatically resolves to default option in headless mode."""
    tool = create_ask_question_tool()
    assert tool.name == "ask_question"

    os.environ["SAGO_HEADLESS"] = "1"
    try:
        questions = [
            {
                "question": "Which database would you like to use?",
                "options": ["PostgreSQL", "SQLite", "MongoDB"],
                "default_option": "PostgreSQL",
            },
            {
                "question": "Enable authentication middleware?",
                "options": ["Yes (JWT)", "No"],
            },
        ]
        result = tool._run(questions=questions)
        assert "PostgreSQL" in result
        assert "Yes (JWT)" in result
    finally:
        os.environ.pop("SAGO_HEADLESS", None)


def test_ask_question_typed_objects():
    """Verify AskQuestionTool works with QuestionItem instances."""
    tool = AskQuestionTool()
    q = QuestionItem(
        question="Select framework",
        options=["FastAPI", "Flask", "Django"],
        default_option="FastAPI",
    )
    os.environ["SAGO_HEADLESS"] = "1"
    try:
        res = tool._run(questions=[q])
        assert "FastAPI" in res
    finally:
        os.environ.pop("SAGO_HEADLESS", None)
