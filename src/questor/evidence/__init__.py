"""evidence —— 验收证据（声称的检查 vs 当时录得的真实输出）。

承担柱子：**可验证**。M4 是最小版：只做"并排核对 + 可追溯 + 导出接口",
**不做复跑核验**（`overview.md` §2 已裁定本轮不引 AfterMatter 机制，留待 M5）。

边界：本模块是**纯函数库**（只读消费 `gesta` 的落盘 Item），不落盘、不 import 编排域；
写 Evidence 由 serve 经 `orchestration.add_evidence`（唯一存储入口）。

# Reimplements wuu@wuu-main internal/tools/review.go 语义（声称 vs 实测）— pitfalls: B-45
"""

from __future__ import annotations

from questor.evidence.compare import (
    CheckClaim,
    RecordedCheck,
    compare_claim,
    compare_claims,
    recorded_check_from_item,
)
from questor.evidence.export import EvidenceCard, EvidenceExport, evidence_card, export_evidence
from questor.evidence.projection import for_subject, verdict_counts

__all__ = [
    "CheckClaim",
    "EvidenceCard",
    "EvidenceExport",
    "RecordedCheck",
    "compare_claim",
    "compare_claims",
    "evidence_card",
    "export_evidence",
    "for_subject",
    "recorded_check_from_item",
    "verdict_counts",
]
