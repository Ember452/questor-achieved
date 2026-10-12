"""长跑驱动接线集成（M4 收口）：schedule/create 校验、双 reconcile、tick 真触发、Goal 轮自驱。

全部以真实落盘事实与真实通知流核验（不 mock 驱动本身）：run 状态回读 gesta、
轮次回读编排 store、通知来自 dispatcher 的真实出口。
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Iterator

import pytest

from questor.engine import Engine
from questor.gesta import load_thread
from questor.gesta.store import add_run, transition_run
from questor.orchestration import goal as orch_goal
from questor.orchestration import store as orch_store
from questor.schemas.model import PermissionMode, Run, RunStatus, utc_timestamp_now
from questor.serve.app_server import AppServer
from questor.serve.assembly import build_engine, ensure_workspace_for_root
from questor.serve.dispatch import HandlerCtx
from questor.serve.envelope import Notification, ProtocolError
from questor.serve.longrun import LongRunDriver
from questor.testenv.fake_home import fake_home
from questor.testenv.fake_model import FakeModel, ScriptedTurn


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def _ctx() -> HandlerCtx:
    return HandlerCtx(request_id="lr", principal="local", trace_id="lr")


def _server(tmp_path: pathlib.Path, turns: int = 8) -> tuple[AppServer, list[Notification]]:
    model = FakeModel([ScriptedTurn(text=f"ok-{i}") for i in range(turns)])

    def factory(thread_id: str, mode: PermissionMode) -> Engine:
        return build_engine(model=model, cwd=str(tmp_path), mode=mode, thread_id=thread_id)

    server = AppServer(
        create_engine=factory, default_workspace_id=ensure_workspace_for_root(tmp_path)
    )
    notes: list[Notification] = []
    server.build_dispatcher(notify=notes.append)
    return server, notes


def _run(run_id: str) -> Run:
    return Run(
        id=run_id,
        turn_id="turn-1",
        engine_id="questor-engine",
        permission_mode=PermissionMode.STANDARD,
        status=RunStatus.QUEUED,
        created_at=utc_timestamp_now(),
    )


def test_schedule_create_validation(tmp_path: pathlib.Path) -> None:
    """create 的输入必须真实校验：kind 枚举、interval 秒数、cron 形状、目标字段。"""
    server, _notes = _server(tmp_path)
    ctx = _ctx()

    async def run() -> None:
        with pytest.raises(ProtocolError):  # interval 缺秒数
            await server.schedule_create(
                {"trigger_kind": "interval", "thread_id": "t", "prompt": "p"}, ctx
            )
        with pytest.raises(ProtocolError):  # cron 表达式非法
            await server.schedule_create(
                {
                    "trigger_kind": "cron",
                    "cron": "bogus expr here x y z",
                    "thread_id": "t",
                    "prompt": "p",
                },
                ctx,
            )
        with pytest.raises(ProtocolError):  # 未知 trigger_kind
            await server.schedule_create(
                {"trigger_kind": "daily", "thread_id": "t", "prompt": "p"}, ctx
            )
        with pytest.raises(ProtocolError):  # 缺 prompt
            await server.schedule_create({"trigger_kind": "once", "thread_id": "t"}, ctx)

        created = await server.schedule_create(
            {
                "trigger_kind": "interval",
                "interval_seconds": 60,
                "thread_id": "thread-x",
                "prompt": "check",
            },
            ctx,
        )
        assert created["schedule"]["enabled"] is True
        listed = await server.schedule_list({}, ctx)
        assert [s["id"] for s in listed["schedules"]] == [created["schedule"]["id"]]

    asyncio.run(run())


def test_startup_reconcile_marks_stale_runs(tmp_path: pathlib.Path) -> None:
    """B-44：重启后落盘的 running 是假活——启动 reconcile 必须收掉。

    running→failed、queued→cancelled（全走 gesta 白名单单点）。
    """
    server, _notes = _server(tmp_path)
    ctx = _ctx()

    async def run() -> None:
        thread_id = (await server.thread_create({"title": "t"}, ctx))["thread"]["id"]
        add_run(thread_id, _run("run-stale"))
        transition_run(thread_id, "run-stale", RunStatus.RUNNING)
        add_run(thread_id, _run("run-queued"))

        driver = LongRunDriver(server, tick_seconds=3600.0)
        await driver.start()  # 启动即一次性全量 reconcile
        await driver.stop()

        statuses = {r.id: r.status for r in load_thread(thread_id).runs}
        assert statuses["run-stale"] is RunStatus.FAILED
        assert statuses["run-queued"] is RunStatus.CANCELLED

    asyncio.run(run())


def test_periodic_sweep_skips_live_runs(tmp_path: pathlib.Path) -> None:
    """周期清扫只收"本进程没有活体在跑"的 running——在飞的 run 属运行时真值，不得误杀。"""
    server, _notes = _server(tmp_path)
    ctx = _ctx()

    async def run() -> None:
        thread_id = (await server.thread_create({"title": "t"}, ctx))["thread"]["id"]
        add_run(thread_id, _run("run-live"))
        transition_run(thread_id, "run-live", RunStatus.RUNNING)
        live: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(30))
        server._runs[thread_id] = live  # 模拟本进程在飞
        driver = LongRunDriver(server, tick_seconds=3600.0)

        driver.sweep_once()  # 活体线程的 run 必须不动
        assert load_thread(thread_id).runs[-1].status is RunStatus.RUNNING

        live.cancel()
        with pytest.raises(asyncio.CancelledError):
            await live
        driver.sweep_once()  # 掉线成僵尸后被收
        assert load_thread(thread_id).runs[-1].status is RunStatus.FAILED

    asyncio.run(run())


def test_driver_tick_fires_interval_trigger(tmp_path: pathlib.Path) -> None:
    """tick 循环真实触发：interval 到点 → turn_start 起一轮 → notice/schedule fired 上通知流。"""
    server, notes = _server(tmp_path)
    ctx = _ctx()

    async def run() -> None:
        thread_id = (await server.thread_create({"title": "t"}, ctx))["thread"]["id"]
        await server.schedule_create(
            {
                "trigger_kind": "interval",
                "interval_seconds": 1,
                "thread_id": thread_id,
                "prompt": "beep",
            },
            ctx,
        )
        driver = LongRunDriver(server, tick_seconds=0.05)
        await driver.start()
        try:
            # 等待窗 10s：全量套件高负载下 tick 会延后，不拿紧时限赌调度（宁慢勿飘）
            for _ in range(200):
                await asyncio.sleep(0.05)
                if any(
                    n.method == "notice/schedule" and n.params["outcome"] == "fired" for n in notes
                ):
                    break
        finally:
            await driver.stop()
            # fired 通知在起轮时就发（turn_start 即刻返回）；断言终态前先等在飞的 run 跑完
            await server.wait_idle()

        assert any(n.method == "notice/schedule" and n.params["outcome"] == "fired" for n in notes)
        runs = load_thread(thread_id).runs
        assert len(runs) >= 1
        assert runs[-1].status.value == "completed"

    asyncio.run(run())


def test_drive_goal_runs_rounds_to_completion(tmp_path: pathlib.Path) -> None:
    """Goal 自驱闭环：每轮 round_instruction 起一轮 run、record_round 记账。

    到 max_rounds 自动 completed。
    """
    server, notes = _server(tmp_path, turns=4)
    ctx = _ctx()

    async def run() -> None:
        thread_id = (await server.thread_create({"title": "t"}, ctx))["thread"]["id"]
        g = orch_goal.create_goal(thread_id=thread_id, objective="loop it", max_rounds=2)
        orch_goal.start_goal(g.id)
        driver = LongRunDriver(server, tick_seconds=3600.0)

        await driver.drive_goal(g.id)

        after = orch_goal.get_goal(g.id)
        assert after.round_count == 2
        assert after.status.value == "completed"
        assert len(load_thread(thread_id).runs) == 2
        assert any(n.method == "goal/status" and n.params["status"] == "completed" for n in notes)

    asyncio.run(run())


def test_driver_start_picks_up_running_goal(tmp_path: pathlib.Path) -> None:
    """重启接管：driver.start() 必须扫出 RUNNING 状态的 Goal 并继续自驱（长跑断电恢复语义）。"""
    server, _notes = _server(tmp_path, turns=4)
    ctx = _ctx()

    async def run() -> None:
        thread_id = (await server.thread_create({"title": "t"}, ctx))["thread"]["id"]
        g = orch_goal.create_goal(thread_id=thread_id, objective="resume me", max_rounds=1)
        orch_goal.start_goal(g.id)
        driver = LongRunDriver(server, tick_seconds=3600.0)
        await driver.start()
        try:
            for _ in range(100):
                await asyncio.sleep(0.05)
                if orch_store.load_view().goals[0].status.value == "completed":
                    break
        finally:
            await driver.stop()

        assert orch_goal.get_goal(g.id).status.value == "completed"

    asyncio.run(run())
