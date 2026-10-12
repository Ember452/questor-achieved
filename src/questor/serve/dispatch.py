"""方法分发：每请求一个任务，慢操作不串行阻塞分发（B-62）；后台任务持强引用（B-01）。

**所有 handler 一律收 `HandlerCtx`**（ADR-0020）：新增上下文字段不再改每个 handler 的
签名，且 `principal` 从第一天就在结构里——M8 要对外暴露时，归属校验有地方放，不必
在已跑通的每个 handler 里插一遍（那是横切重写，不是搬运）。

`principal` 本期只做**传递与回显**：`initialize` 把它回给用户看、日志把它当 `trace_id`
的一部分（AGENTS §四 要求结构化字段带 trace_id）。**这里没有任何鉴权判定**——
本机单用户场景下它没有可拒绝的对象，写判定就是无消费者的实现。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from questor.schemas.model import PermissionMode
from questor.serve.envelope import (
    Notification,
    ProtocolError,
    ProtocolFrameError,
    Request,
    error_line,
    error_payload,
    notification_line,
    parse_line,
    response_line,
    reverse_request_line,
    try_parse_reverse_response,
)

__all__ = ["Dispatcher", "Handler", "HandlerCtx", "Writers"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandlerCtx:
    """一次请求的执行上下文（身份与定位信息都在这里面，不分枝、不猜）。"""

    request_id: str
    principal: str
    trace_id: str
    permission_mode: PermissionMode = PermissionMode.STANDARD
    client_id: str | None = None
    workspace_id: str | None = None
    thread_id: str | None = None
    #: 会话已协商的能力（opt-in 才为真，B-61 同源）
    capabilities: frozenset[str] = frozenset()


@dataclass
class Writers:
    """一次连接的输出汇（响应与通知都走这里，stdout 洁净由 stdio 层负责）。"""

    lines: list[str] = field(default_factory=list)


Handler = Callable[[dict[str, Any], HandlerCtx], Awaitable[dict[str, Any]]]


class Dispatcher:
    """协议方法表 + 分发。`register` 是唯一的登记入口，未登记的方法回 `unknown_method`。"""

    def __init__(
        self,
        *,
        notify: Callable[[Notification], None] | None = None,
        sink: Callable[[str], None] | None = None,
    ) -> None:
        self._handlers: dict[str, Handler] = {}
        self._notify = notify
        #: 行级出口（stdio 写它）：响应与通知都走这里，否则客户端永远拿不到响应
        self._sink = sink
        self._tasks: set[asyncio.Task[None]] = set()
        self.writers = Writers()
        #: 反向请求的 pending 路由表（B-59）：correlation_id → Future
        self._pending: dict[str, asyncio.Future[Any]] = {}

    # ---- 输出 ----

    def push(self, line: str) -> None:
        """一帧一行的唯一出口：先进缓冲（测试与诊断看），再交给传输层。"""
        self.writers.lines.append(line)
        if self._sink is not None:
            self._sink(line)

    def attach_sink(self, sink: Callable[[str], None]) -> None:
        """接上传输层的写函数（stdio/WS/SSE 共用同一个出口，不各写各的）。"""
        self._sink = sink

    # ---- 登记与查询 ----

    def register(self, method: str, handler: Handler) -> None:
        if method in self._handlers:
            raise ValueError(f"方法 {method!r} 已登记，不允许静默覆盖")
        self._handlers[method] = handler

    def known_methods(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def emit(self, notification: Notification) -> None:
        """推送一条通知：既走行级出口，也叫 `notify`（宿主可拿结构体而非文本）。"""
        self.push(notification_line(notification))
        if self._notify is not None:
            self._notify(notification)

    # ---- 分发 ----

    async def handle_line(self, line: str) -> str | None:
        """处理一帧。先判反向响应路由（B-59），否则当客户端上行 Request 处理。

        反向请求的响应帧形式与 Request 同带 id，但无 method——若先走 parse_line 会
        报“必须含 method”，将响应吞成无效帧；因此先给 pending 表机会。
        """
        reverse = try_parse_reverse_response(line)
        if reverse is not None:
            self._resolve_pending(*reverse)
            return None
        try:
            request = parse_line(line)
        except ProtocolFrameError as exc:
            # 帧本身坏了拿不到 id，只能用占位 id 回错——客户端不会去关联它
            return error_line("0", error_payload("invalid_params", str(exc)))
        handler = self._handlers.get(request.method)
        if handler is None:
            return error_line(
                request.id,
                error_payload(
                    "unknown_method",
                    f"未登记的方法 {request.method!r}",
                    model_next_action="call one of the methods listed by initialize",
                ),
            )
        context = _ctx_from(request)
        task = asyncio.create_task(self._run(handler, request, context))
        # B-01：强引用持有并观察异常，否则任务被 GC 中途回收且异常静默
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return None

    # ---- 反向请求（server-initiated） ----

    async def request_client(
        self, method: str, params: dict[str, Any], *, timeout: float = 300.0
    ) -> Any:
        """向客户端发起反向请求（B-59）。返回 result 或抛 ProtocolError。

        FlowCoder 300s 超时同族（B-04）：客户端失联时不能挂死循环；timeout 到期即
        报错并清理 pending 项。本期无具体审批弹窗消费方，通道先就位。
        """
        if self._sink is None:
            raise RuntimeError("Dispatcher 未 attach sink，无法发起反向请求")
        correlation_id = f"srv-{uuid.uuid4().hex[:12]}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[correlation_id] = future
        try:
            self.push(reverse_request_line(correlation_id, method, params))
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as exc:
            raise ProtocolError(
                "internal_error",
                f"反向请求 {method!r} 超时（客户端失联或拒绝回答）",
                model_next_action="check the host connection and retry",
            ) from exc
        finally:
            self._pending.pop(correlation_id, None)

    def _resolve_pending(
        self, correlation_id: str, result: dict[str, Any] | None, error: dict[str, Any] | None
    ) -> None:
        future = self._pending.get(correlation_id)
        if future is None or future.done():
            return
        if error is not None:
            code = str(error.get("code", "internal_error"))
            message = str(error.get("message", "客户端拒绝"))
            future.set_exception(ProtocolError(code, message))
        else:
            future.set_result(result or {})

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error("协议任务异常退出（trace_id 见上下文）：%s", error, exc_info=error)

    async def drain(self) -> None:
        """等所有在飞任务结束（测试与干净退出用）。"""
        if self._tasks:
            await asyncio.gather(*list(self._tasks))

    async def _run(self, handler: Handler, request: Request, context: HandlerCtx) -> None:
        try:
            result = await handler(request.params, context)
        except ProtocolError as exc:
            # 业务错先接：使用其自带 code（stale_revision / boundary_denied 等）；
            # ValueError 仍归 invalid_params，两者不能逆序否则 ProtocolError 会被后接吞。
            self.push(
                error_line(
                    request.id,
                    error_payload(exc.code, str(exc), model_next_action=exc.model_next_action),
                )
            )
            return
        except ValueError as exc:
            self.push(error_line(request.id, error_payload("invalid_params", str(exc))))
            return
        except Exception as exc:  # noqa: BLE001 - 单帧失败不能带走整条连接
            logger.exception("方法 %s 执行失败", request.method)
            self.push(error_line(request.id, error_payload("internal_error", str(exc))))
            return
        self.push(response_line(request.id, result))


def _ctx_from(request: Request) -> HandlerCtx:
    """从帧里取上下文位；缺字段用默认值，**不猜身份**（principal 由连接建立时给定）。"""
    params = request.params
    mode_raw = params.get("permission_mode")
    try:
        mode = PermissionMode(str(mode_raw)) if mode_raw else PermissionMode.STANDARD
    except ValueError:
        mode = PermissionMode.STANDARD
    return HandlerCtx(
        request_id=request.id,
        principal=str(params.get("principal", "")),
        trace_id=str(params.get("trace_id") or f"t{uuid.uuid4().hex[:8]}"),
        permission_mode=mode,
        client_id=_opt_str(params.get("client_id")),
        workspace_id=_opt_str(params.get("workspace_id")),
        thread_id=_opt_str(params.get("thread_id")),
    )


def _opt_str(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None
