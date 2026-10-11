"""state.locks 单元行为：单进程内的获取/释放/幂等与锁文件存续。

跨进程争用与进程死亡的内核释放语义在 tests/adversarial/test_state_lock_contention.py。
"""

from __future__ import annotations

import pathlib

import pytest

from questor.state.locks import LockTimeoutError, store_lock


def test_acquire_release_reacquire(tmp_path: pathlib.Path) -> None:
    lock = store_lock(tmp_path, timeout=1.0)
    with lock:
        assert (tmp_path / ".store.lock").is_file()
    with lock:  # 释放后可立即再取
        pass


def test_release_is_idempotent(tmp_path: pathlib.Path) -> None:
    lock = store_lock(tmp_path, timeout=1.0)
    lock.acquire()
    lock.release()
    lock.release()  # 幂等，不抛错
    with lock:  # 释放后锁可再次获取
        pass


def test_double_acquire_same_handle_rejected(tmp_path: pathlib.Path) -> None:
    lock = store_lock(tmp_path, timeout=1.0)
    lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="重复"):
            lock.acquire()
    finally:
        lock.release()


def test_second_handle_in_same_process_times_out(tmp_path: pathlib.Path) -> None:
    """同进程另一句柄也拿不到锁（锁在内核，不在进程互斥量）。"""
    first = store_lock(tmp_path, timeout=1.0)
    first.acquire()
    try:
        with pytest.raises(LockTimeoutError):
            store_lock(tmp_path, timeout=0.1).acquire()
    finally:
        first.release()


def test_lock_file_survives_release(tmp_path: pathlib.Path) -> None:
    """B-71：锁文件释放后留在原地，两次获取锁的是同一个 inode。"""
    lock_path = tmp_path / ".store.lock"
    first = store_lock(tmp_path, timeout=1.0)
    first.acquire()
    inode_one = lock_path.stat().st_ino
    first.release()
    assert lock_path.exists(), "锁文件禁止删除（删除-重建会让并发进程锁不同 inode）"
    second = store_lock(tmp_path, timeout=1.0)
    second.acquire()
    try:
        assert lock_path.stat().st_ino == inode_one
    finally:
        second.release()


def test_per_call_timeout_override(tmp_path: pathlib.Path) -> None:
    """acquire 的 per-call 超时覆盖实例默认：热路径调用方传更短上限立即放弃。"""
    holder = store_lock(tmp_path, timeout=30.0)
    holder.acquire()
    try:
        import time

        start = time.monotonic()
        with pytest.raises(LockTimeoutError) as exc_info:
            store_lock(tmp_path, timeout=30.0).acquire(timeout=0.1)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, "per-call 超时应立即生效而非等实例默认 30s"
        assert exc_info.value.timeout == 0.1
    finally:
        holder.release()
