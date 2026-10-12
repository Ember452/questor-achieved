"""插话收件箱：进程内 asyncio.Queue + 会话正文 `habena.held_work` 双写。

submit 前先落正文再入队（B-45 的延伸：gate 类消息先持久化定序），崩溃重启时
`preload_from_view` 从 `view.held_work` 重建队列——用户按过的按钮不会因内核
重启而静默丢失（overview §10"无终局证据的执行变成待查阻塞项，不默认成功"）。

幂等：同 `client_id` 提交两次只入队一次（B-63）；`expected_turn_id` 交给调用方
（app_server handler）判，Inbox 本身不管 turn 匹配——它是传输层的责任。
"""

from __future__ import annotations

import asyncio

from questor.gesta.writer import ThreadWriter
from questor.schemas.habena import SteerMessage


class HabenaInbox:
    """一个线程的插话队列。engine 在 iteration 起点 `await inbox.drain()` 消费。"""

    def __init__(self, writer: ThreadWriter) -> None:
        self._writer = writer
        self._queue: asyncio.Queue[SteerMessage] = asyncio.Queue()
        self._seen: set[str] = set()

    def preload_from_view(self, messages: tuple[SteerMessage, ...]) -> None:
        """重启时从 ThreadView 的 held_work 投影重建队列（B-65 的 rehold）。"""
        for msg in messages:
            if msg.client_id in self._seen:
                continue
            self._seen.add(msg.client_id)
            self._queue.put_nowait(msg)

    async def submit(self, msg: SteerMessage) -> bool:
        """落正文入队；同 `client_id` 已见则幂等返回 False（B-63）。"""
        if msg.client_id in self._seen:
            return False
        self._seen.add(msg.client_id)
        # 先落盘再入队：崩溃时盘上已有，重启 preload 拿得回来（B-45 同族）
        await asyncio.to_thread(self._writer.add_held_work, msg)
        await self._queue.put(msg)
        return True

    async def drain(self) -> list[SteerMessage]:
        """取空当前队列；返回按入队顺序的列表（供 engine 一次性消费）。"""
        out: list[SteerMessage] = []
        while True:
            try:
                out.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out

    def forget(self, client_id: str) -> None:
        """从幂等表移除一个 client_id（供 turn/dequeue 允许该消息重新提交）。"""
        self._seen.discard(client_id)

    def __len__(self) -> int:
        return self._queue.qsize()
