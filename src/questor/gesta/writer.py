"""线程写句柄：首开一次全量 fold，此后 stat 校验 + O(1) 追加（M2.2 热路径决策）。

为什么需要句柄：模块级函数（:mod:`questor.gesta.store`）每次写都要全量重读 JSONL
定序——单发操作正确且简单；但 engine 的一轮 run 会高频追加 item/event，O(全文件)
× 每次追加是热路径瓶颈。句柄在 open() 时做**唯一一次**全量 fold，缓存
``(折叠状态, 文件字节数)``；此后每次追加：

1. 持全局 store 锁（跨进程正确性与 wuu 蓝本一致，放弃 per-thread 锁的理由见
   ``docs/architecture/modules/gesta.md``）；
2. ``stat`` 校验文件大小——一致则游标权威，直接 O(1) 追加；变大说明其他进程追加过，
   从缓存字节偏移读尾部**增量同步**（append-only 保证旧偏移前缀不变）；变小即
   append-only 被外部破坏，显式报错；
3. 追加后镜像状态与游标同批更新，索引摘要由镜像增量构造。

崩溃残尾：追加前若文件不以 ``\\n`` 结尾，以 ``\\n`` 前缀起新行——残尾留待读侧跳过
（B-74），追加永不粘接残尾。
"""

from __future__ import annotations

from typing import Any

from questor.gesta.store import (
    ThreadStoreError,
    ThreadView,
    _append_record_locked,
    _ends_with_newline,
    _FoldState,
    _make_record,
    _parse_line,
    _read_records,
    _Record,
    _summary_from_state,
    _upsert_index_entry_locked,
)
from questor.gesta.transitions import transition as _transition
from questor.schemas.context import ContextBoundary, ContextReplacements
from questor.schemas.habena import SteerMessage
from questor.schemas.model import (
    Event,
    ForkOrigin,
    Item,
    Origin,
    Run,
    RunStatus,
    Turn,
)
from questor.state.locks import store_lock
from questor.state.paths import sessions_dir, thread_path, validate_entity_id


