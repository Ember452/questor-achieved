"""编排任务状态机单测（data-model §3.3，ADR-0025）。"""

from __future__ import annotations

import pytest

from questor.orchestration.transitions import (
    InvalidTaskTransition,
    allowed_targets,
    is_terminal,
    transition,
)
from questor.schemas.orchestration import TaskStatus as TS


def test_reject_to_executing_is_allowed() -> None:
    """reviewed → executing 即"打回重做"（M4 出口链一环）。"""
    assert transition(TS.REVIEWED, TS.EXECUTING) is TS.EXECUTING


def test_terminal_states_have_no_exit() -> None:
    assert is_terminal(TS.COMPLETED) and is_terminal(TS.CANCELLED)
    for target in TS:
        with pytest.raises(InvalidTaskTransition):
            transition(TS.COMPLETED, target)


def test_illegal_transition_rejected() -> None:
    with pytest.raises(InvalidTaskTransition):
        transition(TS.INBOX, TS.EXECUTING)  # inbox 不可直接执行


def test_allowed_targets_fail_closed_on_unknown() -> None:
    """未知状态不猜——返回空集（fail closed）。"""
    assert allowed_targets("no-such-status") == frozenset()


def test_whitelist_covers_every_state() -> None:
    """每个状态都在白名单里有条目（加状态时不能漏进表）。"""
    for status in TS:
        allowed_targets(status)  # 不缺条目


def test_whitelist_matches_data_model_s3_3() -> None:
    """抽样逐条对齐 data-model §3.3（防止随手改表）。"""
    assert allowed_targets(TS.EXECUTING) == frozenset(
        {TS.PAUSED, TS.COMPLETED, TS.REVIEWED, TS.FAILED, TS.CANCELLED}
    )
    assert allowed_targets(TS.PAUSED) == frozenset({TS.EXECUTING, TS.CANCELLED})
    assert allowed_targets(TS.FAILED) == frozenset({TS.EXECUTING})
