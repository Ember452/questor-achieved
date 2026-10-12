"""tools 定义的编排端口（R1 端口模式：内核定义 port、上层注册 adapter）。

`tools` 的 import 白名单不含 `orchestration`（structure §5），但模型需要"提议计划 / 建任务"
这两个编排动作——否则编排门 `need_plan_first` 没有真实调用方（违反"不做无消费者形状"）。

解决：port 定义在 `tools`（只收 `schemas` 类型），**实现住在 `orchestration`**，
装配点（`serve/assembly`）注入到 `ToolContext.orchestration`。矩阵不越界，`tools` 永远
不认识编排域；将来的多 Agent 派发、外部引擎（M6）复用同一个 port。

方法失败时抛 `schemas.orchestration.OrchestrationGateError`（结构化方言），
`tools` 捕获转工具错误、`serve` 捕获转 ProtocolError——同一份方言，两种出口。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from questor.schemas.orchestration import Plan, Task

__all__ = ["OrchestrationPort"]


@runtime_checkable
class OrchestrationPort(Protocol):
    """编排动作的最小端口面（M4：计划与任务两件事）。"""

    def propose_plan(
        self,
        *,
        steps: Sequence[str],
        thread_id: str | None = None,
        goal_id: str | None = None,
        plan_id: str | None = None,
        finalize: bool = False,
    ) -> Plan:
        """提议或修订一份计划；门拒绝时抛 :class:`OrchestrationGateError`。"""
        ...

    def create_task(
        self,
        *,
        title: str,
        thread_id: str | None = None,
        goal_id: str | None = None,
        plan_id: str | None = None,
        depends_on: Sequence[str] = (),
    ) -> Task:
        """建一个看板任务；无落库计划时抛 :class:`OrchestrationGateError`（`need_plan_first`）。"""
        ...

    def start_task(self, task_id: str) -> Task:
        """开始执行一个任务；未授权时抛 :class:`OrchestrationGateError`。"""
        ...

    def sync_subtasks(self, *, plan_id: str) -> Sequence[Task]:
        """按**已定稿**计划同步派生子任务（计划 D4）。

        无落库计划抛 :class:`OrchestrationGateError`（`need_plan_first`）；
        未定稿抛同方言（模型可读可重试），已同步的步骤不重复派生。
        """
        ...