class ThreadWriter:
    """一个线程的持锁写句柄；用法：``w = ThreadWriter(tid); view = w.open(); w.add_item(...)``。

    句柄**不是**跨进程共享对象：每个进程各自持有，跨进程一致性靠全局锁 + stat
    校验 + 增量同步三件套。句柄不持有任何打开的文件描述符。
    """

    def __init__(self, thread_id: str, *, lock_timeout: float = 60.0) -> None:
        self._thread_id = validate_entity_id(thread_id)
        self._lock_timeout = lock_timeout
        self._state: _FoldState | None = None
        self._size = 0
        self._needs_newline = False

    # ---- 生命周期 ----

    @property
    def thread_id(self) -> str:
        """句柄绑定的线程 id（spill 等上层操作需要）。"""
        return self._thread_id

    def open(self) -> ThreadView:
        """打开线程并做唯一一次全量 fold；文件不存在抛 ThreadNotFound。"""
        with store_lock(sessions_dir(), timeout=self._lock_timeout):
            path = thread_path(self._thread_id)
            state = _FoldState(self._thread_id)
            for record in _read_records(path):
                state.apply(record)
            self._state = state
            self._size = path.stat().st_size
            self._needs_newline = not _ends_with_newline(path)
            return state.build_view()

    def view(self) -> ThreadView:
        """当前镜像的只读投影（O(1)，不读盘）。"""
        return self._require_open().build_view()

    # ---- 追加操作（与 store 模块函数语义逐字一致） ----

    def add_turn(
        self,
        *,
        turn_id: str,
        origin: Origin,
        created_at: str,
        fork_from: ForkOrigin | None = None,
    ) -> Turn:
        """追加一轮对话；``Turn.seq`` 由句柄在锁内分配（B-45 单点定序）。"""
        state = self._require_open()
        with store_lock(sessions_dir(), timeout=self._lock_timeout):
            placed = Turn(
                id=turn_id,
                thread_id=self._thread_id,
                seq=len(state.turns) + 1,
                origin=origin,
                fork_from=fork_from,
                created_at=created_at,
            )
            self._append_locked(state, "turn.created", placed.model_dump(mode="json"))
            return placed

    def add_run(self, run: Run) -> Run:
        """追加一次引擎执行记录；必须以 queued 入流。"""
        state = self._require_open()
        with store_lock(sessions_dir(), timeout=self._lock_timeout):
            if run.status != RunStatus.QUEUED:
                raise ThreadStoreError("run 必须以 queued 入流，初始状态不得旁路指定")
            self._append_locked(state, "run.created", run.model_dump(mode="json"))
            return run

    def transition_run(self, run_id: str, target: RunStatus) -> Run:
        """推进运行状态：白名单裁决在落盘前爆炸，迁移记录追加进正文。"""
        state = self._require_open()
        with store_lock(sessions_dir(), timeout=self._lock_timeout):
            run = next((r for r in state.runs if r.id == run_id), None)
            if run is None:
                raise ThreadStoreError(f"线程 {self._thread_id} 没有 run {run_id}")
            moved = _transition(run.status, target)  # 白名单外抛 InvalidTransition，不落盘
            self._append_locked(
                state,
                "run.status",
                {"run_id": run_id, "from": run.status.value, "to": moved.value},
            )
            return run.model_copy(update={"status": moved})

    def add_item(self, item: Item) -> Item:
        """追加一个 Item（消息/工具调用/工具结果/引用/批注/交付物）。"""
        state = self._require_open()
        with store_lock(sessions_dir(), timeout=self._lock_timeout):
            self._append_locked(state, "item.appended", item.model_dump(mode="json"))
            return item

    def append_event(
        self,
        *,
        event_type: str,
        run_id: str,
        turn_id: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> Event:
        """追加一条对外推送事件；``Event.seq`` 由句柄分配（会话内全局递增锚点）。"""
        state = self._require_open()
        with store_lock(sessions_dir(), timeout=self._lock_timeout):
            placed = Event(
                seq=state.last_seq + 1,
                type=event_type,
                run_id=run_id,
                turn_id=turn_id,
                payload=payload,
                created_at=created_at,
            )
            self._append_locked(state, "event.appended", placed.model_dump(mode="json"))
            return placed

    # ---- 上下文工程记录（写入口单点） ----

    def add_context_replacements(self, payload: ContextReplacements) -> ContextReplacements:
        """追加一条上下文工程记录（`context.replacements`，ADR-0017）。

        写入口只在本文：`context` 不得自己开文件也不得旁路写盘，否则 append-only 与
        seq 分配会失去单点（`tests/architecture/test_gesta_append_only.py` 强制）。
        """
        state = self._require_open()
        with store_lock(sessions_dir(), timeout=self._lock_timeout):
            self._append_context_locked(state, "context.replacements", payload)
        return payload

    def add_context_boundary(self, payload: ContextBoundary) -> ContextBoundary:
        """追加一条压缩边界记录（`context.boundary`，ADR-0017）。"""
        state = self._require_open()
        with store_lock(sessions_dir(), timeout=self._lock_timeout):
            self._append_context_locked(state, "context.boundary", payload)
        return payload

    def add_held_work(self, msg: SteerMessage) -> SteerMessage:
        """追加一条插话/排队消息到 held_work（M3a-3、B-65）。

        与 context 记录同机制：单点写入，不在 habena 里另开文件；归属线程不一致
        时爆炸（B-45 的延伸：gate 类消息先持久化定序）。本函数同步实现，
        async 调用方走 `await asyncio.to_thread(writer.add_held_work, msg)`。
        """
        state = self._require_open()
        if msg.thread_id != self._thread_id:
            raise ThreadStoreError(
                f"插话归属线程 {msg.thread_id!r} 与句柄线程 {self._thread_id!r} 不一致"
            )
        with store_lock(sessions_dir(), timeout=self._lock_timeout):
            self._append_locked(state, "habena.held_work", msg.model_dump(mode="json"))
        return msg

    def _append_context_locked(self, state: _FoldState, kind: str, payload: Any) -> None:
        """上下文记录的共用路径：先校归属，再走同一把锁与同一个追加器。"""
        thread_id = getattr(payload, "thread_id", None)
        if thread_id != self._thread_id:
            raise ThreadStoreError(
                f"记录归属线程 {thread_id!r} 与句柄线程 {self._thread_id!r} 不一致"
            )
        self._append_locked(state, kind, payload.model_dump(mode="json"))

    # ---- 内部 ----

    def _require_open(self) -> _FoldState:
        if self._state is None:
            raise ThreadStoreError("ThreadWriter 未 open()，先调用 open()")
        return self._state

    def _sync_locked(self, state: _FoldState) -> None:
        """stat 校验游标；被其他进程追加过则从缓存偏移增量同步（append-only 保证前缀不变）。"""
        path = thread_path(self._thread_id)
        current = path.stat().st_size
        if current == self._size:
            return
        if current < self._size:
            raise ThreadStoreError(
                f"线程 {self._thread_id} 的正文被外部截断（append-only 契约被破坏）"
            )
        with path.open("rb") as handle:
            handle.seek(self._size)
            tail = handle.read().decode("utf-8", errors="replace")
        for line in tail.splitlines():
            record = _parse_line(line)  # 残尾容忍与 _read_records 同语义
            if record is not None:
                state.apply(record)
        self._size = current
        self._needs_newline = not _ends_with_newline(path)

    def _append_locked(self, state: _FoldState, kind: str, payload: dict[str, Any]) -> None:
        """锁内：同步游标 → O(1) 追加 → 镜像与游标同批更新 → 索引增量刷新。"""
        self._sync_locked(state)
        record: _Record = _make_record(kind, payload, state.last_seq)
        written = _append_record_locked(self._thread_id, record, prefix_newline=self._needs_newline)
        self._needs_newline = False
        self._size += written
        state.apply(record)
        _upsert_index_entry_locked(_summary_from_state(state))
