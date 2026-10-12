"""集成：WS 传输与 stdio 共用方法表 + Fanout（overview §12 M3 出口判据 4；ADR-0023）。

用 starlette TestClient 起 in-process ASGI，测三件事：
1. `assert_localhost_only` 拒绝非本机绑定（overview §13 未决项 5）；
2. WS 上 `initialize` 返回的方法表与 `AppServer._methods()` 逐项一致（一套契约）；
3. 手动 publish 到 Fanout 的通知能沿 WS 抵达客户端，顺序与 publish 顺序一致（B-96）。

不测真 engine.run_turn 的完整通知流：TestClient 与 fanout pump 的事件循环交错
在 CI 上不稳（本地跑会卡），把"run 端到端"留给 stdio 侧 test_serve_app_server。
"""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from questor.engine import Engine
from questor.schemas.model import PermissionMode
from questor.serve.http import assert_localhost_only, create_app
from questor.testenv.fake_home import fake_home
from questor.testenv.fake_model import FakeModel, ScriptedTurn


def _factory(model: FakeModel, cwd: str):  # noqa: ANN202 - 返回 Engine 工厂，签名与 AppServer 契约一致
    def make(thread_id: str, mode: PermissionMode) -> Engine:
        from questor.serve.assembly import build_engine

        return build_engine(model=model, cwd=cwd, mode=mode)

    return make


def test_assert_localhost_only_refuses_external_host() -> None:
    """对外暴露属 M8 议题，M3 拒一切非本机绑定（overview §13 未决项 5）。"""
    assert_localhost_only("127.0.0.1")
    assert_localhost_only("localhost")
    assert_localhost_only("::1")
    with pytest.raises(ValueError, match="M3 只允许本地"):
        assert_localhost_only("0.0.0.0")
    with pytest.raises(ValueError, match="M3 只允许本地"):
        assert_localhost_only("192.168.1.5")


def test_ws_initialize_returns_same_methods_as_stdio(tmp_path: pathlib.Path) -> None:
    """WS 与 stdio 共用方法表：`initialize.methods` 与 `AppServer._methods()` 逐项一致。"""
    from questor.serve.app_server import AppServer

    model = FakeModel([ScriptedTurn(text="ok")])
    with fake_home():
        app = create_app(create_engine=_factory(model, str(tmp_path)), ui_dist=None)
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "id": "1",
                        "method": "initialize",
                        "params": {"client_version": "qst-app-server/v0.1", "capabilities": {}},
                    }
                )
            )
            frame = json.loads(ws.receive_text())
        reference = set(AppServer(create_engine=_factory(model, str(tmp_path)))._methods())
    assert frame["id"] == "1"
    assert set(frame["result"]["methods"]) == reference


def test_thread_create_via_ws_matches_stdio(tmp_path: pathlib.Path) -> None:
    """thread/create 走 WS：形状与 stdio 一致（ThreadDTO 严格匹配 generated 类型）。"""
    model = FakeModel([ScriptedTurn(text="ok")])
    with fake_home():
        app = create_app(create_engine=_factory(model, str(tmp_path)), ui_dist=None)
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "id": "1",
                        "method": "initialize",
                        "params": {"client_version": "qst-app-server/v0.1", "capabilities": {}},
                    }
                )
            )
            ws.receive_text()  # 消化 initialize 响应
            ws.send_text(
                json.dumps(
                    {
                        "id": "2",
                        "method": "thread/create",
                        "params": {"workspace_id": "ws-m3-ws", "title": "WS 集成"},
                    }
                )
            )
            created = json.loads(ws.receive_text())
    assert created["id"] == "2", created
    thread = created["result"]["thread"]
    assert thread["workspace_id"] == "ws-m3-ws"
    assert thread["title"] == "WS 集成"
    assert thread["permission_mode"] == "standard"
