"""登记表的十工具装配点（engine 与测试共用；无全局单例，每 run 新建）。

八工具（M2.2）+ 两个编排工具（M4：`plan` / `task`，经 OrchestrationPort 生效）。
"""

from __future__ import annotations

from questor.tools.base import Tool
from questor.tools.impl.edit import EditTool
from questor.tools.impl.list import ListTool
from questor.tools.impl.orchestration import PlanTool, TaskTool
from questor.tools.impl.process import ProcessTool
from questor.tools.impl.read import ReadTool
from questor.tools.impl.run import RunTool
from questor.tools.impl.search import SearchTool
from questor.tools.impl.todo import TodoTool
from questor.tools.impl.write import WriteTool
from questor.tools.registry import ToolRegistry


def build_default_registry() -> ToolRegistry:
    """工具登记表：read / edit / write / list / search / todo / run / process / plan / task。"""
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
        PlanTool(),
        TaskTool(),
    ]
    for tool in tools:
        registry.register(tool)
    return registry
