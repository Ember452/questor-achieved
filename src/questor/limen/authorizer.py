"""Authorizer —— 门链最后一环：可选策略提供方，只能收紧、报错即拒。

# Ported from wuu@2026.10.6 internal/tools/authorization.go — pitfalls: B-131
# 对应：``AuthorizationRequest``→:class:`AuthorizationRequest`、``AuthorizationDecision``
# →:class:`AuthorizationDecision`、``Authorizer``→:class:`Authorizer`、
# ``authorizationDenied``→:class:`AuthorizationDenied`。

母本注释原文：*"The workspace boundary remains authoritative and cannot be elevated by an
authorizer decision."* 两条不可让的语义：

1. **位置在最后**（``toolkit.go::checkPermission`` L132-145）——boundary 与 Reviewer 已经
   判过，Authorizer 只能进一步限制，不能用来"给已被拒的调用放行"；
2. **fail closed**：provider 抛错 ⇒ 直接拒（``authorization provider unavailable``）；
   返回的 ``outcome`` **必须字面等于 ``"allow"``**，其他任何值（含空串、"ALLOW"、"approved"）
   都是拒绝。写成"非 deny 即允许"就把一个坏掉的策略提供方变成了默认放行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from questor.limen.boundary import ToolMeta
from questor.schemas.model import PermissionMode

__all__ = [
    "AuthorizationDenied",
    "AuthorizationRequest",
    "Authorizer",
    "enforce_authorizer",
]

_ERROR_KIND = "authorization_denied"
#: 唯一放行值：照母本 ``strings.TrimSpace(decision.Outcome) != "allow"``。
ALLOW_OUTCOME = "allow"


@dataclass(frozen=True)
class AuthorizationRequest:
    """母本 ``AuthorizationRequest`` 的字段集
    （SessionID/ActorID/CWD/PermissionMode/Tool/Arguments）。"""

    session_id: str
    actor_id: str
    cwd: str
    permission_mode: PermissionMode
    tool: ToolMeta
    arguments: str


@dataclass(frozen=True)
class AuthorizationDecision:
    outcome: str
    reason: str = ""


class AuthorizationDenied(RuntimeError):
    """Authorizer 拒绝（或不可用）。

    形状照母本格式串
    ``tool %q denied by authorization provider: error_kind=authorization_denied reason=%q``。
    """

    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        self.error_kind = _ERROR_KIND
        super().__init__(
            f'tool "{tool_name}" denied by authorization provider: '
            f"error_kind={_ERROR_KIND} reason={reason!r}"
        )


@runtime_checkable
class Authorizer(Protocol):
    """可选策略接缝：实现方可以问远程策略服务、可以查本地规则；**无权提权**。"""

    def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision: ...


def enforce_authorizer(authorizer: Authorizer | None, request: AuthorizationRequest) -> None:
    """跑 Authorizer 并把母本的三段判定翻成 Python 异常。

    ``authorizer is None`` → 放行（母本 L132-134：没接策略提供方时门不额外加戏）。
    """
    if authorizer is None:
        return
    try:
        decision = authorizer.authorize(request)
    except AuthorizationDenied:
        raise
    except Exception as exc:  # noqa: BLE001 - 任何 provider 故障都按"不可用"拒，绝不放行
        del exc
        raise AuthorizationDenied(request.tool.name, "authorization provider unavailable") from None
    if decision.outcome.strip() != ALLOW_OUTCOME:
        reason = (
            decision.reason.strip() or "the configured authorization provider denied this action"
        )
        raise AuthorizationDenied(request.tool.name, reason)
