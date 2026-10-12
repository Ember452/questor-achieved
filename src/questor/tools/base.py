"""Tool 协议与执行结果——pydantic params 即 schema 来源（FlowCoder base.py 形状重写）。

每个工具声明：name / description / kind（limen 的 ToolKind）/ mutates（本调用是否
改变世界）/ expects_path（limen B-31 的前提）/ concurrency_safe（B-16 分区依据）。
执行签名是 ``execute(params, ctx)``：ctx 由 engine 组装（filestate、processmgr、
todo、工作目录），工具自身无全局状态。

工具**不 import limen 任何符号**（架构测试 test_permission_gate_single_entry 强制）：
判定输入由 executor 从这里的声明构造，工具只描述自己。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from questor.tools.filestate import FileStateCache
    from questor.tools.impl.todo import TodoStore
    from questor.tools.ports import OrchestrationPort
    from questor.tools.processmgr import ProcessManager

ToolKind = Literal["file", "shell", "process", "meta"]

#: 各工具共用的目录跳过清单（list/search 遍历时忽略）
SKIP_DIRS = frozenset(
    {".git", ".venv", "node_modules", "__pycache__", ".tox", ".mypy_cache", ".ruff_cache"}
)


def resolve_tool_path(ctx: ToolContext, raw: str) -> Path:
    """把工具参数里的路径解析为绝对路径（相对路径相对工作目录；单点在此）。"""
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else Path(ctx.cwd) / candidate


@dataclass(frozen=True)
class ToolResult:
    """工具执行的输出（进 Item.payload 与回喂模型的内容）。"""

    output: str
    is_error: bool = False
    #: 附加的结构化载荷（写时刻 diff、后台移交的 pid 等），进 Item.payload
    data: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolContext:
    """一次 run 的工具执行环境（engine 组装，无全局单例）。

    `workspace_id` 对写工具为必填（写入时需 bump revision）；None 属测试与无工作区场景，
    写时仅落 diff 不 bump（B-92 的诚实边界）。
    """

    cwd: str
    file_state: FileStateCache
    processes: ProcessManager
    todos: TodoStore
    workspace_id: str | None = None
    #: 会话 id（编排工具把计划/任务挂到当前线程；cli 无会话时为 None）
    thread_id: str | None = None
    #: 编排端口（R1：port 定义在 tools、实现在 orchestration、由装配点注入；None = 不可用）
    orchestration: OrchestrationPort | None = None


class Tool(ABC):
    """工具基类：子类提供 name/description/params_model 与 execute。"""

    name: str
    description: str
    kind: ToolKind
    #: 本调用是否改变世界——多数工具恒定；多动作工具（todo/process）覆写 :meth:`mutates_for`
    mutates: bool
    concurrency_safe: bool = False
    expects_path: bool = False
    #: 参数中承载路径的字段名（executor 据此构造 limen 输入）；无路径字段留空
    path_param: str = ""
    #: 路径参数缺省值（如 search 的 "."）——executor 在门**之前**填入，避免 B-31 误伤带默认值的工具
    path_default: str = ""

    #: pydantic 模型即工具 schema 来源（R4：跨进程 schema 纯 JSON Schema，由此生成）
    params_model: type[BaseModel]

    def mutates_for(self, params: BaseModel) -> bool:
        """该次调用的 mutates 判定；默认用类级标记，多动作工具覆写。"""
        return self.mutates

    def declared_path(self, params: BaseModel) -> str | None:
        """按 ``path_param``/``path_default`` 取路径参数（executor 构造判定输入用）。"""
        if not self.path_param:
            return None
        value = getattr(params, self.path_param, None)
        if value is None and self.path_default:
            return self.path_default
        return str(value) if value is not None else None

    def schema(self) -> dict[str, object]:
        """anthropic 形态的平铺 schema（providers M2.3 增加 openai 包装转换点）。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.params_model.model_json_schema(),
        }

    @abstractmethod
    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        """执行工具；pydantic 校验失败与异常都由 executor 转成 error 结果，本方法只管正常路径。"""
