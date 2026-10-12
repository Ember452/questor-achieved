"""HTTP/SSE 传输管道：状态码分类、首事件超时与帧流（两个协议共用，策略只此一处）。

拆出理由：错误映射与超时策略若分散到各协议文件里，就会各修各的、必然漂移
（structure §4 的"测试定位困难/依赖纠缠"信号）。协议文件因此只负责
**请求体装配**与**帧→StreamEvent 翻译**两件事。

超时口径（AGENTS §五"所有 IO 有超时"）：
- 连接：``connect=30s``；
- 读：交给本模块的**间隔守卫**——首帧用 ``first_event_timeout_s``，后续帧用
  ``request_timeout_s``。httpx 的 read 超时设为 None，避免两处各持一个时钟互相抢跑。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx

from questor.providers.errors import (
    LLMTimeoutError,
    NetworkError,
    ProtocolError,
    classify_status,
    error_message_from_body,
    parse_retry_after,
)
from questor.providers.sse import SSEEvent, iter_sse

__all__ = ["CONNECT_TIMEOUT_S", "build_client", "open_sse_stream"]

#: 建立连接的上限；与"读多久没声音"是两件事，分开取值
CONNECT_TIMEOUT_S = 30.0


def build_client() -> httpx.AsyncClient:
    """创建异步客户端（read 超时由本模块的间隔守卫负责，见模块 docstring）。"""
    return httpx.AsyncClient(timeout=httpx.Timeout(None, connect=CONNECT_TIMEOUT_S))


async def open_sse_stream(
    client: httpx.AsyncClient,
    url: str,
    *,
    body: dict[str, Any],
    headers: dict[str, str],
    first_event_timeout_s: float,
    request_timeout_s: float,
) -> AsyncIterator[SSEEvent]:
    """POST 并返回 SSE 帧流；非 200 一律抛分类后的 :class:`LLMError` 家族。

    抛错时机都在"零帧交付"之前，因此调用方可以安全整体重试（B-84）；一旦开始交付帧，
    后续失败只会上抛、不会被任何一层重放。
    """
    try:
        async with client.stream("POST", url, json=body, headers=headers) as response:
            if response.status_code != 200:
                payload = await response.aread()
                raise classify_status(
                    response.status_code,
                    message=error_message_from_body(payload),
                    retry_after_s=parse_retry_after(response.headers.get("retry-after")),
                )
            async for frame in iter_sse(
                _gap_timed_lines(response.aiter_lines(), first_event_timeout_s, request_timeout_s)
            ):
                yield frame
    except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
        # httpx 自己的 ProtocolError（远端帧不合规）与我们的同名不同类，单独映一次
        if isinstance(exc, httpx.TimeoutException):
            raise LLMTimeoutError(f"模型端点超时：{exc}") from exc
        if isinstance(exc, httpx.ProtocolError):
            raise ProtocolError(f"模型端点 HTTP 帧不合规：{exc}") from exc
        raise NetworkError(f"模型端点网络失败：{exc}") from exc


async def _gap_timed_lines(
    lines: AsyncIterator[str], first_event_timeout_s: float, request_timeout_s: float
) -> AsyncIterator[str]:
    """逐行等待；超过对应预算没有新行即判超时（覆盖"连上了却永不出首事件"）。"""
    iterator = lines.__aiter__()
    first = True
    while True:
        budget = first_event_timeout_s if first else request_timeout_s
        try:
            line = await asyncio.wait_for(iterator.__anext__(), timeout=budget)
        except TimeoutError as exc:
            label = "首事件" if first else "后续事件"
            raise LLMTimeoutError(f"流式{label}超过 {budget:.0f}s 无产出") from exc
        except StopAsyncIteration:
            return
        except asyncio.CancelledError:
            raise  # 取消语义放行（AGENTS §五）
        first = False
        yield line
