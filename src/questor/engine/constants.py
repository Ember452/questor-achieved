"""预算与循环常量集中一张表（B-05：禁止魔法数散布——FlowCoder 把 50/3/300s/5
散在 core.py 各处是反例）。改任何阈值只许改这里；唯一的例外是住在共享层的
`CHARS_PER_TOKEN`（context 的压缩阈值与循环必须用同一个数，见 `schemas/llm.py`），
本模块只导入、不定义。"""

from __future__ import annotations

from questor.schemas.llm import CHARS_PER_TOKEN as CHARS_PER_TOKEN

# 循环硬上限：一轮 turn 内的最大模型迭代数
MAX_ITERATIONS = 50

# 未知工具连续调用熔断阈值（B-03：并行批不清零，只有串行已知成功才清零）
UNKNOWN_TOOL_BREAKER = 3

# max_tokens 触顶恢复（B-08）：先提到天花板，再最多分段续写 N 次
MAX_TOKENS_CEILING = 64_000
MAX_OUTPUT_TOKEN_RECOVERIES = 3

# 工具结果落盘阈值（字符）：超过即 spill 全文 + 2KB 预览回链（B-24 语义）。
# 这是**审计面**阈值；模型面（会话内表示）的阈值在 `context/budget.py`，两者不合并
TOOL_RESULT_SPILL_CHARS = 20_000

# gesta 写句柄的锁超时：engine 高频追加传短上限（热路径决策，ADR-0009 同源退路）
LOCK_TIMEOUT_S = 10.0
