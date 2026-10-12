"""对抗：Fanout 顺序性 + 订阅者隔离（B-96）。

publish 按调用顺序塞 queue；每个订阅者独立消费，A 慢不阻塞 B。若破坏顺序则本文件红。
"""

from __future__ import annotations

import asyncio

import pytest

from questor.serve.envelope import Notification
from questor.serve.fanout import Fanout


@pytest.mark.asyncio
async def test_publish_preserves_per_subscriber_order() -> None:
    fanout = Fanout()
    sub_a = fanout.subscribe()
    sub_b = fanout.subscribe()
    for i in range(5):
        fanout.publish(Notification("delta", {"text": f"t{i}"}))
    collected_a = [
        (await asyncio.wait_for(sub_a.queue.get(), timeout=1)).params["text"] for _ in range(5)
    ]
    collected_b = [
        (await asyncio.wait_for(sub_b.queue.get(), timeout=1)).params["text"] for _ in range(5)
    ]
    expected = ["t0", "t1", "t2", "t3", "t4"]
    assert collected_a == expected
    assert collected_b == expected


@pytest.mark.asyncio
async def test_slow_subscriber_does_not_block_publisher() -> None:
    """B-96 的隔离面：一个订阅者不 get，publish 仍非阻塞走完其他订阅者。"""
    fanout = Fanout()
    _sub_slow = fanout.subscribe()  # 不消费
    sub_fast = fanout.subscribe()
    # 若 publish 会因 slow 阻塞，本 await 会超时
    await asyncio.wait_for(
        asyncio.to_thread(
            lambda: [fanout.publish(Notification("run/status", {"status": s})) for s in "abcd"]
        ),
        timeout=1.0,
    )
    for expected in "abcd":
        note = await asyncio.wait_for(sub_fast.queue.get(), timeout=1.0)
        assert note.params["status"] == expected


def test_unsubscribe_is_idempotent() -> None:
    fanout = Fanout()
    sub = fanout.subscribe()
    fanout.unsubscribe(sub)
    fanout.unsubscribe(sub)  # 第二次静默通过
    assert len(fanout) == 0
    fanout.publish(Notification("delta", {"text": "x"}))  # 无订阅者也不炸
