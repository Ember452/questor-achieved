"""engine —— 内置引擎循环、turn 生命周期、事件流（overview §6）。

三柱归属：**可见**与**可干预**的引擎——每轮的流式输出、工具调用、状态迁移都以
事件流出，同时落进 gesta（落盘可回放）。

结构（R2：循环的裁决权在本项目代码；FlowCoder agent/core.py 的形状参照、全部重写）：
- ``constants``：预算常量集中一张表（B-05）；
- ``model``：ModelPort 协议（R1 内核定义 port，providers M2.3 实现；测试用
  testenv 的 fake model）；
- ``conversation``：会话内存形状与用量锚点；
- ``output_recovery``：max_tokens 两阶段恢复（B-08）；
- ``events``：AgentEvent → protocol.md §4 事件族的映射；
- ``loop``：显式状态机循环（B-06——拆方法、禁巨型函数；B-02 收敛轮保留只读工具；
  B-03 未知工具熔断；B-07 单状态机）。

# Reimplements FlowCoder@flowcoder agent/{core,events,budget,output_recovery,
# conversation}.py（形状与语义，未搬代码）— pitfalls: B-01 B-02 B-03 B-05 B-06 B-07 B-08
"""

from __future__ import annotations

from questor.engine.constants import (
    CHARS_PER_TOKEN,
    LOCK_TIMEOUT_S,
    MAX_ITERATIONS,
    MAX_OUTPUT_TOKEN_RECOVERIES,
    MAX_TOKENS_CEILING,
    UNKNOWN_TOOL_BREAKER,
)
from questor.engine.loop import Engine, TurnRequest

__all__ = [
    "CHARS_PER_TOKEN",
    "Engine",
    "LOCK_TIMEOUT_S",
    "MAX_ITERATIONS",
    "MAX_OUTPUT_TOKEN_RECOVERIES",
    "MAX_TOKENS_CEILING",
    "TurnRequest",
    "UNKNOWN_TOOL_BREAKER",
]
