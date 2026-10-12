"""ws —— WebSocket 传输（M3b-3，ADR-0022/0023：只落 WS，SSE 推到 M8）。

一条 ws 连接 = 一个 `Dispatcher` + 一个 `Fanout` 订阅：
- 上行：`websocket.receive_text` → `dispatcher.handle_line(text)`；响应行经 sink 写回；
- 下行：Fanout 的订阅队列 → `websocket.send_text`；由 `pump` 循环搬。

**stdout 洁净不适用本模块**（WS 没有 stdout；协议帧通过 send_text 逐条推），
但**通知顺序 = publish 顺序** 由 Fanout 保证（B-96），断线时 unsubscribe 释放订阅。

sink 里的 send_text 是 fire-and-forget task（B-01）：`sink_tasks` 强引用持有 +
done_callback 里 discard；否则任务被 GC 中途回收、异常静默。close 前 gather 一次
未完成的 send_text，尽力而为不吞新 cancel。

与 `stdio.run_stdio` 完全平级：都从同一个 `AppServer` 领方法表，都不带业务知识。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Coroutine

from starlette.websockets import WebSocket, WebSocketDisconnect

from questor.serve.app_server import AppServer
from questor.serve.dispatch import Dispatcher
from questor.serve.envelope import notification_line
from questor.serve.fanout import Fanout


async def _pump(sub_queue: asyncio.Queue, websocket: WebSocket) -> None:
    """从订阅队列取通知逐条 send_text；被 cancel 时干净退出（AGENTS §五放行 CancelledError）。"""
    try:
        while True:
            note = await sub_queue.get()
            await websocket.send_text(notification_line(note))
    except asyncio.CancelledError:
        raise
    except WebSocketDisconnect:
        return  # 客户端断开是正常终态


def make_ws_handler(
    app_server: AppServer, fanout: Fanout
) -> Callable[[WebSocket], Coroutine[None, None, None]]:
    """工厂：闭包持有 app_server + fanout，返回 starlette WebSocket endpoint。"""

    async def endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        dispatcher: Dispatcher = app_server.build_dispatcher()
        sub = fanout.subscribe()
        # B-01：sink 里的 send_text 是 fire-and-forget，需强引用持有并观察异常
        sink_tasks: set[asyncio.Task[None]] = set()

        def sink(line: str) -> None:
            task = asyncio.create_task(websocket.send_text(line))
            sink_tasks.add(task)
            task.add_done_callback(sink_tasks.discard)

        dispatcher.attach_sink(sink)
        pump_task = asyncio.create_task(_pump(sub.queue, websocket))
        try:
            while True:
                try:
                    text = await websocket.receive_text()
                except WebSocketDisconnect:
                    break
                await dispatcher.handle_line(text)
                await dispatcher.drain()  # 与 stdio 同节奏：单条帧完成再下一帧（M4 长跑改分段）
        finally:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump_task
            fanout.unsubscribe(sub)
            if sink_tasks:
                # 尽力把已排队的 send_text 走完；return_exceptions=True 避免客户端断开时
                # send 报错冒泡到本协程（断开已是正常终态）
                await asyncio.gather(*list(sink_tasks), return_exceptions=True)

    return endpoint
