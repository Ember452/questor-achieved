"""会话记录存储：append-only JSONL 唯一真相源 + 可重建 JSON 摘要索引。

落盘契约（data-model §5、§1）：
- 正文 ``<sessions>/<thread_id>.jsonl``，一行一条记录（``_Record`` 信封），**只追加**；
  读取跳过空行与解析失败的残尾行（B-74——崩溃半行不阻断回放与后续追加）；
- 当前状态 = 记录流的 fold，绝不改写历史行；运行状态迁移必须经
  :mod:`questor.gesta.transitions` 白名单（单点入口，旁路即契约破坏）；
- 索引 ``<sessions>/threads.json`` 是摘要缓存（可丢弃可重建），temp+rename 原子替换；
  SQLite 搜索索引按 B-46 属 M4，M2.1 以 JSON 索引承载（偏离已在 development-plan 留痕）；
- 所有读-改-写全程持 ``state.store_lock(sessions_dir)`` 跨进程锁；纯读者不拿锁。

seq 语义：记录信封的 ``seq`` 会话内全局递增（Event.seq 同源，断线恢复锚点）；
``Turn.seq`` 是线程内轮次序号，同样由本模块单点分配（B-45：gate 类消息先持久化定序）。

热路径（M2.2 前置决策，development-plan M2 第 8 条）：写路径只做**一次**全量 fold，
索引摘要由 fold 状态增量构造；engine 的高频追加走 :class:`questor.gesta.writer.ThreadWriter`
（首开一次 fold，此后 stat 校验 + O(1) 追加）。追加遇到崩溃残尾时以 ``\\n`` 前缀起新行，
残尾留待读侧跳过——追加永不粘接残尾、永不截断。

# Reimplements wuu@wuu-main internal/agentthread/store.go — pitfalls: B-45 B-46 B-74
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from questor.gesta.transitions import InvalidTransition, is_terminal, transition
from questor.schemas.context import ContextBoundary, ContextReplacements
from questor.schemas.habena import SteerMessage
from questor.schemas.model import (
    Event,
    ForkOrigin,
    Item,
    Origin,
    PermissionMode,
    Run,
    RunStatus,
    Thread,
    Turn,
    utc_timestamp_now,
)
from questor.state.atomic import write_atomic, write_excl
from questor.state.locks import store_lock
from questor.state.paths import sessions_dir, thread_path, tool_result_path

# ---- 落盘记录信封 ----


class _Record(BaseModel):
    """JSONL 行的信封：seq 会话内全局递增，payload 按 kind 取实体 dump 或增量。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int = Field(ge=1)
    kind: str
    payload: dict[str, Any]
    recorded_at: str

    def to_line(self) -> str:
        return self.model_dump_json()


class ThreadStoreError(Exception):
    """gesta 存储层错误的基类。"""


class ThreadNotFound(ThreadStoreError):
    """线程正文文件不存在。"""


class ToolResultSpill(BaseModel):
    """工具结果落盘的回链引用（data-model §5：O_EXCL 幂等写，预览 2KB）。"""

    model_config = ConfigDict(frozen=True)

    file: str
    preview: str
    truncated: bool


class ThreadView(BaseModel):
    """一个线程从记录流 fold 出的当前状态（只读投影）。"""

    model_config = ConfigDict(frozen=True)

    thread: Thread
    turns: tuple[Turn, ...]
    runs: tuple[Run, ...]
    items: tuple[Item, ...]
    events: tuple[Event, ...]
    #: 上下文工程的替换决策追加历史（ADR-0017）：恢复时由 `context.rehydrate` 重放
    context_replacements: tuple[ContextReplacements, ...] = ()
    #: 压缩边界历史（ADR-0017）：resume 重建与"它当时看到什么"的对账入口
    context_boundaries: tuple[ContextBoundary, ...] = ()
    #: 未消费的插话/排队消息（held_user_work 双 origin，B-65）；重启时从此重建 Inbox
    held_work: tuple[SteerMessage, ...] = ()
    last_seq: int


class ThreadSummary(BaseModel):
    """索引条目：线程摘要，不含正文。"""

    model_config = ConfigDict(frozen=True)

    id: str
    workspace_id: str
    title: str | None
    engine_id: str
    permission_mode: PermissionMode
    pinned: bool
    archived: bool
    created_at: str
    updated_at: str
    last_seq: int
    turn_count: int
    run_count: int


