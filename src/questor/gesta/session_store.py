"""``SessionStore`` —— SQLite 会话权威库的读写门面（Phase 2a 批次 1）。

# Ported from wuu@2026.10.6 internal/session/session.go — pitfalls: B-45 B-125 B-126 B-127
# 对应函数：``insertSessionTx``→:meth:`create_session`、``appendHistoryRecordTx``→
# :meth:`append_record`（seq 在事务内 ``COALESCE(MAX(seq),0)+1`` 取号）、
# 历史读取→:meth:`load_messages`、控制面→:meth:`get_controls` / :meth:`set_controls`。

三层锁各司其职，不许合并（AGENTS §三 单一来源）：

1. **写路径串行**：一个 store 自有**专用写线程** + 任务队列（本对象的所有写按提交序执行）。
   为什么不是"一把进程内锁 + 共享连接"：``sqlite3`` 的连接**不得跨线程使用**（实测报
   ``SQLite objects created in a thread can only be used in that same thread``），
   而 engine 会经 ``asyncio.to_thread`` 从多个工作线程写同一会话库。
2. **多进程互斥**：:class:`questor.state.locks.StoreLock`（``.store.lock``，Windows
   ``LockFileEx`` / POSIX ``flock``，释放不删文件，B-71），由写线程每笔事务持一次。
3. **库内**：``BEGIN IMMEDIATE`` 让写事务进入即持锁（等价 Go 侧 ``_txlock=immediate``），
   避免两写者 deferred 升级为死锁。

读走**线程局部连接**（WAL 允许读者与写者并存），不进写队列，以免"读一个历史"把写堵住。

**异步说明（诚实登记）**：本门面是同步的。事件循环内不得直接调用（AGENTS §四 禁阻塞），
engine 侧一律经 ``asyncio.to_thread`` 调；不在没有第二个使用者之前先造一套 async wrapper
（可逆性三问）。差异与理由见 ``docs/research/port-ledger.md`` Phase 2a 段。
"""

from __future__ import annotations

import json
import pathlib
import queue
import sqlite3
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from typing import Any

