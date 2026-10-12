"""stdio 宿主集成（桌面 sidecar 的地基）：serve_stdio 的 stdout 洁净、方法表同源、通知泵。

不测真实 run（engine 走 turn/start 需要 model），只锁 sidecar 传输的三条契约：
① stdout 每行都是合法协议帧（日志绝不来这）；② initialize.methods 与 AppServer 方法表
逐项一致（不为桌面开第二套契约，overview §8）；③ run 期经 Fanout publish 的通知与响应
同走一个 stdout 出口、顺序即 publish 顺序（B-96）。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import pytest

from questor.schemas.model import PermissionMode
from questor.serve.app_server import AppServer
from questor.serve.envelope import Notification
from questor.serve.stdio import serve_stdio
from questor.testenv.fake_home import fake_home


def _no_engine(thread_id: str, mode: PermissionMode) -> Any:
    raise AssertionError("本测试不起引擎")


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def _frame(method: str, params: dict[str, Any], req_id: str = "1") -> bytes:
    return (json.dumps({"id": req_id, "method": method, "params": params}) + "\n").encode()


@pytest.mark.asyncio
async def test_stdio_stdout_only_protocol_frames(tmp_path: Any) -> None:
    server = AppServer(create_engine=_no_engine, default_workspace_id="ws-1")
    reader = asyncio.StreamReader()
    reader.feed_data(_frame("initialize", {"protocol_version": "qst-app-server/v0.1"}))
    reader.feed_data(_frame("thread/list", {}, req_id="2"))
    reader.feed_eof()
    out: list[str] = []

    await serve_stdio(server, reader=reader, write=out.append)

    # 每行都是合法 JSON 帧，无 banner/日志混入
    parsed = [json.loads(line) for line in out]
    assert any(p.get("id") == "1" and "result" in p for p in parsed), parsed
    assert all(isinstance(p, dict) for p in parsed)


@pytest.mark.asyncio
async def test_stdio_initialize_methods_match_single_table(tmp_path: Any) -> None:
    """方法表单一真相：stdio 的 initialize.methods 与 AppServer 内部方法表逐项一致。"""
    server = AppServer(create_engine=_no_engine, default_workspace_id="ws-1")
    reader = asyncio.StreamReader()
    reader.feed_data(_frame("initialize", {}))
    reader.feed_eof()
    out: list[str] = []

    await serve_stdio(server, reader=reader, write=out.append)

    init = next(json.loads(line) for line in out if json.loads(line).get("id") == "1")
    methods = init["result"]["methods"]
    assert sorted(methods) == sorted(server._methods())  # noqa: SLF001 - 断言单一真相源


@pytest.mark.asyncio
async def test_stdio_pumps_fanout_notifications_to_stdout(tmp_path: Any) -> None:
    """run 期 publish 的通知经同一 stdout 出口流出，顺序=publish 顺序（B-96）。"""
    server = AppServer(create_engine=_no_engine, default_workspace_id="ws-1")
    reader = asyncio.StreamReader()
    reader.feed_data(_frame("initialize", {}))
    out: list[str] = []

    async def drive() -> None:
        await asyncio.sleep(0.05)  # 让 serve_stdio 先订阅 Fanout 并进循环
        server.publish(Notification("task/status", {"task_id": "t", "status": "reviewed"}))
        server.publish(Notification("evidence/reported", {"task_id": "t", "verdicts": {}}))
        await asyncio.sleep(0.05)
        reader.feed_eof()

    task = asyncio.create_task(drive())
    await serve_stdio(server, reader=reader, write=out.append)
    await task

    methods = [json.loads(line).get("method") for line in out if "method" in json.loads(line)]
    assert "task/status" in methods
    assert "evidence/reported" in methods
    # 顺序：task/status 必在 evidence/reported 之前（publish 顺序）
    assert methods.index("task/status") < methods.index("evidence/reported")
