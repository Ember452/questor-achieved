"""gesta 会话库的写入/读取行为（Phase 2a 批次 1；behavior-gesta-wuu §3）。

蓝本：wuu ``internal/session/session.go`` 的 ``appendHistoryRecordTx``（seq 在事务内取号）、
``insertSessionTx``、``sessions``/``session_controls`` 的 revision 语义。

这里的重心是**存储 ↔ 契约的映射不得有两套真相**：会话正文的权威形状是
``schemas/message.py`` 的 ``ChatMessage``（Phase 1 第一前置件），库里的 ``content`` 等
列只是投影；读回必须逐字段等于写入值（B-85 同型纪律：一条重建路径，不各算各的）。
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from questor.gesta.errors import ControlInvalid, SequenceRejected, SessionNotFound
from questor.gesta.records import StoredMessage
from questor.gesta.session_store import SessionStore
from questor.schemas.message import (
    ChatMessage,
    MessageRole,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[SessionStore]:
    handle = SessionStore(tmp_path / "sessions.sqlite3")
    yield handle
    handle.close()


def _text(role: MessageRole, content: str, **kwargs: object) -> ChatMessage:
    return ChatMessage(role=role, parts=[TextPart(text=content)], **kwargs)  # type: ignore[arg-type]


def test_create_and_load_session(store: SessionStore) -> None:
    store.create_session("s1", cwd="D:/repo", title="初版")
    loaded = store.load_session("s1")
    assert loaded.id == "s1" and loaded.cwd == "D:/repo" and loaded.title == "初版"
    assert loaded.created_at and loaded.updated_at
    with pytest.raises(SessionNotFound):
        store.load_session("没有这个会话")


def test_append_allocates_seq_in_store_and_rejects_caller_supplied_seq(
    store: SessionStore,
) -> None:
    """seq 是"该记录在会话内的稳定地址"，只能由 store 在事务内取号（wuu L2305-2309）。

    调用方自带 seq 会绕过单点分配——两个写入者各算各的就会撞号或跳号（B-45 的同类洞）。
    """
    store.create_session("s1")
    assert store.append_message("s1", _text(MessageRole.USER, "一问")) == 1
    assert store.append_message("s1", _text(MessageRole.ASSISTANT, "一答")) == 2
    assert store.append_message("s1", _text(MessageRole.USER, "二问")) == 3

    with pytest.raises(SequenceRejected, match="seq"):
        store.append_record(
            "s1", StoredMessage(seq=99, message=_text(MessageRole.USER, "自己编号"))
        )

    # 另一会话独立取号：seq 是会话内地址，不是全局计数
    store.create_session("s2")
    assert store.append_message("s2", _text(MessageRole.USER, "另一个会话")) == 1


def test_seq_is_unique_and_contiguous_under_concurrent_appends(tmp_path: Path) -> None:
    """并发追加不得重号或断号：写路径全程持进程内锁 + BEGIN IMMEDIATE。"""
    store = SessionStore(tmp_path / "sessions.sqlite3")
    store.create_session("s1")
    errors: list[BaseException] = []
    barrier = threading.Barrier(4)

    def worker(index: int) -> None:
        try:
            barrier.wait()
            for turn in range(10):
                store.append_message("s1", _text(MessageRole.USER, f"线程{index}-{turn}"))
        except BaseException as exc:  # noqa: BLE001 - 测试需要把子线程异常带回主线程
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    try:
        assert not errors, f"并发写入抛错：{errors!r}"
        seqs = [record.seq for record in store.load_messages("s1")]
        assert seqs == list(range(1, 41)), "seq 必须连续且不重号（1..40）"
    finally:
        store.close()


def test_message_round_trip_is_lossless(store: SessionStore) -> None:
    """写读必须逐字段相等：parts 的权威载体是 content_parts_json，其余列是投影（不各算各的）。"""
    store.create_session("s1")
    original = ChatMessage(
        role=MessageRole.ASSISTANT,
        parts=[
            TextPart(text="先看一眼"),
            ToolCallPart(id="call-1", name="read_file", arguments='{"path":"a.txt"}'),
            ToolResultPart(tool_call_id="call-1", content="内容", is_error=False),
        ],
        origin="plugin",
        origin_id="p-1",
        client_id="c-9",
        display_content="展示文本",
    )
    store.append_message("s1", original)
    restored = store.load_messages("s1")[0].message
    assert restored == original, "parts / origin / client_id / display_content 必须无损回读"


def test_origin_and_role_stay_orthogonal(store: SessionStore) -> None:
    """Origin ≠ Role（port-ledger P1-5）：插件生成的 query 仍投影 role=user，但出处留得住。"""
    store.create_session("s1")
    store.append_message(
        "s1", ChatMessage(role=MessageRole.USER, parts=[TextPart(text="q")], origin="schedule")
    )
    row = store.load_messages("s1")[0]
    assert row.message.role is MessageRole.USER
    assert row.message.origin == "schedule"


def test_projection_columns_are_derived_not_authoritative(store: SessionStore) -> None:
    """``content`` 列是文本投影，供搜索/人读；重建一律走 parts，两条路不得互相矛盾。"""
    store.create_session("s1")
    store.append_message("s1", _text(MessageRole.USER, "正文在此"))
    raw = store.raw_row("s1", 1)
    assert raw["content"] == "正文在此"
    assert raw["role"] == "user"


def test_session_entries_count_and_updated_at_advance(store: SessionStore) -> None:
    store.create_session("s1", title="t")
    first_updated = store.load_session("s1").updated_at
    store.append_message("s1", _text(MessageRole.USER, "一问"))
    loaded = store.load_session("s1")
    assert loaded.entries == 1
    assert loaded.updated_at >= first_updated


def test_list_and_filter_sessions(store: SessionStore) -> None:
    store.create_session("s1", title="一")
    store.create_session("s2", title="二")
    store.rename_session("s1", "一改过")
    listed = {item.id: item for item in store.list_sessions()}
    assert set(listed) == {"s1", "s2"}
    assert listed["s1"].title == "一改过"

    store.set_archived("s2", True)
    assert {item.id for item in store.list_sessions()} == {"s1"}
    assert {item.id for item in store.list_sessions(include_archived=True)} == {"s1", "s2"}


def test_delete_session_cascades_history(store: SessionStore) -> None:
    """protocol.md §3 的 ``thread/delete`` 落到库里是级联删；历史本身仍不可逐行删。"""
    store.create_session("s1")
    store.append_message("s1", _text(MessageRole.USER, "x"))
    store.delete_session("s1")
    with pytest.raises(SessionNotFound):
        store.load_session("s1")
    assert store.load_messages("s1") == []


def test_controls_revision_bumps_monotonically(store: SessionStore) -> None:
    """``session_controls.revision`` 是接管栅栏（ADR-0005）：只能单点递增，不能由调用方指定。"""
    store.create_session("s1")
    initial = store.get_controls("s1")
    assert initial.revision == 0 and initial.state == "active"

    bumped = store.set_controls("s1", manager_id="m1", state="active")
    assert bumped == 1
    assert store.set_controls("s1", manager_id="m2", state="user_controlled") == 2
    controls = store.get_controls("s1")
    assert controls.manager_id == "m2" and controls.state == "user_controlled"

    with pytest.raises(ControlInvalid, match="state"):
        store.set_controls("s1", manager_id="m3", state="随便写")


def test_append_record_carries_usage_and_finish_reason(store: SessionStore) -> None:
    """用量与停止信号随记录落库：compact 阈值与 ``turn/usage`` 都要能指回同一份事实。"""
    store.create_session("s1")
    record = StoredMessage(
        message=_text(MessageRole.ASSISTANT, "答"),
        finish_reason="length",
        truncated=True,
        provider="anthropic",
        model="claude-x",
        input_tokens=120,
        output_tokens=64,
        cache_read_tokens=32,
    )
    store.append_record("s1", record)
    stored = store.load_messages("s1")[0]
    assert stored.finish_reason == "length" and stored.truncated is True
    assert stored.provider == "anthropic" and stored.model == "claude-x"
    assert (stored.input_tokens, stored.output_tokens, stored.cache_read_tokens) == (120, 64, 32)
