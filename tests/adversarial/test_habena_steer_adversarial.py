"""对抗：turn/steer 的 `expected_turn_id` 陈旧时拒（B-64）与幂等（B-63）。

handler 层直接调，不起引擎；测的是 serve 与 habena 交界的判定形状，不测 engine 消费点
（engine 侧由 test_habena_steer 覆盖）。
"""

from __future__ import annotations

import pathlib

import pytest

from questor.engine import Engine
from questor.engine.model import InboxPort
from questor.gesta import create_thread
from questor.schemas.habena import SteerMessage
from questor.schemas.model import (
    PermissionMode,
    Thread,
    Timestamp,
)
from questor.serve.app_server import AppServer
from questor.serve.dispatch import HandlerCtx
from questor.serve.envelope import ProtocolError
from questor.testenv.fake_home import fake_home
from questor.testenv.fake_model import FakeModel, ScriptedTurn
from questor.tools.base import ToolContext
from questor.tools.filestate import FileStateCache
from questor.tools.impl.registry_default import build_default_registry
from questor.tools.impl.todo import TodoStore
from questor.tools.processmgr import ProcessManager

T0: Timestamp = "2026-10-12T08:00:00Z"


class _NullInbox:
    """本文件不测消费；只验 handler 层的判定。drain 恒空。"""

    async def drain(self) -> list[SteerMessage]:
        return []


def _ctx() -> HandlerCtx:
    return HandlerCtx(request_id="r", principal="test", trace_id="t")


def _make_server(tmp_path: pathlib.Path) -> AppServer:
    model = FakeModel([ScriptedTurn(text="ok")])

    def _create(thread_id: str, mode: PermissionMode) -> Engine:
        return Engine(
            model=model,
            registry=build_default_registry(),
            ctx=ToolContext(
                cwd=str(tmp_path),
                file_state=FileStateCache(),
                processes=ProcessManager(),
                todos=TodoStore(),
            ),
            mode=mode,
            roots=[str(tmp_path)],
            inbox=_NullInbox(),  # type: ignore[arg-type]
        )

    return AppServer(create_engine=_create)


def _thread(thread_id: str) -> None:
    create_thread(
        Thread(
            id=thread_id,
            workspace_id="ws-adversarial",
            title="steer 判定",
            engine_id="questor-engine",
            permission_mode=PermissionMode.STANDARD,
            pinned=False,
            archived=False,
            created_at=T0,
            updated_at=T0,
        )
    )


@pytest.mark.asyncio
async def test_steer_with_wrong_expected_turn_is_rejected(tmp_path: pathlib.Path) -> None:
    """B-64：expected_turn_id 非空且不匹配当前 turn 时拒（旧客户端不传则放行）。"""
    with fake_home():
        _thread("thread-steer-adversarial")
        server = _make_server(tmp_path)
        # 先起一轮让 thread 有 active turn
        ack = await server.turn_start(
            {"thread_id": "thread-steer-adversarial", "user_text": "起步"}, _ctx()
        )
        assert ack["accepted"] is True
        await server.wait_idle()
        with pytest.raises(ProtocolError) as exc:
            await server.turn_steer(
                {
                    "thread_id": "thread-steer-adversarial",
                    "client_id": "c-1",
                    "content": "换方向",
                    "expected_turn_id": "turn-nonexistent",
                },
                _ctx(),
            )
        assert exc.value.code == "stale_revision"


@pytest.mark.asyncio
async def test_second_submit_same_client_id_is_idempotent(tmp_path: pathlib.Path) -> None:
    """B-63：同 client_id 二次 submit → 第二次 accepted=False（幂等）。"""
    with fake_home():
        _thread("thread-steer-idempotent")
        server = _make_server(tmp_path)
        first = await server.turn_steer(
            {
                "thread_id": "thread-steer-idempotent",
                "client_id": "dup",
                "content": "hello",
            },
            _ctx(),
        )
        second = await server.turn_steer(
            {
                "thread_id": "thread-steer-idempotent",
                "client_id": "dup",
                "content": "hello",
            },
            _ctx(),
        )
    assert first["accepted"] is True
    assert second["accepted"] is False


def test_inbox_port_is_runtime_checkable() -> None:
    """engine.model.InboxPort 是 runtime_checkable Protocol，`_NullInbox` 应通过 isinstance。"""
    assert isinstance(_NullInbox(), InboxPort)
