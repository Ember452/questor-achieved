"""失败四分类器的行为测试（对照口径必须与 FlowCoder 一致，否则失败率不可比）。

`evals` 已做成包（`evals/__init__.py`），因此静态检查能解析这个导入；
它仍是**非生产代码**，只由跑批器与测试 import。
"""

from __future__ import annotations

import pytest
from evals.runner.failure_tax import FailureKind, classify


def test_timeout_is_budget() -> None:
    assert classify(1, "", timed_out=True, rounds_exhausted=False) is FailureKind.BUDGET


def test_exhausted_rounds_is_budget() -> None:
    assert classify(1, "", timed_out=False, rounds_exhausted=True) is FailureKind.BUDGET


def test_syntax_markers_win_over_exit_code() -> None:
    assert (
        classify(2, "Traceback: SyntaxError: invalid syntax", False, False) is FailureKind.COMPILE
    )


def test_assertion_is_logic() -> None:
    assert classify(1, "AssertionError: 1 != 2", False, False) is FailureKind.LOGIC


def test_runtime_exception_is_test_comprehension() -> None:
    assert classify(1, "KeyError: 'month'", False, False) is FailureKind.TEST_COMPREHENSION


def test_bare_nonzero_exit_falls_back_to_logic() -> None:
    """无特征但退出码非 0：这是参数真正被使用的分支。"""
    assert classify(1, "some unknown failure text", False, False) is FailureKind.LOGIC


def test_contradictory_call_raises() -> None:
    """负向：退出码为 0 且无任何失败特征时不许猜分类，必须报错。

    去掉实现里的 raise 分支，本测试即失败——它是有牙齿的守卫。
    """
    with pytest.raises(ValueError, match="无失败特征"):
        classify(0, "", timed_out=False, rounds_exhausted=False)
