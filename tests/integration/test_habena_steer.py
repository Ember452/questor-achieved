"""集成：habena 插话消费点（overview §12 M3 出口判据 2 "插话在下一个工具边界被消费"）。

FakeModel 三轮决策；run_turn 之前把 steer submit 到 inbox；断言：
- 事件流里 iteration 1 起点出现 running → steered → running 三段迁移；
- `turn/steered` 通知对应内容正确、client_id 回链；
- 会话正文里 Origin.STEER 消息 Item 落盘（payload 带 `steered=True`）；
- conversation 历史里模型下一轮看到 steer 内容（fake model 会记 requests）。

对应 B-67/94（消费点在 BeforeStep）与 B-63/65（client_id 幂等 + held_work 落盘）。
"""

from __future__ import annotations

import pathlib

import pytest

from questor.engine import Engine
from questor.engine.events import RunStatus as RunStatusEvent
from questor.engine.events import SteerConsumed
from questor.engine.loop import TurnRequest
from questor.gesta import create_thread, load_thread
from questor.gesta.writer import ThreadWriter
from questor.habena import HabenaInbox
from questor.schemas.habena import SteerMessage
from questor.schemas.model import (
    PermissionMode,
    Thread,
    Timestamp,
)
from questor.testenv.fake_home import fake_home
from questor.testenv.fake_model import FakeModel, ScriptedTurn
from questor.tools.base import ToolContext
from questor.tools.filestate import FileStateCache
from questor.tools.impl.registry_default import build_default_registry
from questor.tools.impl.todo import TodoStore
from questor.tools.processmgr import ProcessManager

T0: Timestamp = "2026-10-12T08:00:00Z"


def _make_thread(thread_id: str) -> None:
    create_thread(
        Thread(
            id=thread_id,
            workspace_id="ws-steer",
            title="steer 消费点",
            engine_id="questor-engine",
            permission_mode=PermissionMode.STANDARD,
            pinned=False,
            archived=False,
            created_at=T0,
            updated_at=T0,
        )
    )


@pytest.mark.asyncio
async def test_steer_consumed_at_iteration_boundary(tmp_path: pathlib.Path) -> None:
    with fake_home():
        _make_thread("thread-steer-m3")
        # 先建 inbox（同一个 writer 会与 engine 打开的 writer 各自管理，靠 store_lock 串行）
        writer = ThreadWriter("thread-steer-m3")
        writer.open()
        inbox = HabenaInbox(writer)
        await inbox.submit(
            SteerMessage(
                thread_id="thread-steer-m3",
                client_id="cid-1",
                origin="steer",
                content="改成输出 43 而不是 42",
                created_at=T0,
            )
        )

        model = FakeModel(
            [
                ScriptedTurn(text="ok1", tool_calls=()),  # 一轮直接给文本终止
            ]
        )
        engine = Engine(
            model=model,
            registry=build_default_registry(),
            ctx=ToolContext(
                cwd=str(tmp_path),
                file_state=FileStateCache(),
                processes=ProcessManager(),
                todos=TodoStore(),
            ),
            mode=PermissionMode.STANDARD,
            roots=[str(tmp_path)],
        )
        engine.attach_inbox(inbox)

        events = []
        async for event in engine.run_turn(
            TurnRequest(thread_id="thread-steer-m3", user_text="写脚本算 6*7")
        ):
            events.append(event)

        # ---- 状态序列：running → steered → running → completed ----
        statuses = [e.status for e in events if isinstance(e, RunStatusEvent)]
        assert statuses == ["running", "steered", "running", "completed"], statuses

        # ---- SteerConsumed 事件带 client_id 回链 ----
        steered = [e for e in events if isinstance(e, SteerConsumed)]
        assert len(steered) == 1
        assert steered[0].client_id == "cid-1"
        assert "43" in steered[0].content

        # ---- 落盘：Origin.STEER 消息 Item 进正文 ----
        view = load_thread("thread-steer-m3")
        steer_items = [
            i for i in view.items if i.kind.value == "message" and i.payload.get("steered") is True
        ]
        assert len(steer_items) == 1
        assert steer_items[0].payload.get("client_id") == "cid-1"

        # ---- 模型第二请求里应看到 steer 内容（iteration 起点入历史） ----
        # 只有 1 个 ScriptedTurn，因此 engine 只请求了一次；steer 在进入 iteration
        # 起点时已入历史，但下一次请求不存在——改为断言 conversation.add_user 生效：
        # model.requests[0] 里最后一条 user 消息文本应包含 steer 内容
        first_request = model.requests[0]
        user_texts = [m.content for m in first_request.messages if m.role == "user"]
        assert any("改成输出 43" in text for text in user_texts), user_texts

        # ---- held_work 记录也随正文落盘（B-65）----
        assert len(view.held_work) == 1
        assert view.held_work[0].client_id == "cid-1"


@pytest.mark.asyncio
async def test_second_steer_with_same_client_id_is_idempotent(
    tmp_path: pathlib.Path,
) -> None:
    """B-63 幂等：同 client_id 二次 submit 返回 False 且不重复落 held_work。"""
    with fake_home():
        _make_thread("thread-steer-dedup")
        writer = ThreadWriter("thread-steer-dedup")
        writer.open()
        inbox = HabenaInbox(writer)
        msg = SteerMessage(
            thread_id="thread-steer-dedup",
            client_id="dup-1",
            origin="steer",
            content="hello",
            created_at=T0,
        )
        assert await inbox.submit(msg) is True
        assert await inbox.submit(msg) is False
        view = load_thread("thread-steer-dedup")
        assert len(view.held_work) == 1
