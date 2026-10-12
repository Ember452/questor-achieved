"""evals grader：把 tasks.json 声明的 `replay_audit` / `recorded_output` 核验接到真实产品函数。

不重跑工具、不联系模型——只读 orchestration store 落好的证据（`replay_audit`），或对一条
声称重跑一次**只读**核对（`recorded_output`，经 `evidence.verify_claims`）。语义与产品同调：
"没有复跑也不轻信"——绑不到记录的声称必须落 `unverified`，否则该负向任务判不通过。

Verification 复用 runner/protocol.py（失败四分类同处）。本模块是**评测消费者**，只读核心、
不改核心（structure §8：eval 是 agent 的消费者）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from evals.runner.protocol import Verification
from questor.evidence import for_subject, verify_claims
from questor.orchestration import store as orch_store
from questor.schemas.model import AcceptanceStatus
from questor.schemas.orchestration import ClaimedCheck, EvidenceSubjectType, EvidenceVerdict

__all__ = ["grade_recorded_output", "grade_replay_audit"]


def _acceptance_status(subject_type: str, subject_id: str) -> AcceptanceStatus | None:
    """从编排 store 读某 task 的验收态（run/turn 无验收态返回 None）。"""
    if subject_type != EvidenceSubjectType.TASK.value:
        return None
    view = orch_store.load_view()
    task = next((t for t in view.tasks if t.id == subject_id), None)
    return None if task is None else task.acceptance.status


def grade_replay_audit(subject_type: str, subject_id: str, requires: Sequence[str]) -> Verification:
    """离线审计：读该 subject 已落的证据，逐条要求可追溯且不含 unverified。

    支持的 `requires` 记号：
    - `all_claims_have_evidence`：有证据且每条都带 `recorded_output_ref`（指向具体记录条目）；
    - `no_unverified`：没有一条是 `unverified`（无记录不轻信）；
    - `acceptance_verified`：该 task 的验收态为 `verified`。
    """
    items = for_subject(
        orch_store.load_view().evidence, subject_type=subject_type, subject_id=subject_id
    )
    results: list[dict[str, Any]] = []
    if "all_claims_have_evidence" in requires:
        ok = bool(items) and all(e.recorded_output_ref for e in items)
        results.append({"check": "all_claims_have_evidence", "ok": ok})
    if "no_unverified" in requires:
        ok = bool(items) and all(e.verdict is not EvidenceVerdict.UNVERIFIED for e in items)
        results.append({"check": "no_unverified", "ok": ok})
    if "acceptance_verified" in requires:
        ok = _acceptance_status(subject_type, subject_id) is AcceptanceStatus.VERIFIED
        results.append({"check": "acceptance_verified", "ok": ok})
    passed = bool(results) and all(r["ok"] for r in results)
    reason = "replay audit passed" if passed else "replay audit failed: " + str(results)
    return Verification(passed=passed, reason=reason, evidence=results)


def grade_recorded_output(
    thread_id: str,
    claims: Sequence[ClaimedCheck],
    subject_type: str,
    subject_id: str,
    requires: Sequence[str],
) -> Verification:
    """对声称重跑一次只读核对，验证"不轻信"语义（多用于负向任务）。

    支持的 `requires` 记号：
    - `claim_without_record_is_unverified`：至少一条声称因绑不到记录而落 `unverified`；
    - `mismatch_detected`：至少一条声称与录得冲突（`is_error`）判 `mismatch`；
    - `acceptance_not_verified` / `acceptance_regressed`：验收态相应成立。
    """
    items = verify_claims(
        thread_id,
        list(claims),
        subject_type=EvidenceSubjectType(subject_type),
        subject_id=subject_id,
    )
    verdicts = {e.verdict for e in items}
    status = _acceptance_status(subject_type, subject_id)
    results: list[dict[str, Any]] = []
    if "claim_without_record_is_unverified" in requires:
        results.append(
            {"check": "unverified_present", "ok": EvidenceVerdict.UNVERIFIED in verdicts}
        )
    if "mismatch_detected" in requires:
        results.append({"check": "mismatch_present", "ok": EvidenceVerdict.MISMATCH in verdicts})
    if "acceptance_not_verified" in requires:
        ok = status is not None and status is not AcceptanceStatus.VERIFIED
        results.append({"check": "acceptance_not_verified", "ok": ok})
    if "acceptance_regressed" in requires:
        results.append(
            {"check": "acceptance_regressed", "ok": status is AcceptanceStatus.REGRESSED}
        )
    passed = bool(results) and all(r["ok"] for r in results)
    reason = "recorded_output audit passed" if passed else "audit failed: " + str(results)
    return Verification(passed=passed, reason=reason, evidence=results)
