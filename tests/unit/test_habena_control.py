"""单元：接管栅栏的 CAS + revision 语义（overview §12 出口判据 3 "接管即停"）。

表驱动：take_over / pause / release 三动作 × 有/无 expected_revision × 当前 holder 组合。
不测 engine 消费（integration 侧覆盖）；本文件只管 control.py 的形状。
"""

from __future__ import annotations

import pytest

from questor.habena import ControlError, SessionControl


def test_take_over_then_release_roundtrip() -> None:
    control = SessionControl()
    assert control.state.holder == "agent"
    assert control.state.revision == 0

    state = control.take_over()
    assert state.holder == "user"
    assert state.revision == 1
    assert control.is_taken_over

    state = control.release()
    assert state.holder == "agent"
    assert state.revision == 2


def test_stale_take_over_is_rejected() -> None:
    control = SessionControl()
    control.take_over(expected_revision=0)
    with pytest.raises(ControlError) as exc:
        control.take_over(expected_revision=0)  # 已过时的 revision
    assert exc.value.code == "stale_revision"


def test_release_without_take_over_is_invalid() -> None:
    """防 stale UI 撤销人的接管：holder 不是 user 时 release 无效。"""
    control = SessionControl()
    with pytest.raises(ControlError) as exc:
        control.release()
    assert exc.value.code == "invalid_params"


def test_pause_preserves_holder_and_bumps_revision() -> None:
    control = SessionControl()
    control.take_over()
    state = control.pause()
    assert state.holder == "user"  # pause 不切 holder
    assert state.revision == 2
    assert state.paused is True


def test_release_clears_paused() -> None:
    control = SessionControl()
    control.take_over()
    control.pause()
    state = control.release()
    assert state.paused is False
    assert state.holder == "agent"
