"""编排服务：`tools.ports.OrchestrationPort` 的默认实现（在领域动作前过编排门）。

为什么单独一层：`plan.py`/`tasks.py` 只做"能不能做"，门（`gate.py`）只做"准不准做"，
把两者组合并抛 `OrchestrationGateError` 的是本层——它是工具侧与 serve 侧共用的入口，
保证**任何路径都过同一道门**（与 limen 单点入口同调）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from questor.orchestration import store, tasks
from questor.orchestration.gate import evaluate
from questor.orchestration.plan import finalize_plan, propose_plan, revise_plan
from questor.schemas.orchestration import (
    OrchestrationGateError,
    Plan,
    PlanStatus,
    Task,
)

__all__ = ["OrchestrationService"]


class OrchestrationService:
    """默认实现：`authorizer(task_id) -> bool` 决定某个任务是否已获"开始执行"授权。"""

    def __init__(
        self,
        *,
        authorizer: Callable[[str], bool] | None = None,
        thread_id: str | None = None,
    ) -> None:
        self._authorizer: Callable[[str], bool] = authorizer or (lambda _task_id: False)
        self._thread_id = thread_id

    # ---- OrchestrationPort ----

    def propose_plan(
        self,
        *,
        steps: Sequence[str],
        thread_id: str | None = None,
        goal_id: str | None = None,
        plan_id: str | None = None,
        finalize: bool = False,
    ) -> Plan:
        if plan_id:
            plan = revise_plan(plan_id, steps=list(steps))
        else:
            plan = propose_plan(
                steps=list(steps), thread_id=thread_id or self._thread_id, goal_id=goal_id
            )
        if finalize:
            plan = finalize_plan(plan.id)
        return plan

    def create_task(
        self,
        *,
        title: str,
        thread_id: str | None = None,
        goal_id: str | None = None,
        plan_id: str | None = None,
        depends_on: Sequence[str] = (),
    ) -> Task:
        result = evaluate("create_task", has_plan=self._has_plan(plan_id))
        if not result.allowed:
            raise OrchestrationGateError(
                result.error_code or "invalid_params", result.message, result.hint
            )
        return tasks.create_task(
            title=title,
            thread_id=thread_id or self._thread_id,
            goal_id=goal_id,
            plan_id=plan_id,
            depends_on=list(depends_on),
            requirement_revision=self._requirement_revision(plan_id),
        )

    def start_task(self, task_id: str) -> Task:
        result = evaluate("start_execution", authorized=self._authorizer(task_id))
        if not result.allowed:
            raise OrchestrationGateError(
                result.error_code or "invalid_params", result.message, result.hint
            )
        return tasks.start_task(task_id)

    def sync_subtasks(self, *, plan_id: str) -> list[Task]:
        """按已定稿计划同步派生子任务（计划 D4：task 工具的 sync 动作）。

        未定稿在此就用模型可读的结构化方言拒绝，而不是漏存储层异常——
        领域不变式另在 `tasks.sync_subtasks_from_plan` 机械执行，两层同调。
        """
        result = evaluate("create_subtask", has_plan=self._has_plan(plan_id))
        if not result.allowed:
            raise OrchestrationGateError(
                result.error_code or "invalid_params", result.message, result.hint
            )
        current = next((p for p in store.load_view().plans if p.id == plan_id), None)
        if current is None or current.status is not PlanStatus.FINALIZED:
            raise OrchestrationGateError(
                "need_plan_first",
                f"计划 {plan_id} 未定稿，不能派生子任务",
                "先定稿计划（plan 工具 finalize=true）再 sync",
            )
        return tasks.sync_subtasks_from_plan(plan_id)

    # ---- 内部 ----

    def _has_plan(self, plan_id: str | None) -> bool:
        view = store.load_view()
        if plan_id is not None:
            return any(plan.id == plan_id for plan in view.plans)
        return bool(view.plans)

    def _requirement_revision(self, plan_id: str | None) -> int:
        if plan_id is None:
            return 1
        view = store.load_view()
        return next((plan.requirement_revision for plan in view.plans if plan.id == plan_id), 1)
