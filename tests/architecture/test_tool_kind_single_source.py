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


def test_tool_kind_membership_matches_master_vocabulary() -> None:
    """词表逐字锁定：取齐母本 wuu ``internal/tools/tool_info.go`` 的 ``ToolKind`` 常量集。

    ``meta`` 是旧 questor 词（wuu 无对应值，语义最接近 ``unknown``），工具层重写时收敛删除；
    差异已登 port-ledger，因此本断言同时是"临时偏离"的到期计时器。
    """
    wuu_kinds = {
        "file",
        "search",
        "discovery",
        "shell",
        "test",
        "git",
        "web",
        "session",
        "skill",
        "agent",
        "process",
        "schedule",
        "mcp",
        "browser",
        "plugin",
        "unknown",
    }
    assert set(get_args(model.ToolKind)) == wuu_kinds | {"meta"}


def test_every_tool_kind_is_classified_by_the_gate() -> None:
    """每个取值都必须被门的判定表明列（变更类 / 非变更类其一），两表不得重叠。

    旧护栏只锁“四个值都在”，加一档时靠人不漏；本条把“只加一处”从人纪变成机纪：
    新类别若不进 `limen/boundary` 的两张表之一就红（B-133）。
    """
    from questor.limen import boundary

    members = set(get_args(model.ToolKind))
    classified = set(boundary.MUTATING_KINDS) | set(boundary.NON_MUTATING_KINDS)
    assert members - classified == set(), f"工具类未被门判定表覆盖：{sorted(members - classified)}"
    overlap = set(boundary.MUTATING_KINDS) & set(boundary.NON_MUTATING_KINDS)
    assert not overlap, "同一类不能两表都在"
    assert classified - members == set(), "表里有词表没有的值（拼写漂移）"


def test_tools_and_limen_import_the_shared_symbol() -> None:
    """两侧都是 import 而非本地定义（确认护栏没把真实消费面漏掉）。"""
    from questor.limen import gate
    from questor.tools import base

    assert base.ToolKind is model.ToolKind
    assert gate.ToolKind is model.ToolKind
