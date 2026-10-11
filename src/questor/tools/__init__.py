"""tools —— 工具登记、schema、执行与结果封装（overview §6；八工具）。

三柱归属：**可见**的执行面——每个工具调用与结果都封装成可审计的记录，
进会话正文与事件流。

结构（参照 FlowCoder tools/base.py + registry.py 的形状，全部重写）：
- ``base``：Tool 协议（pydantic params 即 schema 来源）与 ToolResult；
- ``registry``：登记表 + 连续安全批分区（B-16）+ 禁用≠未知（B-17）；
- ``filestate``：read-before-edit 门禁（写过先读过、读后未被外部改动）；
- ``processmgr``：后台进程管理（Windows Job Object 整树硬杀，ADR-0007/0015）；
- ``executor``：**唯一** limen.gate 消费者（架构测试强制）——授权→执行→封装。

# Reimplements FlowCoder@flowcoder tools/{base,registry,file_state_cache}.py —
# pitfalls: B-12 B-13 B-14 B-15 B-16 B-17 B-18 B-19
"""

from __future__ import annotations

from questor.tools.base import Tool, ToolContext, ToolResult
from questor.tools.registry import ToolBatch, ToolRegistry, partition_tool_calls

__all__ = [
    "Tool",
    "ToolBatch",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "partition_tool_calls",
]
