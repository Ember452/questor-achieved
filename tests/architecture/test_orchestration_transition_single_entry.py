"""硬断言：编排任务状态迁移只有 orchestration 一个写入入口（data-model §3.3，ADR-0025）。

镜像 `test_status_transition_single_entry.py`（gesta 的那条）：`orchestration.transitions`
是白名单状态机的唯一承载，只有 orchestration 包内部可以 import 它；其他模块必须经
`orchestration.store.transition_task` 推进状态。旁路 import 意味着"白名单外还有一条写状态
的路"——两套真相，直接打回。

负向验证（AGENTS §四：护栏必须会咬人）**已做**：在 `questor/schemas/__init__.py` 临时加一行
`from questor.orchestration.transitions import transition` → 本测试 FAILED；已复原。
"""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "questor"

_TRANSITIONS_QUALNAMES = frozenset(
    {
        "questor.orchestration.transitions",
        "orchestration.transitions",
        "questor.orchestration.acceptance",
        "orchestration.acceptance",
    }
)

#: orchestration 之外允许 import 的名字：异常类型（错误处理要接住它）；迁移函数仍单消费者
_ALLOWED_NAMES_OUTSIDE = frozenset({"InvalidTaskTransition", "InvalidAcceptanceTransition"})


def _violating_imports(tree: ast.AST) -> list[str]:
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in _TRANSITIONS_QUALNAMES:
            bad.extend(
                alias.name for alias in node.names if alias.name not in _ALLOWED_NAMES_OUTSIDE
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _TRANSITIONS_QUALNAMES:
                    bad.append(alias.name)
    return bad


def test_transitions_module_is_importable_only_from_orchestration() -> None:
    violations: list[str] = []
    for py in sorted(SRC.rglob("*.py")):
        parts = py.relative_to(SRC).parts
        inside = len(parts) >= 2 and parts[0] == "orchestration"
        if inside:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        bad_names = _violating_imports(tree)
        if bad_names:
            violations.append(f"{py.relative_to(SRC)} -> {bad_names}")
    assert not violations, (
        "编排状态迁移白名单被 orchestration 之外 import——出现第二套写状态入口：\n"
        + "\n".join(violations)
    )


def test_guard_has_teeth() -> None:
    """确认守卫有可检对象：任务态与验收态白名单都确实被 orchestration 内部 import。"""
    for needle in ("orchestration.transitions", "orchestration.acceptance"):
        importer_found = False
        for py in sorted((SRC / "orchestration").rglob("*.py")):
            if py.name in ("transitions.py", "acceptance.py"):
                continue
            if needle in py.read_text(encoding="utf-8"):
                importer_found = True
                break
        assert importer_found, f"orchestration 内没有 import {needle} 的模块——护栏空转，先确认重构"
