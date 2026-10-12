"""架构守卫（B-85）：新增 record kind 必须与 fold 分支、ThreadView 投影同批登记。

为什么单独立一条：`_parse_line` 对**未知 kind 返回 None**（B-74 的残尾容忍顺手宽恕了
"看不懂的记录"）。于是"writer 追加了一个新 kind、fold 忘了加分支"这种半截改动会
**静默丢记录**——写进去的数据在回放时凭空消失，而所有单测可能照样绿。这正是
`context.replacements`（ADR-0017）引入时的真实风险，所以把三条对齐关系做成断言：

1. 代码里追加的每种 kind 都在 `_RECORD_KINDS` 里；
2. `_RECORD_KINDS` 里每种 kind 都在 `_FoldState.apply` 有分支；
3. apply 里往 `self.<attr>` 攒的每种列表都在 `ThreadView` 有同名字段（否则投影读不到）。

负向验证（AGENTS §四：护栏必须会咬人）**已做**：把 `"context.replacements"` 从
`_RECORD_KINDS` 抽掉后，第 1 条与正例锚点当场报红，且集成回放射到空列表
（`view.context_replacements == []`）——正好是"写进去的东西静默消失"的真形；已回退。
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
STORE = REPO_ROOT / "src" / "questor" / "gesta" / "store.py"
WRITER = REPO_ROOT / "src" / "questor" / "gesta" / "writer.py"


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _record_kinds(store_tree: ast.Module) -> set[str]:
    """取 `_RECORD_KINDS = frozenset({...})` 里的字符串字面量。"""
    for node in store_tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_RECORD_KINDS" for t in node.targets
        ):
            return {
                c.value
                for c in ast.walk(node)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            }
    raise AssertionError("store.py 里没有 _RECORD_KINDS 常量——护栏对象消失了，先确认是否改名")


#: 会往正文追加记录的函数名（共用一个追加工具，但 kind 必须逐处字面量写出）
_APPENDERS = frozenset({"_append_locked", "_append_context_locked"})


def _appended_kinds(*trees: ast.Module) -> set[str]:
    """收集 `_append_locked(state, "<kind>", ...)` 类调用的第二个位置参数字面量。"""
    kinds: set[str] = set()
    for tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name not in _APPENDERS or len(node.args) < 2:
                continue
            candidate = node.args[1]
            if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
                kinds.add(candidate.value)
    return kinds


def _fold_branch_kinds(store_tree: ast.Module) -> set[str]:
    """`_FoldState.apply` 里与 `record.kind` 比较过的字面量。"""
    apply = next(
        node
        for node in ast.walk(store_tree)
        if isinstance(node, ast.AsyncFunctionDef) is False
        and isinstance(node, ast.FunctionDef)
        and node.name == "apply"
    )
    kinds: set[str] = set()
    for node in ast.walk(apply):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if isinstance(left, ast.Attribute) and left.attr == "kind":
            kinds.update(
                c.value
                for c in node.comparators
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            )
    return kinds


def _fold_accumulators(store_tree: ast.Module) -> set[str]:
    """apply 里 `self.<attr>.append(...)` 的 attr 名。"""
    apply = next(
        node
        for node in ast.walk(store_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "apply"
    )
    accumulators: set[str] = set()
    for node in ast.walk(apply):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "append":
            continue
        target = node.func.value
        owner = getattr(target, "value", None)
        if isinstance(target, ast.Attribute) and isinstance(owner, ast.Name) and owner.id == "self":
            accumulators.add(target.attr)
    return accumulators


def _thread_view_fields(store_tree: ast.Module) -> set[str]:
    for node in store_tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ThreadView":
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError("store.py 里没有 ThreadView 类")


def test_appended_kinds_are_declared() -> None:
    """写进去的每种 kind 都必须被登记，否则读侧按"看不懂的行"跳过（B-85）。"""
    store_tree = _tree(STORE)
    declared = _record_kinds(store_tree)
    appended = _appended_kinds(store_tree, _tree(WRITER))
    assert appended, "没有发现任何追加工具调用——本测试会空转，先确认重构"
    assert appended <= declared, f"未登记的 record kind: {sorted(appended - declared)}"


def test_declared_kinds_have_fold_branches() -> None:
    """登记的每种 kind 都要有 fold 分支，否则它被读出来又随手丢掉。"""
    store_tree = _tree(STORE)
    declared = _record_kinds(store_tree)
    handled = _fold_branch_kinds(store_tree)
    assert declared <= handled, f"缺少 fold 分支的 record kind: {sorted(declared - handled)}"


def test_fold_accumulators_are_projected() -> None:
    """fold 攒下的每个列表都必须出现在 ThreadView 里（否则恢复方读不到）。

    `thread`/`turns`/`runs`/`items`/`events`/`context_replacements` 都在此列——
    少一个字段就等于"记录在盘上、投影里不存在"。
    """
    store_tree = _tree(STORE)
    accumulators = _fold_accumulators(store_tree)
    fields = _thread_view_fields(store_tree)
    assert accumulators, "apply 里没有 self.*.append——本测试会空转，先确认重构"
    assert accumulators <= fields, f"未投影的 fold 累积器: {sorted(accumulators - fields)}"


def test_context_replacements_round_trips_through_the_guard() -> None:
    """正例锚点：ADR-0017 引入的 kind 确实处在三条对齐关系的交集里。"""
    store_tree = _tree(STORE)
    kinds = _record_kinds(store_tree) & _appended_kinds(store_tree, _tree(WRITER))
    assert "context.replacements" in kinds
    assert "context.replacements" in _fold_branch_kinds(store_tree)
    assert "context_replacements" in _thread_view_fields(store_tree)
