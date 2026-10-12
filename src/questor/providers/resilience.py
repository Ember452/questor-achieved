"""调用韧性：只在"零交付"时整体重试；交付过任何事件就绝不重放（B-84）。

判据来自流式语义本身，不是保守偏好：一旦正文/工具调用已经吐给消费方，重放就是
"同一轮里出现两份真相"——被中断的工具结果可能未知（overview §10 的"断流不重放"），
整轮重来会写出重复内容。所以这里的重试窗口只有一格：**首帧之前的失败**。

退避不掺随机抖动：本项目是单机单用户的工作站，不构成惊群；两个时钟（本地指数与
`retry-after`）取较大者即可，抖动只会让测试与真实行为分叉。

# Reimplements FlowCoder@flowcoder client/resilience.py 的设计决定 — pitfalls: B-84
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol as TypingProtocol

from questor.providers.errors import LLMError
from questor.providers.spec import ModelCapabilities
from questor.schemas.llm import ModelRequest, StreamEvent

__all__ = ["ResilientModel", "backoff_delay", "DEFAULT_BASE_BACKOFF_S", "DEFAULT_MAX_BACKOFF_S"]

DEFAULT_BASE_BACKOFF_S = 0.5
DEFAULT_MAX_BACKOFF_S = 8.0


def backoff_delay(
    attempt: int,
    *,
    base_s: float = DEFAULT_BASE_BACKOFF_S,
    max_s: float = DEFAULT_MAX_BACKOFF_S,
    retry_after_s: float | None = None,
) -> float:
    """第 ``attempt`` 次重试前的等待（attempt 从 0 起）。

    ``retry_after_s`` 是端点的权威建议，取两者较大：本地指数保证"建议为 0 时不空转"，
    建议值保证"端点说要等 30s 就别 0.5s 后去撞"。
    """
    exponential = min(max_s, base_s * (2**attempt))
    if retry_after_s is None:
        return exponential
    return max(exponential, retry_after_s)


class _StreamPort(TypingProtocol):
    """被包裹的 provider 形状（与 :class:`questor.engine.model.ModelPort` 结构一致）。"""

    @property
    def capabilities(self) -> ModelCapabilities: ...

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]: ...

    async def aclose(self) -> None: ...


class ResilientModel:
    """装饰器：限重试 + 生命周期透传，对消费方（engine/context）完全透明。"""

    def __init__(
        self,
        inner: _StreamPort,
        *,
        max_retries: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries 不能为负数")
        self._inner = inner
        self._max_retries = max_retries
        self._sleep = sleep

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._inner.capabilities

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        delivered = False
        for attempt in range(self._max_retries + 1):
            try:
                async for event in self._inner.stream(request):
                    delivered = True
                    yield event
                return
            except asyncio.CancelledError:
                raise  # 取消语义放行（AGENTS §五）
            except LLMError as exc:
                # 已经交付过事件、错误不可重试、或重试预算用完——三条里任一命中都直接上抛
                if delivered or not exc.retryable or attempt >= self._max_retries:
                    raise
                retry_after = getattr(exc, "retry_after_s", None)
                await self._sleep(backoff_delay(attempt, retry_after_s=retry_after))
