"""serve 编排方法族集成（M4）：门、状态迁移、通知与错误方言的真实往返。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import NoReturn

import pytest

from questor.schemas.model import PermissionMode
from questor.serve.app_server import AppServer
from questor.serve.dispatch import HandlerCtx
from questor.serve.envelope import Notification, ProtocolError
from questor.testenv.fake_home import fake_home


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield


def _no_engine(thread_id: str, mode: PermissionMode) -> NoReturn:
    raise AssertionError("本测试不起引擎")


def _ctx() -> HandlerCtx:
    return HandlerCtx(request_id="r1", principal="local", trace_id="t1")


def _server() -> tuple[AppServer, list[Notification]]:
    server = AppServer(create_engine=_no_engine)
    notes: list[Notification] = []
    server.build_dispatcher(notify=notes.append)
    return server, notes


def test_task_create_requires_plan_then_succeeds() -> None:
    import asyncio

    server, notes = _server()
    ctx = _ctx()

    async def run() -> None:
        with pytest.raises(ProtocolError) as excinfo:
            await server.task_create({"title": "t1"}, ctx)
        assert excinfo.value.code == "need_plan_first"
        assert excinfo.value.model_next_action  # 结构化提示

        plan = await server.task_plan({"steps": [{"title": "a"}, {"title": "b"}]}, ctx)
        assert plan["plan"]["status"] == "drafting"

        created = await server.task_create({"title": "t1"}, ctx)
        assert created["task"]["status"] == "pending"
        assert any(n.method == "task/status" for n in notes)
        assert any(n.method == "plan/updated" for n in notes)

    asyncio.run(run())


def test_task_start_requires_authorization() -> None:
    import asyncio

    server, notes = _server()
    ctx = _ctx()

    async def run() -> None:
        await server.task_plan({"steps": [{"title": "a"}]}, ctx)
        created = await server.task_create({"title": "t1"}, ctx)
        task_id = created["task"]["id"]

        with pytest.raises(ProtocolError) as excinfo:
            await server.task_start({"task_id": task_id}, ctx)
        assert excinfo.value.code == "need_execution_authorization"

        started = await server.task_start({"task_id": task_id, "authorized": True}, ctx)
        assert started["task"]["status"] == "executing"

    asyncio.run(run())


def test_task_reject_chain() -> None:
    """转后台→任务总结→打回：executing → reviewed →（reject）→ executing。"""
    import asyncio

    from questor.orchestration import store
    from questor.schemas.orchestration import TaskStatus as TS

    server, notes = _server()
    ctx = _ctx()

    async def run_chain() -> None:
        await server.task_plan({"steps": [{"title": "a"}]}, ctx)
        task_id = (await server.task_create({"title": "t1"}, ctx))["task"]["id"]
        await server.task_start({"task_id": task_id, "authorized": True}, ctx)
        # 完成待审（reviewed）——任务总结卡在此状态出现；打回即 reviewed→executing
        store.transition_task(task_id, TS.REVIEWED)
        rejected = await server.task_reject({"task_id": task_id}, ctx)
        assert rejected["task"]["status"] == "executing"
        assert any(n.method == "task/status" and n.params["status"] == "executing" for n in notes)

    asyncio.run(run_chain())


def test_goal_and_evidence_methods() -> None:
    import asyncio

    server, notes = _server()
    ctx = _ctx()

    async def run() -> None:
        goal = await server.goal_create(
            {"thread_id": "thread-1", "objective": "ship it", "max_rounds": 2}, ctx
        )
        goal_id = goal["goal"]["id"]
        started = await server.goal_start({"goal_id": goal_id}, ctx)
        assert started["goal"]["status"] == "running"
        assert any(n.method == "goal/status" for n in notes)

        listed = await server.schedule_list({}, ctx)
        assert listed["schedules"] == []

        evidence = await server.evidence_get({"subject_type": "task", "subject_id": "task-1"}, ctx)
        assert evidence["evidence"] == []

    asyncio.run(run())
