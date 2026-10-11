"""登记表的八工具装配点（engine 与测试共用；无全局单例，每 run 新建）。"""

from __future__ import annotations

from questor.tools.base import Tool
from questor.tools.impl.edit import EditTool
from questor.tools.impl.list import ListTool
from questor.tools.impl.process import ProcessTool
from questor.tools.impl.read import ReadTool
from questor.tools.impl.run import RunTool
from questor.tools.impl.search import SearchTool
from questor.tools.impl.todo import TodoTool
from questor.tools.impl.write import WriteTool
from questor.tools.registry import ToolRegistry


def build_default_registry() -> ToolRegistry:
    """八工具登记表：read / edit / write / list / search / todo / run / process。"""
    registry = ToolRegistry()
    tools: list[Tool] = [
        ReadTool(),
        EditTool(),
        WriteTool(),
        ListTool(),
        SearchTool(),
        TodoTool(),
        RunTool(),
        ProcessTool(),
    ]
    for tool in tools:
        registry.register(tool)
    return registry
