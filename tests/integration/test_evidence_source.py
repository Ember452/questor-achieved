"""evidence 只读核对源单测（M5，ADR-0029）：collect_recorded + verify_claims。

只读消费 gesta 落盘 tool_result，不复跑、不联系模型。锁住"缺记录不轻信"与"结论可追溯"两条
——与 report 生产链（test_evidence_report.py）分处：这里验的是源模块本身的契约。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from questor.evidence import collect_recorded, verify_claims
from questor.gesta import add_item, add_run, add_turn, create_thread
from questor.schemas.model import (
    Item,
    ItemKind,
    Origin,
    PermissionMode,
    Run,
    RunStatus,
    Thread,
    utc_timestamp_now,
)
from questor.schemas.orchestration import ClaimedCheck, EvidenceSubjectType, EvidenceVerdict
from questor.testenv.fake_home import fake_home

THREAD = "thread-src"


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def _seed() -> None:
    stamp = utc_timestamp_now()
    create_thread(
        Thread(
            id=THREAD,
            workspace_id="ws-s",
            title="s",
            engine_id="questor-engine",
            permission_mode=PermissionMode.STANDARD,
            pinned=False,
            archived=False,
            created_at=stamp,
            updated_at=stamp,
        )
    )
    turn = add_turn(THREAD, turn_id="turn-1", origin=Origin.USER, created_at=stamp)
    run = add_run(
        THREAD,
        Run(
            id="run-1",
            turn_id=turn.id,
            engine_id="questor-engine",
            permission_mode=PermissionMode.STANDARD,
            status=RunStatus.QUEUED,
            created_at=stamp,
        ),
    )
    add_item(
        THREAD,
        Item(
            id="item-ok",
            run_id=run.id,
            kind=ItemKind.TOOL_RESULT,
            payload={"tool_use_id": "t1", "is_error": False, "output": "2 passed"},
            created_at=stamp,
        ),
    )


def test_collect_recorded_indexes_by_tool_use_id() -> None:
    _seed()
    recorded = collect_recorded(THREAD)
    assert "t1" in recorded
    assert recorded["t1"].ref == "item-ok"
    assert recorded["t1"].is_error is False


def test_collect_recorded_missing_thread_is_empty() -> None:
    """线程不存在 → 空表（不臆造实测；上层据此判 unverified）。"""
    assert collect_recorded("thread-does-not-exist") == {}
    assert collect_recorded("") == {}


def test_verify_claims_verified_and_unverified() -> None:
    _seed()
    items = verify_claims(
        THREAD,
        [
            ClaimedCheck(claimed="tests pass", tool_use_id="t1"),
            ClaimedCheck(claimed="ghost check", tool_use_id="missing"),
        ],
        subject_type=EvidenceSubjectType.TASK,
        subject_id="task-1",
    )
    assert items[0].verdict is EvidenceVerdict.VERIFIED
    assert items[0].recorded_output_ref == "item-ok"
    assert items[1].verdict is EvidenceVerdict.UNVERIFIED
    assert items[1].recorded_output_ref == ""
