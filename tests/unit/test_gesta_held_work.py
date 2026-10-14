"""gesta held_user_work：运行中未决输入的整表替换与序号压缩（Phase 2a 批次 1；behavior §5）。

蓝本：wuu ``internal/session/held_user_work.go``。这是"可干预柱"能在崩溃后重建的地基
（B-65），也是本批最容易写错的一处：

- B-128：单条删除后把后续 position 往前挪，**直接** ``position = position - 1`` 会撞
  ``UNIQUE(session_id, position)``。wuu 的写法是先 ``-position-1`` 取负躲开冲突，
  再 ``-position-2`` 归正——两段必须在同一事务内。
- origin 只有 ``queue``/``steer`` 两个值（协议 ``turn/queue`` 与 ``turn/steer`` 的持久侧）。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from questor.gesta import held_work
from questor.gesta.errors import HeldWorkInvalid
from questor.gesta.records import HeldUserWorkEntry
from questor.gesta.session_store import SessionStore


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[SessionStore]:
    handle = SessionStore(tmp_path / "sessions.sqlite3")
    handle.create_session("s1")
    handle.create_session("s2")
    yield handle
    handle.close()


def _entry(
    entry_id: str,
    origin: str = "queue",
    *,
    message_json: str = '{"id":"x"}',
    runtime_json: str = "{}",
) -> HeldUserWorkEntry:
    """构造一条未决工作。

    ``origin`` 故意是 ``str`` 而不是 Literal：两值域在 **存储层** 校验（照 wuu
    ``ReplaceHeldUserWork``），否则 pydantic 会在建模时就把非法值拦住，测不到存储层的门。
    """
    return HeldUserWorkEntry(
        id=entry_id,
        origin=origin,
        message_json=message_json,
        runtime_json=runtime_json,
    )


def test_replace_assigns_positions_in_given_order(store: SessionStore) -> None:
    """调用方给顺序，position 由枚举下标决定（wuu ReplaceHeldUserWork L44-58）。"""
    held_work.replace(store, "s1", [_entry("a"), _entry("b", "steer"), _entry("c")])
    loaded = held_work.load(store, "s1")
    assert [item.position for item in loaded] == [0, 1, 2]
    assert [item.id for item in loaded] == ["a", "b", "c"]
    assert [item.origin for item in loaded] == ["queue", "steer", "queue"]


def test_empty_list_clears_all_pending_work(store: SessionStore) -> None:
    held_work.replace(store, "s1", [_entry("a"), _entry("b")])
    held_work.replace(store, "s1", [])
    assert held_work.load(store, "s1") == []


def test_origin_is_a_two_value_domain(store: SessionStore) -> None:
    """origin 非 queue/steer 直接报错——写错值会让重启重建时把 steer 当 queue 消费。"""
    with pytest.raises(HeldWorkInvalid):
        held_work.replace(store, "s1", [_entry("a", "immediate")])
    with pytest.raises(HeldWorkInvalid):
        held_work.replace(store, "s1", [_entry("a", "")])


def test_id_and_payloads_are_required(store: SessionStore) -> None:
    with pytest.raises(HeldWorkInvalid):
        held_work.replace(store, "s1", [_entry("  ")])
    with pytest.raises(HeldWorkInvalid):
        held_work.replace(store, "s1", [_entry("a", message_json="")])
    with pytest.raises(HeldWorkInvalid):
        held_work.replace(store, "s1", [_entry("a", runtime_json="")])


def test_replacement_is_atomic_when_a_later_entry_is_invalid(store: SessionStore) -> None:
    """整表替换必须是一个事务：中途校验失败要整体回滚，不能留下"旧的已删、新的只进一半"。"""
    held_work.replace(store, "s1", [_entry("keep-1"), _entry("keep-2")])

    with pytest.raises(HeldWorkInvalid):
        held_work.replace(store, "s1", [_entry("new-1"), _entry("坏的一个", origin="queue!")])

    loaded = held_work.load(store, "s1")
    assert [item.id for item in loaded] == ["keep-1", "keep-2"], "失败的事务必须原样回滚"


def test_delete_middle_compacts_positions_without_unique_conflict(store: SessionStore) -> None:
    """B-128：删掉中间一条后，后续位必须连续且不得撞 ``UNIQUE(session_id, position)``。"""
    held_work.replace(store, "s1", [_entry("a"), _entry("b"), _entry("c"), _entry("d")])

    assert held_work.delete(store, "s1", "b") is True
    loaded = held_work.load(store, "s1")
    assert [item.position for item in loaded] == [0, 1, 2], "压缩后序号必须连续无空洞"
    assert [item.id for item in loaded] == ["a", "c", "d"]

    # 再删头一条与末一条，仍不得冲突
    assert held_work.delete(store, "s1", "a") is True
    assert [item.position for item in held_work.load(store, "s1")] == [0, 1]
    assert held_work.delete(store, "s1", "d") is True
    assert [item.id for item in held_work.load(store, "s1")] == ["c"]


def test_delete_unknown_returns_false(store: SessionStore) -> None:
    """wuu 用 (found, err) 表达"没有这条"，不抛错（held_user_work.go L124-127）。"""
    held_work.replace(store, "s1", [_entry("a")])
    assert held_work.delete(store, "s1", "不存在") is False
    assert held_work.delete(store, "没有这个会话", "a") is False


def test_work_is_scoped_per_session(store: SessionStore) -> None:
    held_work.replace(store, "s1", [_entry("a")])
    held_work.replace(store, "s2", [_entry("z", "steer")])
    assert [item.id for item in held_work.load(store, "s1")] == ["a"]
    assert [item.id for item in held_work.load(store, "s2")] == ["z"]
    assert held_work.delete(store, "s1", "z") is False


def test_pending_work_survives_restart(tmp_path: Path) -> None:
    """B-65 的正题：core 重启后按这张表重建未消费的排队/插话输入。"""
    path = tmp_path / "sessions.sqlite3"
    first = SessionStore(path)
    first.create_session("s1")
    held_work.replace(first, "s1", [_entry("a"), _entry("b", "steer")])
    first.close()

    reopened = SessionStore(path)
    try:
        loaded = held_work.load(reopened, "s1")
        assert [(item.position, item.id, item.origin) for item in loaded] == [
            (0, "a", "queue"),
            (1, "b", "steer"),
        ]
        assert loaded[0].message_json == '{"id":"x"}'
    finally:
        reopened.close()
