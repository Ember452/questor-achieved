"""gesta.writer 单元行为：游标句柄与模块级函数的语义一致性、增量同步、游标校验。"""

from __future__ import annotations

import pytest

import questor.gesta as gesta
from questor.gesta.writer import ThreadWriter
from questor.schemas.model import (
    Item,
    ItemKind,
    Origin,
    PermissionMode,
    Run,
    RunStatus,
    Thread,
    Timestamp,
    utc_timestamp_now,
)
from questor.state.paths import thread_path
from questor.testenv.fake_home import fake_home

T0: Timestamp = "2026-10-11T08:30:00Z"


def _thread(tid: str = "thread-w01") -> Thread:
    return Thread(
        id=tid,
        workspace_id="ws-0001",
        title=None,
        engine_id="engine-01",
        permission_mode=PermissionMode.STANDARD,
        pinned=False,
        archived=False,
        created_at=T0,
        updated_at=T0,
    )


def _item(iid: str, text: str = "hello") -> Item:
    return Item(
        id=iid,
        run_id="run-0001",
        kind=ItemKind.MESSAGE,
        payload={"text": text},
        evidence=None,
        created_at=utc_timestamp_now(),
    )


def _open_with_thread(tid: str = "thread-w01") -> ThreadWriter:
    gesta.create_thread(_thread(tid))
    writer = ThreadWriter(tid)
    writer.open()
    return writer


def test_open_view_matches_module_load() -> None:
    with fake_home():
        gesta.create_thread(_thread())
        gesta.add_turn("thread-w01", turn_id="turn-0001", origin=Origin.USER, created_at=T0)
        writer = ThreadWriter("thread-w01")
        assert writer.open() == gesta.load_thread("thread-w01")


def test_unopened_writer_rejected() -> None:
    with fake_home(), pytest.raises(gesta.ThreadStoreError, match="open"):
        ThreadWriter("thread-w01").view()


def test_writer_ops_match_module_semantics() -> None:
    with fake_home():
        writer = _open_with_thread()
        turn = writer.add_turn(turn_id="turn-0001", origin=Origin.USER, created_at=T0)
        assert turn.seq == 1
        run = writer.add_run(
            Run(
                id="run-0001",
                turn_id="turn-0001",
                engine_id="engine-01",
                permission_mode=PermissionMode.STANDARD,
                status=RunStatus.QUEUED,
                created_at=T0,
            )
        )
        assert run.status == RunStatus.QUEUED
        moved = writer.transition_run("run-0001", RunStatus.RUNNING)
        assert moved.status == RunStatus.RUNNING
        writer.add_item(_item("item-0001"))
        placed = writer.append_event(
            event_type="item/completed",
            run_id="run-0001",
            turn_id="turn-0001",
            payload={},
            created_at=utc_timestamp_now(),
        )
        view = writer.view()
        # created + turn + run + running + item + event = 6 条记录
        assert view.last_seq == 6
        assert len(view.items) == 1
        assert placed.seq == 6
        # 句柄视图与磁盘全量 fold 一致（镜像不漂移）
        assert writer.view() == gesta.load_thread("thread-w01")
        # 非法迁移在落盘前爆炸
        with pytest.raises(gesta.InvalidTransition):
            writer.transition_run("run-0001", RunStatus.QUEUED)
        assert gesta.load_thread("thread-w01").last_seq == 6


def test_external_append_resync() -> None:
    """句柄持有期间其他进程（模块级 API）追加过 → stat 校验触发增量同步，seq 不重号。"""
    with fake_home():
        writer = _open_with_thread()
        writer.add_item(_item("item-0001"))
        # 模拟另一进程写入（绕过句柄）
        gesta.add_item("thread-w01", _item("item-external", "external"))
        writer.add_item(_item("item-0002"))
        view = writer.view()
        assert [i.id for i in view.items] == ["item-0001", "item-external", "item-0002"]
        assert view.last_seq == gesta.load_thread("thread-w01").last_seq
        assert writer.view() == gesta.load_thread("thread-w01")


def test_partial_tail_resync_starts_fresh_line() -> None:
    """崩溃残尾：追加前检测无换行结尾 → 以 \\n 前缀起新行，残尾留待读侧跳过（B-74）。"""
    with fake_home():
        writer = _open_with_thread()
        writer.add_item(_item("item-0001"))
        # 模拟另一进程崩溃留下的半行（无换行）
        path = thread_path("thread-w01")
        with path.open("ab") as handle:
            handle.write(b'{"seq": 99, "kind": "item.app')
        writer.add_item(_item("item-0002"))
        view = gesta.load_thread("thread-w01")
        assert [i.id for i in view.items] == ["item-0001", "item-0002"]
        assert view.last_seq == 3  # 残尾行被跳过，句柄的记录 seq 连续（created+2 items）
        assert writer.view() == view


def test_file_shrunk_is_contract_violation() -> None:
    with fake_home():
        writer = _open_with_thread()
        writer.add_item(_item("item-0001"))
        path = thread_path("thread-w01")
        data = path.read_bytes()
        path.write_bytes(data[: len(data) // 2])  # 模拟外部截断
        with pytest.raises(gesta.ThreadStoreError, match="截断"):
            writer.add_item(_item("item-0002"))


def test_writer_index_stays_consistent() -> None:
    with fake_home():
        writer = _open_with_thread()
        writer.add_turn(turn_id="turn-0001", origin=Origin.USER, created_at=T0)
        writer.add_item(_item("item-0001"))
        entries = gesta.rebuild_index()
        assert gesta.list_threads() == entries
        assert entries[0].last_seq == 3
        assert entries[0].turn_count == 1


def test_two_writers_in_process_share_cursor_safely() -> None:
    """同进程两个句柄交替写：stat 校验让后写者同步先写者的记录。"""
    with fake_home():
        gesta.create_thread(_thread())
        writer_a = ThreadWriter("thread-w01")
        writer_b = ThreadWriter("thread-w01")
        writer_a.open()
        writer_b.open()
        writer_a.add_item(_item("item-0001"))
        writer_b.add_item(_item("item-0002"))
        writer_a.add_item(_item("item-0003"))
        view = gesta.load_thread("thread-w01")
        assert [i.id for i in view.items] == ["item-0001", "item-0002", "item-0003"]
        assert view.last_seq == 4
