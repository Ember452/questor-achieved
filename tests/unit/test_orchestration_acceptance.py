"""验收状态机单测（data-model §3.2，ADR-0029）：白名单迁移、单点入口、回放裁决。

覆盖两类失败方式：① 领域层——非法迁移被白名单拒；② 存储层——验收态只能经
`transition_acceptance` 改，`update_task` 旁路即拒；回放篡改的迁移序列同样过白名单爆炸。

负向验证（AGENTS §四：护栏必须会咬人）**已做**：临时把 `update_task` 的验收态守卫删掉 →
`test_update_task_cannot_change_acceptance_status` FAILED；已复原。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from questor.orchestration import acceptance, store, tasks
from questor.orchestration.acceptance import InvalidAcceptanceTransition
from questor.schemas.model import AcceptanceStatus
from questor.state.paths import orchestration_log_path
from questor.testenv.fake_home import fake_home


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def _lines() -> list[str]:
    path = orchestration_log_path()
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


# ---- 领域层：白名单 ----


def test_forward_chain_is_allowed() -> None:
    """§3.2 的正向路径逐跳放行。"""
    chain = [
        AcceptanceStatus.PROPOSED,
        AcceptanceStatus.ACCEPTED_BY_USER,
        AcceptanceStatus.EXECUTING,
        AcceptanceStatus.REPORTED,
    ]
    for current, target in zip(chain, chain[1:], strict=False):
        assert acceptance.transition(current, target) is target
    assert acceptance.transition(AcceptanceStatus.REPORTED, AcceptanceStatus.VERIFIED) is (
        AcceptanceStatus.VERIFIED
    )
    assert acceptance.transition(AcceptanceStatus.REPORTED, AcceptanceStatus.REGRESSED) is (
        AcceptanceStatus.REGRESSED
    )


def test_regressed_can_rework_to_executing() -> None:
    """打回重做：regressed → executing（与任务 reviewed → executing 同调）。"""
    assert (
        acceptance.transition(AcceptanceStatus.REGRESSED, AcceptanceStatus.EXECUTING)
        is AcceptanceStatus.EXECUTING
    )


def test_verified_is_terminal() -> None:
    assert acceptance.is_terminal(AcceptanceStatus.VERIFIED)
    with pytest.raises(InvalidAcceptanceTransition):
        acceptance.transition(AcceptanceStatus.VERIFIED, AcceptanceStatus.EXECUTING)


def test_illegal_skip_is_rejected() -> None:
    """proposed 直接跳 verified——未经 report，白名单拒。"""
    with pytest.raises(InvalidAcceptanceTransition):
        acceptance.transition(AcceptanceStatus.PROPOSED, AcceptanceStatus.VERIFIED)


def test_allowed_targets_unknown_fails_closed() -> None:
    assert acceptance.allowed_targets("bogus") == frozenset()


# ---- 存储层：单点入口 + 记录 + 回放 ----


def test_transition_acceptance_is_single_entry_and_records() -> None:
    task = tasks.create_task(title="t1")
    moved = store.transition_acceptance(task.id, AcceptanceStatus.ACCEPTED_BY_USER)
    assert moved.acceptance.status is AcceptanceStatus.ACCEPTED_BY_USER
    # created + 一条 acceptance.status
    lines = _lines()
    assert len(lines) == 2
    assert '"acceptance.status"' in lines[1]


def test_illegal_acceptance_transition_rejected_before_write() -> None:
    task = tasks.create_task(title="t1")  # proposed
    with pytest.raises(InvalidAcceptanceTransition):
        store.transition_acceptance(task.id, AcceptanceStatus.VERIFIED)
    assert len(_lines()) == 1  # 非法迁移不落盘


def test_update_task_cannot_change_acceptance_status() -> None:
    """update_task 只改非状态字段：改验收态必须走 transition_acceptance（B-102）。"""
    task = tasks.create_task(title="t1")
    bumped = task.model_copy(
        update={
            "acceptance": task.acceptance.model_copy(update={"status": AcceptanceStatus.EXECUTING})
        }
    )
    with pytest.raises(store.OrchestrationStoreError):
        store.update_task(bumped)


def test_transition_acceptance_links_evidence_ids() -> None:
    """report 驱动到终态时同批链入证据 id。"""
    task = tasks.create_task(title="t1")
    for target in (
        AcceptanceStatus.ACCEPTED_BY_USER,
        AcceptanceStatus.EXECUTING,
        AcceptanceStatus.REPORTED,
    ):
        store.transition_acceptance(task.id, target)
    done = store.transition_acceptance(
        task.id, AcceptanceStatus.VERIFIED, evidence_ids=("ev-a", "ev-b")
    )
    assert done.acceptance.evidence_ids == ("ev-a", "ev-b")
    reloaded = next(t for t in store.load_view().tasks if t.id == task.id)
    assert reloaded.acceptance.status is AcceptanceStatus.VERIFIED
    assert reloaded.acceptance.evidence_ids == ("ev-a", "ev-b")


def _append_raw_record(payload_line: str) -> None:
    with orchestration_log_path().open("a", encoding="utf-8") as handle:
        handle.write(payload_line + "\n")


def test_fold_replays_acceptance_through_whitelist() -> None:
    """篡改历史（proposed 直接到 verified 的迁移记录）回放即炸——白名单在 fold 也生效。"""
    task = tasks.create_task(title="t1")
    _append_raw_record(
        '{"seq": 99, "kind": "acceptance.status", '
        f'"payload": {{"task_id": "{task.id}", "from": "proposed", "to": "verified", '
        '"evidence_ids": []}, "recorded_at": "2026-10-12T00:00:00Z"}'
    )
    with pytest.raises(InvalidAcceptanceTransition):
        store.load_view()
