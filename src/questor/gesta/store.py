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

# Reimplements wuu@wuu-main internal/agentthread/store.go — pitfalls: B-45 B-46 B-74
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from questor.gesta.transitions import InvalidTransition, is_terminal, transition
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
    }
)


# ---- 记录流读取与 fold（无锁；B-74 残尾容忍） ----


def _read_records(path: pathlib.Path) -> list[_Record]:
    if not path.is_file():
        raise ThreadNotFound(str(path))
    records: list[_Record] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                raw = json.loads(text)
                record = _Record.model_validate(raw)
            except (ValueError, ValidationError):
                continue  # 崩溃残尾：整行落地失败或信封损坏的行跳过，不修复不阻断
            if record.kind not in _RECORD_KINDS:
                continue
            records.append(record)
    return records


def _fold(thread_id: str, records: list[_Record]) -> ThreadView:
    thread: Thread | None = None
    turns: list[Turn] = []
    runs: list[Run] = []
    items: list[Item] = []
    events: list[Event] = []
    last_seq = 0
    for record in records:
        last_seq = max(last_seq, record.seq)
        payload = record.payload
        if record.kind == "thread.created":
            if thread is None:
                thread = Thread.model_validate(payload)
        elif record.kind == "thread.renamed":
            if thread is None:
                raise ThreadStoreError(f"线程 {thread_id} 首记录不是 thread.created")
            thread = thread.model_copy(update={"title": payload["title"]})
        elif record.kind == "thread.flagged":
            if thread is None:
                raise ThreadStoreError(f"线程 {thread_id} 首记录不是 thread.created")
            update = {k: payload[k] for k in ("pinned", "archived") if payload.get(k) is not None}
            thread = thread.model_copy(update=update)
        elif record.kind == "turn.created":
            turns.append(Turn.model_validate(payload))
        elif record.kind == "run.created":
            runs.append(Run.model_validate(payload))
        elif record.kind == "run.status":
            run_id = payload["run_id"]
            target = RunStatus(payload["to"])
            run = next(r for r in runs if r.id == run_id)
            moved = transition(run.status, target)  # 回放同样过白名单：篡改历史在此爆炸
            runs[runs.index(run)] = run.model_copy(update={"status": moved})
        elif record.kind == "item.appended":
            items.append(Item.model_validate(payload))
        elif record.kind == "event.appended":
            events.append(Event.model_validate(payload))
    if thread is None:
        raise ThreadStoreError(f"线程 {thread_id} 的记录流没有 thread.created 首记录")
    updated_at = records[-1].recorded_at if records else thread.created_at
    thread = thread.model_copy(update={"updated_at": updated_at})
    return ThreadView(
        thread=thread,
        turns=tuple(turns),
        runs=tuple(runs),
        items=tuple(items),
        events=tuple(events),
        last_seq=last_seq,
    )


# ---- 索引（摘要缓存；可丢弃可重建） ----


def _index_path() -> pathlib.Path:
    return sessions_dir() / "threads.json"


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


def _upsert_index_entry_locked(view: ThreadView) -> None:
    index = _load_index() or _IndexFile(version=_INDEX_VERSION, threads=[])
    entries = [s for s in index.threads if s.id != view.thread.id]
    entries.append(_summary_of(view))
    entries.sort(key=lambda s: s.created_at)
    _rewrite_index_locked(entries)


def _remove_index_entry_locked(thread_id: str) -> None:
    index = _load_index() or _IndexFile(version=_INDEX_VERSION, threads=[])
    entries = [s for s in index.threads if s.id != thread_id]
    _rewrite_index_locked(entries)


# ---- 追加原语（持锁） ----


def _append_locked(thread_id: str, kind: str, payload: dict[str, Any], last_seq: int) -> int:
    record = _Record(seq=last_seq + 1, kind=kind, payload=payload, recorded_at=utc_timestamp_now())
    path = thread_path(thread_id)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(record.to_line() + "\n")
        handle.flush()
    return record.seq


def _load_locked(thread_id: str) -> ThreadView:
    return _fold(thread_id, _read_records(thread_path(thread_id)))


# ---- 公共 API ----


