"""qst-app-server 会话层雏形（M2.3）：方法表 + 一条 run 的生命周期。

本期范围克制到能验接口：`initialize` / `thread/create` / `thread/list` / `turn/start` /
`run/stop`。协议版本**严格相等不降级**（B-60）；反向请求通道 `approval/request` 随 M3
habena 一起做（本期无消费者，不做无消费者的形状，见 ADR-0020 的取舍口径）。

刻意不做的事：WS/SSE 传输属 M3（同方法表、另一种传输），本模块只认 NDJSON 行；
文件与网络 IO 全部经内核模块的单点（gesta/state），不在这里另开一条路。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import platform
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from questor.capability import FeatureFlags
from questor.engine import Engine
from questor.engine.loop import TurnRequest
from questor.gesta import (
    ThreadNotFound,
    ThreadStoreError,
    create_thread,
    delete_thread,
    list_threads,
    load_thread,
    rename_thread,
    set_thread_flags,
)
from questor.gesta.writer import ThreadWriter
from questor.habena import ControlError, HabenaInbox, SessionControl
from questor.review import aggregate_turn_diff
from questor.schemas.habena import SteerMessage
from questor.schemas.model import PermissionMode, Thread, utc_timestamp_now
from questor.serve.dispatch import Dispatcher, Handler, HandlerCtx
from questor.serve.envelope import Notification, ProtocolError
from questor.serve.fanout import Fanout
from questor.serve.notifications import notification_of
from questor.sessiontrace import project_thread, project_turn
from questor.state.paths import thread_path
from questor.version import build_commit, questor_version
from questor.workspaces import (
    current_revision,
    get_workspace,
    is_within_workspace,
    list_workspaces,
)
from questor.workspaces import (
    register as register_workspace,
)
from questor.worktree import WorktreeError, add_worktree, worktree_root

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
    #: 输出汇：旧单一 callback 保留为测试钩子；新多宿主走 _fanout
    _notify: Callable[[Notification], None] | None = None
    #: M3a-3 插话队列与接管栅栏（同线程 lazily 建）
    _inboxes: dict[str, HabenaInbox] = field(default_factory=dict, repr=False)
    _controls: dict[str, SessionControl] = field(default_factory=dict, repr=False)
    #: M3a-3 多宿主扇出：stdio/WS/未来的 IM 渠道都从同一 Fanout 领订阅
    fanout: Fanout = field(default_factory=Fanout, repr=False)

    def build_dispatcher(
        self, *, notify: Callable[[Notification], None] | None = None
    ) -> Dispatcher:
        self._notify = notify
        dispatcher = Dispatcher(notify=self._publish)
        for name in self._methods():
            dispatcher.register(name, self._handler(name))
        return dispatcher

    def _publish(self, notification: Notification) -> None:
        """通知只有一个入口：先给 fanout（多宿主），再给旧 _notify（测试/单元断言用）。"""
        self.fanout.publish(notification)
        if self._notify is not None:
            self._notify(notification)

    # ---- 方法表 ----

    def _methods(self) -> tuple[str, ...]:
        return (
            "initialize",
            "thread/create",
            "thread/list",
            "thread/rename",
            "thread/archive",
            "thread/delete",
            "thread/show",
            "thread/fork",
            "turn/start",
            "turn/steer",
            "turn/queue",
            "turn/dequeue",
            "run/stop",
            "session/control",
            "review/turn_diff",
            "files/read",
            "files/list",
            "content/read",
            "workspace/status",
            "workspace/revision",
            "sessiontrace/get",
        )

    def _handler(self, method: str) -> Handler:
        handlers: dict[str, Handler] = {
            "initialize": self.initialize,
            "thread/create": self.thread_create,
            "thread/list": self.thread_list,
            "thread/rename": self.thread_rename,
            "thread/archive": self.thread_archive,
            "thread/delete": self.thread_delete,
            "thread/show": self.thread_show,
            "thread/fork": self.thread_fork,
            "turn/start": self.turn_start,
            "turn/steer": self.turn_steer,
            "turn/queue": self.turn_queue,
            "turn/dequeue": self.turn_dequeue,
            "run/stop": self.run_stop,
            "session/control": self.session_control,
            "review/turn_diff": self.review_turn_diff,
            "files/read": self.files_read,
            "files/list": self.files_list,
            "content/read": self.content_read,
            "workspace/status": self.workspace_status,
            "workspace/revision": self.workspace_revision,
            "sessiontrace/get": self.sessiontrace_get,
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
        # M3a-3：把插话队列挂到 engine（B-67/94 消费点在 iteration 起点）
        engine.attach_inbox(self._inbox_for(thread_id))
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
        """取消传播：取消生成器任务→ 内核清理→ cancelled 终态（engine 侧已实现）。"""
        del ctx
        thread_id = str(params.get("thread_id", ""))
        task = self._runs.pop(thread_id, None)
        if task is None:
            raise ValueError(f"线程 {thread_id!r} 没有在飞的 run")
        task.cancel()
        return {"thread_id": thread_id, "cancelling": True}

    # ---- 插话与接管（M3a-3）----

    def _inbox_for(self, thread_id: str) -> HabenaInbox:
        """lazily 建线程的插话队列；首次建时从已落盘的 held_work 重建（B-65 rehold）。"""
        existing = self._inboxes.get(thread_id)
        if existing is not None:
            return existing
        writer = ThreadWriter(thread_id)
        view = writer.open()
        inbox = HabenaInbox(writer)
        inbox.preload_from_view(view.held_work)
        self._inboxes[thread_id] = inbox
        return inbox

    def _control_for(self, thread_id: str) -> SessionControl:
        control = self._controls.get(thread_id)
        if control is None:
            control = SessionControl()
            self._controls[thread_id] = control
        return control

    async def _submit_steer(
        self, params: dict[str, Any], ctx: HandlerCtx, *, origin: str
    ) -> dict[str, Any]:
        """turn/steer 与 turn/queue 共用提交路径（origin 不同）。"""
        thread_id = str(params.get("thread_id", ""))
        client_id = str(params.get("client_id", ""))
        content = str(params.get("content", ""))
        if not thread_id or not client_id or not content:
            raise ValueError(f"turn/{origin} 需要 thread_id / client_id / content")
        expected_turn_id_raw = params.get("expected_turn_id")
        expected_turn_id = str(expected_turn_id_raw) if expected_turn_id_raw else None
        inbox = self._inbox_for(thread_id)
        # B-64：expected_turn_id 非空且不匹配当前活跃 turn 时拒（旧客户端传 None 兼容放行）
        if expected_turn_id is not None:
            view = await asyncio.to_thread(load_thread, thread_id)
            current_turn = view.turns[-1].id if view.turns else None
            if current_turn != expected_turn_id:
                raise ProtocolError(
                    "stale_revision",
                    f"expected_turn_id={expected_turn_id!r} 与当前 turn {current_turn!r} 不匹配",
                    model_next_action="re-read the active turn and retry",
                )
        msg = SteerMessage(
            thread_id=thread_id,
            client_id=client_id,
            origin=origin,  # type: ignore[arg-type]
            content=content,
            created_at=utc_timestamp_now(),
            expected_turn_id=expected_turn_id,
        )
        accepted = await inbox.submit(msg)  # 同 client_id 已见 → False，不新开
        del ctx  # handler 签名统一 (params, ctx)；本函数不用 ctx 字段
        return {"thread_id": thread_id, "accepted": accepted}

    async def turn_steer(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        return await self._submit_steer(params, ctx, origin="steer")

    async def turn_queue(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        return await self._submit_steer(params, ctx, origin="queue")

    async def turn_dequeue(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        """从幂等表里丢弃 client_id；已入队的消息本期不反向删（M4 逐条撤）。"""
        del ctx
        thread_id = str(params.get("thread_id", ""))
        client_id = str(params.get("client_id", ""))
        if not thread_id or not client_id:
            raise ValueError("turn/dequeue 需要 thread_id 与 client_id")
        inbox = self._inboxes.get(thread_id)
        if inbox is None:
            return {"removed": False}
        inbox.forget(client_id)
        return {"removed": True}

    async def session_control(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        """接管/暂停/释放：CAS + revision 栅栏，stale 不能撤销人的接管（overview §12）。"""
        del ctx
        thread_id = str(params.get("thread_id", ""))
        action = str(params.get("action", ""))
        if not thread_id or action not in ("take_over", "pause", "release"):
            raise ValueError(
                "session/control 需要 thread_id 与 action ∈ {take_over, pause, release}"
            )
        raw = params.get("expected_revision")
        expected_revision = int(raw) if raw is not None else None
        control = self._control_for(thread_id)
        try:
            state = getattr(control, action)(expected_revision)
        except ControlError as exc:
            raise ProtocolError(exc.code, exc.message) from exc
        return {"holder": state.holder, "revision": state.revision}

    async def thread_fork(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        """分叉新会话：mode=local 同目录、mode=worktree 开 worktree（M3b-2）。

        worktree 模式下先 `git worktree add` 建目录，再拿新目录的 workspace_id；
        非 git 仓库或 worktree 失败 → ProtocolError（invalid_params 面向参数、
        internal_error 面向 CLI 失败）。local 模式不碰盘。不自动回主分支（overview §6）。
        """
        del ctx
        source_thread = str(params.get("thread_id", ""))
        mode = str(params.get("mode", "local"))
        if not source_thread:
            raise ValueError("thread/fork 需要 thread_id")
        if mode not in ("local", "worktree"):
            raise ValueError(f"未知 fork mode: {mode!r}")
        view = await asyncio.to_thread(load_thread, source_thread)
        new_thread_id = str(params.get("new_thread_id") or f"thread-{uuid.uuid4().hex[:12]}")
        if mode == "worktree":
            source_ws = get_workspace(view.thread.workspace_id)
            if source_ws is None:
                raise ProtocolError("invalid_params", "源 workspace 未注册")
            repo_root = Path(source_ws.root_paths[0])
            target = worktree_root(new_thread_id, repo_root)
            branch = f"qst/{new_thread_id}"
            try:
                await asyncio.to_thread(add_worktree, repo_root, branch=branch, path=target)
            except WorktreeError as exc:
                raise ProtocolError("internal_error", str(exc)) from exc
            new_workspace = await asyncio.to_thread(register_workspace, target)
            new_workspace_id = new_workspace.id
        else:
            new_workspace_id = str(params.get("workspace_id") or view.thread.workspace_id)
        thread = Thread(
            id=new_thread_id,
            workspace_id=new_workspace_id,
            title=view.thread.title,
            engine_id=view.thread.engine_id,
            permission_mode=view.thread.permission_mode,
            pinned=False,
            archived=False,
            created_at=utc_timestamp_now(),
            updated_at=utc_timestamp_now(),
        )
        created = await asyncio.to_thread(create_thread, thread)
        return {"thread": created.thread.model_dump(mode="json"), "mode": mode}

    # ---- 会话操作（M3b-1）----

    async def thread_rename(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        del ctx
        thread_id = str(params.get("thread_id", ""))
        title = params.get("title")
        if not thread_id:
            raise ValueError("thread/rename 需要 thread_id")
        thread = await asyncio.to_thread(
            rename_thread, thread_id, str(title) if title is not None else None
        )
        return {"thread": thread.model_dump(mode="json")}

    async def thread_archive(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        del ctx
        thread_id = str(params.get("thread_id", ""))
        if not thread_id:
            raise ValueError("thread/archive 需要 thread_id")
        archived = bool(params.get("archived", True))
        try:
            thread = await asyncio.to_thread(set_thread_flags, thread_id, archived=archived)
        except (ThreadNotFound, ThreadStoreError) as exc:
            # 归档遇活跃 run 抛 ThreadStoreError → 业务错（非信封层参数失败）
            raise ProtocolError("invalid_params", str(exc)) from exc
        return {"thread": thread.model_dump(mode="json")}

    async def thread_delete(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        del ctx
        thread_id = str(params.get("thread_id", ""))
        if not thread_id:
            raise ValueError("thread/delete 需要 thread_id")
        # 先拒在飞 run（_runs 内存项），再交给 delete_thread 拒未终态 run（落盘项）
        if thread_id in self._runs:
            raise ProtocolError(
                "invalid_params",
                f"线程 {thread_id!r} 有在飞 run，先 run/stop 再删",
                model_next_action="call run/stop first, then thread/delete",
            )
        try:
            await asyncio.to_thread(delete_thread, thread_id)
        except (ThreadNotFound, ThreadStoreError) as exc:
            raise ProtocolError("invalid_params", str(exc)) from exc
        return {"deleted": True}

    async def thread_show(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        del ctx
        thread_id = str(params.get("thread_id", ""))
        if not thread_id:
            raise ValueError("thread/show 需要 thread_id")
        try:
            view = await asyncio.to_thread(load_thread, thread_id)
        except ThreadNotFound as exc:
            raise ProtocolError("invalid_params", str(exc)) from exc
        return {
            "thread": view.thread.model_dump(mode="json"),
            "turns": [t.model_dump(mode="json") for t in view.turns],
            "items": [i.model_dump(mode="json") for i in view.items],
            "events": [e.model_dump(mode="json") for e in view.events],
        }

    # ---- 工作台数据面（M3a-2）----

    async def review_turn_diff(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        del ctx
        thread_id = str(params.get("thread_id", ""))
        turn_id = str(params.get("turn_id", ""))
        if not thread_id or not turn_id:
            raise ValueError("review/turn_diff 需要 thread_id 与 turn_id")
        try:
            view = await asyncio.to_thread(load_thread, thread_id)
        except ThreadNotFound as exc:
            raise ProtocolError("invalid_params", str(exc)) from exc
        return {"diffs": aggregate_turn_diff(view, turn_id)}

    async def files_read(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        path = str(params.get("path", ""))
        if not path:
            raise ValueError("files/read 需要 path")
        workspace_id = str(params.get("workspace_id") or ctx.workspace_id or "")
        if not workspace_id:
            raise ValueError("files/read 需要 workspace_id（params 或 ctx）")
        workspace = get_workspace(workspace_id)
        if workspace is None:
            raise ProtocolError("invalid_params", f"未注册 workspace: {workspace_id}")
        target = Path(path).expanduser().resolve()
        if not is_within_workspace(target, workspace):
            raise ProtocolError(
                "boundary_denied",
                f"path {path!r} 不在 workspace 注册根内",
                model_next_action="use a path under the registered workspace roots",
            )
        current = workspace.revision
        expected = params.get("expected_revision")
        if expected is not None and int(expected) != current:
            raise ProtocolError(
                "stale_revision",
                f"expected_revision={expected} 不匹配当前 {current}",
                model_next_action=f"re-read the file at revision {current}",
            )
        try:
            content = await asyncio.to_thread(
                lambda t: t.read_text(encoding="utf-8", errors="replace"), target
            )
        except FileNotFoundError as exc:
            raise ProtocolError("invalid_params", f"文件不存在: {path}") from exc
        fingerprint = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:16]
        return {"content": content, "revision": current, "content_fingerprint": fingerprint}

    async def files_list(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        sub = str(params.get("path", "."))
        workspace_id = str(params.get("workspace_id") or ctx.workspace_id or "")
        if not workspace_id:
            raise ValueError("files/list 需要 workspace_id")
        workspace = get_workspace(workspace_id)
        if workspace is None:
            raise ProtocolError("invalid_params", f"未注册 workspace: {workspace_id}")
        root = Path(workspace.root_paths[0]).expanduser().resolve()
        target = (root / sub).resolve() if sub != "." else root
        if not is_within_workspace(target, workspace):
            raise ProtocolError("boundary_denied", f"路径 {sub!r} 越出 workspace 根")
        recursive = bool(params.get("recursive", False))
        entries = await asyncio.to_thread(_list_entries_sync, target, recursive)
        return {"entries": entries, "revision": current_revision(workspace_id)}

    async def content_read(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        """从会话目录里的 spill 文件读回工具结果全文（B-24 反查）。"""
        del ctx
        thread_id = str(params.get("thread_id", ""))
        tool_use_id = str(params.get("tool_use_id", ""))
        if not thread_id or not tool_use_id:
            raise ValueError("content/read 需要 thread_id 与 tool_use_id")
        offset = int(params.get("offset") or 0)
        limit = int(params.get("limit") or 65536)
        session_root = thread_path(thread_id).parent
        spill = session_root / f"{tool_use_id}.txt"
        if not spill.is_file():
            raise ProtocolError("invalid_params", f"未找到 spill: {tool_use_id}")
        text = await asyncio.to_thread(lambda: spill.read_text(encoding="utf-8", errors="replace"))
        window = text[offset : offset + limit]
        truncated = offset + len(window) < len(text)
        return {
            "content": window,
            "truncated": truncated,
            "next_offset": offset + len(window) if truncated else None,
        }

    async def workspace_status(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        del ctx
        only = params.get("workspace_id")
        workspaces = list_workspaces()
        if only:
            workspaces = [w for w in workspaces if w.id == only]
        return {"workspaces": [w.model_dump(mode="json") for w in workspaces]}

    async def workspace_revision(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        del ctx
        workspace_id = str(params.get("workspace_id", ""))
        if not workspace_id:
            raise ValueError("workspace/revision 需要 workspace_id")
        try:
            rev = await asyncio.to_thread(current_revision, workspace_id)
        except Exception as exc:  # WorkspaceError 的基类在 workspaces里，用 Exception 兑接一次
            raise ProtocolError("invalid_params", str(exc)) from exc
        return {"revision": rev}

    async def sessiontrace_get(self, params: dict[str, Any], ctx: HandlerCtx) -> dict[str, Any]:
        """会话轨迹回放：按 turn 投影 items/events（不重跑工具、不联系模型）。"""
        del ctx
        thread_id = str(params.get("thread_id", ""))
        if not thread_id:
            raise ValueError("sessiontrace/get 需要 thread_id")
        turn_id = params.get("turn_id")
        try:
            view = await asyncio.to_thread(load_thread, thread_id)
        except ThreadNotFound as exc:
            raise ProtocolError("invalid_params", str(exc)) from exc
        if turn_id is not None:
            trace = project_turn(view, str(turn_id))
            if trace is None:
                raise ProtocolError("invalid_params", f"未知 turn: {turn_id}")
            return {"trace": trace.model_dump(mode="json")}
        return {"turns": [t.model_dump(mode="json") for t in project_thread(view)]}


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


#: files/list 目录遍历的条目上限（与 tools/impl/list.py 同形式，防默认无上限列大目录）
_FILES_LIST_MAX = 500


def _list_entries_sync(target: Path, recursive: bool) -> list[dict[str, Any]]:
    """列目录（同步实现，files/list 经 asyncio.to_thread 调）。"""
    if not target.is_dir():
        return []
    iterator = target.rglob("*") if recursive else target.iterdir()
    out: list[dict[str, Any]] = []
    for entry in iterator:
        is_dir = entry.is_dir()
        size = None if is_dir else entry.stat().st_size
        out.append(
            {
                "kind": "dir" if is_dir else "file",
                "path": entry.relative_to(target).as_posix(),
                "size": size,
            }
        )
        if len(out) >= _FILES_LIST_MAX:
            break
    return out
