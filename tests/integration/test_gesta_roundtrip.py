"""集成：gesta 全生命周期落盘可回放（M2.1 出口判据的第一半）。

建线程 → 定 turn → 入 run → 状态推进 → 追加 item（含证据）与 event → 全部终态 →
从磁盘重新 fold，得到与增量 fold 完全一致的视图；索引重建前后一致。
"""

from __future__ import annotations

import questor.gesta as gesta
from questor.schemas.model import (
    Item,
    ItemEvidence,
    ItemKind,
    Origin,
    PermissionMode,
    Run,
    RunStatus,
    Thread,
    Timestamp,
    utc_timestamp_now,
)
from questor.testenv.fake_home import fake_home

T0: Timestamp = "2026-10-11T08:30:00Z"


def test_full_lifecycle_replay() -> None:
    with fake_home():
        gesta.create_thread(
            Thread(
                id="thread-e2e",
                workspace_id="ws-0001",
                title="端到端",
                engine_id="engine-01",
                permission_mode=PermissionMode.STANDARD,
                pinned=False,
                archived=False,
                created_at=T0,
                updated_at=T0,
            )
        )
        gesta.add_turn(
            "thread-e2e",
            turn_id="turn-0001",
            origin=Origin.USER,
            created_at=T0,
        )
        gesta.add_run(
            "thread-e2e",
            Run(
                id="run-0001",
                turn_id="turn-0001",
                engine_id="engine-01",
                permission_mode=PermissionMode.STANDARD,
                workspace_revision_start=0,
                status=RunStatus.QUEUED,
                created_at=T0,
            ),
        )
        gesta.transition_run("thread-e2e", "run-0001", RunStatus.RUNNING)
        spill = gesta.spill_tool_result("thread-e2e", "toolu_01E2E", "command output " * 300)
        gesta.add_item(
            "thread-e2e",
            Item(
                id="item-0001",
                run_id="run-0001",
                kind=ItemKind.TOOL_RESULT,
                payload={
                    "output_ref": spill.file,
                    "preview": spill.preview,
                    "truncated": spill.truncated,
                },
                evidence=ItemEvidence(
                    claimed="tests passed",
                    recorded_output_ref="toolu_01E2E.txt",
                ),
                created_at=utc_timestamp_now(),
            ),
        )
        placed = gesta.append_event(
            "thread-e2e",
            event_type="item/completed",
            run_id="run-0001",
            turn_id="turn-0001",
            payload={"item_id": "item-0001"},
            created_at=utc_timestamp_now(),
        )
        gesta.transition_run("thread-e2e", "run-0001", RunStatus.COMPLETED)

        # 从磁盘重新 fold（无进程内缓存），断言可回放
        replayed = gesta.load_thread("thread-e2e")
        assert replayed.thread.title == "端到端"
        assert replayed.turns[0].seq == 1
        assert replayed.runs[0].status == RunStatus.COMPLETED
        assert replayed.runs[0].workspace_revision_start == 0
        assert len(replayed.items) == 1
        assert replayed.items[0].evidence is not None
        assert replayed.items[0].evidence.claimed == "tests passed"
        assert replayed.events[0].seq == placed.seq == 6
        assert replayed.last_seq == 7  # created/turn/run/running/item/event/completed

        # 索引重建与摘要一致（updated_at 取最后记录时间）
        entries = gesta.rebuild_index()
        assert len(entries) == 1
        assert entries[0].last_seq == 7
        assert entries[0].run_count == 1
        assert entries[0].turn_count == 1
