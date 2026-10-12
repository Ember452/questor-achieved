"""evidence 集成：从真实落盘的 tool_result 反查证据并导出（ADR-0027 的端到端形态）。

不重跑工具、不联系模型——只读 gesta fold 出来的 Item。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from questor import evidence
from questor.gesta import add_item, add_run, add_turn, create_thread, load_thread
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
from questor.schemas.orchestration import EvidenceSubjectType
from questor.testenv.fake_home import fake_home


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def _seed_thread_with_tool_result() -> tuple[str, str]:
    stamp = utc_timestamp_now()
    thread = Thread(
        id="thread-ev",
        workspace_id="ws-ev",
        title="ev",
        engine_id="questor-engine",
        permission_mode=PermissionMode.STANDARD,
        pinned=False,
        archived=False,
        created_at=stamp,
        updated_at=stamp,
    )
    create_thread(thread)
    turn = add_turn("thread-ev", turn_id="turn-1", origin=Origin.USER, created_at=stamp)
    run = add_run(
        "thread-ev",
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
        "thread-ev",
        Item(
            id="item-1",
            run_id=run.id,
            kind=ItemKind.TOOL_RESULT,
            payload={
                "tool_use_id": "t1",
                "name": "run",
                "is_error": False,
                "output": "3 passed",
            },
            created_at=stamp,
        ),
    )
    return "thread-ev", "turn-1"


def test_evidence_roundtrip_from_recorded_item() -> None:
    thread_id, turn_id = _seed_thread_with_tool_result()
    view = load_thread(thread_id)
    recorded = {}
    for item in view.items:
        check = evidence.recorded_check_from_item(item)
        if check is not None:
            recorded[check.tool_use_id] = check
    assert "t1" in recorded

    evidence_items = evidence.compare_claims(
        [evidence.CheckClaim(claimed="pytest passed", tool_use_id="t1")],
        recorded,
        subject_type=EvidenceSubjectType.TURN,
        subject_id=turn_id,
    )
    assert evidence_items[0].verdict.value == "verified"
    assert evidence_items[0].recorded_output_ref == "item-1"  # 指向具体记录条目

    exported = evidence.export_evidence(evidence_items)
    assert exported.items[0].recorded_output_ref == "item-1"
    assert evidence.verdict_counts(evidence_items)["verified"] == 1
    assert evidence.for_subject(evidence_items, subject_type="turn", subject_id=turn_id)


def test_export_shape_is_stable() -> None:
    exported = evidence.export_evidence(())
    dumped = exported.model_dump(mode="json")
    assert set(dumped) == {"generated_at", "items"}  # 形状先定死为接口
