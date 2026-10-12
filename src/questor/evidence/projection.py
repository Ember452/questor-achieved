"""evidence 投影：按 subject 汇总核对结论（供 serve `evidence/get` 与 UI 证据卡消费）。"""

from __future__ import annotations

from questor.schemas.orchestration import Evidence

__all__ = ["for_subject", "verdict_counts"]


def for_subject(
    items: tuple[Evidence, ...], *, subject_type: str, subject_id: str
) -> tuple[Evidence, ...]:
    """某 subject 的全部证据（按创建顺序）。"""
    return tuple(
        item
        for item in items
        if item.subject_type.value == subject_type and item.subject_id == subject_id
    )


def verdict_counts(items: tuple[Evidence, ...]) -> dict[str, int]:
    """各结论计数（`verified` / `mismatch` / `unverified`）——审阅面的概览数字。"""
    counts = {"verified": 0, "mismatch": 0, "unverified": 0}
    for item in items:
        counts[item.verdict.value] = counts.get(item.verdict.value, 0) + 1
    return counts
