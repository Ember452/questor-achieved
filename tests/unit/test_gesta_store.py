"""gesta.store 单元行为：建线程、定序、状态推进、索引、工具结果落盘。

对抗用例（残尾容忍 / 并发追加 / 活跃拒删）在 tests/adversarial/。
"""

from __future__ import annotations

import pytest

import questor.gesta as gesta
from questor.gesta import transitions as transitions_module
from questor.gesta.store import ThreadStoreError, ToolResultSpill
from questor.schemas.model import (
    Event,
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
from questor.state.paths import sessions_dir, thread_path
from questor.testenv.fake_home import fake_home

T0: Timestamp = "2026-10-11T08:30:00Z"


def _thread(tid: str = "thread-0001") -> Thread:
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


def _setup_thread_with_run(tid: str = "thread-0001") -> None:
    """建线程 + 1 turn + 1 queued run（多个用例的共同前置）。"""
    gesta.create_thread(_thread(tid))
    gesta.add_turn(tid, turn_id=f"turn-{tid[-4:]}", origin=Origin.USER, created_at=T0)
    gesta.add_run(
        tid,
        Run(
            id="run-0001",
            turn_id=f"turn-{tid[-4:]}",
            engine_id="engine-01",
            permission_mode=PermissionMode.STANDARD,
            status=RunStatus.QUEUED,
            created_at=T0,
        ),
    )


def test_create_and_load_roundtrip() -> None:
    with fake_home():
        view = gesta.create_thread(_thread())
        assert view.thread.id == "thread-0001"
        assert view.last_seq == 1
        again = gesta.load_thread("thread-0001")
        assert again.thread == view.thread


def test_create_duplicate_rejected() -> None:
    with fake_home():
        gesta.create_thread(_thread())
        with pytest.raises(ThreadStoreError, match="已存在"):
            gesta.create_thread(_thread())


def test_load_missing_thread_raises() -> None:
    with fake_home(), pytest.raises(gesta.ThreadNotFound):
        gesta.load_thread("no-such-thread")


def test_turn_seq_single_point_allocation() -> None:
    """B-45：turn 序号由持久化层单点分配，先持久化者序号在前；调用方无法指定。"""
    with fake_home():
        gesta.create_thread(_thread())
        first = gesta.add_turn(
            "thread-0001", turn_id="turn-0001", origin=Origin.USER, created_at=T0
        )
        second = gesta.add_turn(
            "thread-0001", turn_id="turn-0002", origin=Origin.USER, created_at=T0
        )
        assert (first.seq, second.seq) == (1, 2)


def test_run_must_enter_as_queued() -> None:
    with fake_home():
        gesta.create_thread(_thread())
        gesta.add_turn("thread-0001", turn_id="turn-0001", origin=Origin.USER, created_at=T0)
        premature = Run(
            id="run-0001",
            turn_id="turn-0001",
            engine_id="engine-01",
            permission_mode=PermissionMode.STANDARD,
            status=RunStatus.RUNNING,
            created_at=T0,
        )
        with pytest.raises(ThreadStoreError, match="queued"):
            gesta.add_run("thread-0001", premature)


def test_transition_run_lifecycle_and_persistence() -> None:
    with fake_home():
        _setup_thread_with_run()
        running = gesta.transition_run("thread-0001", "run-0001", RunStatus.RUNNING)
        assert running.status == RunStatus.RUNNING
        steered = gesta.transition_run("thread-0001", "run-0001", RunStatus.STEERED)
        assert steered.status == RunStatus.STEERED
        gesta.transition_run("thread-0001", "run-0001", RunStatus.RUNNING)
        done = gesta.transition_run("thread-0001", "run-0001", RunStatus.COMPLETED)
        assert done.status == RunStatus.COMPLETED
        view = gesta.load_thread("thread-0001")
        assert view.runs[0].status == RunStatus.COMPLETED
        assert view.last_seq == 7  # created + turn + run + 3 次 status


def test_forbidden_transition_leaves_no_record() -> None:
    with fake_home():
        _setup_thread_with_run()
        with pytest.raises(transitions_module.InvalidTransition):
            gesta.transition_run("thread-0001", "run-0001", RunStatus.COMPLETED)
        view = gesta.load_thread("thread-0001")
        assert view.runs[0].status == RunStatus.QUEUED
        assert view.last_seq == 3  # 失败的迁移没有留下任何记录


def test_event_seq_allocated_from_record_stream() -> None:
    with fake_home():
        gesta.create_thread(_thread())
        placed = gesta.append_event(
            "thread-0001",
            event_type="item/started",
            run_id="run-0001",
            turn_id="turn-0001",
            payload={},
            created_at=utc_timestamp_now(),
        )
        assert placed.seq == 2  # thread.created=1 之后
        assert isinstance(placed, Event)


def test_add_item_and_rename_and_flags() -> None:
    with fake_home():
        gesta.create_thread(_thread())
        gesta.add_item(
            "thread-0001",
            Item(
                id="item-0001",
                run_id="run-0001",
                kind=ItemKind.MESSAGE,
                payload={"text": "hello"},
                evidence=None,
                created_at=T0,
            ),
        )
        renamed = gesta.rename_thread("thread-0001", "新标题")
        assert renamed.title == "新标题"
        flagged = gesta.set_thread_flags("thread-0001", pinned=True)
        assert flagged.pinned is True
        view = gesta.load_thread("thread-0001")
        assert len(view.items) == 1


def test_index_matches_rebuild_and_self_heals() -> None:
    with fake_home():
        gesta.create_thread(_thread("thread-a"))
        gesta.create_thread(_thread("thread-b"))
        listed = gesta.list_threads()
        assert [s.id for s in listed] == ["thread-a", "thread-b"]
        assert gesta.rebuild_index() == listed
        # 索引是缓存：损坏即重建，不修复（data-model §5 同语义）
        (sessions_dir() / "threads.json").write_text("not json", encoding="utf-8")
        assert [s.id for s in gesta.list_threads()] == ["thread-a", "thread-b"]


def test_spill_tool_result_idempotent_and_previewed() -> None:
    with fake_home():
        gesta.create_thread(_thread())
        content = "x" * 3000
        first = gesta.spill_tool_result("thread-0001", "toolu_01AAA", content)
        assert isinstance(first, ToolResultSpill)
        assert first.truncated is True
        assert len(first.preview) == 2048
        path = sessions_dir() / first.file
        assert path.read_text(encoding="utf-8") == content
        # B-24：重复落盘静默跳过且不改写已有内容；回读盘上内容构造预览
        second = gesta.spill_tool_result("thread-0001", "toolu_01AAA", "DIFFERENT")
        assert second.truncated is True
        assert second.preview == "x" * 2048
        assert path.read_text(encoding="utf-8") == content
        short = gesta.spill_tool_result("thread-0001", "toolu_02BBB", "short")
        assert short.truncated is False


def test_record_stream_is_whole_lines() -> None:
    """每条记录占一行且可独立解析（并发正确性与残尾容忍的共同前提）。"""
    with fake_home():
        gesta.create_thread(_thread())
        gesta.add_turn("thread-0001", turn_id="turn-0001", origin=Origin.USER, created_at=T0)
        path = thread_path("thread-0001")
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 2
        view = gesta.load_thread("thread-0001")
        assert view.last_seq == 2
