"""运行状态机的唯一迁移入口（data-model §3.1 v1.1，ADR-0014）。

状态迁移只允许经本模块的白名单函数驱动，旁路写入视为契约破坏（架构测试强制：
tests/architecture/test_status_transition_single_entry.py 断言只有 gesta 可以 import 本模块）。
本模块不得被 gesta 之外的任何模块 import——需要推进状态时调用 gesta.transition_run。
"""

from __future__ import annotations

from questor.schemas.model import RunStatus

# 白名单表：键 = 当前状态，值 = 允许的目标状态。逐字对齐 data-model §3.1 v1.1：
# 终态仅 completed|failed|cancelled；steered/waiting 是 running 的旁态，旁态间迁移
# 必须经由 running；queued 可直接取消（ADR-0014），不得伪造 running 起点。
_ALLOWED: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.STEERED,
            RunStatus.WAITING,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.STEERED: frozenset({RunStatus.RUNNING}),
    RunStatus.WAITING: frozenset({RunStatus.RUNNING}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}

_TERMINAL: frozenset[RunStatus] = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
)


class InvalidTransition(Exception):
    """白名单之外的迁移企图——一律拒绝，不猜、不静默修正。"""

    def __init__(self, current: RunStatus, target: RunStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"非法状态迁移：{current.value} → {target.value}")


def transition(current: RunStatus, target: RunStatus) -> RunStatus:
    """校验并放行一次状态迁移；白名单之外抛 :class:`InvalidTransition`。"""
    if target not in _ALLOWED[current]:
        raise InvalidTransition(current, target)
    return target


def is_terminal(status: RunStatus) -> bool:
    """是否终态（终态之后不允许任何迁移）。"""
    return status in _TERMINAL
