"""stdio 传输：读 NDJSON 行 → 分发 → 写回一行一帧（桌面 sidecar 用，M3 的 WS/SSE 同表复用）。

**stdout 洁净**是这里唯一硬约束（protocol.md §1）：本模块只写协议帧，日志与诊断一律
走 stderr——混一行 banner 就会让对端把垃圾当响应解析。护栏见
`tests/unit/test_serve_stdio.py::test_only_protocol_frames_reach_stdout`。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TextIO

from questor.serve.dispatch import Dispatcher

__all__ = ["run_stdio", "write_line"]


async def run_stdio(
    dispatcher: Dispatcher, *, reader: asyncio.StreamReader, write: Callable[[str], None]
) -> None:
    """持续读行直到 EOF；输出全部经行级出口（响应与通知同一条道）。

    本期按"一行一完成"算：读完一帧就 `drain()` 等在飞任务。M3 接并发宿主时改成
    只等该请求自己的任务（否则一个长 run 会卡住后续帧）——那属传输层改动，
    不改方法表，所以不算接口后置。
    """
    dispatcher.attach_sink(write)
    while True:
        line = await reader.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        await dispatcher.handle_line(text)
        await dispatcher.drain()


def write_line(stream: TextIO) -> Callable[[str], None]:
    """给一个文本流做行写入器（刷新到位，sidecar 才不会有延迟可见性）。"""

    def _write(text: str) -> None:
        stream.write(text + "\n")
        stream.flush()

    return _write
