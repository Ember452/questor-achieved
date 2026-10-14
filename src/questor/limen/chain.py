"""PermissionChain —— 门链定序：hook → boundary → （特例）→ Reviewer → Authorizer。

# Ported from wuu@2026.10.6 internal/tools/toolkit.go — pitfalls: B-51 B-55 B-56 B-130 B-131 B-132
# 逐行对应 ``checkPermission``（toolkit.go L112-146）与 ``reviewToolCall``
# （internal/tools/review.go L36-64）。

**顺序本身是安全属性，不是风格问题**（B-130）。母本的顺序读出来是：

1. **幂等护盾**：``permissionCheckedContextKey`` 为真直接放行 —— 同一 ctx 只过一次门
   （B-132）。写反/写成"每次调用都重判"会让嵌套调用与多通道重复弹审批、重复计数。
   注：本仓用可变的 :class:`PermissionContext` 代替 Go 的 ctx value，语义等价；
   母本打标的**确切调用点**本轮未读到，已登 port-ledger L-2 作为待复核项。
2. ``permissionRequestHook``（可选，在**一切判定之前**）。
3. ``boundary.Check`` —— 单一权威。
4. 硬编码特例：母本此处是 ``plugin_manager`` 的非只读硬拒，注释原文 *"Host plugin code is not
   confined by the workspace process sandbox. Optional review must not silently turn into
   implicit execution trust."* —— Questor 不做插件宿主，**该分支不移植**，但这条设计原则
   保留在下面的注释里（任何"可选复核"都不得默认变成隐式执行信任）。
5. ``reviewToolCall`` —— Approve for me（HITL，收紧型）。
6. **Authorizer 在最后**：为 None 放行；provider 报错即 ``authorization provider unavailable``；
   ``outcome`` 必须字面等于 ``"allow"``（B-131）。

五态映射照母本 ``reviewToolCall`` 的 switch：``allow`` 放行、``deny`` → ``review_denied``、
``unsure`` → ``review_needs_context``、``cancelled`` → ``review_cancelled``、
**其余（含 ``failed`` 与任何未知值）→ ``review_failed``** —— 默认分支是拒，不是放行。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from questor.limen.approval import (
    ApprovalDecision,
    ApprovalOutcome,
    ApprovalRequest,
    ReviewBlocked,
    hard_deny_reason,
    needs_review,
)
from questor.limen.authorizer import (
    AuthorizationRequest,
    Authorizer,
    enforce_authorizer,
)
from questor.limen.boundary import BoundaryDenied, ToolMeta, WorkspaceBoundary
from questor.schemas.model import PermissionMode

__all__ = ["PermissionChain", "PermissionContext", "Reviewer", "mark_checked"]

_DENY_NEXT = (
    "do not bypass this decision or retry an equivalent operation; choose a materially safer "
    "alternative or explain the exact action, target and risk in the conversation and wait for "
    "explicit user approval; after informed approval submit that specific action for fresh "
    "review, never skip the permission boundary"
)
_NEEDS_CONTEXT_NEXT = (
    "review could not establish sufficient safety or authorization; do not repeat the same "
    "request; explain the exact action, target and risk in the conversation, ask for missing "
    "information or explicit approval, then submit the specific action for fresh review; "
    "a vague continue is not blanket approval"
)
_CANCELLED_NEXT = (
    "the owning execution was cancelled; no safety verdict was reached and the action was not "
    "executed; do not automatically retry"
)
_FAILED_NEXT = (
    "automatic review could not be completed; this is not a determination that the action is "
    "unsafe or that the user denied permission; do not bypass the check or repeatedly retry; "
    "explain the failure in the conversation and resolve it or ask the user for guidance before "
    "a fresh review"
)
_FORBIDDEN_NEXT = (
    "this is a hard permission boundary; do not retry, bypass it or ask for conversational "
    "approval to override it; explain the restriction and offer a permitted alternative"
)


@dataclass
class PermissionContext:
    """一次工具运行作用域的判定上下文；``checked`` 是母本的幂等护盾。

    与母本一样是**可变**载体（不是 frozen）：护盾的意义就是"这一轮里已经过了门"这件事
    能被下游看到。嵌套调用把同一个 ctx 传下去即可，不需要重新构造。
    """

    checked: bool = False
    extras: Mapping[str, object] = field(default_factory=dict)


def mark_checked(ctx: PermissionContext) -> PermissionContext:
    """给已判过的下游打标（母本 ``markPermissionChecked``）：nested 调用不再重复过门。"""
    ctx.checked = True
    return ctx


class Reviewer(Protocol):
    """宿主审批通道：可以是真人在界面上点，也可以是外部策略；只能收紧不能提权。"""

    def review(self, request: ApprovalRequest) -> ApprovalDecision: ...


@dataclass(frozen=True)
class PermissionChain:
    """把 boundary / hook / Reviewer / Authorizer 按母本顺序串起来的一条链。

    装配点在 ``serve``/``engine`` 侧（谁能注入 reviewer、authorizer 由配置决定），
    链本身不 import 它们 —— 保持 ``limen`` 只依赖标准库与 schemas（structure §3）。
    """

    boundary: WorkspaceBoundary
    mode: PermissionMode = PermissionMode.STANDARD
    hook: object | None = None  # (ctx, info, arguments) -> None，抛异常即拒
    reviewer: Reviewer | None = None
    approve_for_me: bool = False
    authorizer: Authorizer | None = None
    session_id: str = ""
    actor_id: str = ""
    cwd: str = ""
    credential_paths: frozenset[str] = frozenset()

    def check(
        self,
        ctx: PermissionContext,
        info: ToolMeta,
        arguments: Mapping[str, object],
        *,
        call_id: str = "",
        referenced_paths: tuple[str, ...] = (),
    ) -> None:
        """过整条链；放行就安静返回，拒绝必抛带 ``error_kind`` 的异常。"""
        # 1. 幂等护盾（B-132）
        if ctx.checked:
            return
        # 2. 可选 hook，先于一切判定
        if self.hook is not None:
            hook = self.hook
            if not callable(hook):
                # 装配期契约：非可调用即装配错误，早失败（不用 assert：-O 下会被剥离）
                raise TypeError("permission hook 必须是 callable")
            hook(ctx, info, arguments)
        # 3. 单一权威门
        try:
            self.boundary.check(info, dict(arguments))
        except BoundaryDenied:
            # 判定已发生即落护盾（嵌套调用不得再过一次门）。母本用 ctx value +
            # ``markPermissionChecked`` 实现，本仓**未读到它的调用点**，故按“判定完成后打标”
            # 实现并在 port-ledger L-2 标为待复核项，不假装与母本逐字同构。
            ctx.checked = True
            raise
        # 4. 特例位：母本对 plugin_manager 硬拒（Questor 不做插件，故无此分支）。
        #    保留这条注释是为了防止将来把"可选复核"接在 boundary **之前**——
        #    Optional review must not silently turn into implicit execution trust.
        # 5. Approve for me（收紧型 HITL）
        self._review(ctx, info, arguments, call_id=call_id, referenced_paths=referenced_paths)
        # 6. Authorizer 在最后（B-131）
        enforce_authorizer(
            self.authorizer,
            AuthorizationRequest(
                session_id=self.session_id,
                actor_id=self.actor_id,
                cwd=self.cwd,
                permission_mode=self.mode,
                tool=info,
                arguments=_as_json(arguments),
            ),
        )
        mark_checked(ctx)

    def _review(
        self,
        ctx: PermissionContext,
        info: ToolMeta,
        arguments: Mapping[str, object],
        *,
        call_id: str,
        referenced_paths: tuple[str, ...],
    ) -> None:
        if not self.approve_for_me:
            return
        encoded = _as_json(arguments)
        request = ApprovalRequest(
            session_id=self.session_id,
            tool=info,
            arguments=encoded,
            permission_mode=self.mode,
            call_id=call_id,
            cwd=self.cwd,
            referenced_paths=referenced_paths,
        )
        # 硬拒在任何审批者之前判（含用户也不能覆盖）
        if reason := hard_deny_reason(request, self.credential_paths):
            raise ReviewBlocked(info.name, "review_forbidden", reason, _FORBIDDEN_NEXT)
        if not needs_review(request):
            return
        if self.reviewer is None:
            raise ReviewBlocked(
                info.name,
                "review_failed",
                "approve for me is enabled but no reviewer is available",
                _FAILED_NEXT,
            )
        try:
            decision = self.reviewer.review(request)
        except ReviewBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 - 审批通道故障不是"通过"，也不是"用户拒绝"
            del exc
            raise ReviewBlocked(
                info.name, "review_failed", "reviewer unavailable", _FAILED_NEXT
            ) from None
        outcome = str(decision.outcome).strip()
        if outcome == ApprovalOutcome.ALLOW.value:
            return
        if outcome == ApprovalOutcome.DENY.value:
            raise ReviewBlocked(
                info.name,
                "review_denied",
                decision.reason.strip() or "approve for me denied this action",
                _DENY_NEXT,
            )
        if outcome == ApprovalOutcome.UNSURE.value:
            raise ReviewBlocked(
                info.name, "review_needs_context", decision.reason, _NEEDS_CONTEXT_NEXT
            )
        if outcome == ApprovalOutcome.CANCELLED.value:
            raise ReviewBlocked(info.name, "review_cancelled", decision.reason, _CANCELLED_NEXT)
        # 母本 default 分支：failed 与任何未知值一律 review_failed（B-56：不是安全判定）
        raise ReviewBlocked(info.name, "review_failed", decision.reason, _FAILED_NEXT)


def _as_json(arguments: Mapping[str, object]) -> str:
    """把参数映射成母本 ``ToolCall.Arguments`` 那个"原始 JSON 字符串"形状。

    审批与 Authorizer 都按字符串读参数（母本如此），因此这里不预先解构 —— 键名与
    拼法（``permission_mode`` / ``permission-mode``）本身就是被查的对象。
    """
    return json.dumps(dict(arguments), ensure_ascii=False, default=str)