from questor.gesta.errors import (
    ControlInvalid,
    GestaError,
    SequenceRejected,
    SessionExists,
    SessionNotFound,
    StoreCorrupted,
)
from questor.gesta.records import (
    CONTROL_STATES,
    SessionControls,
    SessionInfo,
    StoredMessage,
)
from questor.gesta.schema import DB_FILE_NAME, connect, migrate, now_text, write_txn
from questor.schemas.message import (
    ChatMessage,
    ImagePart,
    MessageRole,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from questor.state.locks import store_lock

__all__ = ["SessionStore", "default_db_path"]

#: 存储行视图：列名 → 值。只在 gesta 内部使用，不出进程边界、不进协议面
#: （出进程的数据一律用 :class:`~questor.schemas.message.ChatMessage` 等契约模型）。
type Row = dict[str, Any]

#: 消息片段的运行时联合类型（``schemas/message.py`` 的 Part 判别联合，此处用具体类集合）。
type AnyPart = TextPart | ReasoningPart | ToolCallPart | ToolResultPart | ImagePart

_PART_BUILDERS: dict[str, type[AnyPart]] = {
    "text": TextPart,
    "reasoning": ReasoningPart,
    "tool_call": ToolCallPart,
    "tool_result": ToolResultPart,
    "image": ImagePart,
}


def default_db_path(home: pathlib.Path) -> pathlib.Path:
    """会话库的默认位置：``<home>/sessions.sqlite3``（文件名照 wuu ``dbFileName``）。"""
    return home / DB_FILE_NAME


def _parts_dump(parts: Sequence[AnyPart]) -> str:
    return json.dumps([part.model_dump(mode="json") for part in parts], ensure_ascii=False)


def _parts_load(encoded: str) -> list[AnyPart]:
    """从 ``content_parts_json`` 重建 parts（唯一重建路径，B-85 同型纪律）。

    坏 JSON 不静默跳过：会话正文解析失败必须报 :class:`StoreCorrupted`，
    否则"少一条工具调用"会被当成"模型真的没请求工具"——那是假历史。
    """
    if not encoded:
        return []
    try:
        raw = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise StoreCorrupted(f"content_parts_json 解析失败：{exc}") from exc
    if not isinstance(raw, list):
        raise StoreCorrupted("content_parts_json 必须是片段数组")
    parts: list[AnyPart] = []
    for item in raw:
        kind = item.get("type") if isinstance(item, dict) else None
        builder = _PART_BUILDERS.get(kind) if isinstance(kind, str) else None
        if builder is None or not isinstance(item, dict):
            raise StoreCorrupted(f"未知的消息片段类型 {kind!r}")
        parts.append(builder.model_validate(item))
    return parts


def _joined_text(parts: Sequence[AnyPart]) -> str:
    return "".join(part.text for part in parts if isinstance(part, (TextPart, ReasoningPart)))


class _WriterThread:
    """一个 store 一笔写：专用线程持唯一连接，写任务按提交序执行。

    这层不是投机抽象：``sqlite3`` 连接不能跨线程（本仓实测），而 engine/serve 会从
    多个工作线程写同一会话库。“锁 + 共享连接”的写法会把阻塞错报成“正常行为”，
    而写线程 + 队列同时供了串行化与单线程连接两个性质。
    """

    def __init__(self, db_path: pathlib.Path, lock_dir: pathlib.Path, lock_timeout: float) -> None:
        self._path = db_path
        self._lock_dir = lock_dir
        self._lock_timeout = lock_timeout
        self._jobs: queue.Queue[tuple[Callable[[sqlite3.Connection], Any], Future] | None] = (
            queue.Queue()
        )
        self._thread = threading.Thread(target=self._run, name="questor-gesta-writer", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        conn = connect(self._path)
        migrate(conn)
        try:
            while True:
                job = self._jobs.get()
                if job is None:
                    return
                action, future = job
                try:
                    with store_lock(self._lock_dir, timeout=self._lock_timeout), write_txn(conn):
                        result = action(conn)
                except BaseException as exc:  # noqa: BLE001 - 必须原递给调用线程
                    future.set_exception(exc)
                else:
                    future.set_result(result)
        finally:
            conn.close()

    def submit(self, action: Callable[[sqlite3.Connection], Any]) -> Any:
        """提交并等待结果（调用方已在 ``to_thread`` 里，阻塞可接受）。"""
        future: Future = Future()
        self._jobs.put((action, future))
        return future.result()

    def close(self) -> None:
        self._jobs.put(None)
        self._thread.join(timeout=30.0)


class SessionStore:
    """会话库的读写门面（读侧也走这里，保证只有一条重建路径）。"""

    def __init__(
        self,
        db_path: pathlib.Path,
        *,
        lock_dir: pathlib.Path | None = None,
        lock_timeout: float = 60.0,
    ) -> None:
        self._path = pathlib.Path(db_path)
        self._lock_dir = self._path.parent if lock_dir is None else lock_dir
        self._lock_timeout = lock_timeout
        # 基线建表先在主线程走一次：之后所有写都在写线程里幂等重跑
        bootstrap = connect(self._path)
        migrate(bootstrap)
        bootstrap.close()
        self._writer = _WriterThread(self._path, self._lock_dir, self._lock_timeout)
        # 只读连接按线程隔离（WAL 下读者不阻写者，也不互相阻）
        self._readers = threading.local()
        self._closed = False

    # ---------------------------------------------------------------- 基础设施

    def close(self) -> None:
        """关闭写线程与本线程的读连接；幂等（便于 fixture 与 finally 并存）。"""
        if self._closed:
            return
        self._closed = True
        self._writer.close()
        reader: sqlite3.Connection | None = getattr(self._readers, "conn", None)
        if reader is not None:
            reader.close()
            self._readers.conn = None

    @property
    def db_path(self) -> pathlib.Path:
        return self._path

    def _require_open(self) -> None:
        if self._closed:
            raise GestaError("SessionStore 已关闭，拒绝继续读写")

    def _reader_conn(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._readers, "conn", None)
        if conn is None:
            conn = connect(self._path)
            self._readers.conn = conn
        return conn

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[Row]:
        """只读查询。不进写队列也不拿写锁——wuu 的纯读者两锁都不拿（L359-361 同调）。"""
        self._require_open()
        return [dict(row) for row in self._reader_conn().execute(sql, params).fetchall()]

    def write(self, action: Callable[[sqlite3.Connection], Any]) -> Any:
        """在一次"写线程串行 → 多进程互斥锁 → ``BEGIN IMMEDIATE`` 事务"里执行 ``action``。

        inbox / held_work 复用这个入口，避免各自再拼一遍锁序——**锁序写反就是死锁**，
        所以序只在这一处定义。
        """
        self._require_open()
        return self._writer.submit(action)

    # ---------------------------------------------------------------- 会话面

    def create_session(
        self,
        session_id: str,
        *,
        cwd: str = "",
        title: str = "",
        parent_id: str = "",
        forked_from_id: str = "",
        worktree_path: str = "",
    ) -> SessionInfo:
        """建会话；同 id 已存在时显式拒绝（静默覆盖会抹掉整段历史）。"""
        if not session_id.strip():
            raise GestaError("session_id 不得为空")
        now = now_text()

        def _insert(conn: sqlite3.Connection) -> None:
            try:
                conn.execute(
                    "INSERT INTO sessions(id, created_at, updated_at, title, cwd, parent_id,"
                    " forked_from_id, worktree_path) VALUES (?,?,?,?,?,?,?,?)",
                    (session_id, now, now, title, cwd, parent_id, forked_from_id, worktree_path),
                )
            except sqlite3.IntegrityError as exc:
                raise SessionExists(f"会话 {session_id!r} 已存在") from exc
            # 控制行随会话建立：revision 从 0 起，接管与幂等栅栏都靠它
            conn.execute(
                "INSERT INTO session_controls(session_id, manager_id, revision, state)"
                " VALUES (?, '', 0, 'active')",
                (session_id,),
            )

        self.write(_insert)
        return self.load_session(session_id)

    def load_session(self, session_id: str) -> SessionInfo:
        self._require_open()
        rows = self.query("SELECT * FROM sessions WHERE id = ?", (session_id,))
        if not rows:
            raise SessionNotFound(f"会话 {session_id!r} 不存在")
        return _to_session_info(rows[0])

    def list_sessions(self, *, include_archived: bool = False) -> list[SessionInfo]:
        self._require_open()
        sql = "SELECT * FROM sessions"
        if not include_archived:
            sql += " WHERE archived_at IS NULL"
        sql += " ORDER BY updated_at DESC, id"
        return [_to_session_info(row) for row in self.query(sql)]

    def rename_session(self, session_id: str, title: str) -> None:
        self._touch(session_id, "UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))

    def set_archived(self, session_id: str, archived: bool) -> None:
        stamp = now_text() if archived else None
        self._touch(
            session_id, "UPDATE sessions SET archived_at = ? WHERE id = ?", (stamp, session_id)
        )

    def set_pinned(self, session_id: str, pinned: bool) -> None:
        stamp = now_text() if pinned else None
        self._touch(
            session_id, "UPDATE sessions SET pinned_at = ? WHERE id = ?", (stamp, session_id)
        )

    def delete_session(self, session_id: str) -> None:
        """删会话（``thread/delete``）。

        历史行不可单删，只能连会话一起级联——这是 append-only 与"用户可删自己的会话"
        唯一相容的写法（触发器的 ``WHEN`` 条件正是为此存在）。
        ``thread/delete`` 的"需 idle"前置属 run 状态面，随 serve 批次接入（port-ledger 登记）。
        """
        self.load_session(session_id)

        def _delete(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

        self.write(_delete)

    def _touch(self, session_id: str, sql: str, params: tuple[Any, ...]) -> None:
        self.load_session(session_id)

        def _apply(conn: sqlite3.Connection) -> None:
            conn.execute(sql, params)
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now_text(), session_id),
            )

        self.write(_apply)

    # ---------------------------------------------------------------- 历史面

    def append_message(self, session_id: str, message: ChatMessage) -> int:
        """追加一条消息并返回 seq（会话内的稳定地址）。"""
        return self.append_record(session_id, StoredMessage(message=message))

    def append_record(self, session_id: str, record: StoredMessage) -> int:
        """追加带元数据的记录。

        ``record.seq`` 非 None 直接拒绝：seq 只能由本方法在事务内取号（B-45 单点分配），
        调用方自带号会让两个写者各算各的，撞号或跳号。
        """
        self.load_session(session_id)
        if record.seq is not None:
            raise SequenceRejected(
                "seq 由 store 在追加事务内分配，调用方不得自带 seq（B-45 单点分配）"
            )

        message = record.message
        parts = list(message.parts)
        parts_json = _parts_dump(parts)
        joined = _joined_text(parts)
        # 投影列：content 优先取 input_text（wuu 的 content=输入原文、display_content=展示）
        content = joined if message.input_text is None else message.input_text
        display = joined if message.display_content is None else message.display_content
        tool_calls = [
            part.model_dump(mode="json") for part in parts if isinstance(part, ToolCallPart)
        ]
        images = [part.model_dump(mode="json") for part in parts if isinstance(part, ImagePart)]
        reasoning = "".join(part.text for part in parts if isinstance(part, ReasoningPart))
        at = now_text() if record.at is None else record.at

        def _append(conn: sqlite3.Connection) -> int:
            # 照 wuu appendHistoryRecordTx：取号与插入必须在同一事务内
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS next FROM session_messages"
                " WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            next_seq = int(row["next"])
            conn.execute(
                "INSERT INTO session_messages(session_id, seq, role, content, display_content,"
                " origin, origin_id, client_id, name, phase, provider_item_id, hidden, steered,"
                " reasoning_content, content_parts_json, tool_calls_json, images_json,"
                " finish_reason, stop_reason, truncated, at, input_tokens, output_tokens,"
                " context_tokens, cache_creation_tokens, cache_read_tokens, provider, model)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    next_seq,
                    message.role.value,
                    content,
                    display,
                    message.origin or "",
                    message.origin_id or "",
                    message.client_id or "",
                    message.name or "",
                    record.phase,
                    record.provider_item_id,
                    1 if record.hidden else 0,
                    1 if record.steered else 0,
                    reasoning,
                    parts_json,
                    json.dumps(tool_calls, ensure_ascii=False) if tool_calls else "",
                    json.dumps(images, ensure_ascii=False) if images else "",
                    record.finish_reason,
                    record.stop_reason,
                    1 if record.truncated else 0,
                    at,
                    record.input_tokens,
                    record.output_tokens,
                    record.context_tokens,
                    record.cache_creation_tokens,
                    record.cache_read_tokens,
                    record.provider,
                    record.model,
                ),
            )
            conn.execute(
                "UPDATE sessions SET entries = entries + 1, updated_at = ? WHERE id = ?",
                (now_text(), session_id),
            )
            return next_seq

        return self.write(_append)

    def load_messages(self, session_id: str, *, after_seq: int = 0) -> list[StoredMessage]:
        """按 seq 序读回历史；``after_seq`` 供续传/增量读。"""
        self._require_open()
        rows = self.query(
            "SELECT * FROM session_messages WHERE session_id = ? AND seq > ? ORDER BY seq",
            (session_id, after_seq),
        )
        return [_to_stored_message(row) for row in rows]

    def raw_row(self, session_id: str, seq: int) -> Row:
        """投影列的诊断视图（测试据此证明投影是从 parts 派生的，不是第二套真相）。"""
        rows = self.query(
            "SELECT * FROM session_messages WHERE session_id = ? AND seq = ?", (session_id, seq)
        )
        if not rows:
            raise SessionNotFound(f"会话 {session_id!r} 没有 seq={seq} 的记录")
        return rows[0]

    # ---------------------------------------------------------------- 控制面

    def get_controls(self, session_id: str) -> SessionControls:
        self._require_open()
        rows = self.query("SELECT * FROM session_controls WHERE session_id = ?", (session_id,))
        if not rows:
            raise SessionNotFound(f"会话 {session_id!r} 没有控制行")
        row = rows[0]
        return SessionControls(
            session_id=session_id,
            manager_id=row["manager_id"] or "",
            revision=int(row["revision"]),
            state=row["state"] or "active",
        )

    def set_controls(self, session_id: str, *, manager_id: str, state: str) -> int:
        """改控制归属/状态并**单点递增** revision，返回新的修订号。

        修订号不由调用方给（ADR-0005：只有一条递增路径），否则接管栅栏可被伪造。
        """
        if state not in CONTROL_STATES:
            raise ControlInvalid(f"state 必须在 {CONTROL_STATES} 内，收到 {state!r}")
        self.load_session(session_id)

        def _apply(conn: sqlite3.Connection) -> int:
            row = conn.execute(
                "SELECT revision FROM session_controls WHERE session_id = ?", (session_id,)
            ).fetchone()
            revision = 1 if row is None else int(row["revision"]) + 1
            if row is None:
                conn.execute(
                    "INSERT INTO session_controls(session_id, manager_id, revision, state)"
                    " VALUES (?,?,?,?)",
                    (session_id, manager_id, revision, state),
                )
            else:
                conn.execute(
                    "UPDATE session_controls SET manager_id = ?, revision = ?, state = ?"
                    " WHERE session_id = ?",
                    (manager_id, revision, state, session_id),
                )
            return revision

        return self.write(_apply)


def _to_session_info(row: Row) -> SessionInfo:
    return SessionInfo(
        id=row["id"],
        title=row["title"] or "",
        summary=row["summary"] or "",
        cwd=row["cwd"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        entries=int(row["entries"]),
        pinned_at=row["pinned_at"],
        archived_at=row["archived_at"],
        folder_id=row["folder_id"] or "",
        forked_from_id=row["forked_from_id"] or "",
        forked_from_turn_id=row["forked_from_turn_id"] or "",
        forked_from_item_id=row["forked_from_item_id"] or "",
        worktree_path=row["worktree_path"] or "",
        worktree_base_head=row["worktree_base_head"] or "",
        worktree_base_repo=row["worktree_base_repo"] or "",
        owner=row["owner"] or "",
        visibility=row["visibility"] or "",
        parent_id=row["parent_id"] or "",
        context_source=row["context_source"] or "",
        instructions=row["instructions"] or "",
    )


def _to_stored_message(row: Row) -> StoredMessage:
    parts = _parts_load(row["content_parts_json"] or "")
    joined = _joined_text(parts)
    content = row["content"] or ""
    display = row["display_content"] or ""
    message = ChatMessage(
        role=MessageRole(row["role"]),
        parts=parts,  # type: ignore[arg-type]
        origin=row["origin"] or None,
        origin_id=row["origin_id"] or None,
        client_id=row["client_id"] or None,
        name=row["name"] or None,
        # 只有当投影列与 parts 拼接不一致时，才说明当初写入给了独立的 input_text/display_content；
        # 一致时保持 None，避免把同一段文本存成两份真相（差异登 port-ledger）。
        input_text=content if content != joined else None,
        display_content=display if display != joined else None,
    )
    return StoredMessage(
        message=message,
        seq=int(row["seq"]),
        phase=row["phase"] or "",
        provider_item_id=row["provider_item_id"] or "",
        finish_reason=row["finish_reason"] or "",
        stop_reason=row["stop_reason"] or "",
        truncated=bool(row["truncated"]),
        hidden=bool(row["hidden"]),
        steered=bool(row["steered"]),
        name=row["name"] or "",
        at=row["at"],
        provider=row["provider"] or "",
        model=row["model"] or "",
        input_tokens=int(row["input_tokens"]),
        output_tokens=int(row["output_tokens"]),
        context_tokens=int(row["context_tokens"]),
        cache_creation_tokens=int(row["cache_creation_tokens"]),
        cache_read_tokens=int(row["cache_read_tokens"]),
    )
