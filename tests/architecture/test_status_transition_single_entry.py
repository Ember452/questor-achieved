"""硬断言：运行状态迁移只有 gesta 一个写入入口（data-model §3.1）。

``questor.gesta.transitions`` 是白名单状态机的唯一承载，只有 gesta 包内部可以
import 它；其他模块必须经 ``gesta.transition_run``（持锁 + 白名单 + 落记录）推进
状态。旁路 import 意味着"白名单外还有一条写状态的路"——两套真相，直接打回。

负向验证（2026-10-11，已复原）：在 questor/state/__init__.py 临时加一行
``from questor.gesta.transitions import transition`` → 本测试 FAILED
（依赖方向违规），且同时被依赖矩阵与 import-linter 咬住。
"""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "questor"

_TRANSITIONS_QUALNAMES = frozenset(
    {
        "questor.gesta.transitions",
        "gesta.transitions",
    }
)


def _imports_transitions(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in _TRANSITIONS_QUALNAMES:
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _TRANSITIONS_QUALNAMES:
                    return True
    return False


def test_transitions_module_is_importable_only_from_gesta() -> None:
    violations: list[str] = []
    for py in sorted(SRC.rglob("*.py")):
        parts = py.relative_to(SRC).parts
        inside_gesta = len(parts) >= 2 and parts[0] == "gesta"
        if inside_gesta:
            continue  # gesta 内部（含 __init__ 的 re-export）合法
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        if _imports_transitions(tree):
            violations.append(str(py.relative_to(SRC)))
    assert not violations, (
        "状态迁移白名单被 gesta 之外 import——出现第二套写状态入口：\n" + "\n".join(violations)
    )
