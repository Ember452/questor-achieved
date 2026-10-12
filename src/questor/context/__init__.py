"""context —— 上下文预算、自适应压缩、压缩边界记录、超预算结果落盘与回读（overview §6）。

三柱归属：**可见**与**可验证**的交界——预算怎么花的必须看得见（`notice/compact` 与
`reclaimed_chars`），而"模型这一轮到底看到什么"要能事后核对（会话内表示落盘）。

矩阵：`context` 只可 import `schemas` `gesta` `providers`（structure §5）——它不碰
engine，也不读 config：预算的输入由调用方给（用量锚点 + 能力声明）。

依赖方向诚实声明：本包直接 import `questor.gesta.store`（落盘原语），而不是"为了分层
绕一圈 engine"——多一层空壳接口只会让读者更困惑（structure §4 的依赖纠缠反例）。
"""

from __future__ import annotations

from questor.context.budget import (
    AGGREGATE_CHAR_LIMIT,
    INLINE_RESULT_CHAR_LIMIT,
    KEEP_RECENT_TURNS,
    OLD_RESULT_SNIP_CHARS,
    PREVIEW_CHARS,
    SINGLE_RESULT_CHAR_LIMIT,
)
from questor.context.compact import (
    CompactBreaker,
    CompactOutcome,
    auto_compact,
    compute_compact_threshold,
    keep_start_index,
    recovery_attachment,
    should_auto_compact,
    spilled_representations,
)
from questor.context.rehydrate import rebuild_history, state_from_view
from questor.context.replacements import ReplacementState, state_from_records
from questor.context.tool_results import BudgetOutcome, apply_tool_result_budget, persisted_preview

__all__ = [
    "AGGREGATE_CHAR_LIMIT",
    "INLINE_RESULT_CHAR_LIMIT",
    "KEEP_RECENT_TURNS",
    "OLD_RESULT_SNIP_CHARS",
    "PREVIEW_CHARS",
    "SINGLE_RESULT_CHAR_LIMIT",
    "BudgetOutcome",
    "CompactBreaker",
    "CompactOutcome",
    "ReplacementState",
    "apply_tool_result_budget",
    "auto_compact",
    "compute_compact_threshold",
    "keep_start_index",
    "persisted_preview",
    "rebuild_history",
    "recovery_attachment",
    "should_auto_compact",
    "spilled_representations",
    "state_from_records",
    "state_from_view",
]
