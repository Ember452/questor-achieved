"""evidence 核对器单测（ADR-0027：无记录不臆断，结论必带引用）。"""

from __future__ import annotations

from questor.evidence.compare import (
    CheckClaim,
    RecordedCheck,
    compare_claim,
    compare_claims,
    recorded_check_from_item,
)
from questor.schemas.orchestration import EvidenceSubjectType, EvidenceVerdict

SUBJECT = EvidenceSubjectType.TASK
SID = "task-1"


def test_missing_record_is_unverified_not_verified() -> None:
    """没有记录支撑 → unverified（诚实呈现：不臆断通过）。"""
    ev = compare_claim(
        CheckClaim(claimed="pytest passed", tool_use_id="t1"),
        None,
        subject_type=SUBJECT,
        subject_id=SID,
    )
    assert ev.verdict is EvidenceVerdict.UNVERIFIED
    assert ev.recorded_output_ref == ""


def test_error_output_is_mismatch() -> None:
    recorded = RecordedCheck(tool_use_id="t1", output="1 failed", is_error=True, ref="item-9")
    ev = compare_claim(
        CheckClaim(claimed="pytest passed", tool_use_id="t1"),
        recorded,
        subject_type=SUBJECT,
        subject_id=SID,
    )
    assert ev.verdict is EvidenceVerdict.MISMATCH
    assert ev.recorded_output_ref == "item-9"  # 结论可追溯


def test_ok_output_is_verified_with_ref() -> None:
    recorded = RecordedCheck(tool_use_id="t1", output="3 passed", is_error=False, ref="item-7")
    ev = compare_claim(
        CheckClaim(claimed="pytest passed", tool_use_id="t1"),
        recorded,
        subject_type=SUBJECT,
        subject_id=SID,
    )
    assert ev.verdict is EvidenceVerdict.VERIFIED
    assert ev.recorded_output_ref == "item-7"


def test_compare_claims_batch() -> None:
    recorded = {"t1": RecordedCheck(tool_use_id="t1", output="ok", is_error=False, ref="i1")}
    evidence = compare_claims(
        [CheckClaim("ran linter", "t1"), CheckClaim("ran tests", "t2")],
        recorded,
        subject_type=SUBJECT,
        subject_id=SID,
    )
    assert [e.verdict.value for e in evidence] == ["verified", "unverified"]


def test_recorded_check_from_item_reads_spill_ref() -> None:
    from questor.schemas.model import Item, ItemKind, utc_timestamp_now

    item = Item(
        id="item-1",
        run_id="run-1",
        kind=ItemKind.TOOL_RESULT,
        payload={
            "tool_use_id": "t1",
            "name": "run",
            "is_error": False,
            "preview": "head",
            "spilled": "t1.txt",
        },
        created_at=utc_timestamp_now(),
    )
    recorded = recorded_check_from_item(item)
    assert recorded is not None
    assert recorded.ref == "t1.txt"  # 溢出时回链到落盘文件
    # 非 tool_result 项返回 None
    message = item.model_copy(update={"kind": ItemKind.MESSAGE, "payload": {}})
    assert recorded_check_from_item(message) is None
