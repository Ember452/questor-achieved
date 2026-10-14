"""gesta inbox：host→会话待投递输入的幂等与送达语义（Phase 2a 批次 1；behavior-gesta-wuu §4）。

蓝本：wuu ``internal/session/inbox.go``。三条硬语义逐条钉住：

- B-63：同 ``client_id`` 重复入队只生效一次（``INSERT OR IGNORE``）。
- B-127：**送达判据是"client_id 已落入持久历史"**，不是入队时间——否则崩溃/重启会把
  同一条用户输入重复注入（`PendingInbox` L92-94 的 EXISTS 关联）。
- B-129：控制栅栏（接管态/修订号）的复判必须发生在**消费时**，不是入队时判一次
  （`validateInboxControls` L173-235 的注释：sender 可能在 hook 跑完前被接管）。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from questor.gesta import inbox
from questor.gesta.errors import ControlChanged, InboxInvalid
from questor.gesta.records import Control, InboxMessage
from questor.gesta.session_store import SessionStore
from questor.schemas.message import ChatMessage, MessageRole, TextPart


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[SessionStore]:
    handle = SessionStore(tmp_path / "sessions.sqlite3")
    handle.create_session("s1")
    yield handle
    handle.close()


def _message(
    client_id: str = "c1",
    session_id: str = "s1",
    content: str = "插一句",
    **kwargs: object,
) -> InboxMessage:
    return InboxMessage(
        client_id=client_id,
        session_id=session_id,
        content=content,
        **kwargs,  # type: ignore[arg-type]
    )


def test_enqueue_requires_client_id_and_session(store: SessionStore) -> None:
    """wuu 在入队前显式报错而不是静默吞（inbox.go L49-51）：空 id 会让幂等判据失效。"""
    with pytest.raises(InboxInvalid):
        inbox.enqueue(store, _message(client_id="  "))
    with pytest.raises(InboxInvalid):
        inbox.enqueue(store, _message(session_id=""))


def test_enqueue_is_idempotent_on_client_id(store: SessionStore) -> None:
    """B-63：同 client_id 提交两次只入队一次，第二次是 no-op（不报错、不重复注入）。"""
    inbox.enqueue(store, _message(client_id="c-dup"))
    inbox.enqueue(store, _message(client_id="c-dup", content="改了内容也不算第二次投递"))
    pending = inbox.pending(store, "s1")
    assert [item.client_id for item in pending] == ["c-dup"]
    assert pending[0].content == "插一句", "重复入队不得覆盖首次内容"


def test_delivered_criterion_is_history_membership(store: SessionStore) -> None:
    """B-127：只有 client_id 出现在持久历史里才算送达；入队本身不改变 delivered_at。"""
    inbox.enqueue(store, _message(client_id="c-live"))
    assert inbox.pending(store, "s1")
    assert inbox.has(store, "c-live") is True

    store.append_message(
        "s1",
        ChatMessage(role=MessageRole.USER, parts=[TextPart(text="插一句")], client_id="c-live"),
    )
    assert inbox.pending(store, "s1") == [], "已落入历史的输入必须被 settle 掉"


def test_pending_survives_restart_without_reinjection(tmp_path: Path) -> None:
    """B-127 的崩溃面：重开库后重试投递不得把同一条输入再投一次。"""
    path = tmp_path / "sessions.sqlite3"
    first = SessionStore(path)
    first.create_session("s1")
    inbox.enqueue(first, _message(client_id="c-restart"))
    first.append_message(
        "s1", ChatMessage(role=MessageRole.USER, parts=[TextPart(text="x")], client_id="c-restart")
    )
    first.close()

    reopened = SessionStore(path)
    try:
        assert inbox.pending(reopened, "s1") == []
        # 重复入队同一 client_id 依然是 no-op
        inbox.enqueue(reopened, _message(client_id="c-restart"))
        assert inbox.pending(reopened, "s1") == []
    finally:
        reopened.close()


def test_pending_returns_creation_order(store: SessionStore) -> None:
    """消费按创建序（``ORDER BY created_at, rowid``）；同时间戳由 rowid 兜底定序。"""
    for client_id in ("c-a", "c-b", "c-c"):
        inbox.enqueue(store, _message(client_id=client_id))
    pending = inbox.pending(store, "s1")
    assert [item.client_id for item in pending] == ["c-a", "c-b", "c-c"]
    assert pending[0].created_at <= pending[-1].created_at


def test_settle_marks_delivered_without_content(store: SessionStore) -> None:
    """``SettleInbox`` 记"已处理"而不注入内容，让后续重试变 no-op（wuu L66-81）。"""
    inbox.settle(store, client_id="c-settled", session_id="s1")
    assert inbox.has(store, "c-settled") is True
    assert inbox.pending(store, "s1") == []
    inbox.enqueue(store, _message(client_id="c-settled"))
    assert inbox.pending(store, "s1") == [], "已 settle 的 client_id 再入队不得复活"


def test_targets_lists_sessions_with_undelivered(store: SessionStore) -> None:
    store.create_session("s2")
    inbox.enqueue(store, _message(client_id="c1", session_id="s1"))
    inbox.enqueue(store, _message(client_id="c2", session_id="s2"))
    assert inbox.targets(store) == ["s1", "s2"]
    store.append_message(
        "s1", ChatMessage(role=MessageRole.USER, parts=[TextPart(text="x")], client_id="c1")
    )
    assert inbox.pending(store, "s1") == []
    assert inbox.targets(store) == ["s2"]


def test_wake_flag_and_cause_are_persisted(store: SessionStore) -> None:
    """``wake`` 决定目标 idle 时是否起一轮；``cause`` 供渲染侧标注来源。"""
    inbox.enqueue(
        store,
        InboxMessage(
            client_id="c-w",
            session_id="s1",
            content="hi",
            wake=False,
            cause="project",
        ),
    )
    restored = inbox.pending(store, "s1")[0]
    assert restored.wake is False and restored.cause == "project"


def test_controls_are_revalidated_at_consume_time(store: SessionStore) -> None:
    """B-129：入队后接管态变了，消费必须拒绝（ErrControlChanged），不能沿用入队时的判定。"""
    store.set_controls("s1", manager_id="m1", state="active")
    inbox.enqueue(
        store,
        InboxMessage(
            client_id="c-ctl",
            session_id="s1",
            content="hi",
            controls=[Control(session_id="s1", manager_id="m1", revision=1, state="active")],
        ),
    )
    inbox.validate_controls(store, "c-ctl")  # 此刻仍合法

    # 用户接管：manager/state 变了 → 消费时复判必须失败
    store.set_controls("s1", manager_id="m2", state="user_controlled")
    with pytest.raises(ControlChanged):
        inbox.validate_controls(store, "c-ctl")


def test_validate_controls_without_controls_is_noop(store: SessionStore) -> None:
    inbox.enqueue(store, _message(client_id="c-plain"))
    inbox.validate_controls(store, "c-plain")  # 无栅栏的普通输入不该被拦
    inbox.validate_controls(store, "从没见过的 client_id")  # 未知 id 也不报错（wuu ErrNoRows→nil）


def test_pending_ignores_other_sessions(store: SessionStore) -> None:
    store.create_session("s2")
    inbox.enqueue(store, _message(client_id="c1", session_id="s1"))
    assert [item.client_id for item in inbox.pending(store, "s2")] == []
