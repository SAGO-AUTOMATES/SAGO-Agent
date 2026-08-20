"""Browser Automation Tool - Headless browser for web interaction, screenshots, and scraping.

Auto-installs Playwright + Chromium if not available.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult
from sago.tools.ensure_dep import ensure_binary, ensure_pip_package, is_available

_BROWSER_TIMEOUT = 30


class BrowserArgs(BaseModel):
    """Arguments for browser automation."""

    action: str = Field(
        ...,
        description=(
            "Browser action: "
            "screenshot, navigate, evaluate, get_text, get_links, "
            "click, fill, wait_for, pdf, title, url, content"
        ),
    )
    url: str = Field(default="", description="Target URL for navigation/screenshot")
    selector: str = Field(default="", description="CSS selector for click/fill/wait_for")
    value: str = Field(default="", description="Value for fill action or JS for evaluate")
    viewport_width: int = Field(default=1280, description="Browser viewport width")
    viewport_height: int = Field(default=720, description="Browser viewport height")
    timeout: int = Field(default=_BROWSER_TIMEOUT, description="Action timeout in seconds")
    output_path: str = Field(default="", description="Path to save screenshot/PDF")
    wait_until: str = Field(
        default="networkidle",
        description="Wait condition: load, domcontentloaded, networkidle",
    )
    auto_install: bool = Field(default=True, description="Auto-install Playwright if missing")


class BrowserTool(BaseTool):
    """Headless browser automation using Playwright (if available) or Chromium."""

    name: str = "browser"
    description: str = (
        "Headless browser automation: take screenshots, navigate pages, extract text/links, "
        "click elements, fill forms, execute JavaScript, generate PDFs. "
        "Auto-installs Playwright + Chromium if not available."
    )
    category: ToolCategory = ToolCategory.WEB
    args_model: type[BaseModel] | None = BrowserArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(**kwargs)
        return result.output

    def execute(
        self,
        action: str,
        url: str = "",
        selector: str = "",
        value: str = "",
        viewport_width: int = 1280,
        viewport_height: int = 720,
        timeout: int = _BROWSER_TIMEOUT,
        output_path: str = "",
        wait_until: str = "networkidle",
        auto_install: bool = True,
        **extra: Any,
    ) -> ToolResult:
        act = (action or "").strip().lower()

        # Ensure Playwright is available
        pw_available = False
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401

            pw_available = True
        except ImportError:
            if auto_install:
                ok, msg = ensure_pip_package("playwright")
                if ok:
                    # Also install chromium browser
                    ok2, msg2 = ensure_binary("chromium", auto_install=False)
                    try:
                        subprocess.run(
                            [
                                __import__("sys").executable,
                                "-m",
                                "playwright",
                                "install",
                                "chromium",
                            ],
                            capture_output=True,
                            timeout=180,
                        )
                    except Exception:
                        pass
                    try:
                        from playwright.sync_api import sync_playwright  # noqa: F401

                        pw_available = True
                    except ImportError:
                        pass

        if pw_available:
            try:
                return self._playwright_action(
                    act,
                    url,
                    selector,
                    value,
                    viewport_width,
                    viewport_height,
                    timeout,
                    output_path,
                    wait_until,
                )
            except Exception:
                pass

        # Fallback: Chromium CLI
        return self._chromium_fallback(act, url, output_path, timeout)

    def _playwright_action(
        self,
        action: str,
        url: str,
        selector: str,
        value: str,
        width: int,
        height: int,
        timeout: int,
        output_path: str,
        wait_until: str,
    ) -> ToolResult:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})

            try:
                if action == "navigate":
                    page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    return ToolResult(
                        output=f"Navigated to {url}\nTitle: {page.title()}",
                        success=True,
                        metadata={"url": page.url, "title": page.title()},
                    )

                elif action == "screenshot":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    path = output_path or tempfile.mktemp(suffix=".png", prefix="sago_browser_")
                    page.screenshot(path=path, full_page=True)
                    return ToolResult(
                        output=f"Screenshot saved to {path}",
                        success=True,
                        metadata={"path": path, "url": page.url, "title": page.title()},
                    )

                elif action == "get_text":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    text = page.inner_text("body") if not selector else page.inner_text(selector)
                    return ToolResult(
                        output=text[:50000],
                        success=True,
                        metadata={"url": page.url, "char_count": len(text)},
                    )

                elif action == "get_links":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    links = page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => ({text: e.innerText.trim(), href: e.href})).filter(l => l.text)",
                    )
                    return ToolResult(
                        output=json.dumps(links[:200], indent=2),
                        success=True,
                        metadata={"url": page.url, "link_count": len(links)},
                    )

                elif action == "content":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    html = page.content()
                    return ToolResult(
                        output=html[:100000],
                        success=True,
                        metadata={"url": page.url, "html_length": len(html)},
                    )

                elif action == "title":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    return ToolResult(output=page.title(), success=True, metadata={"url": page.url})

                elif action == "url":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    return ToolResult(output=page.url, success=True, metadata={"url": page.url})

                elif action == "evaluate":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    result = page.evaluate(value)
                    return ToolResult(
                        output=json.dumps(result, indent=2, default=str)
                        if not isinstance(result, str)
                        else result,
                        success=True,
                        metadata={"url": page.url},
                    )

                elif action == "click":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    page.click(selector, timeout=timeout * 1000)
                    page.wait_for_load_state(wait_until, timeout=timeout * 1000)
                    return ToolResult(
                        output=f"Clicked '{selector}'\nNew URL: {page.url}\nTitle: {page.title()}",
                        success=True,
                        metadata={"url": page.url, "selector": selector},
                    )

                elif action == "fill":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    page.fill(selector, value, timeout=timeout * 1000)
                    return ToolResult(
                        output=f"Filled '{selector}'",
                        success=True,
                        metadata={"url": page.url, "selector": selector},
                    )

                elif action == "wait_for":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    page.wait_for_selector(selector, timeout=timeout * 1000)
                    return ToolResult(
                        output=f"Selector '{selector}' found",
                        success=True,
                        metadata={"url": page.url},
                    )

                elif action == "pdf":
                    if url:
                        page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
                    path = output_path or tempfile.mktemp(suffix=".pdf", prefix="sago_browser_")
                    page.pdf(path=path)
                    return ToolResult(
                        output=f"PDF saved to {path}",
                        success=True,
                        metadata={"path": path, "url": page.url},
                    )

                else:
                    return ToolResult(
                        output=f"Unknown action: '{action}'. Valid: screenshot, navigate, evaluate, get_text, get_links, click, fill, wait_for, pdf, title, url, content",
                        success=False,
                        error="unknown_action",
                    )

            finally:
                browser.close()

    def _chromium_fallback(
        self, action: str, url: str, output_path: str, timeout: int
    ) -> ToolResult:
        """Fallback using chromium CLI for basic screenshot/PDF."""
        if action not in ("screenshot", "pdf"):
            return ToolResult(
                output=(
                    "Playwright not available and only screenshot/pdf supported via CLI fallback.\n"
                    "Auto-installing Playwright...\n"
                    "Run: pip install playwright && playwright install chromium"
                ),
                success=False,
                error="playwright_not_installed",
            )

        for binary in ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"]:
            if is_available(binary):
                try:
                    if action == "screenshot":
                        path = output_path or tempfile.mktemp(suffix=".png", prefix="sago_browser_")
                        cmd = [
                            binary,
                            "--headless",
                            "--disable-gpu",
                            f"--screenshot={path}",
                            f"--window-size={1280},{720}",
                            "--no-sandbox",
                            url,
                        ]
                        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                        if proc.returncode == 0 and Path(path).exists():
                            return ToolResult(
                                output=f"Screenshot saved to {path}",
                                success=True,
                                metadata={"path": path},
                            )
                    elif action == "pdf":
                        path = output_path or tempfile.mktemp(suffix=".pdf", prefix="sago_browser_")
                        cmd = [
                            binary,
                            "--headless",
                            "--disable-gpu",
                            f"--print-to-pdf={path}",
                            "--no-sandbox",
                            url,
                        ]
                        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                        if proc.returncode == 0 and Path(path).exists():
                            return ToolResult(
                                output=f"PDF saved to {path}", success=True, metadata={"path": path}
                            )
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue

        return ToolResult(
            output="No browser found. Install: pip install playwright && playwright install chromium",
            success=False,
            error="no_browser_available",
        )


def get_tool() -> type[BrowserTool]:
    """Get the tool class."""
    return BrowserTool
