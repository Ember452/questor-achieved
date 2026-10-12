"""process 工具"改唤醒周期"单元测试（M4 vigilia，overview §5 L1 承诺）。

唤醒周期让长跑中的后台进程按固定节拍被叫醒查看输出，而不是干等退出。
本测试用真实子进程（与 `tests/adversarial/test_tools_run_process.py` 同法），
只断言"到点判定 + 已读输出清空后不再到点"两条可观察行为。
"""

from __future__ import annotations

import sys
import time

import pytest

from questor.tools.processmgr import ProcessManager, ProcessManagerError

BG_SCRIPT = "import time; print('bg-out', flush=True); time.sleep(30)"
BG_COMMAND = f'"{sys.executable}" -c "{BG_SCRIPT}"'


def _wait_for_output(manager: ProcessManager, process_id: str, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        process = manager.get(process_id)
        if process.stdout_chunks or process.stderr_chunks:
            return
        time.sleep(0.05)
    raise AssertionError("后台进程在超时内没有产出输出")


def test_wake_interval_due_and_reset() -> None:
    manager = ProcessManager()
    process = manager.spawn(BG_COMMAND)
    try:
        _wait_for_output(manager, process.process_id)
        manager.set_wake_interval(process.process_id, 5.0)
        start = time.monotonic()
        # 刚设置：未到点
        assert manager.due_wakes(now=start) == []
        # 超过周期且有未读输出：到点
        assert manager.due_wakes(now=start + 6.0) == [process.process_id]
        # 消费一次唤醒后推进时刻：不再到点（防重复唤醒）
        manager.mark_woken(process.process_id, now=start + 6.0)
        assert manager.due_wakes(now=start + 7.0) == []
    finally:
        manager.stop(process.process_id)


def test_drained_output_is_not_due() -> None:
    manager = ProcessManager()
    process = manager.spawn(BG_COMMAND)
    try:
        _wait_for_output(manager, process.process_id)
        manager.set_wake_interval(process.process_id, 1.0)
        manager.read_output(process.process_id)  # 读空增量缓冲
        assert manager.due_wakes(now=time.monotonic() + 10.0) == []
    finally:
        manager.stop(process.process_id)


def test_wake_interval_can_be_cleared() -> None:
    manager = ProcessManager()
    process = manager.spawn(BG_COMMAND)
    try:
        _wait_for_output(manager, process.process_id)
        manager.set_wake_interval(process.process_id, 1.0)
        manager.set_wake_interval(process.process_id, None)  # 取消周期唤醒
        assert manager.due_wakes(now=time.monotonic() + 10.0) == []
    finally:
        manager.stop(process.process_id)


def test_non_positive_interval_rejected() -> None:
    manager = ProcessManager()
    process = manager.spawn(BG_COMMAND)
    try:
        with pytest.raises(ProcessManagerError):
            manager.set_wake_interval(process.process_id, 0)
    finally:
        manager.stop(process.process_id)
