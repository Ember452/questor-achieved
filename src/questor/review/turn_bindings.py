"""turn ↔ workspace_revision 绑定与聚合（overview §7 / ADR-0005 落地）。

`review/turn_diff` 从 thread view 里按 turn_id 抽出该 turn 覆盖的所有 run 的
tool_result Item，取 `payload["diff"]` 汇总——前端只吃结构化 diff，不重读文件。

Run.workspace_revision_start / _end 字段属模型层已就位（M2.1 落 model.py），
本模块只做读取投影；写入由 engine 在 run 起点/终点通过 writer 落 record。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from questor.review.diff import FileDiff

if TYPE_CHECKING:
    from questor.gesta.store import ThreadView


def aggregate_turn_diff(view: ThreadView, turn_id: str) -> list[FileDiff]:
    """扫该 turn 覆盖的 run 里的 tool_result Item，抽 diff 聚合。

    非工具写Item 的 diff 字段（读工具不产生 diff）跳过；payload 里 `diff` 存在但
    形状不合（不是 dict）也跳过，宁缺毋滥——不造对不上的呈现。
    """
    runs_by_turn = {run.id: run for run in view.runs if run.turn_id == turn_id}
    out: list[FileDiff] = []
    for item in view.items:
        if item.run_id not in runs_by_turn:
            continue
        if item.kind.value != "tool_result":
            continue
        payload: dict[str, Any] = item.payload
        diff = payload.get("diff")
        if isinstance(diff, dict) and "path" in diff and "hunks" in diff:
            out.append(diff)  # type: ignore[arg-type]
    return out