class _IndexFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int
    threads: list[ThreadSummary]


_INDEX_VERSION = 1
_PREVIEW_LIMIT = 2048
_RECORD_KINDS = frozenset(
    {
        "thread.created",
        "thread.renamed",
        "thread.flagged",
        "turn.created",
        "run.created",
        "run.status",
        "item.appended",
        "event.appended",
        # 上下文工程事实与正文同流（ADR-0017）；新 kind 必须同时有
        # _FoldState.apply 分支与 ThreadView 字段（B-85 的护栏就断言这两条）
        "context.replacements",
        "context.boundary",
        # 插话与排队消息与正文同流（M3a-3，B-65）；同样受 B-85 护栏管住
        "habena.held_work",
    }
)


# ---- 记录流读取与 fold（无锁；B-74 残尾容忍） ----


def _parse_line(text: str) -> _Record | None:
    """单行解析：空行/坏行/未知 kind 返回 None（残尾容忍），信封完好才返回。"""
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
        raise ThreadNotFound(str(path))
    records: list[_Record] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = _parse_line(line)
        if record is not None:
            records.append(record)
    return records


class _FoldState:
    """记录流的可变折叠状态——全量 fold 与 ThreadWriter 增量同步共用同一套语义。"""

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        self.thread: Thread | None = None
        self.turns: list[Turn] = []
        self.runs: list[Run] = []
        self.items: list[Item] = []
        self.events: list[Event] = []
        self.context_replacements: list[ContextReplacements] = []
        self.context_boundaries: list[ContextBoundary] = []
        self.held_work: list[SteerMessage] = []
        self.last_seq = 0
        self.last_recorded_at: str | None = None

    def apply(self, record: _Record) -> None:
        """把一条记录折进状态；篡改/损坏的历史在此显式爆炸为 ThreadStoreError
        （可被 rebuild_index 捕获跳过），而不是裸异常逃出 fold 边界。"""
        self.last_seq = max(self.last_seq, record.seq)
        self.last_recorded_at = record.recorded_at
        payload = record.payload
        if record.kind == "thread.created":
            if self.thread is None:
                self.thread = Thread.model_validate(payload)
        elif record.kind == "thread.renamed":
            thread = self._require_thread()
            self.thread = thread.model_copy(update={"title": payload.get("title")})
        elif record.kind == "thread.flagged":
            thread = self._require_thread()
            update = {k: payload[k] for k in ("pinned", "archived") if payload.get(k) is not None}
            self.thread = thread.model_copy(update=update)
        elif record.kind == "turn.created":
            self.turns.append(Turn.model_validate(payload))
        elif record.kind == "run.created":
            self.runs.append(Run.model_validate(payload))
        elif record.kind == "run.status":
            run_id = payload.get("run_id")
            to = payload.get("to")
            run = next((r for r in self.runs if r.id == run_id), None)
            if run is None:
                raise ThreadStoreError(
                    f"线程 {self.thread_id} 的 run.status 记录引用了不存在的 run {run_id!r}"
                )
            if not isinstance(to, str):
                raise ThreadStoreError(f"线程 {self.thread_id} 的 run.status 缺少 to 字段")
            try:
                target = RunStatus(to)
            except ValueError as exc:
                raise ThreadStoreError(
                    f"线程 {self.thread_id} 的 run.status 含未知状态 {to!r}"
                ) from exc
            moved = transition(run.status, target)  # 回放同样过白名单：篡改历史在此爆炸
            self.runs[self.runs.index(run)] = run.model_copy(update={"status": moved})
        elif record.kind == "item.appended":
            self.items.append(Item.model_validate(payload))
        elif record.kind == "event.appended":
            self.events.append(Event.model_validate(payload))
        elif record.kind == "context.replacements":
            # 载荷由 pydantic 模型把门：字段不对就是写错了一整条记录，显式爆炸不静默跳过
            self.context_replacements.append(ContextReplacements.model_validate(payload))
        elif record.kind == "context.boundary":
            self.context_boundaries.append(ContextBoundary.model_validate(payload))
        elif record.kind == "habena.held_work":
            self.held_work.append(SteerMessage.model_validate(payload))

    def _require_thread(self) -> Thread:
        if self.thread is None:
            raise ThreadStoreError(f"线程 {self.thread_id} 首记录不是 thread.created")
        return self.thread

    def build_view(self) -> ThreadView:
        if self.thread is None:
            raise ThreadStoreError(f"线程 {self.thread_id} 的记录流没有 thread.created 首记录")
        updated_at = self.last_recorded_at or self.thread.created_at
        thread = self.thread.model_copy(update={"updated_at": updated_at})
        return ThreadView(
            thread=thread,
            turns=tuple(self.turns),
            runs=tuple(self.runs),
            items=tuple(self.items),
            events=tuple(self.events),
            context_replacements=tuple(self.context_replacements),
            context_boundaries=tuple(self.context_boundaries),
            held_work=tuple(self.held_work),
            last_seq=self.last_seq,
        )


