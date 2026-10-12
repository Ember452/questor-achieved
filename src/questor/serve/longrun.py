"""长跑驱动：宿主生命周期里把 vigilia/orchestration 从"库"变成"在跑的东西"。

M4 计划 M4e.2 的启动 hook 落点。三件事，都不重新发明领域逻辑：

- **tick 循环**：周期驱动 `Scheduler.tick`；触发器到点按 `thread_id`+`prompt` 起一轮
  （`turn/start` 的同一入口，模型提议/工具裁决纪律不因后台而绕行）；
- **双 reconcile**（B-44）：启动时一次性全量收"落盘 running 而本进程无活体"的僵尸 run，
  之后一批一间隔带游标清扫（B-40）；本进程在跑的线程绝不碰——运行态真值优先；
- **Goal 轮自驱**：对 RUNNING 的 Goal 逐轮下发 `round_instruction`、轮末 `record_round`
  记账，到 `max_rounds`/deadline/`goal/stop` 即停。

边界：M4 的 `schedule/create` 只允许 thread_id+prompt 目标，task 派发随 M5；驱动挂在
http 宿主（`serve http` 的长跑形态），stdio sidecar 不挂——`goal/start` 在未接驱动的
宿主只登记状态，不假装在驱（诚实呈现）。
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging

from questor.gesta import InvalidTransition, load_thread
from questor.gesta.store import ThreadStoreError, list_threads, transition_run
from questor.orchestration import goal as orch_goal
from questor.orchestration import store as orch_store
from questor.orchestration import tasks as orch_tasks
from questor.orchestration.transitions import InvalidTaskTransition
from questor.schemas.model import RunStatus, utc_timestamp_now
from questor.schemas.vigilia import ScheduleTrigger
from questor.serve.app_server import AppServer
from questor.serve.dispatch import HandlerCtx
from questor.serve.envelope import Notification
from questor.vigilia import Scheduler, StaleSweeper
from questor.vigilia.constants import DEFAULT_TICK_SECONDS
from questor.vigilia.store import VigiliaStoreError

__all__ = ["LongRunDriver"]

logger = logging.getLogger(__name__)

#: 落盘在这些状态即为"非终态 run"；宿主重启后它们没有活体 = 僵尸（B-44 的候选集）
_STALE_STATUSES = frozenset(
    {RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.STEERED, RunStatus.WAITING}
)
#: thread/run 复合键分隔符：两类 id 都不含 "/"（uuid 段），partition 一次即分干净
_SEP = "/"


class LongRunDriver:
    """tick 循环 + 双 reconcile + Goal 轮驱动的宿主件（挂在 `serve http` 生命周期上）。"""

    def __init__(
        self,
        server: AppServer,
        *,
        tick_seconds: float = DEFAULT_TICK_SECONDS,
        scheduler: Scheduler | None = None,
        sweeper: StaleSweeper | None = None,
    ) -> None:
        self._server = server
        self._tick_seconds = tick_seconds
        self._scheduler = scheduler if scheduler is not None else Scheduler()
        self._sweeper = sweeper if sweeper is not None else StaleSweeper()
        self._tick_task: asyncio.Task[None] | None = None
        self._goal_tasks: dict[str, asyncio.Task[None]] = {}

    # ---- 生命周期 ----

    async def start(self) -> None:
        """启动：登记唤醒位 → 启动全量 reconcile（B-44）→ tick 循环 → 拾取在跑的 Goal。"""
        if self._tick_task is not None:
            return
        self._server.goal_waker = self.wake_goal
        await asyncio.to_thread(self.reconcile_startup)
        self._tick_task = asyncio.create_task(self._loop())
        view = await asyncio.to_thread(orch_store.load_view)
        for goal in view.goals:
            if goal.status is orch_goal.GoalStatus.RUNNING:
                self.wake_goal(goal.id)

    async def stop(self) -> None:
        """停止：tick 与轮任务取消后收干净（run 本体不动——它归 dispatcher 的在飞表管）。"""
        if self._tick_task is not None:
            self._tick_task.cancel()
            await asyncio.gather(self._tick_task, return_exceptions=True)
            self._tick_task = None
        tasks = list(self._goal_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._goal_tasks.clear()
        if self._server.goal_waker is self.wake_goal:
            self._server.goal_waker = None

    # ---- tick ----

    async def _loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._tick_seconds)
                outcomes = await self._scheduler.tick(dt.datetime.now(dt.UTC), self._fire)
                for outcome in outcomes:
                    self._server.publish(
                        Notification(
                            "notice/schedule",
                            {
                                "schedule_id": outcome.trigger_id,
                                "kind": outcome.kind,
                                "outcome": outcome.outcome,
                            },
                        )
                    )
                await asyncio.to_thread(self.sweep_once)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 守护循环不能被单次异常带走，但要留痕
            logger.exception("长跑 tick 循环异常退出（驱动停摆，需重启宿主）")

    async def _fire(self, trigger: ScheduleTrigger) -> None:
        """到点动作：task 目标→派发任务；thread 目标→起一轮。

        目标不合法/线程不存在 → 异常上浮，由调度器如实标 skipped（不谎报 fired）。
        """
        if trigger.task_id is not None:
            await self._fire_task(trigger)
            return
        if not trigger.thread_id or not trigger.prompt:
            raise VigiliaStoreError(f"触发目标缺 thread_id+prompt 或 task_id：{trigger.id}")
        await self._server.turn_start(
            {"thread_id": trigger.thread_id, "user_text": trigger.prompt},
            self._ctx(f"vigilia-{trigger.id}"),
        )

    async def _fire_task(self, trigger: ScheduleTrigger) -> None:
        """到点派发任务（M5，ADR-0029）：先把任务推进到 executing，再在其线程起一轮。

        调度的建立即用户对"到点跑这个任务"的预先授权，故此处直走领域函数 `tasks.start_task`
        （不经 service 的逐次授权门）；任务已 reviewed/completed 等不可迁移态则跳过 start，
        但仍下发本轮指令（幂等，一次调度不因子状态重复报错）。
        """
        task = await asyncio.to_thread(orch_tasks.get_task, trigger.task_id or "")
        if not task.thread_id:
            raise VigiliaStoreError(
                f"任务 {trigger.task_id} 无所属线程，到点无法派发：{trigger.id}"
            )
        with contextlib.suppress(InvalidTaskTransition):
            await asyncio.to_thread(orch_tasks.start_task, task.id)
        await self._server.turn_start(
            {"thread_id": task.thread_id, "user_text": trigger.prompt or task.title},
            self._ctx(f"vigilia-task-{trigger.id}"),
        )

    # ---- Goal 轮自驱 ----

    def wake_goal(self, goal_id: str) -> None:
        """唤醒一个 Goal 的轮循环（幂等：已在驱则不重复起任务）。"""
        task = self._goal_tasks.get(goal_id)
        if task is not None and not task.done():
            return
        self._goal_tasks[goal_id] = asyncio.create_task(self.drive_goal(goal_id))

    async def drive_goal(self, goal_id: str) -> None:
        """逐轮自驱：非 RUNNING 即停；deadline → failed；轮失败 → failed 并停止。

        轮与轮之间等 `wait_thread_idle`——同一 Goal 不叠轮（并发上限的第一道）。
        """
        while True:
            goal = await asyncio.to_thread(orch_goal.get_goal, goal_id)
            if goal.status is not orch_goal.GoalStatus.RUNNING:
                return
            if orch_goal.is_expired(goal, utc_timestamp_now()):
                moved = await asyncio.to_thread(orch_goal.fail_goal, goal_id)
                self._server.publish_goal(moved)
                return
            text = orch_goal.round_instruction(goal)
            try:
                await self._server.turn_start(
                    {"thread_id": goal.thread_id, "user_text": text}, self._ctx(f"goal-{goal_id}")
                )
                await self._server.wait_thread_idle(goal.thread_id)
                after = await asyncio.to_thread(orch_goal.record_round, goal_id)
            except orch_store.OrchestrationStoreError:
                # 轮中被 goal/stop：record_round 的白名单裁决即"诚实收尾"，停驱不追问
                return
            except Exception:  # noqa: BLE001 - 起轮失败不静默续跑，转 failed 并上浮观测面
                logger.warning("Goal %s 起轮失败，迁移 failed", goal_id, exc_info=True)
                try:
                    moved = await asyncio.to_thread(orch_goal.fail_goal, goal_id)
                except orch_store.OrchestrationStoreError:
                    return
                self._server.publish_goal(moved)
                return
            self._server.publish_goal(after)

    # ---- 清扫与 reconcile（同步落盘 IO，由调用侧 to_thread 包裹）----

    def reconcile_startup(self) -> None:
        """启动 reconcile（B-44）：重启后一次性收掉当前全部非终态僵尸 run，游标归零。"""
        result = self._sweeper.startup_reconcile(self._collect_stale())
        for token in result.reconciled:
            self._reconcile_run(token)

    def sweep_once(self) -> None:
        """周期清扫：一批一间隔 + 游标分批（B-40），只收非活体。"""
        result = self._sweeper.sweep(self._collect_stale())
        for token in result.reconciled:
            self._reconcile_run(token)

    def _collect_stale(self) -> list[str]:
        """候选集 = 落盘非终态、且所属线程在本进程没有活体 run。"""
        live = self._server.active_thread_ids()
        tokens: list[str] = []
        for summary in list_threads():
            if summary.id in live:
                continue
            try:
                view = load_thread(summary.id)
            except ThreadStoreError:
                continue  # 竞态删除：候选集读不到就跳过，不臆造
            tokens.extend(
                f"{summary.id}{_SEP}{run.id}" for run in view.runs if run.status in _STALE_STATUSES
            )
        return tokens

    def _reconcile_run(self, token: str) -> None:
        """判终止：queued→cancelled；running→failed；旁态先回 running 再 failed（全走白名单）。"""
        thread_id, _, run_id = token.partition(_SEP)
        try:
            view = load_thread(thread_id)
        except ThreadStoreError:
            return
        run = next((r for r in view.runs if r.id == run_id), None)
        if run is None or run.status not in _STALE_STATUSES:
            return
        try:
            if run.status is RunStatus.QUEUED:
                transition_run(thread_id, run_id, RunStatus.CANCELLED)
            else:
                if run.status in (RunStatus.STEERED, RunStatus.WAITING):
                    transition_run(thread_id, run_id, RunStatus.RUNNING)
                transition_run(thread_id, run_id, RunStatus.FAILED)
        except (InvalidTransition, ThreadStoreError):
            logger.warning(
                "reconcile run %s 被白名单拒绝（状态已被并发推进），跳过", run_id, exc_info=True
            )

    def _ctx(self, request_id: str) -> HandlerCtx:
        """驱动发起的请求上下文：principal 沿用宿主本机标识，trace_id 可追。"""
        return HandlerCtx(
            request_id=request_id, principal=self._server.principal, trace_id=request_id
        )
