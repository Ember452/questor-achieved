"""M5 验收闭环集成：模型上报声称 → 只读核对 → 落 Evidence → 驱动验收态（ADR-0029）。

覆盖可验证柱的完整生产链：`evidence.source.verify_claims` 从落盘 tool_result 反查实测，
`OrchestrationService.report_task` 落证据并把 `executing → reported → verified | regressed`，
并 `executing → reviewed` 进待验收列；绑错/缺记录的声称一律 `unverified`（不轻信）。
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest

from questor.gesta import add_item, add_run, add_turn, create_thread, load_thread
from questor.orchestration import OrchestrationService, store, tasks
from questor.schemas.model import (
    AcceptanceStatus,
    Item,
    ItemKind,
    Origin,
    PermissionMode,
    Run,
    RunStatus,
    Thread,
    utc_timestamp_now,
)
from questor.schemas.orchestration import ClaimedCheck, EvidenceVerdict, OrchestrationGateError
from questor.testenv.fake_home import fake_home

THREAD = "thread-r"


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def _seed_tool_result(tool_use_id: str, *, output: str, is_error: bool, item_id: str) -> None:
    """幂等地向固定线程追加一条带真实输出的 tool_result（声称核对的"实测"来源）。

    首次建线程/turn/run（run 以 queued 入流，gesta 硬规则）；重复调只追加新 item。
    """
    stamp = utc_timestamp_now()
    try:
        load_thread(THREAD)
    except Exception:  # noqa: BLE001 - 线程不存在即建（gesta ThreadNotFound 属此分支）
        create_thread(
            Thread(
                id=THREAD,
                workspace_id="ws-r",
                title="r",
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
            payload={
                "tool_use_id": tool_use_id,
                "name": "run",
                "is_error": is_error,
                "output": output,
            },
            created_at=stamp,
        ),
    )


def _started_task() -> str:
    """建任务并推进到 executing（验收态随之 executing，经 tasks.start_task 单点）。"""
    task = tasks.create_task(title="fix bug", thread_id=THREAD)
    tasks.start_task(task.id)
    return task.id


def test_report_verified_when_recorded_ok() -> None:
    _seed_tool_result("t1", output="3 passed", is_error=False, item_id="item-1")
    task_id = _started_task()
    service = OrchestrationService(thread_id=THREAD)

    moved = service.report_task(task_id, [ClaimedCheck(claimed="pytest passed", tool_use_id="t1")])

    assert moved.acceptance.status is AcceptanceStatus.VERIFIED
    assert moved.status.value == "reviewed"  # 进待验收列
    assert len(moved.acceptance.evidence_ids) == 1
    ev = store.load_view().evidence[0]
    assert ev.verdict is EvidenceVerdict.VERIFIED
    assert ev.recorded_output_ref == "item-1"  # 结论指向具体记录条目（可追溯）


def test_report_regressed_on_mismatch_and_missing_record() -> None:
    """两条声称：一条录得为错误 → mismatch；一条绑到不存在的 tool_use_id → unverified。"""
    _seed_tool_result("t1", output="1 failed", is_error=True, item_id="item-1")
    task_id = _started_task()
    service = OrchestrationService(thread_id=THREAD)

    moved = service.report_task(
        task_id,
        [
            ClaimedCheck(claimed="tests pass", tool_use_id="t1"),
            ClaimedCheck(claimed="linter clean", tool_use_id="ghost"),  # 无此记录
        ],
    )

    assert moved.acceptance.status is AcceptanceStatus.REGRESSED
    verdicts = {e.verdict for e in store.load_view().evidence}
    assert EvidenceVerdict.MISMATCH in verdicts
    assert EvidenceVerdict.UNVERIFIED in verdicts


def test_report_requires_executing_acceptance() -> None:
    """未开始执行（验收态 still proposed）即 report → 结构化方言拒绝，不落证据。"""
    _seed_tool_result("t1", output="ok", is_error=False, item_id="item-1")
    task = tasks.create_task(title="t", thread_id=THREAD)  # 未 start
    service = OrchestrationService(thread_id=THREAD)
    with pytest.raises(OrchestrationGateError) as excinfo:
        service.report_task(task.id, [ClaimedCheck(claimed="x", tool_use_id="t1")])
    assert excinfo.value.error_code == "invalid_acceptance_state"


def test_report_publishes_evidence_reported_via_publisher() -> None:
    _seed_tool_result("t1", output="ok", is_error=False, item_id="item-1")
    task_id = _started_task()
    service = OrchestrationService(thread_id=THREAD)
    seen: list[tuple[str, dict]] = []
    service.bind_publisher(lambda kind, payload: seen.append((kind, payload)))

    service.report_task(task_id, [ClaimedCheck(claimed="pytest passed", tool_use_id="t1")])

    kinds = [k for k, _ in seen]
    assert "evidence/reported" in kinds
    assert "task/status" in kinds
    reported = next(p for k, p in seen if k == "evidence/reported")
    assert reported["acceptance_status"] == "verified"
    assert reported["verdicts"]["verified"] == 1


def test_regressed_can_be_reworked_then_verified() -> None:
    """打回重做闭环：regressed → reject → 重新 report 用对的记录 → verified。"""
    _seed_tool_result("t1", output="1 failed", is_error=True, item_id="item-1")
    task_id = _started_task()
    service = OrchestrationService(thread_id=THREAD)
    first = service.report_task(task_id, [ClaimedCheck(claimed="pass", tool_use_id="t1")])
    assert first.acceptance.status is AcceptanceStatus.REGRESSED

    tasks.reject_task(task_id)  # regressed → executing（重开）
    # 重做后有了成功的录得（新 tool_use_id）
    _seed_tool_result("t2", output="all passed", is_error=False, item_id="item-2")
    second = service.report_task(task_id, [ClaimedCheck(claimed="now passes", tool_use_id="t2")])
    assert second.acceptance.status is AcceptanceStatus.VERIFIED


@pytest.mark.asyncio
async def test_task_tool_report_action(tmp_path: pathlib.Path) -> None:
    """模型侧 `task` 工具的 `report` 动作经注入端口走通（D4 同源的真实路径）。"""
    from questor.tools.base import ToolContext
    from questor.tools.filestate import FileStateCache
    from questor.tools.impl.orchestration import TaskParams, TaskTool
    from questor.tools.impl.todo import TodoStore
    from questor.tools.processmgr import ProcessManager

    _seed_tool_result("t1", output="all passed", is_error=False, item_id="item-1")
    task_id = _started_task()
    wired = ToolContext(
        cwd=str(tmp_path),
        file_state=FileStateCache(),
        processes=ProcessManager(),
        todos=TodoStore(),
        thread_id=THREAD,
        orchestration=OrchestrationService(thread_id=THREAD),
    )
    result = await TaskTool().execute(
        TaskParams(
            action="report",
            task_id=task_id,
            checks=[ClaimedCheck(claimed="pytest passed", tool_use_id="t1")],
        ),
        wired,
    )
    assert not result.is_error, result.output
    assert result.data["acceptance_status"] == "verified"
