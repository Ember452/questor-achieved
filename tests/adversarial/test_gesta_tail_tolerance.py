"""对抗：会话 JSONL 的残尾容忍（B-74）。

崩溃会把最后一行切成半行。契约：坏行跳过、回放可用、且**后续追加照常工作**
（下一次 append 仍 O_APPEND 到文件末尾，seq 从最大有效记录继续）。
fixture：tests/fixtures/gesta-corrupt-tail.jsonl（3 条有效记录 + 半行 + 空行 + 未知 kind 行）。
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Iterator

import pytest

import questor.gesta as gesta
from questor.schemas.model import RunStatus
from questor.state.paths import sessions_dir
from questor.testenv.fake_home import fake_home

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "gesta-corrupt-tail.jsonl"


@pytest.fixture()
def corrupt_thread() -> Iterator[None]:
    with fake_home():
        sessions_dir().mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURE, sessions_dir() / "test-thread-01.jsonl")
        yield


def test_corrupt_tail_does_not_block_replay(corrupt_thread: None) -> None:
    view = gesta.load_thread("test-thread-01")
    assert view.thread.id == "test-thread-01"
    assert len(view.turns) == 1
    assert len(view.runs) == 1
    assert view.runs[0].status == RunStatus.QUEUED
    assert view.last_seq == 3  # 半行与未知 kind 行都被跳过


def test_append_after_corrupt_tail_still_works(corrupt_thread: None) -> None:
    gesta.transition_run("test-thread-01", "run-0001", RunStatus.RUNNING)
    view = gesta.load_thread("test-thread-01")
    assert view.runs[0].status == RunStatus.RUNNING
    assert view.last_seq == 4  # 从最大有效 seq 继续，不重号


def test_corrupt_thread_is_skipped_by_index_rebuild(corrupt_thread: None) -> None:
    entries = gesta.rebuild_index()
    assert [s.id for s in entries] == ["test-thread-01"]  # 有效线程仍在索引
    assert entries[0].last_seq == 3


def test_tampered_history_raises_thread_store_error_not_stopiteration() -> None:
    """fold 对篡改历史必须抛 ThreadStoreError（rebuild_index 能捕获跳过），
    而不是裸 StopIteration/KeyError/ValueError 逃出 fold 边界。"""
    with fake_home():
        sessions_dir().mkdir(parents=True, exist_ok=True)
        base = FIXTURE.read_text(encoding="utf-8").splitlines()
        valid = [line for line in base if '"run.created"' in line or '"thread.created"' in line]
        # run.status 引用不存在的 run
        tampered = valid + [
            '{"seq": 9, "kind": "run.status", "payload": {"run_id": "run-ghost",'
            ' "from": "queued", "to": "running"},'
            ' "recorded_at": "2026-10-11T08:31:00Z"}'
        ]
        target = sessions_dir() / "test-thread-01.jsonl"
        target.write_text("\n".join(tampered) + "\n", encoding="utf-8", newline="\n")
        with pytest.raises(gesta.ThreadStoreError, match="不存在的 run"):
            gesta.load_thread("test-thread-01")
        assert gesta.rebuild_index() == []  # 损坏线程被索引重建跳过，不炸全表
        # to 字段为未知状态值 → 同样显式爆炸
        unknown_status = valid + [
            '{"seq": 9, "kind": "run.status", "payload": {"run_id": "run-0001",'
            ' "from": "queued", "to": "exploded"},'
            ' "recorded_at": "2026-10-11T08:31:00Z"}'
        ]
        target.write_text("\n".join(unknown_status) + "\n", encoding="utf-8", newline="\n")
        with pytest.raises(gesta.ThreadStoreError, match="未知状态"):
            gesta.load_thread("test-thread-01")
