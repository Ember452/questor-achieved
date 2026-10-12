"""evidence 核对器：把"声称的检查"与"当时录得的真实输出"并排核对（ADR-0027）。

只读消费：输入是落盘的 Item（tool_result）与模型声称的检查文本，**不重跑工具、不联系模型**。
结论必须带 `recorded_output_ref`（指向 Item id 或 spill 回链），无记录即 `unverified`——
不臆断打分（诚实呈现铁律）。

本模块是**纯函数库**：不落盘、不 import 编排域。写 Evidence 由 serve 经
`orchestration.add_evidence` 完成（那是唯一存储入口）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from questor.schemas.model import Item, ItemKind, utc_timestamp_now
from questor.schemas.orchestration import Evidence, EvidenceSubjectType, EvidenceVerdict

__all__ = [
    "CheckClaim",
    "RecordedCheck",
    "compare_claim",
    "compare_claims",
    "recorded_check_from_item",
]


@dataclass(frozen=True)
class CheckClaim:
    """模型/工具声称做过的一次检查（如"pytest 通过"）；`tool_use_id` 指向对应结果。"""

    claimed: str
    tool_use_id: str | None = None


@dataclass(frozen=True)
class RecordedCheck:
    """当时真实录得的一次工具结果。"""

    tool_use_id: str
    output: str
    is_error: bool
    ref: str  # 指向具体记录条目：Item id 或落盘 spill 文件名


def recorded_check_from_item(item: Item) -> RecordedCheck | None:
    """从落盘的 tool_result Item 提取真实录得结果；非 tool_result 返回 None。"""
    if item.kind != ItemKind.TOOL_RESULT:
        return None
    payload = item.payload
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_use_id, str):
        return None
    output = payload.get("output")
    if not isinstance(output, str):
        preview = payload.get("preview")
        output = preview if isinstance(preview, str) else ""
    spilled = payload.get("spilled")
    ref = spilled if isinstance(spilled, str) else item.id
    return RecordedCheck(
        tool_use_id=tool_use_id,
        output=output,
        is_error=bool(payload.get("is_error")),
        ref=ref,
    )


def compare_claim(
    claim: CheckClaim,
    recorded: RecordedCheck | None,
    *,
    subject_type: EvidenceSubjectType,
    subject_id: str,
) -> Evidence:
    """核对一条声称：无记录 → unverified；记录为错误 → mismatch；否则 verified。"""
    if recorded is None:
        verdict = EvidenceVerdict.UNVERIFIED
        ref = ""
    elif recorded.is_error:
        verdict = EvidenceVerdict.MISMATCH
        ref = recorded.ref
    else:
        verdict = EvidenceVerdict.VERIFIED
        ref = recorded.ref
    return Evidence(
        id=f"ev-{uuid.uuid4().hex[:12]}",
        subject_type=subject_type,
        subject_id=subject_id,
        claimed=claim.claimed,
        recorded_output_ref=ref,
        verdict=verdict,
        created_at=utc_timestamp_now(),
    )


def compare_claims(
    claims: list[CheckClaim],
    recorded: dict[str, RecordedCheck],
    *,
    subject_type: EvidenceSubjectType,
    subject_id: str,
) -> tuple[Evidence, ...]:
    """批量核对：按 `tool_use_id` 在录得结果里查找；缺 key 即 unverified。"""
    return tuple(
        compare_claim(
            claim,
            recorded.get(claim.tool_use_id) if claim.tool_use_id else None,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        for claim in claims
    )
