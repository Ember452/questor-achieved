"""WorkspaceBoundary —— 唯一权威门的结构与 `mutates` 判定表。

# Ported from wuu@2026.10.6 internal/tools/boundary.go — pitfalls: B-50 B-51 B-52
# 逐段对应：``WorkspaceBoundary`` 结构 → :class:`WorkspaceBoundary`；
# ``StandardBoundary/ReadOnlyBoundary/UnconfinedBoundary`` → :func:`standard_boundary`
# / :func:`read_only_boundary` / :func:`unconfined_boundary`；``Check`` → :meth:`check`；
# ``mutates`` → :func:`mutates`；``boundaryError`` 的格式串 → :class:`BoundaryDenied`。

母本注释原文（决定了本模块一切形状）：*"The single authority gate in the system. It answers
exactly one question per tool call: is this action allowed to happen? The answer is derived
from reachability, never from trust. There is no approval, no human-in-the-loop, no per-tool
trust policy."* 因此：

- 本模块**没有** ask/审批结果，也**绝不**为等用户输入而阻塞（B-51）——那是
  :mod:`questor.limen.approval` 与 :mod:`questor.limen.authorizer` 的职责，由
  :mod:`questor.limen.chain` 按母本顺序串起来；
- 拒绝必带 ``error_kind`` + ``reason`` + ``model_next_action``（B-52），方言与
  ``protocol.md`` §7 一致；
- 路径约束**不在** :meth:`check` 内（母本由 ``Env.ResolvePath`` 落地），本仓由
  ``tools`` 侧以 Guard 注入——门本身不解析路径，避免同一个越权判断有两处实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from questor.schemas.model import PermissionMode, ToolKind

__all__ = [
    "BoundaryDenied",
    "Guard",
    "MUTATING_KINDS",
    "NON_MUTATING_KINDS",
    "ToolMeta",
    "WorkspaceBoundary",
    "mutates",
    "read_only_boundary",
    "standard_boundary",
    "unconfined_boundary",
]

_ERROR_KIND = "boundary_denied"


#: 母本 ``ToolInfo`` 的门内视图：判定只需要"这是什么类工具、这次调用改不改世界"。
#: ``read_only`` 是**本次调用**的分类（多动作工具用），不是工具级恒量——B-50 的粒度所在。
@dataclass(frozen=True)
class ToolMeta:
    name: str
    kind: ToolKind
    read_only: bool = False
    destructive: bool = False
    risk: str = ""
    reason: str = ""


# wuu ``boundary.go`` 的 mutation 判定表：以下工具类一律视为"改变世界"。
# ``browser`` 在表内，但母本注释明言：read-only 会话必须拦
# navigate/click/type 而放 observe/screenshot，靠的就是 :attr:`ToolMeta.read_only`
# 在查表**之前**短路（B-50）——顺序写反了就变成"整个浏览器工具全禁"或"全放"。
MUTATING_KINDS: frozenset[ToolKind] = frozenset(
    {
        "file",
        "shell",
        "test",
        "git",
        "agent",
        "process",
        "schedule",
        "mcp",
        "browser",
        "plugin",
    }
)

#: 明确"不算变更"的类。存在理由不是给 :func:`mutates` 查表（它查上表，未命中即非变更，
#: 照母本 ``default: return false``），而是让"新加一个工具类"必须在这里或上表出现一次：
#: 护栏 ``test_every_tool_kind_is_classified_by_the_gate`` 靠这两张表的并集覆盖全集。
#: 否则加词表而忘判定的后果从"静默落到兜底档"升级成"门永远判不到该类"。
NON_MUTATING_KINDS: frozenset[ToolKind] = frozenset(
    {"search", "discovery", "web", "session", "skill", "unknown", "meta"}
)


def mutates(info: ToolMeta) -> bool:
    """本次调用是否改变世界（母本 ``mutates(info)`` 直译，顺序不可改）。"""
    if info.read_only:
        return False
    return info.kind in MUTATING_KINDS


class BoundaryDenied(RuntimeError):
    """门拒绝；携带模型读得懂的 reason 与下一步（B-52）。

    ``str()`` 的形状照母本格式串：
    ``tool %q denied by workspace boundary: error_kind=boundary_denied``
    ``reason=%q model_next_action=%q``
    ——上游把它转成协议错误方言时不需要再猜字段。
    """

    def __init__(self, tool_name: str, reason: str, model_next_action: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        self.model_next_action = model_next_action
        self.error_kind = _ERROR_KIND
        super().__init__(
            f'tool "{tool_name}" denied by workspace boundary: error_kind={_ERROR_KIND} '
            f'reason="{reason}" model_next_action="{model_next_action}"'
        )


@runtime_checkable
class Guard(Protocol):
    """硬判扩展点：只回答"允许吗"，绝不变成审批（B-51）。

    实现方不得阻塞等输入、不得返回 ask；抛 :class:`BoundaryDenied` 即拒绝。
    """

    def check(self, info: ToolMeta, arguments: dict[str, object]) -> None: ...


_READ_ONLY_REASON = "this agent is read-only; it may observe but not modify"
_READ_ONLY_NEXT = "use read-only tools, or tell the user this agent cannot make changes"


@dataclass(frozen=True)
class WorkspaceBoundary:
    """``{Enforce, AllowMutations, Guards}`` 三元组（母本同名同序）。"""

    enforce: bool
    allow_mutations: bool
    guards: tuple[Guard, ...] = field(default=())

    def check(self, info: ToolMeta, arguments: dict[str, object]) -> None:
        """只读闸先决，再跑 Guard 链；命中即抛，层间不合并回溯（B-34）。"""
        if not self.allow_mutations and mutates(info):
            raise BoundaryDenied(info.name, _READ_ONLY_REASON, _READ_ONLY_NEXT)
        for guard in self.guards:
            # 母本对 nil guard 直接 continue（L55-57）：装配期占位不该炸运行时
            if guard is None:  # pragma: no cover - 防御性，装配不产 None
                continue
            guard.check(info, arguments)


# 三档构造器：与 matrix.MODE_BOUNDARIES 同源（表是数据，这里是母本形状的入口）。
def standard_boundary(*guards: Guard) -> WorkspaceBoundary:
    """默认档：可达根内全权、无审批（路径约束由注入的 Guard/ResolvePath 承担）。"""
    return WorkspaceBoundary(enforce=True, allow_mutations=True, guards=tuple(guards))


def read_only_boundary(*guards: Guard) -> WorkspaceBoundary:
    """只读档：拒一切变更，读仍受约束。"""
    return WorkspaceBoundary(enforce=True, allow_mutations=False, guards=tuple(guards))


def unconfined_boundary(*guards: Guard) -> WorkspaceBoundary:
    """逃生阀：解除路径约束；**敏感守卫与脱敏不随之解除**（B-54，故仍收 guards）。"""
    return WorkspaceBoundary(enforce=False, allow_mutations=True, guards=tuple(guards))


#: 档位 → 构造器（B-33：表驱动，不散 if/else）。守卫由装配方注入，故此处给空链。
_BUILDERS = {
    PermissionMode.READ_ONLY: read_only_boundary,
    PermissionMode.STANDARD: standard_boundary,
    PermissionMode.UNCONFINED: unconfined_boundary,
}


def boundary_for_mode(mode: PermissionMode, *guards: Guard) -> WorkspaceBoundary:
    """按档位取边界并注入守卫链；未知模式显式 KeyError（枚举兜底，不静默降级）。"""
    return _BUILDERS[mode](*guards)
