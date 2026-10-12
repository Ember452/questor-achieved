"""vigilia —— 值守长跑（调度、唤醒检查点、僵尸运行清扫）。

承担柱子：**可干预 + 长跑**。边界层身份：cron/interval/once 的时间调度与重启后可续的
检查点（不是业务语义），语义规格来自 EvoFlow 的无人值守队列实测
（`docs/specs/behavior-queue-ef.md`）。

分工与刻意边界：
- 调度只回答"此刻该不该跑、跑了怎么记"，**不决定跑什么**——`fire` 回调由上层注入，
  长跑隔离（worktree）/远端执行将来只换回调；
- 清扫只读落盘事实，运行时真相由调用方以"候选 stale 集"给出（`overview.md` §3 裁定
  不复用任何框架 runs API）；
- 触发器与检查点是**声明式数据**（`schemas/vigilia.py`），加触发类型不改调度循环。

# Reimplements evoflow@<tag> backend/app/gateway/task_queue_runner.py
#   + automation_runner.py + zombie_run_sweeper.py — pitfalls: B-40 B-41 B-42 B-44 B-49
"""

from __future__ import annotations

from questor.vigilia.scheduler import (
    FireCallback,
    Scheduler,
    TickOutcome,
    advance,
    cron_matches,
    is_due,
    minute_slot,
)
from questor.vigilia.store import (
    ScheduleNotFound,
    VigiliaStoreError,
    add_trigger,
    get_trigger,
    load_view,
    set_checkpoint,
    update_trigger,
)
from questor.vigilia.sweep import StaleSweeper, SweepResult, next_batch

__all__ = [
    "FireCallback",
    "ScheduleNotFound",
    "Scheduler",
    "StaleSweeper",
    "SweepResult",
    "TickOutcome",
    "VigiliaStoreError",
    "add_trigger",
    "advance",
    "cron_matches",
    "get_trigger",
    "is_due",
    "load_view",
    "minute_slot",
    "next_batch",
    "set_checkpoint",
    "update_trigger",
]
