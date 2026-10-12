"""护栏：engine 循环形状（B-05 常量单表 + B-06 禁巨型函数）的机械保证。

负向验证（2026-10-11，已复原）：往 loop.py 临时塞一个 81 行的函数 →
``test_no_giant_functions_in_loop`` FAILED；把 MAX_ITERATIONS 字面量抄进 loop.py
的 UPPER_CASE 赋值 → ``test_thresholds_live_in_constants_table`` FAILED。
"""

from __future__ import annotations

import ast
import pathlib

ENGINE_SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "questor" / "engine"

# FlowCoder core.py 的 1076 行巨型 `_run_loop`（单函数 ~400 行）是 B-06 反例。
# 上限定 80：带判定的编排函数天然在 60-80 行之间，真正的反例是数百行；
# 80 仍会咬住任何"往循环里继续塞逻辑"的回归。
MAX_FUNCTION_LINES = 80


def test_thresholds_live_in_constants_table() -> None:
    """B-05：阈值只允许住在 constants.py——loop.py 等不得新增 UPPER_CASE 数值常量。"""
    violations: list[str] = []
    for py in ENGINE_SRC.glob("*.py"):
        if py.name == "constants.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        violations.append(f"{py.name}: {target.id}")
    assert not violations, "阈值常量必须集中在 constants.py（B-05）：\n" + "\n".join(violations)


def test_no_giant_functions_in_loop() -> None:
    """B-06：循环拆显式状态机——loop.py 单函数不得超过 MAX_FUNCTION_LINES 行。"""
    tree = ast.parse((ENGINE_SRC / "loop.py").read_text(encoding="utf-8"), filename="loop.py")
    giants: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.end_lineno is not None and node.lineno is not None
            length = node.end_lineno - node.lineno + 1
            if length > MAX_FUNCTION_LINES:
                giants.append(f"{node.name}: {length} lines")
    assert not giants, "loop.py 出现巨型函数（B-06 反例回归）：\n" + "\n".join(giants)
