"""僵尸运行清扫：一批一间隔 + 游标分批 + 启动/周期双 reconcile（ADR-0026）。

为什么必须自建：`overview.md` §3 裁定 EvoFlow 的自愈清扫绑在框架 runs API 上、换底座即失效，
Questor 不依赖任何框架 API——清扫只读落盘事实，reconcile 的判据由调用方给出
（谁掌握运行时真相，谁给候选集；清扫器只管"怎么扫、怎么判终止"）。

两道坑：
- **B-40**：清扫必须分批带游标——无 offset 重查同一 top-N，当 sticky running ≥ batch 时
  会每 0.5s 紧密空转。`next_batch` 保证游标单调推进、下一批不重查本批。
- **B-44**：运行状态真值在运行时侧，重启必有 stale running——**启动 + 周期双 reconcile**
  是补救本身，不是可选优化。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from questor.schemas.vigilia import ScheduleCheckpoint
from questor.vigilia import store
from questor.vigilia.constants import SWEEP_BATCH_MIN

__all__ = ["StaleSweeper", "SweepResult", "next_batch"]

logger = logging.getLogger(__name__)


def next_batch(ids: Sequence[str], cursor: int, batch: int) -> tuple[tuple[str, ...], int]:
    """按游标从有序 id 列表取一批；返回 (本批, 下一游标)。

    `next_batch` 是纯函数：游标从 `cursor % n` 起取 `batch` 个并前移，
    因此**下一批不会重查本批**（B-40）；取到末尾时环绕到下轮继续。
    批大小有下限（`SWEEP_BATCH_MIN`），防调用方传 0/负数导致空转。
    """
    if not ids:
        return (), 0
    size = max(batch, SWEEP_BATCH_MIN)
    ordered = sorted(ids)
    start = cursor % len(ordered)
    picked = tuple(ordered[start : start + size])
    return picked, (start + len(picked)) % len(ordered)


@dataclass(frozen=True)
class SweepResult:
    """一次清扫的结果（游标、本批数量、被判 stale 的 id）。"""

    cursor: int
    scanned: int
    reconciled: tuple[str, ...]


class StaleSweeper:
    """僵尸运行清扫器：游标持久化在 vigilia 检查点里（重启续扫，不从头重扫）。"""

    def __init__(self, *, batch: int = SWEEP_BATCH_MIN, enabled: bool = True) -> None:
        self._batch = batch
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """清扫可整体开关（feature flag 语义，ADR-0026）。"""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def sweep(self, stale_ids: Sequence[str]) -> SweepResult:
        """周期清扫：一批一间隔，剩余下轮再收（B-40）。关闭时不动游标、不返回任何 id。"""
        view = store.load_view()
        cursor = view.checkpoint.sweep_cursor
        if not self._enabled:
            return SweepResult(cursor=cursor, scanned=0, reconciled=())
        picked, next_cursor = next_batch(stale_ids, cursor, self._batch)
        store.set_checkpoint(
            ScheduleCheckpoint(last_tick_at=view.checkpoint.last_tick_at, sweep_cursor=next_cursor)
        )
        if picked:
            logger.info(
                "清扫 reconcile %d 个 stale 运行（游标 %d→%d）", len(picked), cursor, next_cursor
            )
        return SweepResult(cursor=next_cursor, scanned=len(picked), reconciled=picked)

    def startup_reconcile(self, stale_ids: Sequence[str]) -> SweepResult:
        """启动 reconcile（B-44）：重启后一次性把当前全部 stale 运行收掉，游标归零。"""
        view = store.load_view()
        if not self._enabled:
            return SweepResult(cursor=view.checkpoint.sweep_cursor, scanned=0, reconciled=())
        ordered = tuple(sorted(stale_ids))
        store.set_checkpoint(
            ScheduleCheckpoint(last_tick_at=view.checkpoint.last_tick_at, sweep_cursor=0)
        )
        if ordered:
            logger.info("启动 reconcile %d 个 stale 运行", len(ordered))
        return SweepResult(cursor=0, scanned=len(ordered), reconciled=ordered)
