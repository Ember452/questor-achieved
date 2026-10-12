"""模型侧编排工具（M4）：`plan`（提议/修订/定稿计划）与 `task`（建任务/开始执行）。

两个工具都经 :class:`questor.tools.ports.OrchestrationPort` 调用——`tools` 不认识
`orchestration`（矩阵），编排门拒绝以 :class:`OrchestrationGateError` 结构化方言抛出，
本模块捕获后转成工具错误回喂模型（B-43：模型可读、可重试）。
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel, Field

from questor.prompts import raw as prompt_raw
from questor.schemas.orchestration import OrchestrationGateError
from questor.tools.base import Tool, ToolContext, ToolResult
from questor.tools.ports import OrchestrationPort

__all__ = ["PlanTool", "TaskTool"]


class PlanParams(BaseModel):
    """提议一份计划；给 `plan_id` 即修订该计划。"""

    steps: list[str] = Field(default_factory=list)
    plan_id: str | None = None
    finalize: bool = False


class PlanTool(Tool):
    name = "plan"
    #: 由 __init__ 从资产注入（plan_protocol.toml）；类级只占位，避免内联提示词
    description = ""
    kind = "meta"
    mutates = True
    concurrency_safe = False
    expects_path = False
    params_model = PlanParams

    def __init__(self) -> None:
        # 提示词入资产、禁止内联（prompts 纪律）：描述取自随包发布的 plan_protocol.toml
        self.description = prompt_raw("plan_protocol")

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, PlanParams)
        port: OrchestrationPort | None = ctx.orchestration
        if port is None:
            return ToolResult(
                output="plan 不可用：本会话未装配编排端口（orchestration 未启用）",
                is_error=True,
            )
        if not params.steps:
            return ToolResult(output="plan 需要至少一个步骤标题", is_error=True)
        try:
            plan = await asyncio.to_thread(
                port.propose_plan,
                steps=params.steps,
                thread_id=ctx.thread_id,
                plan_id=params.plan_id,
                finalize=params.finalize,
            )
        except OrchestrationGateError as exc:
            return ToolResult(
                output=f"{exc.error_code}: {exc.message} (hint: {exc.hint})",
                is_error=True,
            )
        return ToolResult(
            output=(
                f"plan {plan.id} [{plan.status.value}] rev={plan.requirement_revision}\n"
                + "\n".join(f"  - {step.id} {step.title}" for step in plan.steps)
            ),
            data={"plan_id": plan.id, "requirement_revision": plan.requirement_revision},
        )


class TaskParams(BaseModel):
    """建任务、同步子任务或开始执行（其余状态由用户经 serve 推进）。"""

    action: Literal["create", "sync", "start"] = "create"
    title: str | None = None
    task_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    plan_id: str | None = None


class TaskTool(Tool):
    name = "task"
    #: 由 __init__ 从资产注入（task_protocol.toml）；类级只占位，避免内联提示词
    description = ""
    kind = "meta"
    mutates = True
    concurrency_safe = False
    expects_path = False
    params_model = TaskParams

    def __init__(self) -> None:
        self.description = prompt_raw("task_protocol")

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, TaskParams)
        port: OrchestrationPort | None = ctx.orchestration
        if port is None:
            return ToolResult(
                output="task 不可用：本会话未装配编排端口（orchestration 未启用）",
                is_error=True,
            )
        try:
            if params.action == "sync":
                if not params.plan_id:
                    return ToolResult(output="task sync 需要 plan_id", is_error=True)
                derived = await asyncio.to_thread(port.sync_subtasks, plan_id=params.plan_id)
                return ToolResult(
                    output=(
                        f"synced {len(derived)} task(s) from plan {params.plan_id}\n"
                        + "\n".join(f"  - {t.id} [{t.status.value}] {t.title}" for t in derived)
                    ),
                    data={"task_ids": [t.id for t in derived]},
                )
            if params.action == "create":
                if not params.title:
                    return ToolResult(output="task create 需要 title", is_error=True)
                task = await asyncio.to_thread(
                    port.create_task,
                    title=params.title,
                    thread_id=ctx.thread_id,
                    plan_id=params.plan_id,
                    depends_on=params.depends_on,
                )
            else:
                if not params.task_id:
                    return ToolResult(output="task start 需要 task_id", is_error=True)
                task = await asyncio.to_thread(port.start_task, params.task_id)
        except OrchestrationGateError as exc:
            return ToolResult(
                output=f"{exc.error_code}: {exc.message} (hint: {exc.hint})",
                is_error=True,
            )
        return ToolResult(
            output=f"task {task.id} [{task.status.value}] {task.title}",
            data={"task_id": task.id, "status": task.status.value},
        )
