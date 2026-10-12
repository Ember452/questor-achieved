"""SSE 帧解析（providers 流式底座）。失败场景先枚举，再对着写断言。"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from questor.providers.errors import ProtocolError
from questor.providers.sse import SSEEvent, iter_sse


async def _lines(*items: str) -> AsyncIterator[str]:
    for item in items:
        yield item


async def _collect(*items: str, max_line_chars: int = 8 * 1024 * 1024) -> list[SSEEvent]:
    return [frame async for frame in iter_sse(_lines(*items), max_line_chars=max_line_chars)]


async def test_event_and_data_pair_into_one_frame() -> None:
    frames = await _collect("event: message_start", 'data: {"type":"x"}', "")
    assert frames == [SSEEvent(event="message_start", data='{"type":"x"}')]


async def test_multiline_data_joins_with_newline() -> None:
    """SSE 的 `data:` 分行必须拼回一个载荷（多行 JSON 与 pretty-print 端点都走这条路）。"""
    frames = await _collect("data: {", 'data: "a": 1}', "")
    assert frames[0].data == '{\n"a": 1}'


async def test_comment_and_blank_lines_are_ignored_and_do_not_emit() -> None:
    """心跳 `:` 行不产出帧——把它当数据会让上层 JSON 解析炸掉。"""
    frames = await _collect(": keep-alive", "")
    assert frames == []


async def test_frame_without_trailing_blank_line_is_flushed_at_eof() -> None:
    """OpenAI 兼容端点常在 `data: [DONE]` 后直接断连；严格 SSE 会丢弃它，等于丢终局信号。"""
    frames = await _collect("data: [DONE]")
    assert frames == [SSEEvent(event=None, data="[DONE]")]


async def test_crlf_line_ending_is_normalized() -> None:
    """端点用 CRLF 时，`\\r` 留在值里会让 `data == "[DONE]"` 判等失败（实测各家不一）。"""
    frames = await _collect("data: [DONE]\r", "")
    assert frames[0].data == "[DONE]"


async def test_oversized_single_line_raises_protocol_error() -> None:
    """一行无限增长必须挡住，否则端点异常时会把内存吃光。"""
    with pytest.raises(ProtocolError, match="超过上限"):
        await _collect("data: " + "x" * 200, max_line_chars=64)


async def test_id_and_retry_fields_are_tolerated() -> None:
    """本层不消费重连语义，但也不能因为见到它们就报错。"""
    frames = await _collect("id: 7", "retry: 1000", "data: hi", "")
    assert frames == [SSEEvent(event=None, data="hi")]
