"""vigilia 调度存储：append-only JSONL 唯一真相源 + fold 投影（ADR-0026）。

落盘契约与 `gesta/store.py` 同构（B-74 残尾容忍、append-only、`state` 跨进程锁），
但记录更少、且**不建索引**——触发器数量天然很小，折叠成本可忽略，少一个可重建缓存
就少一处漂移面（与 gesta 的索引取舍不同，理由是"有无第二个真实读者"）。

记录 kind：`schedule.created` / `schedule.updated` / `schedule.checkpoint`。
`schedule.updated` 承载触发器全量 dump（幂等覆盖），使"触发后写 once_fired / next_fire_at"
是一次整对象追加，而不是字段增量的拼接。

# Reimplements evoflow@<tag> gateway/automation_runner.py — pitfalls: B-41 B-42
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from questor.schemas.model import utc_timestamp_now
from questor.schemas.vigilia import ScheduleCheckpoint, ScheduleTrigger, ScheduleView
from questor.state.locks import store_lock
from questor.state.paths import vigilia_dir, vigilia_log_path

__all__ = [
    "ScheduleNotFound",
    "VigiliaStoreError",
    "add_trigger",
    "get_trigger",
    "load_view",
    "record_tick",
    "set_checkpoint",
    "set_sweep_cursor",
    "update_trigger",
]


class VigiliaStoreError(Exception):
    """vigilia 存储层错误的基类。"""


class ScheduleNotFound(VigiliaStoreError):
    """引用了不存在的触发器 id。"""


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int
    kind: str
    payload: dict[str, Any]
    recorded_at: str

    def to_line(self) -> str:
        return self.model_dump_json()


_RECORD_KINDS = frozenset({"schedule.created", "schedule.updated", "schedule.checkpoint"})


def _parse_line(text: str) -> _Record | None:
    text = text.strip()
    if not text:
        return None
    try:
        record = _Record.model_validate(json.loads(text))
    except (ValueError, ValidationError):
        return None
    if record.kind not in _RECORD_KINDS:
        return None
    return record


def _read_records(path: pathlib.Path) -> list[_Record]:
    if not path.is_file():
        return []
    records: list[_Record] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = _parse_line(line)
        if record is not None:
            records.append(record)
    return records


def _fold(records: list[_Record]) -> ScheduleView:
    triggers: dict[str, ScheduleTrigger] = {}
    checkpoint = ScheduleCheckpoint()
    last_seq = 0
    for record in records:
        last_seq = max(last_seq, record.seq)
        if record.kind in ("schedule.created", "schedule.updated"):
            trigger = ScheduleTrigger.model_validate(record.payload)
            triggers[trigger.id] = trigger
        elif record.kind == "schedule.checkpoint":
            checkpoint = ScheduleCheckpoint.model_validate(record.payload)
    return ScheduleView(triggers=tuple(triggers.values()), checkpoint=checkpoint, last_seq=last_seq)


def load_view() -> ScheduleView:
    """读取并 fold 调度状态；无文件返回空视图（尚未建任何触发器）。"""
    return _fold(_read_records(vigilia_log_path()))


def get_trigger(trigger_id: str) -> ScheduleTrigger:
    for trigger in load_view().triggers:
        if trigger.id == trigger_id:
            return trigger
    raise ScheduleNotFound(trigger_id)


def _ends_with_newline(path: pathlib.Path) -> bool:
    if not path.exists():
        return True
    size = path.stat().st_size
    if size == 0:
        return True
    with path.open("rb") as handle:
        handle.seek(-1, 2)
        return handle.read(1) == b"\n"


def _append_locked(kind: str, payload: dict[str, Any], last_seq: int) -> None:
    record = _Record(seq=last_seq + 1, kind=kind, payload=payload, recorded_at=utc_timestamp_now())
    path = vigilia_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = record.to_line().encode("utf-8") + b"\n"
    if not _ends_with_newline(path):
        data = b"\n" + data  # 崩溃残尾不粘接（B-74），追加永不截断
    with path.open("ab") as handle:
        handle.write(data)
        handle.flush()


def add_trigger(trigger: ScheduleTrigger) -> ScheduleTrigger:
    """追加一个触发器；同 id 已存在即抛 :class:`VigiliaStoreError`。"""
    with store_lock(vigilia_dir()):
        view = load_view()
        if any(t.id == trigger.id for t in view.triggers):
            raise VigiliaStoreError(f"触发器 {trigger.id} 已存在")
        _append_locked("schedule.created", trigger.model_dump(mode="json"), view.last_seq)
        return trigger


def update_trigger(trigger: ScheduleTrigger) -> ScheduleTrigger:
    """整对象覆盖一个触发器（触发后写 once_fired / next_fire_at / last_fired_slot）。"""
    with store_lock(vigilia_dir()):
        view = load_view()
        if not any(t.id == trigger.id for t in view.triggers):
            raise ScheduleNotFound(trigger.id)
        _append_locked("schedule.updated", trigger.model_dump(mode="json"), view.last_seq)
        return trigger


def set_checkpoint(checkpoint: ScheduleCheckpoint) -> ScheduleCheckpoint:
    """整体写入唤醒检查点（初始化/测试用；日常更新走 :func:`record_tick` 或
    :func:`set_sweep_cursor`——两个写方各自只推进自己的字段）。"""
    with store_lock(vigilia_dir()):
        view = load_view()
        _append_locked("schedule.checkpoint", checkpoint.model_dump(mode="json"), view.last_seq)
        return checkpoint


def record_tick(last_tick_at: str) -> ScheduleCheckpoint:
    """tick 收尾记 `last_tick_at`，**持锁下读盘保留当前清扫游标**。

    tick 开头读到的是旧游标：若照旧游标整写回，会盖掉 tick 执行窗口内清扫已推进的
    游标（回退即重查同一 top-N，B-40 空转洞重开）。读-改-写在锁内完成。
    """
    with store_lock(vigilia_dir()):
        view = load_view()
        checkpoint = ScheduleCheckpoint(
            last_tick_at=last_tick_at, sweep_cursor=view.checkpoint.sweep_cursor
        )
        _append_locked("schedule.checkpoint", checkpoint.model_dump(mode="json"), view.last_seq)
        return checkpoint


def set_sweep_cursor(cursor: int) -> ScheduleCheckpoint:
    """推进清扫游标，持锁下保留当前 `last_tick_at`（与 :func:`record_tick` 对称）。"""
    with store_lock(vigilia_dir()):
        view = load_view()
        checkpoint = ScheduleCheckpoint(
            last_tick_at=view.checkpoint.last_tick_at, sweep_cursor=cursor
        )
        _append_locked("schedule.checkpoint", checkpoint.model_dump(mode="json"), view.last_seq)
        return checkpoint
