"""编排门：破坏性编排动作的前置裁决，返回**结构化错误载荷**而非异常（B-43）。

与 limen 的分层：limen 是**写域权限门**（磁盘/进程边界），编排门是**领域门**
（先有计划、先有授权）。两层职责分开（behavior-orchestration-ef §2）。

为什么返回载荷而不是抛异常：门要告诉模型"这一步先别做、去做哪个前置动作"——
异常会变成"整轮失败"或"静默失败"，而结构化 `{error_code, message, hint}` 是
模型可读、可重试的方言（wuu/limen 同调）。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "EXEC_AUTHORIZATION_ACTIONS",
    "PLAN_REDUNDANT_SETUP_ACTIONS",
    "PLAN_REQUIRED_ACTIONS",
    "GateResult",
    "evaluate",
]

#: 须先有落库 Plan 的编排动作（工具返回错误，而非中间件注入拦截）
PLAN_REQUIRED_ACTIONS: frozenset[str] = frozenset(
    {"create_task", "create_subtask", "set_task_planned"}
)
#: Plan 步骤已同步子任务后，禁止再批量建任务（防重复建）
PLAN_REDUNDANT_SETUP_ACTIONS: frozenset[str] = frozenset({"create_task_batch"})
#: 须用户「开始执行」授权的动作（审批只能收紧，不能提权）
EXEC_AUTHORIZATION_ACTIONS: frozenset[str] = frozenset(
    {"start_execution", "retry_subtask", "interrupt_subtask", "steer_subtask", "complete_subtask"}
)


@dataclass(frozen=True)
class GateResult:
    """门裁决结果；`allowed=False` 时带结构化载荷（模型可读、可重试）。"""

    allowed: bool
    error_code: str | None = None
    message: str = ""
    hint: str = ""

    def payload(self) -> dict[str, str]:
        """结构化错误载荷（error_code / message / hint）；放行时返回空 dict。"""
        if self.allowed:
            return {}
        return {
            "error_code": self.error_code or "invalid_params",
            "message": self.message,
            "hint": self.hint,
        }


def evaluate(
    action: str,
    *,
    has_plan: bool = False,
    plan_subtasks_synced: bool = False,
    authorized: bool = False,
) -> GateResult:
    """裁决一次编排动作；非受限动作直接放行（非严格路径不拦）。"""
    if action in PLAN_REQUIRED_ACTIONS and not has_plan:
        return GateResult(
            allowed=False,
            error_code="need_plan_first",
            message=f"动作 {action!r} 需要先落库一份计划",
            hint="先调用 plan 工具落库计划，再建任务",
        )
    if action in PLAN_REDUNDANT_SETUP_ACTIONS and plan_subtasks_synced:
        return GateResult(
            allowed=False,
            error_code="plan_subtasks_already_synced",
            message="计划步骤已同步为子任务，禁止重复批量建任务",
            hint="用 task 工具派发执行（start），不要重复建任务",
        )
    if action in EXEC_AUTHORIZATION_ACTIONS and not authorized:
        return GateResult(
            allowed=False,
            error_code="need_execution_authorization",
            message=f"动作 {action!r} 需要用户「开始执行」授权",
            hint="待用户确认「开始执行」后重试",
        )
    return GateResult(allowed=True)
