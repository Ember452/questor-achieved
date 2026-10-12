"""Fanout：内核通知到多宿主的扇出（B-96 顺序 + B-01 强引用）。

单一 `AppServer._notify` callback 只够一条传输；M3b-3 起桌面 stdio 与网页 WS
并发时，同一个 run 的通知要同时进两条道。**每订阅者一个 `asyncio.Queue`**：

- 顺序保证（B-96）：`publish` 按调用顺序 `.put_nowait(...)`，queue FIFO，
  传输侧从自己的 queue 消费即有序；
- 隔离：慢订阅者不阻塞 publisher——队列无上限，M3 简单策略；M4 长跑引入背压
  时走 ADR-0025；
- 强引用（B-01）：Fanout 持 `list[Queue]` 引用，订阅者不用则显式 unsubscribe
  释放，不给 GC 留"半途订阅者被回收"的空档。

与传输层解耦：本模块不认识 WS / stdio / SSE；它只吐 `Notification` 对象，
每订阅者一条队列。
"""

from __future__ import annotations

import asyncio
import contextlib

from questor.serve.envelope import Notification


class Subscriber:
    """一个订阅者的队列句柄；`get()` 供传输层循环消费。"""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[Notification] = asyncio.Queue()

    async def get(self) -> Notification:
        return await self.queue.get()


class Fanout:
    """通知扇出中心：`subscribe()` 拿 Subscriber，`publish()` 遍历塞队列。"""

    def __init__(self) -> None:
        self._subs: list[Subscriber] = []

    def subscribe(self) -> Subscriber:
        sub = Subscriber()
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        # 幂等：重复 unsubscribe 或已移除不炸（B-01 强引用释放路径上多一道保护）
        with contextlib.suppress(ValueError):
            self._subs.remove(sub)

    def publish(self, notification: Notification) -> None:
        """按调用顺序把通知塞进每个订阅者的 queue（B-96）。

        同步接口：queue 无上限、put_nowait 不阻塞。传输侧协程 `await sub.get()`
        消费；若下游断线未 unsubscribe，queue 会一直 grow——M3 单机量级不担心，
        M4 长跑引入背压时走 ADR-0025。
        """
        for sub in self._subs:
            sub.queue.put_nowait(notification)

    def __len__(self) -> int:
        return len(self._subs)
