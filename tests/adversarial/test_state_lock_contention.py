"""对抗：跨进程锁争用与进程死亡的内核释放语义（B-71 的运行时面）。

用真实子进程验证——这不是"看起来能跑"的模拟：
- 持有者活着时，另一进程在超时窗口内拿不到锁（LockTimeoutError，不死等）；
- 持有者**死亡**（而非释放）后，内核锁自动消亡，等待者可立即拿锁——
  这正是"无需心跳与陈旧锁清理"的依据。
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

import pytest

from questor.state.locks import LockTimeoutError, store_lock

REPO = pathlib.Path(__file__).resolve().parents[2]

_CHILD = """
import pathlib, sys, time
from questor.state.locks import store_lock

directory = pathlib.Path(sys.argv[1])
hold_seconds = float(sys.argv[2])
marker = directory / "held.marker"
with store_lock(directory, timeout=5.0):
    marker.write_text("held", encoding="utf-8")
    time.sleep(hold_seconds)
"""


def _spawn_holder(directory: pathlib.Path, hold_seconds: float) -> subprocess.Popen[bytes]:
    env = dict(os.environ)
    src = str(REPO / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.Popen(
        [sys.executable, "-c", _CHILD, str(directory), str(hold_seconds)],
        env=env,
    )


def _wait_for_marker(marker: pathlib.Path, deadline_s: float = 15.0) -> None:
    limit = time.monotonic() + deadline_s
    while not marker.exists():
        if time.monotonic() > limit:
            raise TimeoutError("子进程迟迟未持锁")
        time.sleep(0.02)


def test_timeout_while_holder_alive(tmp_path: pathlib.Path) -> None:
    holder = _spawn_holder(tmp_path, hold_seconds=1.5)
    try:
        _wait_for_marker(tmp_path / "held.marker")
        with pytest.raises(LockTimeoutError):
            store_lock(tmp_path, timeout=0.3).acquire()
    finally:
        holder.wait(timeout=15)


def test_kernel_releases_on_holder_death(tmp_path: pathlib.Path) -> None:
    """持有者不带释放地死亡后，锁必须立即可取（内核持有语义，B-71 无需清理逻辑）。"""
    # 子进程持锁期间被 SIGKILL：没有 release、没有清理，锁必须随进程消亡
    holder = _spawn_holder(tmp_path, hold_seconds=30.0)
    try:
        _wait_for_marker(tmp_path / "held.marker")
        holder.kill()
        holder.wait(timeout=15)
        lock = store_lock(tmp_path, timeout=5.0)  # 若锁未随死亡释放，这里将超时
        lock.acquire()
        lock.release()
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=15)
