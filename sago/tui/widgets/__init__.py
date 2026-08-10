"""TUI widgets for Sago."""

from __future__ import annotations

from textual.widgets import Static


class Spinner(Static):
    """Animated spinner widget."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, text: str = "Thinking", **kwargs) -> None:
        super().__init__(**kwargs)
        self.text = text
        self.frame = 0

    def render(self) -> str:
        return f"{self.FRAMES[self.frame]} {self.text}"

    def advance(self) -> None:
        self.frame = (self.frame + 1) % len(self.FRAMES)
        self.refresh()
