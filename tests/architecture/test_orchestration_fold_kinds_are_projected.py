"""架构守卫（B-85 的编排侧镜像）：新增 record kind 必须与 fold 分支、投影字段同批登记。

与 `test_fold_kinds_are_projected.py`（gesta）同因：`_parse_line` 对未知 kind 返回 None，
"writer 追加了新 kind、fold 忘了加分支"会**静默丢记录**。编排 store 是独立 append-only
真相源，同样需要这条护栏。

三条对齐关系：
1. 代码里 `_append_locked("<kind>", ...)` 写下的每种 kind 都在 `_RECORD_KINDS` 里；
2. `_RECORD_KINDS` 与 `_FoldState.apply` 里出现过的 kind **互为子集**（不多不少）；
3. apply 里赋值/追加到的每个 `self.<attr>` 都是 `OrchestrationView` 的字段。

负向验证（AGENTS §四）**已做**：把 `"goal.updated"` 从 `_RECORD_KINDS` 抽掉 →
第 1 条与第 2 条当场报红；已复原。
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
STORE = REPO_ROOT / "src" / "questor" / "orchestration" / "store.py"


def _tree() -> ast.Module:
    return ast.parse(STORE.read_text(encoding="utf-8"))


def _record_kinds(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_RECORD_KINDS" for t in node.targets
        ):
            return {
                c.value
                for c in ast.walk(node)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            }
    raise AssertionError("store.py 里没有 _RECORD_KINDS 常量——护栏对象消失了")


def _appended_kinds(tree: ast.Module) -> set[str]:
    kinds: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name != "_append_locked" or len(node.args) < 1:
            continue
        candidate = node.args[0]
        if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
            kinds.add(candidate.value)
    return kinds


def _fold_apply(tree: ast.Module) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "apply"
    )


def _fold_branch_kinds(apply: ast.FunctionDef) -> set[str]:
    """`record.kind == "x"` 与 `record.kind in ("x", "y")` 里的字面量。"""
    kinds: set[str] = set()
    for node in ast.walk(apply):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if not (isinstance(left, ast.Attribute) and left.attr == "kind"):
            continue
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                kinds.add(comparator.value)
            elif isinstance(comparator, ast.Tuple):
                kinds.update(
                    elt.value
                    for elt in comparator.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                )
    return kinds


def _self_attr_name(node: ast.AST) -> str | None:
    """node 若是 `self.<attr>` 则返回 `<attr>`。"""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return None


def _fold_self_attrs(apply: ast.FunctionDef) -> set[str]:
    """apply 里赋值/追加到的 `self.<attr>`（投影必须看得见的那些）。"""
    attrs: set[str] = set()
    for node in ast.walk(apply):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                name = _self_attr_name(target)
                if name:
                    attrs.add(name)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "append":
                name = _self_attr_name(node.func.value)
                if name:
                    attrs.add(name)
    return attrs


def _view_fields(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "OrchestrationView":
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError("store.py 里没有 OrchestrationView 类")


def test_appended_kinds_are_declared() -> None:
    tree = _tree()
    appended = _appended_kinds(tree)
    declared = _record_kinds(tree)
    assert appended, "没有发现 _append_locked 调用——护栏空转，先确认重构"
    assert appended <= declared, f"未登记的 record kind: {sorted(appended - declared)}"


def test_declared_and_handled_kinds_are_equal() -> None:
    tree = _tree()
    declared = _record_kinds(tree)
    handled = _fold_branch_kinds(_fold_apply(tree))
    assert declared <= handled, f"缺少 fold 分支的 record kind: {sorted(declared - handled)}"
    assert handled <= declared, f"有 fold 分支但未登记的 kind: {sorted(handled - declared)}"


def test_fold_self_attrs_are_projected() -> None:
    tree = _tree()
    attrs = _fold_self_attrs(_fold_apply(tree))
    fields = _view_fields(tree)
    # `last_seq` 也是投影字段（断线恢复锚点），因此不排除
    assert attrs, "apply 里没有 self.* 赋值/追加——护栏空转"
    assert attrs <= fields, f"未投影的 fold 属性: {sorted(attrs - fields)}"
