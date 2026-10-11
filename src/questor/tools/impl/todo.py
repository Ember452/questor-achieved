"""todo 工具：会话内任务清单（overview §5；M2.2 为内存态，落盘随 M4 orchestration）。

mutates 按 action 判定：list 只读、add/update 变更（limen 的 read_only 档借
mutates_for 拦截变更类动作）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from questor.tools.base import Tool, ToolContext, ToolResult

_STATUS_MARK = {"pending": "○", "in_progress": "◐", "done": "●"}


@dataclass
class TodoItem:
    id: str
    title: str
    status: Literal["pending", "in_progress", "done"] = "pending"


@dataclass
class TodoStore:
    """run 内的清单状态（engine 组装进 ToolContext；无跨 run 持久化）。"""

    items: list[TodoItem] = field(default_factory=list)

    def add(self, title: str) -> TodoItem:
        item = TodoItem(id=uuid.uuid4().hex[:8], title=title)
        self.items.append(item)
        return item

    def update(
        self,
        item_id: str,
        *,
        title: str | None = None,
        status: Literal["pending", "in_progress", "done"] | None = None,
    ) -> TodoItem:
        for item in self.items:
            if item.id == item_id:
                if title is not None:
                    item.title = title
                if status is not None:
                    item.status = status
                return item
        raise KeyError(f"todo {item_id!r} 不存在")

    def render(self) -> str:
        if not self.items:
            return "(no todos)"
        return "\n".join(
            f"{_STATUS_MARK[item.status]} {item.id} {item.title}" for item in self.items
        )


class TodoParams(BaseModel):
    action: Literal["add", "update", "list"]
    id: str | None = None
    """update 时的目标条目。"""
    title: str | None = None
    status: Literal["pending", "in_progress", "done"] | None = None


class TodoTool(Tool):
    name = "todo"
    description = (
        "Maintain the session todo list: add items, update status "
        "(pending/in_progress/done), or list. Use it to track multi-step work."
    )
    kind = "meta"
    mutates = True  # 默认值；实际按 action 判定（list 只读）
    expects_path = False
    params_model = TodoParams

    def mutates_for(self, params: BaseModel) -> bool:
        assert isinstance(params, TodoParams)
        return params.action != "list"

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, TodoParams)
        todos = ctx.todos
        if params.action == "list":
            return ToolResult(output=todos.render())
        if params.action == "add":
            if not params.title:
                return ToolResult(output="add requires 'title'", is_error=True)
            item = todos.add(params.title)
            return ToolResult(output=f"added {item.id} {item.title}\n{todos.render()}")
        # update
        if params.id is None:
            return ToolResult(output="update requires 'id'", is_error=True)
        try:
            item = todos.update(params.id, title=params.title, status=params.status)
        except KeyError as exc:
            return ToolResult(output=str(exc), is_error=True)
        return ToolResult(output=f"updated {item.id}\n{todos.render()}")
