"""上下文预算常量表（唯一来源；B-05 的同一纪律搬到 context——阈值只许住这里）。

数值取自 `docs/specs/behavior-context-fc.md` 的 FlowCoder 实测摘录（重写实现、沿用规格），
两处刻意不同的地方在注释里写明。

**与 `engine/constants.py` 的分工**（两个"截断阈值"不是重复定义）：
- `engine` 的 `TOOL_RESULT_SPILL_CHARS` 管**审计面**——工具输出写进 Item 时何时落盘；
- 本表的 `SINGLE_RESULT_CHAR_LIMIT` 管**模型面**——回喂模型的会话内表示何时替换成预览。
同一个 20k 输出完全可能"落盘了但仍全文回喂"或反之，所以两件事必须两个旋钮。
"""

from __future__ import annotations

__all__ = [
    "AGGREGATE_CHAR_LIMIT",
    "AUTO_COMPACT_SAFETY_MARGIN",
    "BYTES_PER_KIB",
    "COMPACT_BREAKER_FAILURES",
    "INLINE_RESULT_CHAR_LIMIT",
    "KEEP_MAX_TOKENS",
    "KEEP_RECENT_MESSAGES",
    "KEEP_RECENT_TOKENS",
    "KEEP_RECENT_TURNS",
    "MANUAL_COMPACT_SAFETY_MARGIN",
    "MIN_SUMMARIZE_PREFIX_TOKENS",
    "OLD_RESULT_SNIP_CHARS",
    "PREVIEW_CHARS",
    "RECOVERY_FILE_LIMIT",
    "RECOVERY_TOKENS_PER_FILE",
    "SINGLE_RESULT_CHAR_LIMIT",
    "SNIPPED_HEAD_CHARS",
    "SUMMARY_OUTPUT_RESERVE",
]

#: 单条结果超过此长度 → 全文落盘 + 预览回链（会话内表示只留预览）
SINGLE_RESULT_CHAR_LIMIT = 50_000

#: 次档：不落盘但内联截断（长度不足以撑爆窗口，全文进盘反而让审计链多一份字节）
INLINE_RESULT_CHAR_LIMIT = 10_000

#: 同一轮所有工具结果的聚合上限：超了按单条长度降序逐条落盘，直到达标（B-26）
AGGREGATE_CHAR_LIMIT = 200_000

#: 落盘后的预览长度（字符）。与 gesta 的回链预览同源取值，改动要同时核对 data-model §5
PREVIEW_CHARS = 2_000

#: 陈旧裁剪保留的近期轮数：早于此的结果剪到 OLD_RESULT_SNIP_CHARS
KEEP_RECENT_TURNS = 10

#: 陈旧结果裁剪后的保留长度（FlowCoder 取 2_000；这里是"旧结果"不是"新落盘"）
OLD_RESULT_SNIP_CHARS = 2_000

#: 裁剪后仍留给模型看的开头长度（小到能忽略，但得能认出"这是哪条结果"）
SNIPPED_HEAD_CHARS = 200

#: 预览里报体积用的除数（阈值全是字符数，体积报 KiB 才读得懂）
BYTES_PER_KIB = 1024

# ---- Layer2 自动压缩（数值沿用 behavior-context-fc.md 的实测摘录） ----

#: 给摘要输出预留的窗口：不留这块，摘要请求自己就会因超长被拒
SUMMARY_OUTPUT_RESERVE = 20_000

#: 自动/手动压缩的触发冗余：自动档更早触发（还有下一轮要跑），手动档可贴近上限
AUTO_COMPACT_SAFETY_MARGIN = 13_000
MANUAL_COMPACT_SAFETY_MARGIN = 3_000

#: 尾部原文保留窗口：token 下限与条数下限**先到先停**，硬上限防单条超大吃掉整个窗口
KEEP_RECENT_TOKENS = 10_000
KEEP_RECENT_MESSAGES = 5
KEEP_MAX_TOKENS = 40_000

#: 待摘要前缀回收空间低于此就退化为不压缩（B-22：“压了个寂寞”）
MIN_SUMMARIZE_PREFIX_TOKENS = 2_000

#: 连续摘要失败多少次后熔断 open（B-23）
COMPACT_BREAKER_FAILURES = 3

# ---- 压缩后的工作集重注入（B-11；记忆/技能段随各自模块加入） ----

RECOVERY_FILE_LIMIT = 5
RECOVERY_TOKENS_PER_FILE = 5_000
