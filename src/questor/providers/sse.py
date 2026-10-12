"""SSE（Server-Sent Events）帧解析——providers 的流式底座。

只处理两件事：**字段归属**（``event:`` / ``data:`` / ``:`` 注释 / 多行 data 以 ``\\n`` 拼接）
与**帧边界**（空行结束一帧）。协议语义（哪个事件是正文增量、哪个是工具分片）留在各协议里。

两处刻意的取舍：

- 结尾无空行的残帧在流 EOF 时**冲刷**（严格 SSE 应丢弃）。理由：OpenAI 兼容端点的最后一个
  ``data: [DONE]`` 常常不带空行就断连，丢弃等于丢终局信号；本模块只在 EOF 处冲刷，不在
  中途猜。
- 单行长度有上限（``max_line_chars``），超限即抛 :class:`ProtocolError`——防端点异常时
  一行无限增长吃光内存（与 protocol.md §1 的行缓冲上限同源）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from questor.providers.errors import ProtocolError

__all__ = ["SSEEvent", "MAX_SSE_LINE_CHARS", "iter_sse"]

#: 单行上限：远大于正常事件帧，但挡住"一行无限长"的失败形态
MAX_SSE_LINE_CHARS = 8 * 1024 * 1024


@dataclass(frozen=True)
class SSEEvent:
    """一个 SSE 帧：``event`` 为 ``event:`` 字段（OpenAI 风格常为 None），``data`` 为拼接后的
    ``data:`` 载荷。
    """

    event: str | None
    data: str


async def iter_sse(
    lines: AsyncIterator[str], *, max_line_chars: int = MAX_SSE_LINE_CHARS
) -> AsyncIterator[SSEEvent]:
    """把行流折成帧流。空行结束一帧；注释行与无字段行忽略。"""
    event: str | None = None
    data_parts: list[str] = []
    has_fields = False

    async for raw in lines:
        if len(raw) > max_line_chars:
            raise ProtocolError(f"SSE 单行超过上限 {max_line_chars} 字符")
        line = raw.rstrip("\r")
        if not line:
            if has_fields:
                yield SSEEvent(event=event, data="\n".join(data_parts))
            event, data_parts, has_fields = None, [], False
            continue
        if line.startswith(":"):
            continue  # 注释/心跳
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event = value
            has_fields = True
        elif field == "data":
            data_parts.append(value)
            has_fields = True
        # id:/retry: 字段本层不消费（无重连语义在 providers 里），忽略但不报错

    if has_fields:
        yield SSEEvent(event=event, data="\n".join(data_parts))
