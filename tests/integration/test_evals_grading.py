"""evals grader 集成：把 tasks.json 声明的 replay_audit/recorded_output 接到真实产品函数核验。

用 M5 的 report 机器造出真实证据，再让 grader **只读**核验——证明评测消费的是真链路，
不是把 grading.type 复述成断言。负向（无记录不轻信）必须被 grader 判"审计通过"（即系统正确拒绝）。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from evals.runner.grading import grade_recorded_output, grade_replay_audit

from questor.gesta import add_item, add_run, add_turn, create_thread
from questor.orchestration import OrchestrationService, tasks
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
from questor.schemas.orchestration import ClaimedCheck, EvidenceSubjectType
from questor.testenv.fake_home import fake_home

THREAD = "thread-g"


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def _seed_tool_result(tool_use_id: str, *, output: str, is_error: bool, item_id: str) -> None:
    stamp = utc_timestamp_now()
    try:
        from questor.gesta import load_thread

        load_thread(THREAD)
    except Exception:  # noqa: BLE001 - 线程不存在即建
        create_thread(
            Thread(
                id=THREAD,
                workspace_id="ws-g",
                title="g",
                engine_id="questor-engine",
                permission_mode=PermissionMode.STANDARD,
                pinned=False,
                archived=False,
                created_at=stamp,
                updated_at=stamp,
            )
        )
        add_turn(THREAD, turn_id="turn-1", origin=Origin.USER, created_at=stamp)
        add_run(
            THREAD,
            Run(
                id="run-1",
                turn_id="turn-1",
                engine_id="questor-engine",
                permission_mode=PermissionMode.STANDARD,
                status=RunStatus.QUEUED,
                created_at=stamp,
            ),
        )
    add_item(
        THREAD,
        Item(
            id=item_id,
            run_id="run-1",
            kind=ItemKind.TOOL_RESULT,
            payload={"tool_use_id": tool_use_id, "is_error": is_error, "output": output},
            created_at=stamp,
        ),
    )


def _reported_task(claims: list[ClaimedCheck]) -> str:
    task = tasks.create_task(title="g", thread_id=THREAD)
    tasks.start_task(task.id)
    OrchestrationService(thread_id=THREAD).report_task(task.id, claims)
    return task.id


def test_replay_audit_passes_on_verified_chain() -> None:
    _seed_tool_result("t1", output="3 passed", is_error=False, item_id="item-1")
    task_id = _reported_task([ClaimedCheck(claimed="pytest passed", tool_use_id="t1")])

    v = grade_replay_audit(
        EvidenceSubjectType.TASK.value,
        task_id,
        ["all_claims_have_evidence", "no_unverified", "acceptance_verified"],
    )
    assert v.passed, v.reason


def test_replay_audit_fails_when_a_claim_unverified() -> None:
    _seed_tool_result("t1", output="ok", is_error=False, item_id="item-1")
    # 第二条绑到不存在的记录 → unverified → no_unverified 应判不通过
    task_id = _reported_task(
        [
            ClaimedCheck(claimed="ok", tool_use_id="t1"),
            ClaimedCheck(claimed="ghost", tool_use_id="nope"),
        ]
    )

    v = grade_replay_audit(EvidenceSubjectType.TASK.value, task_id, ["no_unverified"])
    assert not v.passed, v.reason


def test_recorded_output_negative_detects_unverified() -> None:
    """负向任务（missing-record）：grader 确认系统正确落 unverified、未误判 verified。"""
    _seed_tool_result("real", output="ok", is_error=False, item_id="item-1")
    task = tasks.create_task(title="g", thread_id=THREAD)
    tasks.start_task(task.id)
    # 上报一个绑到不存在 tool_use_id 的声称
    OrchestrationService(thread_id=THREAD).report_task(
        task.id, [ClaimedCheck(claimed="linter clean", tool_use_id="ghost")]
    )

    v = grade_recorded_output(
        THREAD,
        [ClaimedCheck(claimed="linter clean", tool_use_id="ghost")],
        EvidenceSubjectType.TASK.value,
        task.id,
        ["claim_without_record_is_unverified", "acceptance_not_verified"],
    )
    assert v.passed, v.reason
