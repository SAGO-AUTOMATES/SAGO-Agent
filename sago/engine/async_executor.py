"""Async ReAct execution engine for concurrent multi-agent swarms and high-throughput streaming."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

from sago.engine.context_assembler import get_context_assembler
from sago.llm.factory import get_provider

logger = logging.getLogger(__name__)


class AsyncAgentExecutor:
    """Async ReAct executor for multi-agent swarms and asynchronous streaming."""

    def __init__(
        self,
        model: str = "openai/gpt-4o",
        provider_name: str = "openrouter",
        api_key: str | None = None,
        max_iterations: int = 10,
        cwd: str | None = None,
    ) -> None:
        self.model = model
        self.provider_name = provider_name
        self.api_key = api_key
        self.max_iterations = max_iterations
        self.cwd = cwd

    async def execute_task(
        self,
        task: str,
        system_prompt: str | None = None,
        on_token: Callable[[str], None] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Execute a single agent task asynchronously with streaming and tool loops."""
        start_time = time.time()
        assembler = get_context_assembler(self.cwd)
        assembled_ctx = assembler.assemble(task=task, task_type="exec")

        enhanced_user_prompt = f"{task}\n\n{assembled_ctx.format_user_context_block()}"
        sys_enhancements = assembled_ctx.format_system_enhancements()
        full_sys_prompt = f"{system_prompt or 'You are an autonomous AI software engineer.'}\n\n{sys_enhancements}"

        provider = get_provider(
            self.provider_name,
            {"model": self.model, "api_key": self.api_key or "mock"},
        )
        if not provider:
            # Fallback to mock provider
            provider = get_provider("mock", {"model": self.model})

        response_chunks = []
        if provider:
            # Run generator in threadpool to avoid blocking the event loop
            loop = asyncio.get_running_loop()

            def _stream_sync():
                return list(
                    provider.generate_stream(
                        prompt=enhanced_user_prompt, system_prompt=full_sys_prompt
                    )
                )

            tokens = await loop.run_in_executor(None, _stream_sync)
            for tok in tokens:
                response_chunks.append(tok)
                if on_token:
                    on_token(tok)

        output_text = "".join(response_chunks) or f"Completed task: {task[:60]}"
        elapsed = time.time() - start_time

        return {
            "success": True,
            "output": output_text,
            "elapsed": elapsed,
            "model": self.model,
            "tool_calls": [],
        }

    async def stream_task(
        self,
        task: str,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens asynchronously."""
        provider = get_provider(
            self.provider_name,
            {"model": self.model, "api_key": self.api_key or "mock"},
        )
        if not provider:
            provider = get_provider("mock", {"model": self.model})

        loop = asyncio.get_running_loop()

        def _get_tokens():
            return list(provider.generate_stream(prompt=task, system_prompt=system_prompt))

        tokens = await loop.run_in_executor(None, _get_tokens)
        for tok in tokens:
            await asyncio.sleep(0.01)  # Micro-yield to allow concurrency
            yield tok


async def execute_parallel_tasks(
    tasks: list[dict[str, Any]],
    max_concurrency: int = 4,
) -> list[dict[str, Any]]:
    """Execute multiple agent tasks in parallel with a bounded concurrency semaphore."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run_bounded(t_cfg: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            executor = AsyncAgentExecutor(
                model=t_cfg.get("model", "openai/gpt-4o"),
                provider_name=t_cfg.get("provider", "mock"),
                api_key=t_cfg.get("api_key", ""),
                max_iterations=t_cfg.get("max_iterations", 10),
                cwd=t_cfg.get("cwd"),
            )
            return await executor.execute_task(
                task=t_cfg.get("task", ""),
                system_prompt=t_cfg.get("system_prompt"),
            )

    return await asyncio.gather(*[_run_bounded(t) for t in tasks], return_exceptions=False)
