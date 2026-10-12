"""韧性层：零交付前才整体重试；交付过就不重放（B-84）。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

import pytest

from questor.prompts import system_assembly
from questor.providers.errors import NetworkError, QuotaExceededError, RateLimitError
from questor.providers.resilience import ResilientModel, backoff_delay
from questor.providers.spec import ModelCapabilities, WindowSource
from questor.schemas.llm import ModelRequest, StreamDelta, StreamEnd, StreamEvent

_CAPABILITIES = ModelCapabilities(
    context_window=32_000,
    max_output_tokens=8_000,
    supports_thinking=False,
    supports_prompt_cache=False,
    window_source=WindowSource.CONSERVATIVE,
)


class _ScriptedProvider:
    """按脚本逐次回应：每次一个事件列表，列表里遇到异常就地抛出。

    统一成"事件序列"这一个形状，才能表达"先交付、中途失败"——B-84 的判定点恰好在这。
    """

    def __init__(self, script: Sequence[list[StreamEvent | BaseException]]) -> None:
        self._script = list(script)
        self.calls = 0
        self.closed = False

    @property
    def capabilities(self) -> ModelCapabilities:
        return _CAPABILITIES

    def set_max_output_tokens(self, tokens: int) -> None:
        raise AssertionError("上限不得再写进客户端状态（B-08 改后的回归守卫）")

    async def aclose(self) -> None:
        self.closed = True

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        del request
        self.calls += 1
        for element in self._script[min(self.calls - 1, len(self._script) - 1)]:
            # 判定用 ``BaseException``：``asyncio.CancelledError`` 不是 ``Exception``，
            # 漏判会让取消被当成普通事件送上线（AGENTS §五 取消必须放行）
            if isinstance(element, BaseException):
                raise element
            yield element


def _request() -> ModelRequest:
    return ModelRequest(messages=[], prompt=system_assembly(), max_output_tokens=1000, tools=[])


def _sleeps() -> tuple[Callable[[float], Awaitable[None]], list[float]]:
    recorded: list[float] = []

    async def _sleep(seconds: float) -> None:
        recorded.append(seconds)

    return _sleep, recorded


def test_backoff_delay_prefers_endpoint_suggestion_when_larger() -> None:
    assert backoff_delay(0, base_s=0.5, max_s=8.0) == 0.5
    assert backoff_delay(3, base_s=0.5, max_s=8.0) == 4.0
    assert backoff_delay(9, base_s=0.5, max_s=8.0) == 8.0  # 封顶
    assert backoff_delay(0, base_s=0.5, retry_after_s=30.0) == 30.0
    assert backoff_delay(0, base_s=0.5, retry_after_s=0.1) == 0.5  # 本地指数兜底防空转


async def test_retries_only_until_first_event_is_delivered() -> None:
    provider = _ScriptedProvider(
        [[NetworkError("boom")], [StreamDelta(text="ok"), StreamEnd(stop_reason="end_turn")]]
    )
    sleep, sleeps = _sleeps()
    model = ResilientModel(provider, max_retries=2, sleep=sleep)

    events = [event async for event in model.stream(_request())]

    assert provider.calls == 2
    assert [type(event) for event in events] == [StreamDelta, StreamEnd]
    assert sleeps == [0.5]


async def test_never_replays_after_delivery() -> None:
    """B-84 的核心：已经吐出正文之后再失败，绝不重来——重放会让同一轮出现两份正文，
    而中断掉的工具结果本身可能已生效（overview §10"断流不重放"）。"""
    provider = _ScriptedProvider([[StreamDelta(text="半句"), NetworkError("mid")]])
    model = ResilientModel(provider, max_retries=3, sleep=_sleeps()[0])

    collected: list[object] = []
    with pytest.raises(NetworkError):
        async for event in model.stream(_request()):
            collected.append(event)

    assert [type(event) for event in collected] == [StreamDelta]
    assert provider.calls == 1


async def test_non_retryable_error_fails_immediately() -> None:
    """402/鉴权类错误重试只是烧预算：一次就停，并把原因留给上层。"""
    provider = _ScriptedProvider([[QuotaExceededError("Insufficient Balance", status=402)]])
    model = ResilientModel(provider, max_retries=3, sleep=_sleeps()[0])

    with pytest.raises(QuotaExceededError):
        async for _ in model.stream(_request()):
            pass

    assert provider.calls == 1


async def test_retry_budget_is_bounded() -> None:
    provider = _ScriptedProvider(
        [[NetworkError("1")], [NetworkError("2")], [NetworkError("3")], [NetworkError("4")]]
    )
    sleep, sleeps = _sleeps()
    model = ResilientModel(provider, max_retries=2, sleep=sleep)

    with pytest.raises(NetworkError):
        async for _ in model.stream(_request()):
            pass

    assert provider.calls == 3  # 首次 + 两次重试
    assert sleeps == [0.5, 1.0]


async def test_retry_after_is_honoured_between_attempts() -> None:
    provider = _ScriptedProvider(
        [[RateLimitError("slow", retry_after_s=12.0)], [StreamEnd(stop_reason="end_turn")]]
    )
    sleep, sleeps = _sleeps()
    model = ResilientModel(provider, max_retries=1, sleep=sleep)

    async for _ in model.stream(_request()):
        pass

    assert sleeps == [12.0]


async def test_cancelled_error_is_never_swallowed() -> None:
    """取消不是错误，不能被重试逻辑吃掉（AGENTS §五）。"""
    provider = _ScriptedProvider([[asyncio.CancelledError()], [StreamEnd(stop_reason="end_turn")]])
    model = ResilientModel(provider, max_retries=2, sleep=_sleeps()[0])

    with pytest.raises(asyncio.CancelledError):
        async for _ in model.stream(_request()):
            pass

    assert provider.calls == 1


async def test_lifecycle_and_capabilities_are_delegated() -> None:
    provider = _ScriptedProvider([[StreamEnd(stop_reason="end_turn")]])
    model = ResilientModel(provider, max_retries=0)

    await model.aclose()
    await model.aclose()  # 幂等：二次关闭不额外触碰端点

    assert provider.closed is True
    assert model.capabilities is _CAPABILITIES


def test_negative_max_retries_is_rejected() -> None:
    provider = _ScriptedProvider([[StreamEnd(stop_reason="end_turn")]])
    with pytest.raises(ValueError, match="不能为负数"):
        ResilientModel(provider, max_retries=-1)
