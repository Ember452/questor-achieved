"""验收状态机的唯一迁移入口（data-model §3.2，ADR-0029）。

镜像 `transitions.py`（任务状态机）的纪律：`AcceptanceStatus` 的迁移只允许经本模块的
白名单裁决，旁路写入视为契约破坏（架构测试 + store 边界双重强制）。本模块不得被
`orchestration` 之外的模块 import——推进验收态请调 `store.transition_acceptance`。

与任务状态机（§3.3）的分工：任务态管"执行到哪一步"，验收态管"结论 verdict"；二者在
`report`（executing → reported → verified | regressed）处交汇。`verified` 为终态；
`regressed` 可经打回重做再回 `executing`（与任务 reviewed → executing 同调）。
"""

from __future__ import annotations

from questor.schemas.model import AcceptanceStatus

# 白名单表：键 = 当前验收态，值 = 允许的目标态集合。逐字对齐 data-model §3.2 v1.4。
# 需求改版作废（重置为 proposed）不在此表内——它由 `acceptance.invalidated` 记录经领域规则
# 直接重置，是"作废"而非"迁移"，故走 store._apply_invalidation 而非本白名单。
_ALLOWED: dict[AcceptanceStatus, frozenset[AcceptanceStatus]] = {
    AcceptanceStatus.PROPOSED: frozenset({AcceptanceStatus.ACCEPTED_BY_USER}),
    AcceptanceStatus.ACCEPTED_BY_USER: frozenset({AcceptanceStatus.EXECUTING}),
    AcceptanceStatus.EXECUTING: frozenset({AcceptanceStatus.REPORTED}),
    AcceptanceStatus.REPORTED: frozenset({AcceptanceStatus.VERIFIED, AcceptanceStatus.REGRESSED}),
    AcceptanceStatus.REGRESSED: frozenset({AcceptanceStatus.EXECUTING}),
    AcceptanceStatus.VERIFIED: frozenset(),
}

_TERMINAL: frozenset[AcceptanceStatus] = frozenset({AcceptanceStatus.VERIFIED})


class InvalidAcceptanceTransition(Exception):
    """白名单之外的验收态迁移企图——一律拒绝，不猜、不静默修正。"""

    def __init__(self, current: AcceptanceStatus, target: AcceptanceStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"非法验收状态迁移：{current.value} → {target.value}")


def transition(current: AcceptanceStatus, target: AcceptanceStatus) -> AcceptanceStatus:
    """校验并放行一次验收态迁移；白名单之外抛 :class:`InvalidAcceptanceTransition`。"""
    if target not in _ALLOWED[current]:
        raise InvalidAcceptanceTransition(current, target)
    return target


def is_terminal(status: AcceptanceStatus) -> bool:
    """是否终态（`verified` 之后无常规迁移；需求改版作废另计）。"""
    return status in _TERMINAL


def allowed_targets(current: AcceptanceStatus | str) -> frozenset[AcceptanceStatus]:
    """当前验收态的合法目标集（未知状态返回空集——fail closed）。"""
    try:
        key = AcceptanceStatus(current)
    except ValueError:
        return frozenset()
    return _ALLOWED.get(key, frozenset())
