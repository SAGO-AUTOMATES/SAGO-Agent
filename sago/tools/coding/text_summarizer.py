"""Text Summarizer Tool - Summarize text content."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.coding.text_summarizer")


class TextSummarizerArgs(BaseModel):
    """Arguments for text summarization."""

    operation: str = Field(description="Operation: summarize, extract-keywords, extract-entities")
    text: str = Field(description="Text to summarize")
    max_sentences: int = Field(default=5, description="Maximum sentences in summary")
    language: str = Field(default="en", description="Language code")


class TextSummarizer(BaseTool):
    """Tool for summarizing and extracting information from text."""

    name: str = "text_summarizer"
    description: str = "Summarize text, extract keywords and entities. Supports multiple languages."
    args_model: type[BaseModel] = TextSummarizerArgs

    def _run(
        self,
        operation: str,
        text: str,
        max_sentences: int = 5,
        language: str = "en",
        **kwargs: Any,
    ) -> str:
        """Execute text summarization."""
        try:
            if operation == "summarize":
                return self._summarize(text, max_sentences)
            elif operation == "extract-keywords":
                return self._extract_keywords(text)
            elif operation == "extract-entities":
                return self._extract_entities(text)
            else:
                return f"Error: Invalid operation '{operation}'"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    def _summarize(self, text: str, max_sentences: int) -> str:
        """Simple extractive summarization."""
        # Split into sentences
        sentences = []
        for line in text.split("\n"):
            line = line.strip()
            if line and len(line) > 20:
                sentences.append(line)

        if not sentences:
            return "No content to summarize"

        # Score sentences by position and word frequency
        words = text.lower().split()
        word_freq: dict[str, int] = {}
        for word in words:
            if len(word) > 3:
                word_freq[word] = word_freq.get(word, 0) + 1

        scored = []
        for i, sentence in enumerate(sentences):
            score = 0
            # Position score (first sentences more important)
            if i < 3:
                score += 3 - i
            # Word frequency score
            for word in sentence.lower().split():
                if word in word_freq:
                    score += word_freq[word]
            scored.append((score, i, sentence))

        # Get top sentences
        scored.sort(key=lambda x: x[0], reverse=True)
        top = sorted(scored[:max_sentences], key=lambda x: x[1])

        summary = " ".join(s[2] for s in top)
        return f"Summary ({len(top)} sentences):\n{summary}"

    def _extract_keywords(self, text: str) -> str:
        """Extract keywords from text."""
        words = text.lower().split()
        word_freq: dict[str, int] = {}

        # Common stop words
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
            "not",
            "no",
        }

        for word in words:
            word = word.strip(".,!?;:'\"()[]{}")
            if len(word) > 3 and word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1

        # Get top keywords
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        top_keywords = sorted_words[:20]

        if not top_keywords:
            return "No keywords found"

        result_parts = ["Keywords:"]
        for word, freq in top_keywords:
            result_parts.append(f"  - {word} (x{freq})")

        return "\n".join(result_parts)

    def _extract_entities(self, text: str) -> str:
        """Extract simple entities (names, dates, emails, urls)."""
        import re

        entities: dict[str, list[str]] = {
            "emails": [],
            "urls": [],
            "dates": [],
            "phone_numbers": [],
        }

        # Email pattern
        emails = re.findall(r"[\w.-]+@[\w.-]+\.\w+", text)
        entities["emails"] = list(set(emails))

        # URL pattern
        urls = re.findall(r"https?://\S+", text)
        entities["urls"] = list(set(urls))

        # Date pattern (simple)
        dates = re.findall(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", text)
        entities["dates"] = list(set(dates))

        # Phone pattern
        phones = re.findall(r"[\+]?[(]?\d{3}[)]?[-\s.]?\d{3}[-\s.]?\d{4}", text)
        entities["phone_numbers"] = list(set(phones))

        result_parts = ["Entities found:"]
        for entity_type, values in entities.items():
            if values:
                result_parts.append(f"\n{entity_type.upper()}:")
                for v in values[:5]:
                    result_parts.append(f"  - {v}")

        if len(result_parts) == 1:
            return "No entities found"

        return "\n".join(result_parts)


def get_tool() -> type[TextSummarizer]:
    """Get the tool class."""
    return TextSummarizer
