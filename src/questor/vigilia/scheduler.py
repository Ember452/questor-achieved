"""vigilia 调度器：tick + 声明式触发器匹配 + 幂等（ADR-0026）。

调度循环只做四件事，全部对应一条坑：
- **tick 并发上限**：一个 tick 最多同时启动 `max_concurrent` 个触发；
- **per-task 锁 + 守卫锁**：同一触发器不会被并发推进（B-49）；
- **幂等**：`once` 触发成功后写 `once_fired`，标记失败记 warning 但不阻塞（B-42）；
- **同分钟去重**：`cron` 命中后写 `last_fired_slot`，同分钟不再重复（B-41）。

`fire` 是注入的异步回调（起一轮 / 派发一个任务），使调度器不绑定具体执行方式——
长跑隔离（worktree）或远端执行将来只换回调，不改调度循环。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from questor.schemas.vigilia import (
    ScheduleTrigger,
    TriggerKind,
)
from questor.vigilia import store
from questor.vigilia.constants import DEFAULT_MAX_CONCURRENT
from questor.vigilia.store import VigiliaStoreError

__all__ = [
    "FireCallback",
    "Scheduler",
    "TickOutcome",
    "advance",
    "cron_matches",
    "is_due",
    "minute_slot",
    "parse_timestamp",
]

logger = logging.getLogger(__name__)

#: 触发回调：吃一个触发器，起一轮/派发一个任务（异常由调度器捕获，不带走整个 tick）
FireCallback = Callable[[ScheduleTrigger], Awaitable[None]]

_TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_timestamp(text: str) -> dt.datetime:
    """解析 data-model §1 形状的 UTC 时间戳为带时区 datetime。"""
    return dt.datetime.strptime(text, _TIMESTAMP_FMT).replace(tzinfo=dt.UTC)


def format_timestamp(moment: dt.datetime) -> str:
    """datetime → data-model §1 形状的 UTC 秒级时间戳。"""
    return moment.astimezone(dt.UTC).strftime(_TIMESTAMP_FMT)


def minute_slot(now: dt.datetime) -> str:
    """当前"分钟槽"（`YYYY-MM-DDTHH:MM`）——cron 同分钟去重的键（B-41）。"""
    return now.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M")


def _at_or_after(now: dt.datetime, when: str | None) -> bool:
    """`now` 是否已到/超过 `when`；`when` 为空视为"立即到点"。"""
    return when is None or now >= parse_timestamp(when)


def _parse_cron_field(field: str, lo: int, hi: int) -> frozenset[int]:
    """解析一个 cron 字段：支持 `*`、`a-b`、`*/n`、逗号列表与组合（`a,b-c/d`）。"""
    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
            if step <= 0:
                raise ValueError(f"非法 cron 步长：{field!r}")
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(part)
        if start < lo or end > hi or start > end:
            raise ValueError(f"cron 字段越界：{field!r}（允许 {lo}-{hi}）")
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError(f"cron 字段为空：{field!r}")
    return frozenset(values)


def cron_matches(expr: str, now: dt.datetime) -> bool:
    """5 字段 cron（分 时 日 月 周）是否命中 `now`；周日=0（标准 cron 语义）。

    依赖**本机时钟**（B-41）：休眠/时钟漂移会漏触发，由检查点与"错过不重放"补偿。
    """
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"cron 必须是 5 字段（分 时 日 月 周）：{expr!r}")
    minute, hour, day, month, weekday = fields
    moment = now.astimezone(dt.UTC)
    weekday_value = (moment.weekday() + 1) % 7  # Python 周一=0 → cron 周日=0
    return (
        moment.minute in _parse_cron_field(minute, 0, 59)
        and moment.hour in _parse_cron_field(hour, 0, 23)
        and moment.day in _parse_cron_field(day, 1, 31)
        and moment.month in _parse_cron_field(month, 1, 12)
        and weekday_value in _parse_cron_field(weekday, 0, 6)
    )


def is_due(trigger: ScheduleTrigger, now: dt.datetime) -> bool:
    """该触发器此刻是否到点（disabled / 已 fire 的 once 一律不到点）。"""
    if not trigger.enabled:
        return False
    if trigger.trigger_kind == TriggerKind.ONCE:
        if trigger.once_fired:
            return False
        return _at_or_after(now, trigger.next_fire_at)
    if trigger.trigger_kind == TriggerKind.INTERVAL:
        return _at_or_after(now, trigger.next_fire_at)
    # cron：同分钟去重单闸（B-41）
    if trigger.last_fired_slot == minute_slot(now):
        return False
    if not trigger.cron:
        return False
    return cron_matches(trigger.cron, now)


def advance(trigger: ScheduleTrigger, now: dt.datetime) -> ScheduleTrigger:
    """触发后推进触发器状态：once 置幂等标记、interval 推下次到点、cron 记分钟槽。"""
    stamp = format_timestamp(now)
    if trigger.trigger_kind == TriggerKind.ONCE:
        return trigger.model_copy(
            update={"once_fired": True, "next_fire_at": None, "updated_at": stamp}
        )
    if trigger.trigger_kind == TriggerKind.INTERVAL:
        seconds = trigger.interval_seconds or 0
        next_at = format_timestamp(now + dt.timedelta(seconds=seconds))
        return trigger.model_copy(update={"next_fire_at": next_at, "updated_at": stamp})
    return trigger.model_copy(update={"last_fired_slot": minute_slot(now), "updated_at": stamp})


@dataclass(frozen=True)
class TickOutcome:
    """一次 tick 内单个触发器的结果，供上层发 `notice/schedule` 通知。"""

    trigger_id: str
    outcome: str  # fired | skipped
    #: 触发器类型（once/interval/cron）；通知形状需要它，这里带上免得上层再读盘
    kind: str = ""


class Scheduler:
    """内存态调度器：持 per-task 锁表（B-49）与并发上限；触发器真相仍在 store。"""

    def __init__(self, *, max_concurrent: int = DEFAULT_MAX_CONCURRENT) -> None:
        self._max_concurrent = max_concurrent
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    def _lock_for(self, trigger_id: str) -> asyncio.Lock:
        """per-task `asyncio.Lock` 字典 + 守卫锁：防同一触发器被并发推进（B-49）。"""
        lock = self._locks.get(trigger_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[trigger_id] = lock
        return lock

    async def tick(self, now: dt.datetime, fire: FireCallback) -> list[TickOutcome]:
        """跑一个 tick：取到点触发器，限并发启动，收尾写检查点。

        单个触发器失败（回调抛错 / 标记写失败）只记 warning，不带走整个 tick，
        也不静默把失败当成功——本轮结果如实标 `skipped`（诚实呈现铁律）。
        """
        view = await asyncio.to_thread(store.load_view)
        due = [t for t in view.triggers if is_due(t, now)]
        semaphore = asyncio.Semaphore(self._max_concurrent)
        results = await asyncio.gather(*(self._fire(t, now, fire, semaphore) for t in due))
        # 只推进 last_tick_at：游标由清扫自己写（持锁读-改-写，防回退 B-40）
        await asyncio.to_thread(store.record_tick, format_timestamp(now))
        return list(results)

    async def _fire(
        self,
        trigger: ScheduleTrigger,
        now: dt.datetime,
        fire: FireCallback,
        semaphore: asyncio.Semaphore,
    ) -> TickOutcome:
        async with self._guard:
            lock = self._lock_for(trigger.id)
        async with semaphore, lock:
            # 拿到锁后**重读**触发器并复判到点：并发 tick 会在锁上排队，
            # 先到的那个已把 once_fired/next_fire_at 写回，后到的必须看到新状态而放弃
            # （否则 per-task 锁只串行化、不阻断重复触发——B-49 的实质）。
            fresh = await asyncio.to_thread(_reload_trigger, trigger.id)
            if fresh is None or not is_due(fresh, now):
                return TickOutcome(trigger.id, "skipped", trigger.trigger_kind.value)
            try:
                await fire(fresh)
            except Exception:  # noqa: BLE001 - 单个触发器失败不能带走整个 tick
                logger.warning("触发器 %s 执行失败，本轮不标记为已触发", trigger.id, exc_info=True)
                return TickOutcome(trigger.id, "skipped", fresh.trigger_kind.value)
            advanced = advance(fresh, now)
            try:
                await asyncio.to_thread(store.update_trigger, advanced)
            except VigiliaStoreError:
                # B-42：once_fired 标记失败记 warning 但不阻塞——下一 tick 可能重触发，
                # 这比"卡住不跑"更可取（幂等由回调侧再兜一层）。
                logger.warning(
                    "触发器 %s 已触发但写回失败（不阻塞本轮）", trigger.id, exc_info=True
                )
        return TickOutcome(trigger.id, "fired", fresh.trigger_kind.value)


def _reload_trigger(trigger_id: str) -> ScheduleTrigger | None:
    """重读触发器最新落盘状态；已被删除则返回 None。"""
    try:
        return store.get_trigger(trigger_id)
    except store.ScheduleNotFound:
        return None
