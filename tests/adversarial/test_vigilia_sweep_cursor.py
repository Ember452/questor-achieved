"""对抗用例（B-40）：sticky running ≥ batch 时清扫不空转。

场景：一批 stale 运行一直"粘着"（reconcile 是幂等 no-op，id 不退场）。若清扫器无游标、
每轮都重查同一 top-N，就会紧密空转——这正是 EvoFlow 记录过的历史坑。
本用例断言：连续多轮 sweep 的返回集**逐轮错位推进**，同一轮不重扫上一轮的集合。

`tests/adversarial/` 只增不减（AGENTS §四）。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from questor.testenv.fake_home import fake_home
from questor.vigilia.constants import SWEEP_BATCH_MIN
from questor.vigilia.sweep import StaleSweeper


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def test_sticky_stale_set_does_not_spin() -> None:
    # 粘着的 stale 集合：3 批规模，永不缩小（最坏情况）
    sticky = [f"r-{i:03d}" for i in range(SWEEP_BATCH_MIN * 3)]
    sweeper = StaleSweeper(batch=SWEEP_BATCH_MIN)
    seen: list[tuple[str, ...]] = []
    for _ in range(6):
        result = sweeper.sweep(sticky)
        seen.append(result.reconciled)
    # 连续两轮不得返回同一集合（否则就是无 offset 的紧密空转）
    for previous, current in zip(seen, seen[1:], strict=False):
        assert previous != current, f"连续两轮重扫同一批：{previous}"
    # 且每轮批量不超过 batch 下限的规模（分批，不一次全扫）
    assert all(len(batch) <= SWEEP_BATCH_MIN for batch in seen)


def test_cursor_cycle_covers_all_ids_before_repeat() -> None:
    """游标环绕：一轮周期内覆盖全部 id 才回到起点（不遗漏、不提前重复）。"""
    sticky = [f"r-{i:03d}" for i in range(SWEEP_BATCH_MIN * 2)]
    sweeper = StaleSweeper(batch=SWEEP_BATCH_MIN)
    covered: set[str] = set()
    for _ in range(2):
        covered.update(sweeper.sweep(sticky).reconciled)
    assert covered == set(sticky)
