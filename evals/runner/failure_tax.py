"""失败四分类（与 FlowCoder `eval/failure_tax.py` 语义对齐，2026-10-11 实测摘录）。

对照报告的"失败率"必须按同一分类口径计算，否则两个被测者不可比。
"""

from __future__ import annotations

from enum import Enum


class FailureKind(str, Enum):
    COMPILE = "compile"  # 语法/编译错（SyntaxError/IndentationError/编译失败）
    LOGIC = "logic"  # 断言失败（AssertionError）及无特征兜底
    TEST_COMPREHENSION = "test_comprehension"  # 其他运行时异常（TypeError/KeyError/...）
    BUDGET = "budget"  # 执行超时或修复轮耗尽


def classify(outcome_exit_code: int, stderr: str, timed_out: bool, rounds_exhausted: bool) -> FailureKind:
    """按 FlowCoder 同族规则归类一次失败。"""
    if timed_out or rounds_exhausted:
        return FailureKind.BUDGET
    markers = ("SyntaxError", "IndentationError", "TabError")
    if any(m in stderr for m in markers):
        return FailureKind.COMPILE
    if "AssertionError" in stderr:
        return FailureKind.LOGIC
    runtime_markers = ("TypeError", "KeyError", "AttributeError", "IndexError", "NameError", "ValueError", "RecursionError")
    if any(m in stderr for m in runtime_markers):
        return FailureKind.TEST_COMPREHENSION
    return FailureKind.LOGIC
