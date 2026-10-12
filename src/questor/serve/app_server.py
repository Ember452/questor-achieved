"""qst-app-server 会话层雏形（M2.3）：方法表 + 一条 run 的生命周期。

本期范围克制到能验接口：`initialize` / `thread/create` / `thread/list` / `turn/start` /
`run/stop`。协议版本**严格相等不降级**（B-60）；反向请求通道 `approval/request` 随 M3
habena 一起做（本期无消费者，不做无消费者的形状，见 ADR-0020 的取舍口径）。

刻意不做的事：WS/SSE 传输属 M3（同方法表、另一种传输），本模块只认 NDJSON 行；
文件与网络 IO 全部经内核模块的单点（gesta/state），不在这里另开一条路。
"""

from __future__ import annotations

import asyncio
import logging
import platform
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from questor.capability import FeatureFlags
from questor.engine import Engine
from questor.engine.loop import TurnRequest
from questor.gesta import create_thread, list_threads
from questor.schemas.model import PermissionMode, Thread, utc_timestamp_now
from questor.serve.dispatch import Dispatcher, Handler, HandlerCtx
from questor.serve.envelope import Notification
from questor.serve.notifications import notification_of
from questor.version import build_commit, questor_version

__all__ = ["PROTOCOL_NAME", "AppServer", "build_dispatcher"]

logger = logging.getLogger(__name__)

PROTOCOL_NAME = "qst-app-server/v0.1"
#: 本期支持的内置引擎（外部适配器随 M6 engine/adapters 加入）
BUILTIN_ENGINE_ID = "questor-engine"


def _local_principal() -> str:
    """本机归属的默认表示。拿不到主机名时写 `local-user`，**不拿用户名当凭据**：
    本期它只是传递与回显用的标识，不是鉴权根据（ADR-0020）。"""
    return platform.node() or "local-user"


