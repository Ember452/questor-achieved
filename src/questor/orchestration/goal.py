"""Goal：后台自驱长跑目标（data-model §2，ADR-0025）。

每轮 1–3 句指令、唯一结束信号、并发与时长上限（EvoFlow goal_service 形状）。
本模块只管理 Goal 的生命周期与轮次记账；**跑哪一轮由调用方（serve/vigilia）派发**，
`round_instruction` 从提示词资产取（禁止在代码里内联提示词）。
"""

from __future__ import annotations

import uuid

from questor.orchestration import store
from questor.prompts import render
from questor.schemas.model import utc_timestamp_now
from questor.schemas.orchestration import Goal, GoalStatus

__all__ = [
    "create_goal",
    "fail_goal",
    "get_goal",
    "is_expired",
    "record_round",
    "round_instruction",
    "start_goal",
    "stop_goal",
]

#: Goal 状态迁移白名单（与任务状态机同纪律：非法迁移即拒）
_ALLOWED: dict[GoalStatus, frozenset[GoalStatus]] = {
    GoalStatus.IDLE: frozenset({GoalStatus.RUNNING, GoalStatus.CANCELLED}),
    GoalStatus.RUNNING: frozenset(
        {GoalStatus.PAUSED, GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.CANCELLED}
    ),
    GoalStatus.PAUSED: frozenset({GoalStatus.RUNNING, GoalStatus.CANCELLED}),
    GoalStatus.COMPLETED: frozenset(),
    GoalStatus.FAILED: frozenset({GoalStatus.RUNNING}),
    GoalStatus.CANCELLED: frozenset(),
}


def _move(goal: Goal, target: GoalStatus) -> Goal:
    if target not in _ALLOWED[goal.status]:
        raise store.OrchestrationStoreError(
            f"非法 Goal 状态迁移：{goal.status.value} → {target.value}"
        )
    return store.update_goal(
        goal.model_copy(update={"status": target, "updated_at": utc_timestamp_now()})
    )


def create_goal(
    *,
    thread_id: str,
    objective: str,
    max_rounds: int | None = None,
    deadline: str | None = None,
) -> Goal:
    stamp = utc_timestamp_now()
    goal = Goal(
        id=f"goal-{uuid.uuid4().hex[:12]}",
        thread_id=thread_id,
        objective=objective,
        status=GoalStatus.IDLE,
        max_rounds=max_rounds,
        round_count=0,
        deadline=deadline,
        created_at=stamp,
        updated_at=stamp,
    )
    return store.add_goal(goal)


def get_goal(goal_id: str) -> Goal:
    for goal in store.load_view().goals:
        if goal.id == goal_id:
            return goal
    raise store.OrchestrationStoreError(f"目标 {goal_id} 不存在")


def start_goal(goal_id: str) -> Goal:
    return _move(get_goal(goal_id), GoalStatus.RUNNING)


def stop_goal(goal_id: str) -> Goal:
    return _move(get_goal(goal_id), GoalStatus.CANCELLED)


def fail_goal(goal_id: str) -> Goal:
    """到 deadline/起轮失败：RUNNING → FAILED（仍经白名单，不另开状态写入口）。"""
    return _move(get_goal(goal_id), GoalStatus.FAILED)


def record_round(goal_id: str) -> Goal:
    """记一轮结束：`round_count` +1；到 `max_rounds` 即自动完成（长跑止损）。

    只有 RUNNING 可记轮：轮次记账也是状态写路径，不得绕开 :func:`_move` 白名单
    （否则已停/空闲的 Goal 会被旁门翻成 completed，与任务状态机同一纪律）。
    """
    goal = get_goal(goal_id)
    if goal.status is not GoalStatus.RUNNING:
        raise store.OrchestrationStoreError(
            f"只有进行中的 Goal 可记轮（当前：{goal.status.value}）"
        )
    next_count = goal.round_count + 1
    bumped = goal.model_copy(update={"round_count": next_count, "updated_at": utc_timestamp_now()})
    if goal.max_rounds is not None and next_count >= goal.max_rounds:
        return _move(bumped, GoalStatus.COMPLETED)
    return store.update_goal(bumped)


def is_expired(goal: Goal, now: str) -> bool:
    """是否超过时长上限（UTC 时间戳字符串比较；`deadline` 为空视为无上限）。"""
    return goal.deadline is not None and now >= goal.deadline


def round_instruction(goal: Goal) -> str:
    """本轮下发给模型的指令（1–3 句；正文来自提示词资产 `goal_loop`）。"""
    return render(
        "goal_loop",
        objective=goal.objective,
        round=str(goal.round_count + 1),
        max_rounds=str(goal.max_rounds) if goal.max_rounds is not None else "∞",
    )
