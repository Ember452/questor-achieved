"""vigilia 调度器单元测试（ADR-0026 的坑逐条钉住）。

先枚举失败方式再写实现：
- B-49：同一触发器并发触发只执行一次（per-task 锁 + 守卫锁）；
- B-41：cron 同分钟去重单闸（同分钟再 tick 不重触发）；
- B-42：once 触发成功后写幂等标记（再 tick 不再触发）；标记写失败不阻塞本轮；
- B-44 与 B-40 的清扫侧在 test_vigilia_sweep.py。
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Iterator

import pytest

from questor.schemas.model import utc_timestamp_now
from questor.schemas.vigilia import ScheduleCheckpoint, ScheduleTrigger, TriggerKind
from questor.state.paths import vigilia_log_path
from questor.testenv.fake_home import fake_home
from questor.vigilia import Scheduler, store
from questor.vigilia.scheduler import cron_matches, is_due, minute_slot, parse_timestamp

NOW = dt.datetime(2026, 10, 12, 8, 0, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    """每个用例一个隔离的 `QUESTOR_HOME`（不污染真实会话记录）。"""
    with fake_home():
        yield


def _trigger(
    trigger_kind: TriggerKind,
    *,
    next_fire_at: str | None = None,
    interval_seconds: int | None = None,
    cron: str | None = None,
    enabled: bool = True,
    once_fired: bool = False,
    thread_id: str | None = None,
    prompt: str | None = None,
) -> ScheduleTrigger:
    """构造一个触发器；id 由类型决定（同一用例内互不冲突）。"""
    return ScheduleTrigger(
        id=f"t-{trigger_kind.value}",
        trigger_kind=trigger_kind,
        next_fire_at=next_fire_at,
        interval_seconds=interval_seconds,
        cron=cron,
        enabled=enabled,
        once_fired=once_fired,
        thread_id=thread_id,
        prompt=prompt,
        created_at=utc_timestamp_now(),
        updated_at=utc_timestamp_now(),
    )


def test_tick_does_not_rewind_sweep_cursor_advanced_during_fire() -> None:
    """B-40 回归：tick 收尾写检查点时不得拿 tick 开头读到的旧视图，
    把中途（fire 回调里）清扫推进的游标回退——游标回退等于重查同一 top-N。"""
    trigger = _trigger(TriggerKind.ONCE, next_fire_at="2026-10-12T07:59:59Z")
    store.add_trigger(trigger)
    store.set_checkpoint(ScheduleCheckpoint(last_tick_at="2026-10-12T07:00:00Z", sweep_cursor=5))
    scheduler = Scheduler()

    async def run() -> None:
        async def fire(_t: ScheduleTrigger) -> None:
            # 模拟 tick 执行窗口内清扫推进了一批（5 → 9）
            store.set_checkpoint(
                ScheduleCheckpoint(last_tick_at="2026-10-12T07:30:00Z", sweep_cursor=9)
            )

        await scheduler.tick(NOW, fire)

    asyncio.run(run())
    assert store.load_view().checkpoint.sweep_cursor == 9  # tick 不得把游标写回旧值 5


def test_once_fires_once_and_is_idempotent() -> None:
    """B-42：once 到点触发一次，成功后写 once_fired；第二次 tick 不再触发。"""
    fired: list[str] = []
    trigger = _trigger(TriggerKind.ONCE, next_fire_at="2026-10-12T07:59:59Z")
    store.add_trigger(trigger)
    scheduler = Scheduler()

    async def run() -> None:
        async def fire(t: ScheduleTrigger) -> None:
            fired.append(t.id)

        outcomes = await scheduler.tick(NOW, fire)
        assert [o.outcome for o in outcomes] == ["fired"]
        after = store.load_view().triggers[0]
        assert after.once_fired is True
        outcomes2 = await scheduler.tick(NOW + dt.timedelta(minutes=5), fire)
        assert outcomes2 == []

    asyncio.run(run())
    assert fired == [trigger.id]


def test_interval_advances_next_fire_at() -> None:
    """interval：触发后 next_fire_at 前移到 now+间隔；未到点不触发。"""
    fired: list[str] = []
    trigger = _trigger(
        TriggerKind.INTERVAL, interval_seconds=60, next_fire_at="2026-10-12T07:59:59Z"
    )
    store.add_trigger(trigger)
    scheduler = Scheduler()

    async def run() -> None:
        async def fire(t: ScheduleTrigger) -> None:
            fired.append(t.id)

        out1 = await scheduler.tick(NOW, fire)
        assert [o.outcome for o in out1] == ["fired"]
        advanced = store.load_view().triggers[0]
        assert advanced.next_fire_at == "2026-10-12T08:01:00Z"
        out2 = await scheduler.tick(NOW + dt.timedelta(seconds=30), fire)
        assert out2 == []
        out3 = await scheduler.tick(NOW + dt.timedelta(seconds=90), fire)
        assert [o.outcome for o in out3] == ["fired"]

    asyncio.run(run())
    assert len(fired) == 2


def test_per_task_lock_prevents_concurrent_fire() -> None:
    """B-49：同一触发器并发 tick 也只执行一次（per-task 锁 + 守卫锁）。"""
    trigger = _trigger(TriggerKind.ONCE, next_fire_at="2026-10-12T07:59:59Z")
    store.add_trigger(trigger)
    scheduler = Scheduler(max_concurrent=4)
    concurrent = 0
    peak = 0

    async def run() -> None:
        nonlocal concurrent, peak

        async def fire(t: ScheduleTrigger) -> None:
            nonlocal concurrent, peak
            concurrent += 1
            peak = max(peak, concurrent)
            await asyncio.sleep(0.02)
            concurrent -= 1

        results = await asyncio.gather(*[scheduler.tick(NOW, fire) for _ in range(5)])
        fired = [o for batch in results for o in batch if o.outcome == "fired"]
        assert len(fired) == 1, f"同一触发器被并发推进：{fired}"
        assert peak <= 1, "fire 回调被重入"

    asyncio.run(run())


def test_cron_dedupes_same_minute() -> None:
    """B-41：cron 同分钟去重——同一分钟再 tick 不重触发。"""
    fired: list[str] = []
    trigger = _trigger(TriggerKind.CRON, cron="0 8 * * *")
    store.add_trigger(trigger)
    scheduler = Scheduler()

    async def run() -> None:
        async def fire(t: ScheduleTrigger) -> None:
            fired.append(t.id)

        out1 = await scheduler.tick(NOW, fire)  # 08:00:00 命中
        assert [o.outcome for o in out1] == ["fired"]
        out2 = await scheduler.tick(NOW + dt.timedelta(seconds=30), fire)
        assert out2 == []
        out3 = await scheduler.tick(NOW + dt.timedelta(days=1), fire)
        assert [o.outcome for o in out3] == ["fired"]

    asyncio.run(run())
    assert len(fired) == 2


def test_disabled_and_fired_once_are_never_due() -> None:
    disabled = _trigger(TriggerKind.ONCE, next_fire_at="2026-10-12T07:59:59Z", enabled=False)
    assert is_due(disabled, NOW) is False
    fired = _trigger(TriggerKind.ONCE, next_fire_at="2026-10-12T07:59:59Z", once_fired=True)
    assert is_due(fired, NOW) is False


def test_cron_matches_and_minute_slot() -> None:
    assert cron_matches("0 8 * * *", NOW) is True
    assert cron_matches("30 8 * * *", NOW) is False
    assert cron_matches("*/15 * * * *", NOW) is True  # 08:00 是 15 的倍数
    assert minute_slot(NOW) == "2026-10-12T08:00"


def test_fire_failure_is_reported_not_silent() -> None:
    """诚实呈现：回调抛错 → 本轮标 skipped 而非 fired；不吞成成功。"""
    trigger = _trigger(TriggerKind.ONCE, next_fire_at="2026-10-12T07:59:59Z")
    store.add_trigger(trigger)
    scheduler = Scheduler()

    async def run() -> None:
        async def fire(t: ScheduleTrigger) -> None:
            raise RuntimeError("boom")

        out = await scheduler.tick(NOW, fire)
        assert [o.outcome for o in out] == ["skipped"]

    asyncio.run(run())


def test_checkpoint_persisted_on_every_tick() -> None:
    trigger = _trigger(
        TriggerKind.INTERVAL, interval_seconds=60, next_fire_at="2026-10-12T07:59:59Z"
    )
    store.add_trigger(trigger)
    scheduler = Scheduler()

    async def run() -> None:
        async def fire(t: ScheduleTrigger) -> None:
            pass

        await scheduler.tick(NOW, fire)
        view = store.load_view()
        assert view.checkpoint.last_tick_at == "2026-10-12T08:00:00Z"
        assert isinstance(view.checkpoint, ScheduleCheckpoint)

    asyncio.run(run())


def test_store_roundtrip_and_append_only() -> None:
    """store：追加往返 + append-only（改历史 = 新记录，不改写旧行）。"""
    trigger = _trigger(TriggerKind.ONCE, next_fire_at="2026-10-12T07:59:59Z")
    store.add_trigger(trigger)
    store.update_trigger(trigger.model_copy(update={"once_fired": True}))
    store.set_checkpoint(ScheduleCheckpoint(last_tick_at="2026-10-12T08:00:00Z"))
    view = store.load_view()
    assert view.triggers[0].once_fired is True
    assert view.last_seq == 3  # created + updated + checkpoint = 3 条
    lines = vigilia_log_path().read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "schedule.checkpoint" in lines[-1]


def test_duplicate_trigger_rejected() -> None:
    trigger = _trigger(TriggerKind.ONCE)
    store.add_trigger(trigger)
    with pytest.raises(store.VigiliaStoreError):
        store.add_trigger(trigger)


def test_missing_trigger_raises_not_found() -> None:
    with pytest.raises(store.ScheduleNotFound):
        store.update_trigger(_trigger(TriggerKind.ONCE))
    with pytest.raises(store.ScheduleNotFound):
        store.get_trigger("nope")


def test_parse_timestamp_roundtrip() -> None:
    assert parse_timestamp("2026-10-12T08:00:00Z") == NOW
