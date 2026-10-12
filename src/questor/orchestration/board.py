"""看板投影：任务 + DAG 依赖边（只读，供 serve 与 UI 消费）。

不做完整图布局（那是 E1 的 `@xyflow/react` 面板）；这里只给出**已验证的边集**：
`depends_on` 指向不存在的任务时丢弃该边（诚实呈现，不臆造依赖），并暴露环检测供上层
在派发前拒绝自环/循环依赖。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from questor.schemas.orchestration import Task, TaskStatus

__all__ = ["BoardEdge", "BoardView", "build_board", "has_cycle"]


class BoardEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_task_id: str
    to_task_id: str


class BoardView(BaseModel):
    model_config = ConfigDict(frozen=True)

    tasks: tuple[Task, ...]
    edges: tuple[BoardEdge, ...]


def build_board(tasks: tuple[Task, ...]) -> BoardView:
    """从任务集构造看板：保留指向已知任务的依赖边，丢弃悬空边。"""
    known = {task.id for task in tasks}
    edges = [
        BoardEdge(from_task_id=dependency, to_task_id=task.id)
        for task in tasks
        for dependency in task.depends_on
        if dependency in known
    ]
    return BoardView(tasks=tasks, edges=tuple(edges))


def has_cycle(view: BoardView) -> bool:
    """依赖图是否有环（DFS 三色）。派发前用它拒自环与循环依赖。"""
    adjacency: dict[str, list[str]] = {task.id: [] for task in view.tasks}
    for edge in view.edges:
        adjacency.setdefault(edge.from_task_id, []).append(edge.to_task_id)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(adjacency, WHITE)

    def visit(node: str) -> bool:
        color[node] = GRAY
        for nxt in adjacency.get(node, []):
            if color.get(nxt, WHITE) == GRAY:
                return True
            if color.get(nxt, WHITE) == WHITE and visit(nxt):
                return True
        color[node] = BLACK
        return False

    return any(visit(node) for node in list(adjacency) if color[node] == WHITE)


def open_tasks(tasks: tuple[Task, ...]) -> tuple[Task, ...]:
    """未终态任务（看板"进行中"列；终态 = completed/cancelled）。"""
    terminal = {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
    return tuple(task for task in tasks if task.status not in terminal)
