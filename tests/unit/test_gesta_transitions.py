"""gesta.transitions 单元行为：白名单逐字对齐 data-model §3.1 v1.1（含 ADR-0014）。"""

from __future__ import annotations

import pytest

from questor.gesta.transitions import InvalidTransition, is_terminal, transition
from questor.schemas.model import RunStatus as S


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.QUEUED, S.RUNNING),
        (S.QUEUED, S.CANCELLED),  # ADR-0014：未起跑可取消，不伪造 running 起点
        (S.RUNNING, S.STEERED),
        (S.RUNNING, S.WAITING),
        (S.RUNNING, S.COMPLETED),
        (S.RUNNING, S.FAILED),
        (S.RUNNING, S.CANCELLED),
        (S.STEERED, S.RUNNING),
        (S.WAITING, S.RUNNING),
    ],
)
def test_allowed_transitions(current: S, target: S) -> None:
    assert transition(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.QUEUED, S.COMPLETED),  # 没跑完不能声称完成
        (S.QUEUED, S.FAILED),
        (S.QUEUED, S.STEERED),  # 旁态必须经 running
        (S.QUEUED, S.WAITING),
        (S.RUNNING, S.QUEUED),  # 状态机不倒带
        (S.STEERED, S.COMPLETED),  # 旁态迁移必经 running
        (S.STEERED, S.WAITING),
        (S.WAITING, S.STEERED),
        (S.COMPLETED, S.RUNNING),
        (S.COMPLETED, S.FAILED),
        (S.FAILED, S.RUNNING),
        (S.CANCELLED, S.RUNNING),
    ],
)
def test_forbidden_transitions(current: S, target: S) -> None:
    with pytest.raises(InvalidTransition):
        transition(current, target)


@pytest.mark.parametrize("terminal", [S.COMPLETED, S.FAILED, S.CANCELLED])
def test_terminal_states(terminal: S) -> None:
    assert is_terminal(terminal)
    assert not is_terminal(S.QUEUED)
    assert not is_terminal(S.RUNNING)
