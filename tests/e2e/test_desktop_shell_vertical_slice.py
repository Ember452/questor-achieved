"""Phase U Track B 出口 e2e：同一会话层、两宿主（stdio + WS）契约同形。

M5 的 `test_serve_stdio_host.py` 与 M3 的 `test_serve_http_ws.py` 各自钉住宿主本身
的传输形状，但**没有直接对比**"两宿主同一序列的结果是否严格相等"。B9 只补这一
条跨宿主等价断言——不重单元测、不测真 turn 执行（那属 M3 已覆盖）、不测
Electron（属 [real-terminal]）。

关联：Phase U Track B 出口判据 1 与 4；ADR-0006 §结论 2/4。
"""

from __future__ import annotations

import asyncio
import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from questor.engine import Engine
from questor.schemas.model import PermissionMode
from questor.serve.app_server import AppServer
from questor.serve.assembly import build_engine, ensure_workspace_for_root
from questor.serve.http import create_app
from questor.serve.stdio import serve_stdio
from questor.testenv.fake_home import fake_home
from questor.testenv.fake_model import FakeModel, ScriptedTurn


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def _factory(model: FakeModel, cwd: str) -> Any:
    def make(thread_id: str, mode: PermissionMode) -> Engine:
        return build_engine(model=model, cwd=cwd, mode=mode, thread_id=thread_id)

    return make


def _frame(method: str, params: dict[str, Any], req_id: str) -> bytes:
    return (json.dumps({"id": req_id, "method": method, "params": params}) + "\n").encode()


async def _drive_stdio(
    tmp_path: pathlib.Path, frames: list[tuple[str, str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    """喂一串帧给 stdio 宿主，返回按 id 匹配的响应帧。"""
    model = FakeModel([ScriptedTurn(text="ok")])
    server = AppServer(
        create_engine=_factory(model, str(tmp_path)),
        default_workspace_id=ensure_workspace_for_root(tmp_path),
    )
    reader = asyncio.StreamReader()
    for req_id, method, params in frames:
        reader.feed_data(_frame(method, params, req_id))
    reader.feed_eof()
    out: list[str] = []
    await serve_stdio(server, reader=reader, write=out.append)
    responses: dict[str, dict[str, Any]] = {}
    for line in out:
        parsed = json.loads(line)
        if "id" in parsed and "method" not in parsed:
            responses[parsed["id"]] = parsed
    return [responses[req_id] for req_id, _m, _p in frames if req_id in responses]


def _drive_ws(
    tmp_path: pathlib.Path, frames: list[tuple[str, str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    """同样一串帧通过 WS 客户端喂，返回按 id 匹配顺序的响应帧。"""
    model = FakeModel([ScriptedTurn(text="ok")])
    app = create_app(
        create_engine=_factory(model, str(tmp_path)),
        ui_dist=None,
    )
    client = TestClient(app)
    responses: dict[str, dict[str, Any]] = {}
    with client.websocket_connect("/ws") as ws:
        # 起手先握手 initialize（WS 上任何业务方法前都需 initialize，与 stdio 同形）。
        ws.send_text(json.dumps({"id": "1", "method": "initialize", "params": {}}))
        responses["1"] = json.loads(ws.receive_text())
        for req_id, method, params in frames:
            if req_id == "1":
                continue  # initialize 已回
            ws.send_text(json.dumps({"id": req_id, "method": method, "params": params}))
            responses[req_id] = json.loads(ws.receive_text())
    return [responses[r] for r, _m, _p in frames if r in responses]


@pytest.mark.asyncio
async def test_initialize_methods_identical_across_stdio_and_ws(tmp_path: pathlib.Path) -> None:
    """两宿主 initialize.methods 严格同集合——桌面壳与浏览器共享方法契约不破。"""
    frames = [("1", "initialize", {})]
    stdio_responses = await _drive_stdio(tmp_path, frames)
    ws_responses = _drive_ws(tmp_path, frames)
    assert len(stdio_responses) == 1, stdio_responses
    assert len(ws_responses) == 1, ws_responses
    stdio_methods = set(stdio_responses[0]["result"]["methods"])
    ws_methods = set(ws_responses[0]["result"]["methods"])
    assert stdio_methods == ws_methods, (
        f"stdio 独有：{stdio_methods - ws_methods}；WS 独有：{ws_methods - stdio_methods}"
    )


@pytest.mark.asyncio
async def test_thread_create_shape_identical_across_stdio_and_ws(tmp_path: pathlib.Path) -> None:
    """两宿主 thread/create 返回的 ThreadDTO 字段集合与关键值一致（B-101 生成链依赖）。

    workspace_id 与 title 一致；permission_mode 同 default（standard）；
    忽略 id/时间戳这些运行期非确定字段。
    """
    workspace_id = str(ensure_workspace_for_root(tmp_path))
    frames = [
        ("1", "initialize", {}),
        ("2", "thread/create", {"workspace_id": workspace_id, "title": "e2e 双宿主"}),
    ]
    stdio_responses = await _drive_stdio(tmp_path, frames)
    ws_responses = _drive_ws(tmp_path, frames)
    stdio_thread = stdio_responses[1]["result"]["thread"]
    ws_thread = ws_responses[1]["result"]["thread"]
    # 忽略非确定字段（thread_id 由 fake 会话层生成、时间戳每次不同）。
    deterministic = {"workspace_id", "title", "permission_mode"}
    assert {k: stdio_thread[k] for k in deterministic} == {
        k: ws_thread[k] for k in deterministic
    }, f"stdio={stdio_thread} WS={ws_thread}"
    # 两边字段集合也应相等（防某一侧偷偷多/少字段）。
    assert set(stdio_thread.keys()) == set(ws_thread.keys())
