"""limen —— 唯一权威权限门：三档、可达性推导、敏感守卫、收紧型审批与最后防线 Authorizer。

三柱归属：**可干预**与**可验证**的边界——拒绝必须带模型读得懂的理由与下一步动作，
且"什么被拒了为什么"全部进会话记录。

两层结构（别混）：**硬判定层** :mod:`~questor.limen.boundary`（只答"允许吗"，
无审批无阻塞，B-51）与**链层** :mod:`~questor.limen.chain`（按母本定序把
hook → boundary → Reviewer → Authorizer 串起来，B-130/B-131/B-132）。
:func:`~questor.limen.gate.decide` 是旧世界还在用的硬判定入口，随工具层重写（批次 3a）
收敛到链层——差异与时间表见 ``docs/research/port-ledger.md`` Phase 2a 段。

依赖裁决（structure §3）：本包只 import 标准库与 schemas；可达根与凭据文件名以
纯数据注入，不 import workspaces/state/tools/serve。

# Ported from wuu@2026.10.6 internal/tools/{boundary.go,toolkit.go,review.go,authorization.go,
# tool_info.go} + internal/approvefor/review.go — pitfalls: B-10 B-30 B-31 B-32 B-33 B-34
# B-50 B-51 B-52 B-53 B-54 B-55 B-56 B-58 B-130 B-131 B-132
"""

from __future__ import annotations

from questor.limen.approval import (
    ApprovalDecision,
    ApprovalOutcome,
    ApprovalRequest,
    ReviewBlocked,
    hard_deny_reason,
    needs_review,
)
from questor.limen.authorizer import (
    AuthorizationDecision,
    AuthorizationDenied,
    AuthorizationRequest,
    Authorizer,
    enforce_authorizer,
)
from questor.limen.boundary import (
    MUTATING_KINDS,
    NON_MUTATING_KINDS,
    BoundaryDenied,
    Guard,
    ToolMeta,
    WorkspaceBoundary,
    mutates,
    read_only_boundary,
    standard_boundary,
    unconfined_boundary,
)
from questor.limen.chain import PermissionChain, PermissionContext, Reviewer, mark_checked
from questor.limen.commands import is_dangerous_command
from questor.limen.gate import (
    Boundary,
    Decision,
    ToolCallInfo,
    ToolKind,
    decide,
)
from questor.limen.matrix import MODE_BOUNDARIES, boundary_for

__all__ = [
    # 硬判定层（母本 boundary.go 形状）
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
    # 链层与审批/授权
    "ApprovalDecision",
    "ApprovalOutcome",
    "ApprovalRequest",
    "AuthorizationDecision",
    "AuthorizationDenied",
    "AuthorizationRequest",
    "Authorizer",
    "PermissionChain",
    "PermissionContext",
    "Reviewer",
    "ReviewBlocked",
    "enforce_authorizer",
    "hard_deny_reason",
    "mark_checked",
    "needs_review",
    # 旧世界入口（随批次 3a 收敛）
    "Boundary",
    "Decision",
    "MODE_BOUNDARIES",
    "ToolCallInfo",
    "ToolKind",
    "boundary_for",
    "decide",
    "is_dangerous_command",
]
