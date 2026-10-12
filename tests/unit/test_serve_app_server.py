"""serve 雏形的行为：信封往返、方法表、通知流出、取消与 stdout 洁净。

集成部分走真实 stdio 回路（`asyncio.StreamReader` 喂字节 + 收集写出行），
因为"一行一帧"最容易坏在换行/刷新与通知与响应的交错上，单元级 mock 看不出。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from questor.engine import Engine
from questor.schemas.model import PermissionMode, Thread, Timestamp
from questor.serve import Dispatcher, Notification, parse_line, run_stdio
from questor.serve.app_server import PROTOCOL_NAME, AppServer
from questor.serve.envelope import encode_line, error_payload
from questor.testenv.fake_home import fake_home
from questor.testenv.fake_model import FakeModel, ScriptedTurn

T0: Timestamp = "2026-10-12T08:30:00Z"


def _frame(method: str, params: dict[str, Any], request_id: str = "1") -> str:
    return encode_line({"id": request_id, "method": method, "params": params})


def _no_engine(thread_id: str, mode: PermissionMode) -> Engine:
    """只要方法表/信封、不要真跑引擎的测试用这个工厂：被调就是测试写错了。"""
    raise AssertionError(f"本测试不该起引擎（thread={thread_id}, mode={mode}）")


def _build_server(
    tmp_path: Any, model: FakeModel
) -> tuple[AppServer, Dispatcher, list[Notification]]:
    """返回 server + 已接好的分发器 + 通知收集列（必须复用同一个分发器：
    再 `build_dispatcher()` 一次会把 `_notify` 接成 None，通知看起来"没发"。"""
    seen: list[Notification] = []

    def create_engine(thread_id: str, mode: PermissionMode) -> Engine:
        del thread_id, mode
        return Engine(
            model=model,
            registry=_registry(),
            ctx=_ctx(tmp_path),
            mode=PermissionMode.STANDARD,
            roots=[str(tmp_path)],
        )

    server = AppServer(create_engine=create_engine, principal="tester")
    return server, server.build_dispatcher(notify=seen.append), seen


def _registry() -> Any:
    from questor.tools.impl.registry_default import build_default_registry

    return build_default_registry()


def _ctx(tmp_path: Any) -> Any:
    from questor.tools.base import ToolContext
    from questor.tools.filestate import FileStateCache
    from questor.tools.impl.todo import TodoStore
    from questor.tools.processmgr import ProcessManager

    return ToolContext(
        cwd=str(tmp_path),
        file_state=FileStateCache(),
        processes=ProcessManager(),
        todos=TodoStore(),
    )


# ---- 信封 ----


def test_parse_line_roundtrip_and_rejects() -> None:
    request = parse_line(_frame("thread/list", {}))
    assert (request.id, request.method) == ("1", "thread/list")
    from questor.serve.envelope import ProtocolFrameError

    with pytest.raises(ProtocolFrameError):
        parse_line("not json")
    with pytest.raises(ProtocolFrameError, match="id"):
        parse_line('{"method":"thread/list"}')  # 缺 id
    with pytest.raises(ProtocolFrameError, match="params"):
        parse_line('{"id":"1","method":"x","params":[]}')


def test_unknown_method_is_answered_not_raised() -> None:
    async def _run() -> str | None:
        dispatcher = AppServer(create_engine=_no_engine).build_dispatcher()
        return await dispatcher.handle_line(_frame("thread/teleport", {}, "7"))

    line = asyncio.run(_run())
    assert line is not None
    payload = json.loads(line)
    assert payload["id"] == "7"
    assert payload["error"]["code"] == "unknown_method"
    assert payload["error"]["model_next_action"]  # 拒绝要给出下一步


@pytest.mark.asyncio
async def test_initialize_rejects_version_mismatch() -> None:
    server = AppServer(create_engine=_no_engine)
    dispatcher = server.build_dispatcher()
    line = await dispatcher.handle_line(
        _frame("initialize", {"protocol_version": "qst-app-server/v0.0"})
    )
    await dispatcher.drain()
    payload = json.loads(dispatcher.writers.lines[-1] if line is None else line)
    assert "协议版本不匹配" in str(payload["error"]["message"])


@pytest.mark.asyncio
async def test_initialize_echoes_principal_and_method_table() -> None:
    server = AppServer(create_engine=_no_engine, issues=("no model configured",))
    dispatcher = server.build_dispatcher()
    await dispatcher.handle_line(_frame("initialize", {"protocol_version": PROTOCOL_NAME}))
    await dispatcher.drain()
    result = json.loads(dispatcher.writers.lines[-1])["result"]
    assert result["status"] == "needs_setup"  # 配置有问题时连接仍可用
    assert result["issues"] == ["no model configured"]
    assert result["principal"] == server.principal
    assert "turn/start" in result["methods"]
    assert result["engines"][0]["status"] == "ready"


@pytest.mark.asyncio
async def test_turn_start_streams_notifications_and_terminal_status() -> None:
    with fake_home():
        from questor.gesta import create_thread

        create_thread(
            Thread(
                id="thread-srv1",
                workspace_id="ws-srv",
                title="协议往返",
                engine_id="questor-engine",
                permission_mode=PermissionMode.STANDARD,
                pinned=False,
                archived=False,
                created_at=T0,
                updated_at=T0,
            )
        )
        model = FakeModel([ScriptedTurn(text="协议侧看到的回答。")])
        server, dispatcher, seen = _build_server(".", model)  # 本轮不调工具，cwd 无作用

        reply = await dispatcher.handle_line(
            _frame("turn/start", {"thread_id": "thread-srv1", "user_text": "说一句话"})
        )
        assert reply is None  # 长任务：响应异步补，不在读帧时串行阻塞
        await dispatcher.drain()
        await server.wait_idle()  # 等 in-flight 的 run：_pump 由 server 跟踪（B-01）

        families = [notification.method for notification in seen]
        assert "run/status" in families and "delta" in families
        assert families[0] == "run/status"  # queued→running 先到
        assert families[-1] == "run/status"  # 终态最后到达
        assert json.loads(dispatcher.writers.lines[-1])["id"] == "1"


@pytest.mark.asyncio
async def test_run_stop_requires_an_inflight_run(tmp_path: Any) -> None:
    server, dispatcher, _ = _build_server(tmp_path, FakeModel([]))
    await dispatcher.handle_line(_frame("run/stop", {"thread_id": "thread-none"}, "9"))
    await dispatcher.drain()
    payload = json.loads(dispatcher.writers.lines[-1])
    assert payload["id"] == "9"
    assert payload["error"]["code"] == "invalid_params"


@pytest.mark.asyncio
async def test_handler_failure_becomes_internal_error_not_a_dead_connection(tmp_path: Any) -> None:
    server, dispatcher, _ = _build_server(tmp_path, FakeModel([]))

    async def _boom(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
        del params, ctx
        raise RuntimeError("handler 内部炸了")

    dispatcher.register("debug/boom", _boom)  # 测试专用方法，不走契约核对
    await dispatcher.handle_line(_frame("debug/boom", {}, "11"))
    await dispatcher.drain()
    payload = json.loads(dispatcher.writers.lines[-1])
    assert payload["error"]["code"] == "internal_error"
    # 同一条连接还能继续服务
    again = await dispatcher.handle_line(_frame("thread/list", {}, "12"))
    await dispatcher.drain()
    assert again is None
    assert json.loads(dispatcher.writers.lines[-1])["id"] == "12"


@pytest.mark.asyncio
async def test_stdio_writes_only_protocol_frames(tmp_path: Any) -> None:
    """stdout 洁净（protocol §1）：只有一帧一行的 JSON，日志一律不走这里。"""
    server, dispatcher, _ = _build_server(tmp_path, FakeModel([]))
    out: list[str] = []
    reader = asyncio.StreamReader()
    reader.feed_data((_frame("thread/list", {}, "1") + "\n").encode("utf-8"))
    reader.feed_eof()

    await run_stdio(dispatcher, reader=reader, write=out.append)

    assert out and all("\n" not in line for line in out)
    assert all(isinstance(json.loads(line), dict) for line in out)
    assert isinstance(dispatcher, Dispatcher)


def test_error_payload_shape_is_stable() -> None:
    assert error_payload("invalid_params", "bad") == {"code": "invalid_params", "message": "bad"}
