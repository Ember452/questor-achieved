"""evidence 导出：把核对结论打包成**先定死为接口**的形状（overview §14 已留的门）。

形状一旦定下，将来接复跑核验或纵向统计时只改消费方，不改事件契约（ADR-0027）。
本模块只做形状与序列化，不做 IO、不落盘。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from questor.schemas.model import utc_timestamp_now
from questor.schemas.orchestration import Evidence, EvidenceSubjectType, EvidenceVerdict

__all__ = ["EvidenceCard", "EvidenceExport", "evidence_card", "export_evidence"]


class EvidenceCard(BaseModel):
    """一条证据的可展示形态（结论可点击回 `recorded_output_ref`）。"""

    model_config = ConfigDict(frozen=True)

    id: str
    subject_type: EvidenceSubjectType
    subject_id: str
    claimed: str
    recorded_output_ref: str
    verdict: EvidenceVerdict


class EvidenceExport(BaseModel):
    """导出包：`generated_at` + 证据卡片列表。"""

    model_config = ConfigDict(frozen=True)

    generated_at: str
    items: tuple[EvidenceCard, ...]


def evidence_card(item: Evidence) -> EvidenceCard:
    return EvidenceCard(
        id=item.id,
        subject_type=item.subject_type,
        subject_id=item.subject_id,
        claimed=item.claimed,
        recorded_output_ref=item.recorded_output_ref,
        verdict=item.verdict,
    )


def export_evidence(items: tuple[Evidence, ...]) -> EvidenceExport:
    """打包导出（形状固定：`generated_at` + `items`）。"""
    return EvidenceExport(
        generated_at=utc_timestamp_now(),
        items=tuple(evidence_card(item) for item in items),
    )
