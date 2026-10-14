"""gesta 并发与跨进程锁（Phase 2a 批次 1；behavior-gesta-wuu §6；B-71/B-63）。

对抗面（AGENTS §四：先枚举它能怎么坏）：

1. sidecar 与 CLI 同开、两个写者抢同一库 → 必须**串行成功**而不是 ``database is locked``；
2. 两个写者并发取 seq → 不得重号、断号或覆盖（单点分配的真正考验）；
3. 跨进程锁被他人持有时 → 必须在超时后报 ``LockTimeoutError``（不死等、不"绕过锁继续写"）；
4. 释放锁**不得删除锁文件**（B-71：删-重建会让竞争者锁到不同 inode，互斥失效）。
"""

from __future__ import annotations

import pathlib
import threading

import pytest

from questor.gesta import inbox
from questor.gesta.records import InboxMessage
from questor.gesta.session_store import SessionStore
from questor.schemas.message import ChatMessage, MessageRole, TextPart
from questor.state.locks import LockTimeoutError, store_lock


def _message(text: str) -> ChatMessage:
    return ChatMessage(role=MessageRole.USER, parts=[TextPart(text=text)])


def test_two_stores_writing_same_db_do_not_lose_or_duplicate(tmp_path: pathlib.Path) -> None:
    """两个独立 SessionStore（各自的连接与进程内锁）共写一库：seq 全局连续、无锁报错。"""
    path = tmp_path / "sessions.sqlite3"
    bootstrap = SessionStore(path)
    bootstrap.create_session("s1")
    bootstrap.close()

    stores = [SessionStore(path) for _ in range(2)]
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker(index: SessionStore, label: str) -> None:
        try:
            barrier.wait()
            for turn in range(8):
                index.append_message("s1", _message(f"{label}-{turn}"))
        except BaseException as exc:  # noqa: BLE001 - 子线程异常必须带回主线程断言
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(store, f"句柄{i}")) for i, store in enumerate(stores)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for store in stores:
        store.close()

    assert not errors, f"并发写抛错（多为 database is locked / 锁未串行化）：{errors!r}"
    reader = SessionStore(path)
    try:
        seqs = [record.seq for record in reader.load_messages("s1")]
        assert seqs == list(range(1, 17)), f"seq 必须连续且不重号，实际：{seqs}"
    finally:
        reader.close()


def test_store_lock_blocks_second_holder_and_survives_release(tmp_path: pathlib.Path) -> None:
    """锁被占用时第二者必须超时（B-71 的另一半：释放后锁文件仍在原地，不删）。"""
    holder = store_lock(tmp_path, timeout=0.05)
    holder.acquire()
    try:
        competitor = store_lock(tmp_path, timeout=0.05)
        with pytest.raises(LockTimeoutError):
            competitor.acquire()
        assert holder.path.is_file()
    finally:
        holder.release()

    # 释放后锁文件必须还在（删掉就会让后来者锁到另一个 inode）
    assert holder.path.is_file(), "B-71：锁文件释放后禁止删除"
    reopened = store_lock(tmp_path, timeout=1.0)
    reopened.acquire()
    reopened.release()


def test_append_then_pending_settle_never_flaps(tmp_path: pathlib.Path) -> None:
    """B-127 的竞态面：追加与 pending 并发时，送达判定不得“回弹”。

    不变量：一旦某次轮询看到该输入已清空（settle 完成），后续轮不得再看到它未决。
    回弹意味着“已落历史又当未投递”，下一次消费会把它再注入一次——就是重复注入的真正成因。
    """
    path = tmp_path / "sessions.sqlite3"
    store = SessionStore(path)
    store.create_session("s1")
    inbox.enqueue(store, InboxMessage(client_id="c-race", session_id="s1", content="插话内容"))

    settled: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def appender() -> None:
        barrier.wait()
        store.append_message(
            "s1",
            ChatMessage(
                role=MessageRole.USER, parts=[TextPart(text="插话内容")], client_id="c-race"
            ),
        )

    def sweeper() -> None:
        barrier.wait()
        for _ in range(30):
            count = len(inbox.pending(store, "s1"))
            with lock:
                settled.append(count)

    threads = [threading.Thread(target=appender), threading.Thread(target=sweeper)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    try:
        assert settled, "轮询未记录到任何结果"
        # 单调：序列只能是 1…1, 0…0（一旦 settle 就不得回到 1）
        first_empty = next((i for i, count in enumerate(settled) if count == 0), None)
        if first_empty is not None:
            assert all(count == 0 for count in settled[first_empty:]), f"送达判定回弹：{settled}"
        assert inbox.pending(store, "s1") == [], "追加已落历史后，末态必须已 settle"
    finally:
        store.close()
