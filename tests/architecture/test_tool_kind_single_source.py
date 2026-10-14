"""架构护栏：`ToolKind` 只许一处定义（tools 与 limen 共用同一个对象）。

审计发现的形状：`tools/base.py:27` 与 `limen/gate.py:40` 曾各写一遍
`Literal["file","shell","process","meta"]`。两份字面量抄本的危害不是重复，而是
**它们可以各自漂**：给 limen 加一档 `"browser"` 而 tools 侧忘了跟，executor 按
tools 的类型标注构造判定输入、门按 limen 的类型消费，pyright 各自都绿，运行时
却是一个门永远判不到的类别（新工具静默落到兜底档）。

正确解法是把定义放到中立层 `schemas/model.py`：`tools`（第 7 层）与 `limen`（第 9 层）
都在 `schemas`（底层）之上，分层契约允许两边向下 import，而 tools→limen 仍被
`test_permission_gate_single_entry` 禁着——所以 schemas 是唯一能同时服务两处的家。

负向验证：把任一文件改回本地 `Literal[...]` 定义，本文件即红。

**为何不用 `is` 比对象**（实测踩坑）：`typing` 对 `Literal` 按参数元组缓存特化，
两份各自手写的 `Literal["file", ...]` 拿到的**是同一个对象**，`base.ToolKind is
gate.ToolKind` 在分叉状态下仍为绿——一条不会咬人的护栏等于没写（AGENTS §四）。
故这里扫源码 AST 的**赋值定义点**，它不受运行时缓存影响。
"""

from __future__ import annotations

import ast
import pathlib
from typing import get_args

from questor.schemas import model

SRC_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "questor"

#: 唯一允许给 `ToolKind` 赋值的模块（其余位置只能 import）
_DEFINER = "questor/schemas/model.py"


def _assign_targets(rel_path: pathlib.Path) -> set[str]:
    """取一个模块顶层赋值的名字集合（`X = ...` 与 `X: T = ...` 都算）。"""
    tree = ast.parse(rel_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_tool_kind_is_defined_in_exactly_one_module() -> None:
    """全仓扫定义点：`ToolKind` 只能由 schemas 赋值，别处抄一份即红。"""
    definers = {
        path.relative_to(SRC_ROOT.parent).as_posix()
        for path in SRC_ROOT.rglob("*.py")
        if "ToolKind" in _assign_targets(path)
    }
    assert definers == {_DEFINER}, f"ToolKind 的定义点不止一处: {sorted(definers)}"


def test_tool_kind_members_are_the_declared_four() -> None:
    """四档取值逐字锁定：新增类别要同时改门判定与呈现，不许只加一处。"""
    assert get_args(model.ToolKind) == ("file", "shell", "process", "meta")


def test_tools_and_limen_import_the_shared_symbol() -> None:
    """两侧都是 import 而非本地定义（确认护栏没把真实消费面漏掉）。"""
    from questor.limen import gate
    from questor.tools import base

    assert base.ToolKind is model.ToolKind
    assert gate.ToolKind is model.ToolKind
