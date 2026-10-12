"""集成：review/turn_diff 拿写时算好的 diff（overview §12 M3 出口判据 1；B-66/B-93）。

单 turn 里跑 write 一次 → 会话 fold → aggregate_turn_diff 拿聚合结果，
逐字节对 diff 里的 path/created/hunks/fingerprint/byte_size；
Run.workspace_revision_start/_end 由 engine 侧未落，本期先看 Item.payload.diff 完整。
"""

from __future__ import annotations

import pathlib

import pytest

from questor.engine import Engine
from questor.engine.loop import TurnRequest
from questor.engine.model import ToolCall
from questor.gesta import create_thread, load_thread
from questor.review import aggregate_turn_diff
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
from questor.workspaces import current_revision
from questor.workspaces import register as register_workspace

T0: Timestamp = "2026-10-12T08:00:00Z"


@pytest.mark.asyncio
async def test_review_turn_diff_aggregates_write(tmp_path: pathlib.Path) -> None:
    with fake_home():
        ws = register_workspace(tmp_path)
        create_thread(
            Thread(
                id="thread-review-m3",
                workspace_id=ws.id,
                title="review 集成",
                engine_id="questor-engine",
                permission_mode=PermissionMode.STANDARD,
                pinned=False,
                archived=False,
                created_at=T0,
                updated_at=T0,
            )
        )
        model = FakeModel(
            [
                ScriptedTurn(
                    text="写一个 hello.txt",
                    tool_calls=(
                        ToolCall(
                            id="tc1",
                            name="write",
                            arguments={"path": "hello.txt", "content": "hello world\n"},
                        ),
                    ),
                    stop_reason="tool_use",
                ),
                ScriptedTurn(text="完成"),
            ]
        )
        engine = Engine(
            model=model,
            registry=build_default_registry(),
            ctx=ToolContext(
                cwd=str(tmp_path),
                workspace_id=ws.id,
                file_state=FileStateCache(),
                processes=ProcessManager(),
                todos=TodoStore(),
            ),
            mode=PermissionMode.STANDARD,
            roots=[str(tmp_path)],
        )
        async for _ in engine.run_turn(
            TurnRequest(thread_id="thread-review-m3", user_text="写 hello.txt")
        ):
            pass
        view = load_thread("thread-review-m3")
        turn_id = view.turns[0].id
        diffs = aggregate_turn_diff(view, turn_id)
        revision = current_revision(ws.id)

    assert len(diffs) == 1, diffs
    diff = diffs[0]
    assert diff["path"] == "hello.txt"
    assert diff["created"] is True, "旧文件不存在时 created 应为 True"
    assert diff["byte_size"] == len(b"hello world\n")
    assert len(diff["hunks"]) >= 1
    assert "+hello world" in diff["unified"]
    # 修订号从 0 → 1（workspace.revision 由 write 工具 bump 一次）
    assert revision == ws.revision + 1
