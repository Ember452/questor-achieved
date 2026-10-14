"""Approve for me —— 收紧型审批：硬拒三件在前、送审判定在中、五态结果在后。

# Ported from wuu@2026.10.6 internal/approvefor/review.go — pitfalls: B-55 B-56
# 对应：``Outcome*``→:class:`ApprovalOutcome`、``Request``→:class:`ApprovalRequest`、
# ``NeedsReview``→:func:`needs_review`、``HardDenyReason``→:func:`hard_deny_reason`、
# ``looksLikePermissionEscalation``→:func:`looks_like_permission_escalation`、
# ``argumentPaths``→:func:`argument_paths`。
# 调用侧（何时触发、拒绝文案）见 :mod:`questor.limen.chain` 与 :class:`ReviewBlocked`。

三条容易被写坏的母本语义：

1. **只在 standard 档生效**（``EnabledForMode``）——read_only 无写可审、unconfined 是显式逃生阀，
   在档位上再叠一层审批等于把逃生阀变成"问一句就能过"；
2. **shell 一律送审，连分类成只读的低风险也不例外**——注释原文：*"Read-only classification is
   not proof that a shell command cannot read credentials (even a simple cat can)"*；
   并且**同时看原生工具名**，防"元数据里没填 Kind 就绕过审批"；
3. **硬拒不可被覆盖**：凭据文件、参数里试图 ``permission_mode=unconfined``、敏感路径写——
   判定看**目标路径**而不是内容子串（注释原文：*"a credential basename in source is not
   evidence of file access"*）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum

from questor.limen.boundary import ToolMeta
from questor.limen.sensitive import classify
from questor.schemas.model import PermissionMode

__all__ = [
    "ApprovalDecision",
    "ApprovalOutcome",
    "ApprovalRequest",
    "ReviewBlocked",
    "argument_paths",
    "enabled_for_mode",
    "hard_deny_reason",
    "looks_like_permission_escalation",
    "needs_review",
]

#: 参数里可能携带路径的键（母本 ``argumentPaths`` 的三键表，单点定义）。
_PATH_ARGUMENT_KEYS = ("path", "file_path", "target")
#: 提权探测的两种拼法（母本 L112：下划线与连字符都要查，漏一个就是绕过口）。
_ESCALATION_KEYS = ("permission_mode", "permission-mode")
_RISK_HIGH = "high"
_WRITE_TOOL_NAMES = frozenset({"write_file", "edit_file"})


class ApprovalOutcome(StrEnum):
    """审批五态。``FAILED``/``CANCELLED`` 是**基础设施状态，不是安全判定**（B-56）。"""

    ALLOW = "allow"
    DENY = "deny"
    UNSURE = "unsure"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewBlocked(RuntimeError):
    """审批层拒绝/受阻；``action_executed=false`` 是硬事实（未执行，别说"可能已执行"）。

    形状照母本 ``reviewBlocked``：
    ``tool %q blocked by approve for me: error_kind=%s action_executed=false``
    ``reason=%q model_next_action=%q``
    """

    def __init__(self, tool_name: str, kind: str, reason: str, model_next_action: str) -> None:
        self.tool_name = tool_name
        self.error_kind = kind
        self.reason = reason
        self.model_next_action = model_next_action
        self.action_executed = False
        super().__init__(
            f'tool "{tool_name}" blocked by approve for me: error_kind={kind} '
            f"action_executed=false reason={reason!r} "
            f'model_next_action="{model_next_action}"'
        )


@dataclass(frozen=True)
class ApprovalRequest:
    """一次送审请求（母本 ``approvefor.Request``）。

    ``user_messages`` **只由宿主填**，绝不从工具参数取——否则模型可以自证"用户同意过"。
    """

    session_id: str
    tool: ToolMeta
    arguments: str = ""
    permission_mode: PermissionMode = PermissionMode.STANDARD
    turn_id: str = ""
    call_id: str = ""
    cwd: str = ""
    user_messages: tuple[str, ...] = ()
    referenced_paths: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ApprovalDecision:
    outcome: ApprovalOutcome | str
    reason: str = ""


def enabled_for_mode(mode: PermissionMode | str) -> bool:
    """只有 standard 档启用 Approve for me。"""
    value = mode.value if isinstance(mode, PermissionMode) else str(mode).strip().lower()
    return value == PermissionMode.STANDARD.value


def _payload(arguments: str) -> dict[str, object]:
    """把工具参数 JSON 解成 map；解不出时按母本一样"无路径可查"处理而不是抛错。"""
    try:
        loaded = json.loads(arguments.strip() or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def argument_paths(arguments: str) -> tuple[str, ...]:
    """参数里的字面路径操作数（母本 ``argumentPaths``：path / file_path / target）。"""
    payload = _payload(arguments)
    paths: list[str] = []
    for key in _PATH_ARGUMENT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value)
    return tuple(paths)


def looks_like_permission_escalation(arguments: str) -> bool:
    """参数试图把本次调用升到 unconfined —— 审批不能提权（B-55）。"""
    payload = _payload(arguments)
    for key in _ESCALATION_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip().lower() == PermissionMode.UNCONFINED.value:
            return True
    return False


def sensitive_path_reason(path: str) -> tuple[str, bool]:
    """复用 :func:`questor.limen.sensitive.classify` 作为敏感判定的**唯一**实现。

    母本在 ``approvefor`` 里另写了一份更窄的 ``sensitivePathReason``（只认 .env / SSH 私钥 /
    private-key），与 ``tools`` 里那份宽表并存——同一事实两套真相。Questor 单点复用宽表，
    差异（更严）已登 port-ledger。
    """
    kind = classify(path)
    return (kind or "", kind is not None)


def needs_review(request: ApprovalRequest) -> bool:
    """送审判定（母本 ``NeedsReview`` L60-85 的分支顺序**逐条保留**）。"""
    if not enabled_for_mode(request.permission_mode):
        return False
    # shell 无条件送审：分类为只读不能证明 cat 读不到凭据。
    # 同时看原生工具名——缺 Kind 元数据不该成为绕过审批的后门。
    if request.tool.kind == "shell" or request.tool.name == "bash":
        return True
    if request.tool.read_only and request.tool.risk != _RISK_HIGH:
        return False
    if request.tool.risk == _RISK_HIGH or request.tool.destructive:
        return True
    return request.tool.kind in {"git", "process", "browser", "mcp"}


def hard_deny_reason(
    request: ApprovalRequest,
    credential_paths: frozenset[str] = frozenset(),
) -> str:
    """没有任何审批者（含用户）能覆盖的硬拒；返回空串表示无硬拒。

    ``credential_paths`` 是宿主目录下的应用自身凭据文件名集合（母本 ``isWuuCredentialPath``
    的"只认 home 根下那四个文件名"），由装配方注入 —— limen 不 import state/config
    （structure §5 依赖裁决），故这里以纯数据传入。
    """
    for path in (*argument_paths(request.arguments), *request.referenced_paths):
        candidate = path
        if credential_paths and _basename(candidate) in credential_paths:
            return "credential files are never accessible to the agent in any permission mode"
    if looks_like_permission_escalation(request.arguments):
        return "approve for me cannot raise the session permission mode"
    if request.tool.name in _WRITE_TOOL_NAMES:
        for path in argument_paths(request.arguments):
            reason, hit = sensitive_path_reason(path)
            if hit:
                return f"sensitive path {reason} cannot be modified through Approve for me"
    return ""


def _basename(path: str) -> str:
    normalized = path.replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized
