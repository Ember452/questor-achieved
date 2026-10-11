"""工具登记表：注册 / 禁用 / schema 导出 / 连续安全批分区（B-15 B-16 B-17）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from questor.tools.base import Tool


class ToolRegistryError(ValueError):
    """登记表操作错误（重名注册、未知工具禁用等）。"""


@dataclass(frozen=True)
class ToolCallRequest:
    """一次待执行的模型工具调用（executor 的输入）。"""

    tool_use_id: str
    tool_name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ToolBatch:
    """分区单元：``concurrent`` 批内的调用并行执行（B-16：连续安全合并，非安全打断）。"""

    concurrent: bool
    calls: list[ToolCallRequest] = field(default_factory=list)


def partition_tool_calls(calls: list[ToolCallRequest], registry: ToolRegistry) -> list[ToolBatch]:
    """按"连续 concurrency_safe 且已启用"切批——非安全工具打断并行段，
    顺序语义保持模型给出的调用顺序（B-16）。单元素安全批不值得并行，按串行走。"""
    batches: list[ToolBatch] = []
    current: ToolBatch | None = None
    for call in calls:
        tool = registry.get(call.tool_name)
        safe = tool is not None and tool.concurrency_safe and registry.is_enabled(call.tool_name)
        if safe:
            if current is None or not current.concurrent:
                current = ToolBatch(concurrent=True)
                batches.append(current)
            current.calls.append(call)
        else:
            current = ToolBatch(concurrent=False, calls=[call])
            batches.append(current)
    # 单元素并行批退化为串行（无并行收益，统一走串行路径）
    return [
        ToolBatch(concurrent=False, calls=b.calls) if b.concurrent and len(b.calls) < 2 else b
        for b in batches
    ]


class ToolRegistry:
    """登记表：重名注册报错；禁用与未知是两回事（B-17：只有未知计入熔断计数）。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._disabled: set[str] = set()

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ToolRegistryError(f"工具 {tool.name!r} 重复注册")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def is_known(self, name: str) -> bool:
        return name in self._tools

    def is_enabled(self, name: str) -> bool:
        return name in self._tools and name not in self._disabled

    def disable(self, name: str) -> None:
        if name not in self._tools:
            raise ToolRegistryError(f"工具 {name!r} 不存在，无法禁用")
        self._disabled.add(name)

    def enable(self, name: str) -> None:
        self._disabled.discard(name)

    def schemas(self) -> list[dict[str, object]]:
        """全部已启用工具的 schema（B-17：禁用的不进 schema——模型看不到就不会调用）。"""
        return [
            self._tools[name].schema() for name in sorted(self._tools) if name not in self._disabled
        ]