def _fold(thread_id: str, records: list[_Record]) -> ThreadView:
    state = _FoldState(thread_id)
    for record in records:
        state.apply(record)
    return state.build_view()


# ---- 索引（摘要缓存；可丢弃可重建） ----


def _index_path() -> pathlib.Path:
    return sessions_dir() / "threads.json"


def _summary_from_state(state: _FoldState) -> ThreadSummary:
    thread = state.build_view().thread
    return ThreadSummary(
        id=thread.id,
        workspace_id=thread.workspace_id,
        title=thread.title,
        engine_id=thread.engine_id,
        permission_mode=thread.permission_mode,
        pinned=thread.pinned,
        archived=thread.archived,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        last_seq=state.last_seq,
        turn_count=len(state.turns),
        run_count=len(state.runs),
    )


def _rewrite_index_locked(entries: list[ThreadSummary]) -> None:
    data = _IndexFile(version=_INDEX_VERSION, threads=entries)
    write_atomic(_index_path(), data.model_dump_json(indent=2).encode("utf-8") + b"\n")


def _load_index() -> _IndexFile | None:
    path = _index_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _IndexFile.model_validate(raw)
    except (ValueError, ValidationError):
        return None  # 索引是缓存：损坏即重建，不修复（data-model §5 同语义）


def rebuild_index() -> list[ThreadSummary]:
    """从各线程 JSONL 全量重建摘要索引并落盘；返回重建后的条目。"""
    entries: list[ThreadSummary] = []
    for path in sorted(sessions_dir().glob("*.jsonl")):
        try:
            view = _fold(path.stem, _read_records(path))
        except (ThreadNotFound, ThreadStoreError, InvalidTransition):
            continue  # 空文件/全残尾的线程不进索引
        entries.append(_summary_of(view))
    with store_lock(sessions_dir()):
        _rewrite_index_locked(entries)
    return entries


def _upsert_index_entry_locked(summary: ThreadSummary) -> None:
    index = _load_index() or _IndexFile(version=_INDEX_VERSION, threads=[])
    entries = [s for s in index.threads if s.id != summary.id]
    entries.append(summary)
    entries.sort(key=lambda s: s.created_at)
    _rewrite_index_locked(entries)


def _remove_index_entry_locked(thread_id: str) -> None:
    index = _load_index() or _IndexFile(version=_INDEX_VERSION, threads=[])
    entries = [s for s in index.threads if s.id != thread_id]
    _rewrite_index_locked(entries)


def _summary_of(view: ThreadView) -> ThreadSummary:
    thread = view.thread
    return ThreadSummary(
        id=thread.id,
        workspace_id=thread.workspace_id,
        title=thread.title,
        engine_id=thread.engine_id,
        permission_mode=thread.permission_mode,
        pinned=thread.pinned,
        archived=thread.archived,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        last_seq=view.last_seq,
        turn_count=len(view.turns),
        run_count=len(view.runs),
    )


# ---- 追加原语（持锁调用） ----


def _ends_with_newline(path: pathlib.Path) -> bool:
    size = path.stat().st_size
    if size == 0:
        return True
    with path.open("rb") as handle:
        handle.seek(-1, 2)
        return handle.read(1) == b"\n"


def _append_record_locked(thread_id: str, record: _Record, *, prefix_newline: bool = False) -> int:
    """整行追加一条记录，返回写入的字节数；追加永不粘接残尾（前缀起新行）、永不截断。"""
    data = record.to_line().encode("utf-8") + b"\n"
    if prefix_newline:
        data = b"\n" + data
    with thread_path(thread_id).open("ab") as handle:
        handle.write(data)
        handle.flush()
    return len(data)


