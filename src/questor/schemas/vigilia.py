"""vigilia 的调度形状（`data-model.md` v1.3 编排域，ADR-0026）。

触发器与检查点是**声明式数据**（不是分支）：加一种触发类型只改这里的枚举与调度表，
不改调度循环的控制流。住 `schemas` 的理由与 `habena.py`/`orchestration.py` 同源——
写方是 `vigilia`、落盘与回放是 vigilia store、跨进程呈现是 `serve`，三方看同一份定义。

全部 frozen + `extra="forbid"`（append-only 纪律）；本模块不 import 任何业务模块。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ScheduleCheckpoint",
    "ScheduleTrigger",
    "ScheduleView",
    "TriggerKind",
]


class TriggerKind(StrEnum):
    """触发器类型（ADR-0026）。"""

    ONCE = "once"
    INTERVAL = "interval"
    CRON = "cron"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScheduleTrigger(_Frozen):
    """一个值守触发器。

    - `once`：到点触发一次，成功后写 `once_fired` 幂等标记（B-42）；错过不重放。
    - `interval`：每 `interval_seconds` 触发；`next_fire_at` 记录下次到点时刻。
    - `cron`：5 字段 cron 表达式；依赖**本机时钟**（B-41），同分钟去重靠检查点的 `last_slot`。

    触发目标二选一：`task_id`（编排任务）或 `thread_id` + `prompt`（直接起一轮）。
    """

    id: str = Field(min_length=1)
    trigger_kind: TriggerKind
    enabled: bool = True
    once_fired: bool = False
    interval_seconds: int | None = Field(default=None, ge=1)
    cron: str | None = None
    next_fire_at: str | None = None
    #: 上次命中的"分钟槽"（`YYYY-MM-DDTHH:MM`）：cron 同分钟去重的单闸（B-41）
    last_fired_slot: str | None = None
    task_id: str | None = None
    thread_id: str | None = None
    prompt: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class ScheduleCheckpoint(_Frozen):
    """唤醒检查点：调度进度落盘，重启据此续跑（不靠内存态，ADR-0026）。

    - `last_tick_at`：上次 tick 时刻（长跑重启后从此刻续，不重放错过的触发）；
    - `sweep_cursor`：清扫游标（一批一间隔、不重查同一 top-N，B-40）。

    一次性幂等标记住在触发器自身的 `once_fired`（B-42），不在此重复一份。
    """

    last_tick_at: str | None = None
    sweep_cursor: int = Field(default=0, ge=0)


class ScheduleView(_Frozen):
    """vigilia 记录流 fold 出的当前状态（只读投影）。"""

    triggers: tuple[ScheduleTrigger, ...] = ()
    checkpoint: ScheduleCheckpoint = ScheduleCheckpoint()
    last_seq: int = Field(default=0, ge=0)
