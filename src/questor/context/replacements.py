"""替换决策状态（B-25 的持久面：seen / representations 跨轮保持）。

为什么必须有它：同一轮的工具结果若每轮重新判定，预览长度会随手抖动——模型会看到
"同一条结果上一轮是全文、这一轮是预览"，等于对同一事实给出两套表示。决策一旦做出就
钉住，后续轮次直接复用（FlowCoder 的 `ContentReplacementState` 同一语义，重写实现）。

状态本身不是真相源：它由 `context.replacements` 记录（会话正文）重建，见
:func:`state_from_records`——进程重启/崩溃后判定结果可复现。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from questor.schemas.context import ReplacementRecord

__all__ = ["ReplacementState", "records_from_state", "state_from_records"]


@dataclass
class ReplacementState:
    """一轮接一轮累积的替换决策。``representations`` 的键只会是见过的 tool_use_id。"""

    seen_ids: set[str] = field(default_factory=set)
    representations: dict[str, str] = field(default_factory=dict)
    #: 陈旧裁剪从哪个轮序号起生效（B-27：边界入状态，不靠每次重算）
    stale_boundary_turn: int | None = None
    #: 本轮新做的决策（供落盘成一条 `context.replacements` 记录）
    pending: list[ReplacementRecord] = field(default_factory=list)

    def decide(self, tool_use_id: str, representation: str, spilled_file: str | None) -> None:
        """钉住一条结果的会话内表示（同 id 二次调用不覆盖——决策已做就不再改）。"""
        if tool_use_id in self.representations:
            return
        self.representations[tool_use_id] = representation
        self.seen_ids.add(tool_use_id)
        self.pending.append(
            ReplacementRecord(
                tool_use_id=tool_use_id, representation=representation, spilled_file=spilled_file
            )
        )

    def mark_seen(self, tool_use_id: str) -> None:
        self.seen_ids.add(tool_use_id)

    def clear_pending(self) -> list[ReplacementRecord]:
        """取走本轮增量（落盘后调用，避免下一轮重复追加同一批决策）。"""
        taken = list(self.pending)
        self.pending.clear()
        return taken


def records_from_state(state: ReplacementState) -> list[ReplacementRecord]:
    """状态 → 可落盘的全量决策快照（诊断与验收导出用；正文只追加 pending）。"""
    return [
        ReplacementRecord(tool_use_id=key, representation=value, spilled_file=None)
        for key, value in sorted(state.representations.items())
    ]


def state_from_records(records: Iterable[Any], candidate_ids: Iterable[str]) -> ReplacementState:
    """从历史 `context.replacements` 记录重建状态（B-25/B-27 的恢复面）。

    只采纳**仍在会话历史里**的 tool_use_id：已随压缩离场的结果不该继续占内存，否则
    长跑会话的状态会无界增长。多条记录按到达顺序覆盖，边界取最后一个非空值。
    """
    state = ReplacementState()
    candidates = set(candidate_ids)
    for record in records:
        for decision in record.records:
            if decision.tool_use_id in candidates:
                state.representations[decision.tool_use_id] = decision.representation
                state.seen_ids.add(decision.tool_use_id)
        state.seen_ids.update(i for i in record.seen_ids if i in candidates)
        if record.stale_boundary_turn is not None:
            state.stale_boundary_turn = record.stale_boundary_turn
    return state
