"""limen —— 唯一权威权限门：三档、可达性推导、敏感路径守卫（overview §6 §9）。

三柱归属：**可干预**与**可验证**的边界——拒绝必须带模型读得懂的理由与下一步动作，
且"什么被拒了为什么"全部进会话记录。

依赖裁决（structure §5）：本包只 import 标准库与 schemas；可达根以纯数据
（``root_paths`` 字符串列表）注入，不 import workspaces/state/tools。
判定链见 :mod:`questor.limen.gate`；模式 → 边界的显式表见 :mod:`questor.limen.matrix`。

# Reimplements wuu@wuu-main internal/tools/boundary.go + internal/tools/sensitive_paths.go
# + FlowCoder@flowcoder permissions/{checker,modes,sandbox,dangerous}.py（六层→三档+守卫链）
# — pitfalls: B-10 B-30 B-31 B-32 B-33 B-34 B-50 B-51 B-52 B-53 B-54 B-58
"""

from __future__ import annotations

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
    "Boundary",
    "Decision",
    "MODE_BOUNDARIES",
    "ToolCallInfo",
    "ToolKind",
    "boundary_for",
    "decide",
    "is_dangerous_command",
]
