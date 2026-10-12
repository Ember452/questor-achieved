"""sessiontrace —— 会话轨迹回放（不重跑工具、不联系模型；overview §6）。

**投影 = fold 的切片**：从 `gesta.load_thread` 拿 ThreadView，按 turn 分组 items/events，
输出 `TurnTrace`。本包**只读**，不写盘不改状态；崩溃恢复与 UI 回放都走同一入口。

依赖方向：sessiontrace → gesta + schemas，反向禁止。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from questor.gesta.store import ThreadView


class TurnTrace(BaseModel):
    """一轮 turn 的完整投影：turn 元信息 + 该轮覆盖的 run 与 item / event。"""

    model_config = ConfigDict(frozen=True)

    turn_id: str
    seq: int
    origin: str
    run_ids: tuple[str, ...]
    items: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]


def project_turn(view: ThreadView, turn_id: str) -> TurnTrace | None:
    """按 turn_id 从 view 抽该轮所有 items 与 events；turn 不存在返回 None。"""
    turn = next((t for t in view.turns if t.id == turn_id), None)
    if turn is None:
        return None
    runs_of_turn = tuple(r for r in view.runs if r.turn_id == turn_id)
    run_ids = tuple(r.id for r in runs_of_turn)
    run_id_set = set(run_ids)
    items = tuple(item.model_dump(mode="json") for item in view.items if item.run_id in run_id_set)
    events = tuple(
        event.model_dump(mode="json") for event in view.events if event.turn_id == turn_id
    )
    return TurnTrace(
        turn_id=turn.id,
        seq=turn.seq,
        origin=turn.origin.value,
        run_ids=run_ids,
        items=items,
        events=events,
    )


def project_thread(view: ThreadView) -> tuple[TurnTrace, ...]:
    """整线程的 turn 序列投影（按 seq 递增）。"""
    traces = [project_turn(view, turn.id) for turn in view.turns]
    return tuple(t for t in traces if t is not None)
