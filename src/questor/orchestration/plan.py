"""Plan：先澄清 → 可修订 → 定稿才执行（data-model §2，ADR-0025）。

关键语义：`requirement_revision` 递增即**自动作废**既有验收——作废表现为追加一条
`acceptance.invalidated` 记录，不改写历史（append-only）。
"""

from __future__ import annotations

import uuid

from questor.orchestration import store
from questor.schemas.model import utc_timestamp_now
from questor.schemas.orchestration import Plan, PlanStatus, PlanStep

__all__ = ["finalize_plan", "get_plan", "plan_task_ids", "propose_plan", "revise_plan"]


def _pid() -> str:
    return f"plan-{uuid.uuid4().hex[:12]}"


def propose_plan(
    *,
    steps: list[str],
    thread_id: str | None = None,
    goal_id: str | None = None,
    requirement_revision: int = 1,
) -> Plan:
    """落库一份草案计划（DRAFTING）；步骤从标题列表构造。"""
    stamp = utc_timestamp_now()
    plan = Plan(
        id=_pid(),
        thread_id=thread_id,
        goal_id=goal_id,
        requirement_revision=requirement_revision,
        status=PlanStatus.DRAFTING,
        steps=tuple(
            PlanStep(id=f"step-{index + 1}", title=title) for index, title in enumerate(steps)
        ),
        created_at=stamp,
        updated_at=stamp,
    )
    return store.add_plan(plan)


def revise_plan(plan_id: str, *, steps: list[str], requirement_revision: int | None = None) -> Plan:
    """修订计划：步骤重写、状态回到 PROPOSED、需求修订号递增并作废旧验收。

    `requirement_revision` 缺省为当前 +1；递增时对**已派生任务**调用
    :func:`store.invalidate_acceptances`（追加作废记录）。
    """
    view = store.load_view()
    current = get_plan(plan_id)
    new_revision = requirement_revision or (current.requirement_revision + 1)
    stamp = utc_timestamp_now()
    revised = current.model_copy(
        update={
            "steps": tuple(
                PlanStep(id=f"step-{index + 1}", title=title) for index, title in enumerate(steps)
            ),
            "status": PlanStatus.PROPOSED,
            "requirement_revision": new_revision,
            "updated_at": stamp,
        }
    )
    if new_revision > current.requirement_revision:
        derived = plan_task_ids(view, plan_id)
        store.invalidate_acceptances(task_ids=derived, requirement_revision=new_revision)
    return store.update_plan(revised)


def finalize_plan(plan_id: str) -> Plan:
    """定稿计划（FINALIZED）——定稿后其步骤可同步派生 Task（tasks.sync_subtasks_from_plan）。"""
    current = get_plan(plan_id)
    finalized = current.model_copy(
        update={"status": PlanStatus.FINALIZED, "updated_at": utc_timestamp_now()}
    )
    return store.update_plan(finalized)


def get_plan(plan_id: str) -> Plan:
    for plan in store.load_view().plans:
        if plan.id == plan_id:
            return plan
    raise store.OrchestrationStoreError(f"计划 {plan_id} 不存在")


def plan_task_ids(view: store.OrchestrationView, plan_id: str) -> list[str]:
    """某计划已派生的任务 id（作废验收时按此定位）。"""
    return [task.id for task in view.tasks if task.plan_id == plan_id]
