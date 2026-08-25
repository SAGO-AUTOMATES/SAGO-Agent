"""Interactive Question & Decision Tool for SAGO Agents.

Allows agents to prompt the user with multiple-choice questions (MCQs),
architectural decisions, and design options during execution.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field, field_validator

from sago.tools.base import BaseTool


class QuestionItem(BaseModel):
    """A single multiple-choice or decision question."""

    question: str = Field(..., description="The question text to ask the user.")
    options: list[str] = Field(
        default_factory=list,
        description="Selectable multiple-choice options for the user.",
    )
    is_multi_select: bool = Field(
        default=False,
        description="If True, allows the user to select multiple options.",
    )
    default_option: str | None = Field(
        default=None,
        description="Default option to select if non-interactive or timed out.",
    )

    @field_validator("options", mode="before")
    @classmethod
    def _normalize_options(cls, v: Any) -> Any:
        """Coerce dict-style options {label, description} to strings."""
        if not isinstance(v, list):
            return v
        out: list[str] = []
        for opt in v:
            if isinstance(opt, str):
                out.append(opt)
            elif isinstance(opt, dict):
                label = opt.get("label") or opt.get("title") or opt.get("name") or ""
                desc = opt.get("description") or opt.get("desc") or opt.get("detail") or ""
                if label and desc and label != desc:
                    out.append(f"{label}: {desc[:120]}")
                else:
                    out.append(str(label or desc or opt))
            else:
                out.append(str(opt))
        return out


class AskQuestionArgs(BaseModel):
    """Arguments for ask_question tool."""

    questions: list[QuestionItem] = Field(
        ...,
        description="List of questions/decisions to present to the user.",
    )


class AskQuestionTool(BaseTool):
    """Tool for agents to ask multiple-choice questions and request user decisions."""

    name = "ask_question"
    description = (
        "Ask the user one or more multiple-choice questions or decision prompts "
        "to clarify underspecified requirements, select architectural options, "
        "or resolve ambiguous decisions."
    )
    args_model = AskQuestionArgs

    def _run(self, questions: list[dict[str, Any] | QuestionItem], **kwargs: Any) -> str:
        """Execute the interactive question prompt."""
        if not questions:
            return "No questions provided."

        parsed_questions: list[QuestionItem] = []
        for q in questions:
            if isinstance(q, QuestionItem):
                parsed_questions.append(q)
            elif isinstance(q, dict):
                parsed_questions.append(QuestionItem(**q))

        # Check if running in headless / non-interactive environment
        is_headless = (
            os.environ.get("CI") == "true"
            or os.environ.get("SAGO_HEADLESS") == "1"
            or not os.isatty(0)
        )

        results: list[dict[str, Any]] = []

        for idx, q_item in enumerate(parsed_questions, start=1):
            q_text = q_item.question
            options = q_item.options

            if is_headless or not options:
                # Default selection
                selected = (
                    q_item.default_option
                    if q_item.default_option
                    else (options[0] if options else "Proceed with default implementation")
                )
                results.append(
                    {
                        "question": q_text,
                        "selected": selected,
                        "mode": "auto_default",
                    }
                )
                continue

            # In interactive CLI: present MCQ format
            print(f"\n[?] Question {idx}/{len(parsed_questions)}: {q_text}")
            for opt_idx, opt in enumerate(options, start=1):
                print(f"  [{opt_idx}] {opt}")

            default_val = q_item.default_option or options[0]
            try:
                raw_in = input(f"Select option (1-{len(options)}) [default: 1]: ").strip()
                if not raw_in:
                    selected = default_val
                elif raw_in.isdigit() and 1 <= int(raw_in) <= len(options):
                    selected = options[int(raw_in) - 1]
                else:
                    selected = raw_in  # Custom write-in
            except (EOFError, KeyboardInterrupt):
                selected = default_val

            results.append(
                {
                    "question": q_text,
                    "selected": selected,
                    "mode": "user_input",
                }
            )

        formatted_answers = []
        for r in results:
            formatted_answers.append(f"Q: {r['question']}\nSelected Answer: {r['selected']}")

        return "\n\n".join(formatted_answers)


def create_ask_question_tool() -> AskQuestionTool:
    """Factory function for AskQuestionTool."""
    return AskQuestionTool()
