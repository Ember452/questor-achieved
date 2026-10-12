"""测试基建：假模型端点（httpx MockTransport 上的 SSE 回放与可编程故障）。

为什么需要它：providers 的 wire 层必须能被确定性地测试——真实端点的响应形状
不可控（而且本轮实测时账户欠费，一次 200 都拿不到）。本模块按
`docs/notes/2026-10-12-m23-wire-probe.md` 记下的**真实形状**造响应：
402 带误导性 body、404 空 body、流中 error 帧、断流、usage-only 尾帧。

生产代码禁止 import 本模块（`tests/architecture/test_dependency_matrix.py` 强制）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterable

import httpx

__all__ = ["FakeEndpoint", "broken_stream_response", "error_response", "sse_response", "sse_text"]


class FakeEndpoint:
    """记录请求并按脚本回应；用法：`endpoint.responses.append(...)` 或用 handler 覆盖。"""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict[str, object]] = []
        self.responses: list[httpx.Response] = []
        self._handler = handler

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        raw = request.content.decode("utf-8", errors="replace")
        try:
            self.bodies.append(json.loads(raw) if raw else {})
        except ValueError:
            self.bodies.append({"__raw__": raw})
        if self._handler is not None:
            return self._handler(request)
        if not self.responses:
            raise AssertionError("FakeEndpoint 的响应脚本已用尽（不静默复用最后一帧）")
        return self.responses.pop(0)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


def sse_text(frames: Iterable[tuple[str | None, str]]) -> bytes:
    """把 (event, data) 序列拼成 SSE 原文；``event=None`` 表示只有 ``data:`` 行。"""
    chunks: list[str] = []
    for event, data in frames:
        if event is not None:
            chunks.append(f"event: {event}\n")
        chunks.append(f"data: {data}\n\n")
    return "".join(chunks).encode("utf-8")


def sse_response(
    frames: Iterable[tuple[str | None, str]], *, trailing_blank: bool = True
) -> httpx.Response:
    """一次性 SSE 响应。``trailing_blank=False`` 复刻"[DONE] 后直接断连"的形态。"""
    payload = sse_text(frames)
    if not trailing_blank:
        payload = payload.rstrip(b"\n")
    return httpx.Response(
        200,
        content=payload,
        headers={"content-type": "text/event-stream"},
    )


def error_response(
    status: int, *, body: bytes = b"", headers: dict[str, str] | None = None
) -> httpx.Response:
    """错误响应；body 缺省为空（实测 404 就是 `content-length: 0`）。"""
    return httpx.Response(status, content=body, headers=headers or {})


class _ScriptedStream(httpx.AsyncByteStream):
    """按块产出，产出完后抛指定异常（模拟"流中途断"）。"""

    def __init__(self, chunks: list[bytes], error: Exception | None = None) -> None:
        self._chunks = chunks
        self._error = error

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk
        if self._error is not None:
            raise self._error


def broken_stream_response(chunks: list[bytes], error: Exception) -> httpx.Response:
    """先交付若干块、随后连接失败——B-84 的判定点就在这条路径上。"""
    return httpx.Response(
        200,
        stream=_ScriptedStream(chunks, error),
        headers={"content-type": "text/event-stream"},
    )