def create_thread(thread: Thread) -> ThreadView:
    """落盘线程首记录；同 id 已存在即抛 :class:`ThreadStoreError`。"""
    path = thread_path(thread.id)
    with store_lock(sessions_dir()):
        if path.exists():
            raise ThreadStoreError(f"线程 {thread.id} 已存在")
        payload = thread.model_dump(mode="json")
        _append_locked(thread.id, "thread.created", payload, last_seq=0)
        view = _load_locked(thread.id)
        _upsert_index_entry_locked(view)
        return view


def load_thread(thread_id: str) -> ThreadView:
    """读取并 fold 线程当前状态；文件不存在抛 :class:`ThreadNotFound`。"""
    return _fold(thread_id, _read_records(thread_path(thread_id)))


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
        view = _load_locked(thread_id)
        placed = Turn(
            id=turn_id,
            thread_id=thread_id,
            seq=len(view.turns) + 1,
            origin=origin,
            fork_from=fork_from,
            created_at=created_at,
        )
        _append_locked(thread_id, "turn.created", placed.model_dump(mode="json"), view.last_seq)
        _upsert_index_entry_locked(_load_locked(thread_id))
        return placed


def add_run(thread_id: str, run: Run) -> Run:
    """追加一次引擎执行记录（初始状态入流，之后只经 transition_run 推进）。"""
    with store_lock(sessions_dir()):
        view = _load_locked(thread_id)
        if run.status != RunStatus.QUEUED:
            raise ThreadStoreError("run 必须以 queued 入流，初始状态不得旁路指定")
        _append_locked(thread_id, "run.created", run.model_dump(mode="json"), view.last_seq)
        _upsert_index_entry_locked(_load_locked(thread_id))
        return run


def transition_run(thread_id: str, run_id: str, target: RunStatus) -> Run:
    """推进运行状态：唯一入口（transitions 白名单裁决），迁移记录追加进正文。"""
    with store_lock(sessions_dir()):
        view = _load_locked(thread_id)
        run = next((r for r in view.runs if r.id == run_id), None)
        if run is None:
            raise ThreadStoreError(f"线程 {thread_id} 没有 run {run_id}")
        moved = transition(run.status, target)  # 白名单外抛 InvalidTransition，不落盘
        _append_locked(
            thread_id,
            "run.status",
            {"run_id": run_id, "from": run.status.value, "to": moved.value},
            view.last_seq,
        )
        _upsert_index_entry_locked(_load_locked(thread_id))
        return run.model_copy(update={"status": moved})


def add_item(thread_id: str, item: Item) -> Item:
    """追加一个 Item（消息/工具调用/工具结果/引用/批注/交付物）。"""
    with store_lock(sessions_dir()):
        view = _load_locked(thread_id)
        _append_locked(thread_id, "item.appended", item.model_dump(mode="json"), view.last_seq)
        _upsert_index_entry_locked(_load_locked(thread_id))
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
        view = _load_locked(thread_id)
        placed = Event(
            seq=view.last_seq + 1,
            type=event_type,
            run_id=run_id,
            turn_id=turn_id,
            payload=payload,
            created_at=created_at,
        )
        _append_locked(thread_id, "event.appended", placed.model_dump(mode="json"), view.last_seq)
        _upsert_index_entry_locked(_load_locked(thread_id))
        return placed


def rename_thread(thread_id: str, title: str | None) -> Thread:
    """重命名线程（data-model §2 Thread.title 可重命名）；None 表示清除标题。"""
    with store_lock(sessions_dir()):
        view = _load_locked(thread_id)
        _append_locked(thread_id, "thread.renamed", {"title": title}, view.last_seq)
        return _load_locked(thread_id).thread


def set_thread_flags(
    thread_id: str, *, pinned: bool | None = None, archived: bool | None = None
) -> Thread:
    """置顶/归档线程；归档有未终态 run 时拒绝（wuu 语义：归档运行中拒绝）。"""
    with store_lock(sessions_dir()):
        view = _load_locked(thread_id)
        if archived and any(not is_terminal(r.status) for r in view.runs):
            raise ThreadStoreError(f"线程 {thread_id} 有运行中的 run，拒绝归档")
        payload: dict[str, Any] = {"pinned": pinned, "archived": archived}
        _append_locked(thread_id, "thread.flagged", payload, view.last_seq)
        return _load_locked(thread_id).thread


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
