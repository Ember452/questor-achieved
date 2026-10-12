"""stdio 传输：读 NDJSON 行 → 分发 → 写回一行一帧（桌面 sidecar 用，与 WS/SSE 同表复用）。

**stdout 洁净**是这里唯一硬约束（protocol.md §1）：本模块只写协议帧，日志与诊断一律
走 stderr——混一行 banner 就会让对端把垃圾当响应解析。护栏见
`tests/integration/test_serve_stdio_host.py::test_stdio_stdout_only_protocol_frames`。

`run_stdio` 是入站循环（供注入 reader/write，单测可直接驱动）；`serve_stdio` 是完整宿主：
从同一个 `AppServer` 领方法表、订阅 `Fanout` 把 run 通知泵到同一出口，与 `ws.py` 完全平级
（同一契约、同一方法表，不为桌面开私有端点）。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import TextIO

from questor.serve.app_server import AppServer
from questor.serve.dispatch import Dispatcher
from questor.serve.envelope import notification_line

__all__ = ["run_stdio", "serve_stdio", "write_line"]


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


async def _pump_notifications(queue: asyncio.Queue, write: Callable[[str], None]) -> None:
    """从 Fanout 订阅队列搬通知到行出口；被 cancel 时干净退出（放行 CancelledError）。"""
    try:
        while True:
            note = await queue.get()
            write(notification_line(note))
    except asyncio.CancelledError:
        raise


async def serve_stdio(
    app_server: AppServer, *, reader: asyncio.StreamReader, write: Callable[[str], None]
) -> None:
    """完整 stdio 宿主：入站请求走 dispatcher，run 通知走同一 Fanout 订阅→同一出口。

    与 WS 端点同构：`build_dispatcher()` 不带业务知识、方法表单一真相；订阅 Fanout 使
    长命 run 的 `delta`/`run/status`/`evidence/reported` 与请求响应同走 stdout（通知
    顺序即 publish 顺序，B-96）。EOF 后回收泵任务并退订（不泄漏订阅）。
    """
    dispatcher = app_server.build_dispatcher()
    sub = app_server.fanout.subscribe()
    pump = asyncio.create_task(_pump_notifications(sub.queue, write))
    try:
        await run_stdio(dispatcher, reader=reader, write=write)
    finally:
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump
        app_server.fanout.unsubscribe(sub)
