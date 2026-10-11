"""权威门：Boundary 三元组 + 短路判定链 + 模型可读错误方言。

结构直译 wuu ``boundary.go``：``{Enforce, AllowMutations, Guards}``。判定顺序
（B-34：短路先决、命中即返回、层间不合并）：

1. **只读闸**：``not allow_mutations and call.mutates`` → deny（B-50 原则：
   mutates 判定在守卫之前——read_only 的粒度问题在调用方的 mutates 标记里解决）；
2. **敏感路径守卫**（全档位）：写恒拒（B-54）；读在非 unconfined 拒、unconfined
   降级为脱敏放行；
3. **危险命令守卫**（全档位，B-32）；
4. **路径门**（``enforce_paths`` 时）：B-30 二段 resolve + 根集合比较；
   缺路径参数视为 deny（B-31）；
5. 兜底 allow。

Guard 契约（B-51）：硬 allow/deny 与审批严格分层——本门**没有** ask 结果，
也不等待用户输入；审批收紧归 habena（M3）。

错误方言（B-52）：拒绝必须带 ``error_kind + reason + model_next_action``，
error_kind 取值对齐 protocol.md §7 / app_server v0-1 ``ErrorPayload.code``
（本门只产生 ``boundary_denied``）。

**唯一消费入口**：本模块只能被 ``tools/executor.py`` import（架构测试
``test_permission_gate_single_entry`` 强制）——工具实现永远摸不到门，
"权限判定无绕过路径"由此机械成立。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from questor.limen.commands import is_dangerous_command
from questor.limen.reachability import is_within
from questor.limen.sensitive import classify, read_blocked, redact
from questor.schemas.model import PermissionMode

ToolKind = Literal["file", "shell", "process", "meta"]
Effect = Literal["allow", "deny"]

_ERROR_KIND = "boundary_denied"


@dataclass(frozen=True)
class Boundary:
    """模式对应的行为三元组（matrix.py 的表值）；守卫链全档位恒开，不在三元组里。"""

    enforce_paths: bool
    allow_mutations: bool


@dataclass(frozen=True)
class ToolCallInfo:
    """一次工具调用的判定输入（由 executor 从工具声明与参数构造）。"""

    tool_name: str
    kind: ToolKind
    mutates: bool
    expects_path: bool
    path: str | None = None
    command: str | None = None
    #: 参数键里试图携带的权限模式（B-55 的 limen 侧前哨：参数提权在此硬拒）
    requested_mode: PermissionMode | None = field(default=None)


@dataclass(frozen=True)
class Decision:
    """判定结果；deny 必带三件套方言，allow 可带 ``redact_output``（B-54 降级读）。"""

    effect: Effect
    reason: str = ""
    error_kind: str | None = None
    model_next_action: str | None = None
    redact_output: bool = False


_READ_ONLY_REASON = "this agent is read-only; it may observe but not modify"
_READ_ONLY_NEXT = "use read-only tools, or tell the user this agent cannot make changes"


def _deny(reason: str, model_next_action: str) -> Decision:
    return Decision(
        effect="deny",
        reason=reason,
        error_kind=_ERROR_KIND,
        model_next_action=model_next_action,
    )


def decide(call: ToolCallInfo, mode: PermissionMode, roots: list[str]) -> Decision:
    """唯一判定入口（executor 之外不得 import 本模块——架构测试强制）。

    短路先决（B-34）：每层命中即返回，层间不合并回溯。模式 → 边界的表在
    matrix.py，此处函数级延迟导入以保持 import 方向单向（matrix → gate）。
    """
    from questor.limen.matrix import MODE_BOUNDARIES

    boundary = MODE_BOUNDARIES[mode]
    unconfined = mode is PermissionMode.UNCONFINED

    # 1. 参数提权前哨：调用参数里试图携带更高档位一律硬拒（B-55 的门内侧）
    if call.requested_mode is not None and call.requested_mode != mode:
        return _deny(
            f"tool call attempted to elevate permission_mode to {call.requested_mode.value}",
            "retry without permission_mode in the arguments; escalation is not permitted",
        )

    # 2. 只读闸（B-50：mutates 判定先于守卫）
    if not boundary.allow_mutations and call.mutates:
        return _deny(_READ_ONLY_REASON, _READ_ONLY_NEXT)

    # 3. B-31：触路径工具缺路径参数视为 deny——先于路径门，unconfined 同样适用
    #    （缺参数是调用形状错误，不是"无边界可查"）
    if call.expects_path and (call.path is None or not call.path.strip()):
        return _deny(
            "tool call is missing its required path argument",
            "supply the target path in the arguments",
        )

    # 4. 敏感路径守卫（全档位；B-53 按段匹配 + 源码豁免，B-54 写恒拒/读降级）
    if call.path is not None:
        kind = classify(call.path)
        if kind is not None:
            if call.mutates:
                return _deny(
                    f"path is credential-bearing ({kind}); writes are refused in every mode",
                    "choose a non-credential target path, or ask the user to handle it",
                )
            if read_blocked(call.path, unconfined=unconfined):
                return _deny(
                    f"path is credential-bearing ({kind}); reading it is refused in this mode",
                    "ask the user to inspect the credential file instead",
                )
            # unconfined 降级读：放行但输出必须脱敏（B-54）
            if unconfined:
                return Decision(
                    effect="allow",
                    reason=f"sensitive path read downgraded; output will be redacted ({kind})",
                    redact_output=True,
                )

    # 5. 危险命令守卫（全档位，B-32）
    if call.command is not None:
        label = is_dangerous_command(call.command)
        if label is not None:
            return _deny(
                f"command matches the dangerous-command blacklist ({label})",
                "restate the task without destructive operations, or ask the user to run it",
            )

    # 6. 路径门（standard/read_only 强制；unconfined 不查，B-30 二段 resolve 在此生效）
    if boundary.enforce_paths and call.path is not None and not is_within(call.path, roots):
        return _deny(
            f"path {call.path!r} is outside the registered workspace roots",
            "work inside the registered workspace roots, or ask the user to register the path",
        )

    return Decision(effect="allow")


def redact_output(decision: Decision, output: str) -> str:
    """按判定对工具输出脱敏；非降级读原样返回（executor 在结果封装处调用）。"""
    if decision.redact_output:
        return redact(output)
    return output
