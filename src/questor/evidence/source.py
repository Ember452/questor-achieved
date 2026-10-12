"""evidence 录得源：只读消费 gesta 落盘的 tool_result，把"声称"与"当时真实输出"核对（ADR-0029）。

这是"可验证柱"的**唯一录得入口**：`collect_recorded(thread_id)` 从会话记录 fold 出的 Item
里取真实工具结果，`verify_claims(...)` 用核对器（`compare.py`）逐条比对，产出 `Evidence`。

边界（与 ADR-0027 一致）：**只读、不落盘、不 import 编排域**。写 Evidence 由 serve/orchestration
经 `orchestration.add_evidence`（唯一存储入口）。将来接沙箱复跑核验，只需替换 `collect_recorded`
的实现源（重放工具产真实输出），`verify_claims` 与 `Evidence`/export/验收态契约零改动。

线程纪律：`load_thread` 是阻塞磁盘 IO，调用方（serve/orchestration）在事件循环里须走
`asyncio.to_thread`。

# Reimplements wuu@wuu-main internal/tools/review.go 语义（声称 vs 实测）— pitfalls: B-45 B-101
"""

from __future__ import annotations

from collections.abc import Sequence

from questor.evidence.compare import (
    CheckClaim,
    RecordedCheck,
    compare_claims,
    recorded_check_from_item,
)
from questor.gesta import ThreadNotFound, load_thread
from questor.schemas.orchestration import ClaimedCheck, Evidence, EvidenceSubjectType

__all__ = ["collect_recorded", "verify_claims"]


def collect_recorded(thread_id: str) -> dict[str, RecordedCheck]:
    """读某线程落盘的 tool_result，按 `tool_use_id` 建真实录得结果表。

    线程不存在 → 空表（诚实：没有记录就没有"实测"，交给上层判 `unverified`，不臆造）。
    """
    if not thread_id:
        return {}
    try:
        view = load_thread(thread_id)
    except ThreadNotFound:
        return {}
    recorded: dict[str, RecordedCheck] = {}
    for item in view.items:
        check = recorded_check_from_item(item)
        if check is not None:
            recorded[check.tool_use_id] = check
    return recorded


def verify_claims(
    thread_id: str,
    checks: Sequence[ClaimedCheck],
    *,
    subject_type: EvidenceSubjectType,
    subject_id: str,
) -> tuple[Evidence, ...]:
    """把一批声称与该线程的录得结果并排核对，返回逐条 `Evidence`（不落盘）。

    缺记录、绑到不存在/陈旧 `tool_use_id` 一律 `unverified`（诚实呈现，B-101）。
    """
    recorded = collect_recorded(thread_id)
    claims = [CheckClaim(claimed=c.claimed, tool_use_id=c.tool_use_id) for c in checks]
    return compare_claims(
        claims,
        recorded,
        subject_type=subject_type,
        subject_id=subject_id,
    )
