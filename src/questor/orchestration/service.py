"""编排服务：`tools.ports.OrchestrationPort` 的默认实现（在领域动作前过编排门）。

为什么单独一层：`plan.py`/`tasks.py` 只做"能不能做"，门（`gate.py`）只做"准不准做"，
把两者组合并抛 `OrchestrationGateError` 的是本层——它是工具侧与 serve 侧共用的入口，
保证**任何路径都过同一道门**（与 limen 单点入口同调）。
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence

from questor.evidence import evidence_card, verdict_counts, verify_claims
from questor.orchestration import store, tasks
from questor.orchestration.gate import evaluate
from questor.orchestration.plan import finalize_plan, propose_plan, revise_plan
from questor.orchestration.transitions import InvalidTaskTransition
from questor.schemas.model import AcceptanceStatus
from questor.schemas.orchestration import (
    ClaimedCheck,
    EvidenceSubjectType,
    EvidenceVerdict,
    OrchestrationGateError,
    Plan,
    PlanStatus,
    Task,
    TaskStatus,
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
        #: 宿主事件循环发布器（serve 在起轮前经 `bind_publisher` 注入）；未接则不广报
        #: （诚实：stdio/CLI 无 fanout 时 report 仍落盘与驱动验收态，只是不实时推送）。
        self._publisher: Callable[[str, dict], None] | None = None

    def bind_publisher(self, publisher: Callable[[str, dict], None]) -> None:
        """宿主接上通知出口（形态同 `Engine.attach_inbox`，不改 `create_engine` 契约）。

        publisher 在 report 的工作线程里被调；**跳回事件循环的线程安全由 publisher 负责**。
        """
        self._publisher = publisher

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

    def report_task(self, task_id: str, checks: Sequence[ClaimedCheck]) -> Task:
        """上报声称并核对（M5，ADR-0029）：落 `Evidence` + 驱动验收态 + 进待审。

        只读消费该任务线程的录得结果逐条核对；无记录/绑错 `tool_use_id` 一律
        `unverified`。全 `verified` 才进 `verified`，否则 `regressed`（"没有复跑也不轻信"）。
        任务不在执行中（验收态未到 `executing`）以模型可读的结构化方言拒绝。
        """
        try:
            task = tasks.get_task(task_id)
        except store.TaskNotFound as exc:
            raise OrchestrationGateError(
                "invalid_params", f"任务 {task_id} 不存在", "先建任务再上报"
            ) from exc
        if task.acceptance.status is not AcceptanceStatus.EXECUTING:
            raise OrchestrationGateError(
                "invalid_acceptance_state",
                f"任务 {task_id} 验收态为 {task.acceptance.status.value}，report 需在执行中",
                "先经用户授权开始执行（task/start authorized=true），再上报声称",
            )
        items = verify_claims(
            task.thread_id or "",
            checks,
            subject_type=EvidenceSubjectType.TASK,
            subject_id=task_id,
        )
        ev_ids: list[str] = []
        for ev in items:
            store.add_evidence(ev)
            ev_ids.append(ev.id)
        store.transition_acceptance(task_id, AcceptanceStatus.REPORTED, evidence_ids=tuple(ev_ids))
        all_ok = bool(items) and all(ev.verdict is EvidenceVerdict.VERIFIED for ev in items)
        final = AcceptanceStatus.VERIFIED if all_ok else AcceptanceStatus.REGRESSED
        moved = store.transition_acceptance(task_id, final)
        # 任务态：executing → reviewed（进看板待验收列）；已不在 executing 则幂等跳过
        with contextlib.suppress(InvalidTaskTransition):
            moved = store.transition_task(task_id, TaskStatus.REVIEWED)
        if self._publisher is not None:
            cards = [evidence_card(ev).model_dump(mode="json") for ev in items]
            self._publisher(
                "evidence/reported",
                {
                    "task_id": task_id,
                    "acceptance_status": moved.acceptance.status.value,
                    "verdicts": verdict_counts(items),
                    "evidence": cards,
                },
            )
            self._publisher(
                "task/status",
                {"task_id": moved.id, "status": moved.status.value, "title": moved.title},
            )
        return moved

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