def _make_record(kind: str, payload: dict[str, Any], last_seq: int) -> _Record:
    return _Record(seq=last_seq + 1, kind=kind, payload=payload, recorded_at=utc_timestamp_now())


def _load_state_locked(thread_id: str) -> _FoldState:
    state = _FoldState(thread_id)
    for record in _read_records(thread_path(thread_id)):
        state.apply(record)
    return state


def _load_locked(thread_id: str) -> ThreadView:
    return _load_state_locked(thread_id).build_view()


# ---- 公共 API ----


def create_thread(thread: Thread) -> ThreadView:
    """落盘线程首记录；同 id 已存在即抛 :class:`ThreadStoreError`。"""
    path = thread_path(thread.id)
    with store_lock(sessions_dir()):
        if path.exists():
            raise ThreadStoreError(f"线程 {thread.id} 已存在")
        state = _FoldState(thread.id)
        record = _make_record("thread.created", thread.model_dump(mode="json"), last_seq=0)
        _append_record_locked(thread.id, record)
        state.apply(record)
        _upsert_index_entry_locked(_summary_from_state(state))
        return state.build_view()


def load_thread(thread_id: str) -> ThreadView:
    """读取并 fold 线程当前状态；文件不存在抛 :class:`ThreadNotFound`。"""
    return _load_locked(thread_id)


def list_threads() -> list[ThreadSummary]:
    """列出线程摘要（读索引；索引缺失或损坏时先重建）。"""
    index = _load_index()
    if index is None:
        return rebuild_index()
    return sorted(index.threads, key=lambda s: s.created_at)


def add_turn(
    thread_id: str,
    *,
    turn_id: str,
    origin: Origin,
    created_at: str,
    fork_from: ForkOrigin | None = None,
) -> Turn:
    """追加一轮对话并返回带真实序号的 Turn（B-45 单点定序）。

    ``Turn.seq`` 由本模块在锁内分配（持久化顺序裁决先来后到），不接受调用方
    指定——gate/插话类消息必须"先持久化定序"，用户的跟进行才能排在后面。
    """
    with store_lock(sessions_dir()):
        state = _load_state_locked(thread_id)
        placed = Turn(
            id=turn_id,
            thread_id=thread_id,
            seq=len(state.turns) + 1,
            origin=origin,
            fork_from=fork_from,
            created_at=created_at,
        )
        record = _make_record("turn.created", placed.model_dump(mode="json"), state.last_seq)
        _append_record_locked(
            thread_id, record, prefix_newline=not _ends_with_newline(thread_path(thread_id))
        )
        state.apply(record)
        _upsert_index_entry_locked(_summary_from_state(state))
        return placed


def add_run(thread_id: str, run: Run) -> Run:
    """追加一次引擎执行记录（初始状态入流，之后只经 transition_run 推进）。"""
    with store_lock(sessions_dir()):
        state = _load_state_locked(thread_id)
        if run.status != RunStatus.QUEUED:
            raise ThreadStoreError("run 必须以 queued 入流，初始状态不得旁路指定")
        record = _make_record("run.created", run.model_dump(mode="json"), state.last_seq)
        _append_record_locked(
            thread_id, record, prefix_newline=not _ends_with_newline(thread_path(thread_id))
        )
        state.apply(record)
        _upsert_index_entry_locked(_summary_from_state(state))
        return run


def transition_run(thread_id: str, run_id: str, target: RunStatus) -> Run:
    """推进运行状态：唯一入口（transitions 白名单裁决），迁移记录追加进正文。"""
    with store_lock(sessions_dir()):
        state = _load_state_locked(thread_id)
        run = next((r for r in state.runs if r.id == run_id), None)
        if run is None:
            raise ThreadStoreError(f"线程 {thread_id} 没有 run {run_id}")
        moved = transition(run.status, target)  # 白名单外抛 InvalidTransition，不落盘
        record = _make_record(
            "run.status",
            {"run_id": run_id, "from": run.status.value, "to": moved.value},
            state.last_seq,
        )
        _append_record_locked(
            thread_id, record, prefix_newline=not _ends_with_newline(thread_path(thread_id))
        )
        state.apply(record)
        _upsert_index_entry_locked(_summary_from_state(state))
        return run.model_copy(update={"status": moved})


