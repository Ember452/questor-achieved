"""vigilia 僵尸清扫单元测试（B-40 分批游标、B-44 双 reconcile、开关即停）。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from questor.testenv.fake_home import fake_home
from questor.vigilia import store
from questor.vigilia.constants import SWEEP_BATCH_MIN
from questor.vigilia.sweep import StaleSweeper, next_batch


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def test_next_batch_advances_cursor_without_revisiting() -> None:
    """B-40：下一批不重查本批——游标前移，连续两批无交集。"""
    ids = [f"r-{i:03d}" for i in range(25)]
    first, cursor = next_batch(ids, 0, 10)
    second, cursor = next_batch(ids, cursor, 10)
    third, _ = next_batch(ids, cursor, 10)
    assert len(first) == 10 and len(second) == 10 and len(third) == 5
    assert set(first).isdisjoint(second)
    assert set(second).isdisjoint(third)


def test_next_batch_wraps_around() -> None:
    ids = [f"r-{i:03d}" for i in range(3)]
    picked, cursor = next_batch(ids, 0, SWEEP_BATCH_MIN)
    assert picked == tuple(ids)
    assert cursor == 0  # 一批取完，环绕回起点


def test_batch_floor_prevents_spin() -> None:
    """批大小有下限：传 0/负数不会导致空转（B-40）。"""
    ids = [f"r-{i:03d}" for i in range(SWEEP_BATCH_MIN + 5)]
    picked, _ = next_batch(ids, 0, 0)
    assert len(picked) == SWEEP_BATCH_MIN


def test_empty_ids_return_empty() -> None:
    assert next_batch([], 0, 10) == ((), 0)


def test_sweep_persists_cursor_and_does_not_revisit() -> None:
    sweeper = StaleSweeper(batch=SWEEP_BATCH_MIN)
    ids = [f"r-{i:03d}" for i in range(SWEEP_BATCH_MIN * 3)]
    first = sweeper.sweep(ids)
    second = sweeper.sweep(ids)
    assert first.reconciled and second.reconciled
    assert set(first.reconciled).isdisjoint(second.reconciled)
    # 游标已持久化到检查点（重启续扫，不从头重扫）
    assert store.load_view().checkpoint.sweep_cursor == second.cursor


def test_startup_reconcile_collects_all_and_resets_cursor() -> None:
    """B-44：启动 reconcile 把当前全部 stale 运行收掉，游标归零。"""
    sweeper = StaleSweeper()
    ids = [f"r-{i:03d}" for i in range(7)]
    result = sweeper.startup_reconcile(ids)
    assert set(result.reconciled) == set(ids)
    assert result.cursor == 0


def test_disabled_sweeper_is_inert() -> None:
    """开关关闭即停：不动游标、不返回任何 id（feature flag 语义）。"""
    sweeper = StaleSweeper(enabled=False)
    result = sweeper.sweep([f"r-{i:03d}" for i in range(50)])
    assert result.reconciled == ()
    assert store.load_view().checkpoint.sweep_cursor == 0
    enabled_after = StaleSweeper()
    enabled_after.set_enabled(True)
    assert enabled_after.sweep(["r-001"]).reconciled == ("r-001",)
