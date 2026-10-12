"""Task：看板任务单元的创建、计划派生与状态推进（data-model §2/§3.3，ADR-0025）。

状态推进一律经 :func:`store.transition_task`（白名单唯一入口）；本模块只提供语义化
的名字（start/pause/resume/review/reject/complete/retry），不绕过状态机。
"""

from __future__ import annotations

import uuid

from questor.orchestration import store
from questor.orchestration.plan import get_plan
from questor.schemas.model import utc_timestamp_now
from questor.schemas.orchestration import (
    Plan,
    PlanStep,
    PlanStepStatus,
    Task,
    TaskAcceptance,
    TaskStatus,
)

__all__ = [
    "complete_task",
    "create_task",
    "get_task",
    "mark_step_done",
    "pause_task",
    "reject_task",
    "resume_task",
    "retry_task",
    "review_task",
    "start_task",
    "sync_subtasks_from_plan",
]


def _tid() -> str:
    return f"task-{uuid.uuid4().hex[:12]}"


def create_task(
    *,
    title: str,
    thread_id: str | None = None,
    goal_id: str | None = None,
    plan_id: str | None = None,
    parent_task_id: str | None = None,
    depends_on: list[str] | None = None,
    requirement_revision: int = 1,
    status: TaskStatus = TaskStatus.PENDING,
) -> Task:
    """新建任务。调用方负责先过编排门（无计划时建任务应被 `need_plan_first` 拒）。"""
    stamp = utc_timestamp_now()
    task = Task(
        id=_tid(),
        thread_id=thread_id,
        goal_id=goal_id,
        plan_id=plan_id,
        title=title,
        status=status,
        parent_task_id=parent_task_id,
        depends_on=tuple(depends_on or ()),
        acceptance=TaskAcceptance(status="proposed", requirement_revision=requirement_revision),
        created_at=stamp,
        updated_at=stamp,
    )
    return store.add_task(task)


def get_task(task_id: str) -> Task:
    for task in store.load_view().tasks:
        if task.id == task_id:
            return task
    raise store.TaskNotFound(task_id)


def sync_subtasks_from_plan(plan_id: str) -> list[Task]:
    """把**已定稿**计划的步骤同步派生为子任务，并回填 step.task_id。

    这是编排门 `plan_subtasks_already_synced` 的来源：同步过一次后再批量建任务即被拒。
    """
    plan = get_plan(plan_id)
    created: list[Task] = []
    steps: list[PlanStep] = []
    for step in plan.steps:
        if step.task_id:
            steps.append(step)
            continue
        task = create_task(
            title=step.title,
            thread_id=plan.thread_id,
            goal_id=plan.goal_id,
            plan_id=plan.id,
            requirement_revision=plan.requirement_revision,
        )
        created.append(task)
        steps.append(step.model_copy(update={"task_id": task.id}))
    if created:
        store.update_plan(
            plan.model_copy(update={"steps": tuple(steps), "updated_at": utc_timestamp_now()})
        )
    return created


def start_task(task_id: str, *, run_id: str | None = None) -> Task:
    """开始执行（pending/planned → executing）；绑定 run_id（若有）。"""
    moved = store.transition_task(task_id, TaskStatus.EXECUTING)
    if run_id is not None:
        moved = store.update_task(moved.model_copy(update={"run_id": run_id}))
    return moved


def pause_task(task_id: str) -> Task:
    return store.transition_task(task_id, TaskStatus.PAUSED)


def resume_task(task_id: str) -> Task:
    return store.transition_task(task_id, TaskStatus.EXECUTING)


def review_task(task_id: str) -> Task:
    """执行完成待审（executing → reviewed）——任务总结卡在此状态出现。"""
    return store.transition_task(task_id, TaskStatus.REVIEWED)


def reject_task(task_id: str) -> Task:
    """打回重做（reviewed → executing）——M4 出口链的一环。"""
    return store.transition_task(task_id, TaskStatus.EXECUTING)


def retry_task(task_id: str) -> Task:
    """失败重试（failed → executing）。"""
    return store.transition_task(task_id, TaskStatus.EXECUTING)


def complete_task(task_id: str) -> Task:
    """验收通过（reviewed/executing → completed）。"""
    return store.transition_task(task_id, TaskStatus.COMPLETED)


def mark_step_done(plan: Plan, step_id: str) -> Plan:
    """把计划某步骤标记完成（派生任务的进度回写）。"""
    steps = tuple(
        step.model_copy(update={"status": PlanStepStatus.DONE}) if step.id == step_id else step
        for step in plan.steps
    )
    return store.update_plan(
        plan.model_copy(update={"steps": steps, "updated_at": utc_timestamp_now()})
    )
