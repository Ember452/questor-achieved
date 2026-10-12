"""编排任务状态机的唯一迁移入口（data-model §3.3，ADR-0025）。

状态迁移只允许经本模块的白名单函数驱动，旁路写入视为契约破坏（架构测试强制：
tests/architecture/test_orchestration_transition_single_entry.py 断言只有 orchestration 可
import 本模块）。本模块不得被 orchestration 之外的任何模块 import——需要推进状态时调用
orchestration.store.transition_task。
"""

from __future__ import annotations

from questor.schemas.orchestration import TaskStatus

# 白名单表：键 = 当前状态，值 = 允许的目标状态。逐字对齐 data-model §3.3 v1.3：
# reviewed → executing 即"打回重做"（M4 出口链一环）；completed/cancelled 是终态。
# 键用 str 存放 TaskStatus（StrEnum 本身即 str），以便未知状态的原始字符串也能查询。
_ALLOWED: dict[str, frozenset[TaskStatus]] = {
    TaskStatus.INBOX: frozenset({TaskStatus.PENDING, TaskStatus.COMPLETED, TaskStatus.CANCELLED}),
    TaskStatus.PENDING: frozenset(
        {TaskStatus.PLANNING, TaskStatus.PLANNED, TaskStatus.EXECUTING, TaskStatus.CANCELLED}
    ),
    TaskStatus.PLANNING: frozenset({TaskStatus.PLANNED, TaskStatus.FAILED, TaskStatus.CANCELLED}),
    TaskStatus.PLANNED: frozenset(
        {TaskStatus.PLANNING, TaskStatus.EXECUTING, TaskStatus.CANCELLED}
    ),
    TaskStatus.EXECUTING: frozenset(
        {
            TaskStatus.PAUSED,
            TaskStatus.COMPLETED,
            TaskStatus.REVIEWED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.PAUSED: frozenset({TaskStatus.EXECUTING, TaskStatus.CANCELLED}),
    TaskStatus.REVIEWED: frozenset(
        {TaskStatus.COMPLETED, TaskStatus.EXECUTING, TaskStatus.CANCELLED}
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset({TaskStatus.EXECUTING}),
    TaskStatus.CANCELLED: frozenset(),
}

_TERMINAL: frozenset[TaskStatus] = frozenset({TaskStatus.COMPLETED, TaskStatus.CANCELLED})


class InvalidTaskTransition(Exception):
    """白名单之外的迁移企图——一律拒绝，不猜、不静默修正。"""

    def __init__(self, current: TaskStatus, target: TaskStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"非法任务状态迁移：{current.value} → {target.value}")


def transition(current: TaskStatus, target: TaskStatus) -> TaskStatus:
    """校验并放行一次任务状态迁移；白名单之外抛 :class:`InvalidTaskTransition`。"""
    if target not in _ALLOWED[current]:
        raise InvalidTaskTransition(current, target)
    return target


def is_terminal(status: TaskStatus) -> bool:
    """是否终态（终态之后不允许任何迁移）。"""
    return status in _TERMINAL


def allowed_targets(current: TaskStatus | str) -> frozenset[TaskStatus]:
    """当前状态的合法目标集（未知状态返回空集——fail closed）。

    参数放宽到 `str` 以便调用方在校验前用原始值查询（回放含未知状态时也走这里）。
    """
    return _ALLOWED.get(current, frozenset())
