"""orchestration store / plan / tasks / goal / board / service / 工具 单测。

覆盖：append-only 与唯一状态入口、索引可重建、残尾容忍、需求改版作废验收、
编排门（经 service 与工具两条路径）、Goal 轮次止损、看板环检测。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from questor.orchestration import (
    OrchestrationService,
    board,
    goal,
    plan,
    store,
    tasks,
)
from questor.orchestration.transitions import InvalidTaskTransition
from questor.schemas.model import AcceptanceStatus
from questor.schemas.orchestration import OrchestrationGateError, TaskStatus
from questor.state.paths import orchestration_log_path
from questor.testenv.fake_home import fake_home
from questor.tools.base import ToolContext
from questor.tools.filestate import FileStateCache
from questor.tools.impl.orchestration import PlanParams, PlanTool, TaskParams, TaskTool
from questor.tools.impl.todo import TodoStore
from questor.tools.processmgr import ProcessManager


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def _lines() -> list[str]:
    path = orchestration_log_path()
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_store_is_append_only_and_transition_is_single_entry() -> None:
    task = tasks.create_task(title="t1")
    moved = store.transition_task(task.id, TaskStatus.EXECUTING)
    assert moved.status is TaskStatus.EXECUTING
    # 历史行只增不改：created + status 两条都在
    kinds = [line for line in _lines()]
    assert len(kinds) == 2
    assert '"task.created"' in kinds[0]
    assert '"task.status"' in kinds[1]


def test_illegal_transition_rejected_before_write() -> None:
    task = tasks.create_task(title="t1")  # pending
    with pytest.raises(InvalidTaskTransition):
        store.transition_task(task.id, TaskStatus.INBOX)
    assert len(_lines()) == 1  # 非法迁移不落盘


def test_update_task_cannot_change_status() -> None:
    task = tasks.create_task(title="t1")
    bumped = task.model_copy(update={"status": TaskStatus.EXECUTING})
    with pytest.raises(store.OrchestrationStoreError):
        store.update_task(bumped)


def test_record_round_rejected_when_goal_not_running() -> None:
    """Goal 轮次记账必须同受白名单约束：空闲/已停的 Goal 不得记轮，
    更不得经 record_round 绕开 _move 被翻成 completed。"""
    g = goal.create_goal(thread_id="thread-1", objective="o", max_rounds=1)
    with pytest.raises(store.OrchestrationStoreError):
        goal.record_round(g.id)  # IDLE：未起跑不得记轮
    goal.start_goal(g.id)
    goal.stop_goal(g.id)  # CANCELLED 终态
    with pytest.raises(store.OrchestrationStoreError):
        goal.record_round(g.id)


def _append_raw_record(payload_line: str) -> None:
    """向记录流手工追加一行（制造回放时才可能遇到的脏记录）。"""
    with orchestration_log_path().open("a", encoding="utf-8") as handle:
        handle.write(payload_line + "\n")


def test_invalidation_record_missing_revision_raises_store_error() -> None:
    """脏作废记录回放必须报 OrchestrationStoreError，不得漏裸 KeyError（B-76 口径）。"""
    task = tasks.create_task(title="t1")
    _append_raw_record(
        '{"seq": 99, "kind": "acceptance.invalidated", '
        f'"payload": {{"task_ids": ["{task.id}"]}}, "recorded_at": "2026-10-12T00:00:00Z"}}'
    )
    with pytest.raises(store.OrchestrationStoreError):
        store.load_view()


def test_invalidation_record_bad_task_ids_raises_store_error() -> None:
    """task_ids 非列表不得被逐字符迭代静默吞掉，必须拒。"""
    tasks.create_task(title="t1")
    _append_raw_record(
        '{"seq": 99, "kind": "acceptance.invalidated", '
        '"payload": {"task_ids": "oops", "requirement_revision": 2}, '
        '"recorded_at": "2026-10-12T00:00:00Z"}'
    )
    with pytest.raises(store.OrchestrationStoreError):
        store.load_view()


def test_sync_subtasks_requires_finalized_plan() -> None:
    """领域不变式：只有已定稿计划可派生子任务（“定稿才执行”不能只写在 docstring 里）。"""
    p = plan.propose_plan(steps=["a", "b"])
    with pytest.raises(store.OrchestrationStoreError):
        tasks.sync_subtasks_from_plan(p.id)  # DRAFTING 不得派生
    plan.finalize_plan(p.id)
    assert len(tasks.sync_subtasks_from_plan(p.id)) == 2


def test_sync_subtasks_is_idempotent_per_step() -> None:
    """同步过的步骤（step.task_id 已回填）不重复派生——崩溃后重跑不造重复任务。"""
    p = plan.finalize_plan(plan.propose_plan(steps=["a", "b"]).id)
    created = tasks.sync_subtasks_from_plan(p.id)
    again = tasks.sync_subtasks_from_plan(p.id)
    assert len(created) == 2
    assert again == []
    assert len(store.load_view().tasks) == 2


def test_requirement_revision_invalidates_acceptance() -> None:
    """需求改版递增 requirement_revision → 既有验收作废（追加作废记录，不改写）。"""
    p = plan.propose_plan(steps=["a", "b"], thread_id="thread-1")
    p = plan.finalize_plan(p.id)
    created = tasks.sync_subtasks_from_plan(p.id)
    assert len(created) == 2
    # 先按验收状态机驱动一个任务到 verified（update_task 不得旁路改验收态）
    task = created[0]
    for target in (
        AcceptanceStatus.ACCEPTED_BY_USER,
        AcceptanceStatus.EXECUTING,
        AcceptanceStatus.REPORTED,
    ):
        store.transition_acceptance(task.id, target)
    accepted = store.transition_acceptance(
        task.id, AcceptanceStatus.VERIFIED, evidence_ids=("ev-1",)
    )
    assert accepted.acceptance.status is AcceptanceStatus.VERIFIED
    assert accepted.acceptance.evidence_ids == ("ev-1",)
    # 改版 → 作废
    plan.revise_plan(p.id, steps=["a", "b", "c"])
    refreshed = store.load_view()
    after = next(t for t in refreshed.tasks if t.id == task.id)
    assert after.acceptance.status is AcceptanceStatus.PROPOSED
    assert after.acceptance.evidence_ids == ()
    assert after.acceptance.requirement_revision == 2


def test_index_is_rebuildable() -> None:
    tasks.create_task(title="t1")
    tasks.create_task(title="t2")
    entries = store.rebuild_index()
    assert {e.title for e in entries} == {"t1", "t2"}
    assert {s.title for s in store.list_tasks()} == {"t1", "t2"}


def test_tail_tolerance_and_rebuild() -> None:
    """崩溃残尾不阻断读取与后续追加（B-74）。"""
    tasks.create_task(title="t1")
    with orchestration_log_path().open("a", encoding="utf-8") as handle:
        handle.write('{"seq": 99, "kind": "task.created", "payload":')  # 残尾半行
    tasks.create_task(title="t2")
    assert {t.title for t in store.load_view().tasks} == {"t1", "t2"}


def test_service_gate_requires_plan_then_allows() -> None:
    service = OrchestrationService(thread_id="thread-1")
    with pytest.raises(OrchestrationGateError) as excinfo:
        service.create_task(title="t1")
    assert excinfo.value.error_code == "need_plan_first"
    service.propose_plan(steps=["a"], finalize=True)
    task = service.create_task(title="t1")
    assert task.title == "t1"


def test_service_start_requires_authorization() -> None:
    service = OrchestrationService(thread_id="thread-1")
    service.propose_plan(steps=["a"], finalize=True)
    task = service.create_task(title="t1")
    with pytest.raises(OrchestrationGateError) as excinfo:
        service.start_task(task.id)  # 默认未授权
    assert excinfo.value.error_code == "need_execution_authorization"
    authorized = OrchestrationService(authorizer=lambda _tid: True, thread_id="thread-1")
    started = authorized.start_task(task.id)
    assert started.status is TaskStatus.EXECUTING


def test_tools_go_through_the_port() -> None:
    """plan/task 工具经 OrchestrationPort 生效；无计划时 task create 被门拒绝。"""
    ctx = ToolContext(
        cwd=".",
        file_state=FileStateCache(),
        processes=ProcessManager(),
        todos=TodoStore(),
        thread_id="thread-1",
        orchestration=OrchestrationService(thread_id="thread-1"),
    )
    plan_tool = PlanTool()
    task_tool = TaskTool()

    async def run() -> None:
        refused = await task_tool.execute(TaskParams(action="create", title="t1"), ctx)
        assert refused.is_error and "need_plan_first" in refused.output
        made = await plan_tool.execute(PlanParams(steps=["a", "b"], finalize=True), ctx)
        assert not made.is_error
        ok = await task_tool.execute(TaskParams(action="create", title="t1"), ctx)
        assert not ok.is_error

    asyncio.run(run())


def test_service_sync_gate_requires_plan() -> None:
    """sync 也是建任务：无落库计划时被门拒（need_plan_first）。"""
    service = OrchestrationService(thread_id="thread-1")
    with pytest.raises(OrchestrationGateError) as excinfo:
        service.sync_subtasks(plan_id="plan-ghost")
    assert excinfo.value.error_code == "need_plan_first"


def test_tool_task_sync_action() -> None:
    """模型侧 task 工具的 sync 动作（计划 D4：“按已定稿计划同步子任务”）。"""
    ctx = ToolContext(
        cwd=".",
        file_state=FileStateCache(),
        processes=ProcessManager(),
        todos=TodoStore(),
        thread_id="thread-1",
        orchestration=OrchestrationService(thread_id="thread-1"),
    )
    plan_tool = PlanTool()
    task_tool = TaskTool()

    async def run() -> None:
        made = await plan_tool.execute(PlanParams(steps=["a", "b"], finalize=True), ctx)
        assert not made.is_error
        plan_id = str(made.data["plan_id"])
        synced = await task_tool.execute(TaskParams(action="sync", plan_id=plan_id), ctx)
        assert not synced.is_error, synced.output
        assert len(store.load_view().tasks) == 2
        # 未定稿计划 sync → 工具报错回喂（不抛异常带走整轮）
        draft = await plan_tool.execute(PlanParams(steps=["c"]), ctx)
        refused = await task_tool.execute(
            TaskParams(action="sync", plan_id=str(draft.data["plan_id"])), ctx
        )
        assert refused.is_error and "定稿" in refused.output

    asyncio.run(run())


def test_goal_round_stop_loss() -> None:
    g = goal.create_goal(thread_id="thread-1", objective="ship it", max_rounds=2)
    goal.start_goal(g.id)
    g = goal.record_round(g.id)
    assert g.round_count == 1 and g.status.value == "running"
    g = goal.record_round(g.id)
    assert g.round_count == 2 and g.status.value == "completed"  # 到上限自动完成


def test_orchestration_tool_descriptions_come_from_assets() -> None:
    """提示词入资产、禁止内联：plan/task 工具的描述取自随包 toml（防"放了资产没人用"）。"""
    from questor import prompts

    assert PlanTool().description == prompts.raw("plan_protocol")
    assert TaskTool().description == prompts.raw("task_protocol")
    assert PlanTool().description.strip()  # 非空


def test_goal_instruction_comes_from_asset() -> None:
    g = goal.create_goal(thread_id="thread-1", objective="ship it", max_rounds=3)
    text = goal.round_instruction(g)
    assert "ship it" in text  # 资产渲染注入了 objective


def test_board_edges_and_cycle_detection() -> None:
    a = tasks.create_task(title="a")
    b = tasks.create_task(title="b", depends_on=[a.id])
    view = board.build_board(store.load_view().tasks)
    assert any(edge.from_task_id == a.id and edge.to_task_id == b.id for edge in view.edges)
    assert board.has_cycle(view) is False
    # 造环：b 依赖 a、a 依赖 b
    store.update_task(a.model_copy(update={"depends_on": (b.id,)}))
    cyclic = board.build_board(store.load_view().tasks)
    assert board.has_cycle(cyclic) is True


def test_board_drops_dangling_edges() -> None:
    a = tasks.create_task(title="a", depends_on=["task-ghost"])
    view = board.build_board(store.load_view().tasks)
    assert view.tasks[0].id == a.id
    assert view.edges == ()