def add_item(thread_id: str, item: Item) -> Item:
    """追加一个 Item（消息/工具调用/工具结果/引用/批注/交付物）。"""
    with store_lock(sessions_dir()):
        state = _load_state_locked(thread_id)
        record = _make_record("item.appended", item.model_dump(mode="json"), state.last_seq)
        _append_record_locked(
            thread_id, record, prefix_newline=not _ends_with_newline(thread_path(thread_id))
        )
        state.apply(record)
        _upsert_index_entry_locked(_summary_from_state(state))
        return item


def append_event(
    thread_id: str,
    *,
    event_type: str,
    run_id: str,
    turn_id: str,
    payload: dict[str, Any],
    created_at: str,
) -> Event:
    """追加一条对外推送事件；``Event.seq`` 由本模块分配（会话内全局递增锚点）。"""
    with store_lock(sessions_dir()):
        state = _load_state_locked(thread_id)
        placed = Event(
            seq=state.last_seq + 1,
            type=event_type,
            run_id=run_id,
            turn_id=turn_id,
            payload=payload,
            created_at=created_at,
        )
        record = _make_record("event.appended", placed.model_dump(mode="json"), state.last_seq)
        _append_record_locked(
            thread_id, record, prefix_newline=not _ends_with_newline(thread_path(thread_id))
        )
        state.apply(record)
        _upsert_index_entry_locked(_summary_from_state(state))
        return placed


def rename_thread(thread_id: str, title: str | None) -> Thread:
    """重命名线程（data-model §2 Thread.title 可重命名）；None 表示清除标题。"""
    with store_lock(sessions_dir()):
        state = _load_state_locked(thread_id)
        record = _make_record("thread.renamed", {"title": title}, state.last_seq)
        _append_record_locked(
            thread_id, record, prefix_newline=not _ends_with_newline(thread_path(thread_id))
        )
        state.apply(record)
        _upsert_index_entry_locked(_summary_from_state(state))
        return state.build_view().thread


def set_thread_flags(
    thread_id: str, *, pinned: bool | None = None, archived: bool | None = None
) -> Thread:
    """置顶/归档线程；归档有未终态 run 时拒绝（wuu 语义：归档运行中拒绝）。"""
    with store_lock(sessions_dir()):
        state = _load_state_locked(thread_id)
        if archived and any(not is_terminal(r.status) for r in state.runs):
            raise ThreadStoreError(f"线程 {thread_id} 有运行中的 run，拒绝归档")
        record = _make_record(
            "thread.flagged", {"pinned": pinned, "archived": archived}, state.last_seq
        )
        _append_record_locked(
            thread_id, record, prefix_newline=not _ends_with_newline(thread_path(thread_id))
        )
        state.apply(record)
        _upsert_index_entry_locked(_summary_from_state(state))
        return state.build_view().thread


def delete_thread(thread_id: str) -> None:
    """删除线程（正文 + 索引条目）；有未终态 run 时拒绝。

    工具结果文件刻意不删——已落盘的证据不因会话删除而消失（可验证柱）；
    孤儿清理属存储治理，M4 随会话操作语义一并定义。
    """
    path = thread_path(thread_id)
    with store_lock(sessions_dir()):
        view = _load_locked(thread_id)
        if any(not is_terminal(r.status) for r in view.runs):
            raise ThreadStoreError(f"线程 {thread_id} 有未终态 run，拒绝删除")
        path.unlink()
        _remove_index_entry_locked(thread_id)


def spill_tool_result(thread_id: str, tool_use_id: str, content: str) -> ToolResultSpill:
    """工具结果全量落盘（O_EXCL 幂等，B-24），返回 2KB 预览回链。

    已存在时跳过写入并**回读盘上内容**构造预览——回链描述的是磁盘上的事实，
    不是本次调用试图写入的内容（诚实呈现）。
    """
    path = tool_result_path(tool_use_id)
    data = content.encode("utf-8")
    written = write_excl(path, data)
    if not written:
        data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    return ToolResultSpill(
        file=path.name,
        preview=text[:_PREVIEW_LIMIT],
        truncated=len(text) > _PREVIEW_LIMIT,
    )