@dataclass
class AppServer:
    """一台机器上一个会话层的运行态：引擎工厂 + 在飞的 run + 已协商能力。"""

    create_engine: Callable[[str, PermissionMode], Engine]
    principal: str = field(default_factory=_local_principal)
    feature_flags: FeatureFlags = field(default_factory=FeatureFlags)
    max_concurrency: int = 2
    issues: tuple[str, ...] = ()
    _runs: dict[str, asyncio.Task[None]] = field(default_factory=dict, repr=False)
    #: 输出汇：通知的对外出口，由 `build_dispatcher` 接上
    _notify: Callable[[Notification], None] | None = None

    def build_dispatcher(
        self, *, notify: Callable[[Notification], None] | None = None
    ) -> Dispatcher:
        self._notify = notify
        dispatcher = Dispatcher(notify=self._publish)
        for name in self._methods():
            dispatcher.register(name, self._handler(name))
        return dispatcher

    def _publish(self, notification: Notification) -> None:
        """通知只有一个出口：有回调就交出去（stdio 层负责写与刷新）。"""
        if self._notify is not None:
            self._notify(notification)

    # ---- 方法表 ----

    def _methods(self) -> tuple[str, ...]:
        return (
            "initialize",
            "thread/create",
            "thread/list",
            "turn/start",
            "run/stop",
        )

    def _handler(self, method: str) -> Handler:
        handlers: dict[str, Handler] = {
            "initialize": self.initialize,
            "thread/create": self.thread_create,
            "thread/list": self.thread_list,
            "turn/start": self.turn_start,
            "run/stop": self.run_stop,
        }
        return handlers[method]

    async def initialize(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        """握手：版本严格相等；`needs_setup` 时连接仍可用（问题列在 issues）。"""
        client_version = str(params.get("protocol_version", ""))
        if client_version and client_version != PROTOCOL_NAME:
            raise ValueError(
                f"协议版本不匹配：客户端 {client_version!r}，服务端 {PROTOCOL_NAME!r}（不降级兼容）"
            )
        capabilities = params.get("capabilities") or {}
        return {
            "protocol_version": PROTOCOL_NAME,
            "status": "needs_setup" if self.issues else "ready",
            "issues": list(self.issues),
            "build": {"version": questor_version(), "commit": build_commit()},
            "host": {"os": platform.system().lower(), "arch": platform.machine().lower()},
            "principal": ctx.principal or self.principal,
            "threads": [summary.id for summary in list_threads()],
            "permissions": {"mode": ctx.permission_mode.value, "sandboxed": False},
            "engines": [{"id": BUILTIN_ENGINE_ID, "status": "ready"}],
            "feature_flags": list(self.feature_flags.enabled_names()),
            "max_concurrency": self.max_concurrency,
            "methods": list(self._methods()),
            "notification_families": [
                "delta",
                "item/started",
                "item/completed",
                "turn/usage",
                "run/status",
                "notice/compact",
            ],
            "client_capabilities": capabilities if isinstance(capabilities, dict) else {},
        }

    async def thread_create(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        del ctx
        workspace_id = params.get("workspace_id")
        if not isinstance(workspace_id, str) or not workspace_id:
            raise ValueError("thread/create 缺少必需字段 workspace_id")
        thread = Thread(
            id=str(params.get("id") or f"thread-{uuid.uuid4().hex[:12]}"),
            workspace_id=workspace_id,
            title=params.get("title"),
            engine_id=str(params.get("engine_id", BUILTIN_ENGINE_ID)),
            permission_mode=PermissionMode(str(params.get("permission_mode", "standard"))),
            pinned=False,
            archived=False,
            created_at=utc_timestamp_now(),
            updated_at=utc_timestamp_now(),
        )
        view = create_thread(thread)
        return {"thread": view.thread.model_dump(mode="json")}

    async def thread_list(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        del params
        return {
            "threads": [summary.model_dump(mode="json") for summary in list_threads()],
            "principal": ctx.principal or self.principal,
        }

    async def turn_start(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        """起一轮 run：响应立即返回，事件以通知流出（客户端须持续读通知）。"""
        thread_id = str(params.get("thread_id", ""))
        text = str(params.get("user_text", ""))
        if not thread_id or not text:
            raise ValueError("turn/start 需要 thread_id 与 user_text")
        engine = self.create_engine(thread_id, ctx.permission_mode)
        request = TurnRequest(
            thread_id=thread_id, user_text=text, resume=bool(params.get("resume", False))
        )
        task = asyncio.create_task(self._pump(engine, request, thread_id))
        self._runs[thread_id] = task
        # B-01：_pump 不是分发器跟踪的任务（它在响应之后还要跑很久），所以强引用由
        # `self._runs` 持有，异常在此观察——不写这一句就会被 GC 静默吞掉
        task.add_done_callback(lambda done, key=thread_id: self._pump_done(key, done))
        return {"thread_id": thread_id, "accepted": True, "origin": "user"}

    def _pump_done(self, thread_id: str, task: asyncio.Task[None]) -> None:
        self._runs.pop(thread_id, None)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.exception("线程 %s 的 run 异常结束", thread_id, exc_info=error)

    async def wait_idle(self) -> None:
        """等所有在飞的 run 结束（宿主、测试与干净退出用）。"""
        pending = [task for task in self._runs.values() if not task.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _pump(self, engine: Engine, request: TurnRequest, thread_id: str) -> None:
        del thread_id
        async for event in engine.run_turn(request):
            notification = notification_of(event)
            if notification is not None:
                self._publish(notification)

    async def run_stop(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        """取消传播：取消生成器任务 → 内核清理 → cancelled 终态（engine 侧已实现）。"""
        del ctx
        thread_id = str(params.get("thread_id", ""))
        task = self._runs.pop(thread_id, None)
        if task is None:
            raise ValueError(f"线程 {thread_id!r} 没有在飞的 run")
        task.cancel()
        return {"thread_id": thread_id, "cancelling": True}


def build_dispatcher(
    create_engine: Callable[[str, PermissionMode], Engine],
    *,
    notify: Callable[[Notification], None] | None = None,
    principal: str | None = None,
    feature_flags: FeatureFlags | None = None,
    issues: tuple[str, ...] = (),
) -> Dispatcher:
    """装配点用的便捷入口：构造会话层并返回登记好方法的分发器。"""
    server = AppServer(
        create_engine=create_engine,
        principal=principal or _local_principal(),
        feature_flags=feature_flags or FeatureFlags(),
        issues=issues,
    )
    return server.build_dispatcher(notify=notify)
