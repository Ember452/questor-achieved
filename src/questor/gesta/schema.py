"""SQLite 会话权威库的连接、PRAGMA、建表与迁移（ADR-0041；behavior-gesta-wuu §1 §2）。

# Ported from wuu@2026.10.6 internal/session/session.go — pitfalls: B-125 B-126 B-46
# 逐段对应：``sqliteDSN``→:func:`connect`、``configureDB``→:func:`configure`、
# ``migrateSchema``→:func:`migrate`、``schemaMigration.addColumnIfMissing``→:func:`ensure_column`。
# 形状与取值照搬，代码是 Python 重写（无 CGO 依赖，标准库 ``sqlite3``）。

三条只能照母本、不能自创的理由：

1. **PRAGMA 取值**：WAL + ``synchronous=NORMAL`` + ``busy_timeout=5000`` +
   ``foreign_keys=ON`` + ``auto_vacuum=INCREMENTAL``。少 ``busy_timeout`` 或多进程抢写就会
   ``database is locked``；少 ``foreign_keys`` 级联删除静默失效。
2. **``_txlock=immediate``**：Go 驱动靠 DSN 参数；Python ``sqlite3`` 没有这个参数，等价做法是
   ``isolation_level=None``（自动提交）+ 写事务显式 ``BEGIN IMMEDIATE``（见
   :func:`write_txn`）。**deferred 事务先读后写会在两写者间升级为死锁**，这条不能省。
3. **建表列集 ≠ 写入列集**（B-126）：wuu 的 ``session_inbox`` CREATE 只有 8 列，另外 4 列
   （``controls_json/work_id/work_revision/work_version``）由迁移追加；照抄 CREATE 会让写入方
   在运行期才报 ``no such column``。本模块的 DDL 直接给全列（新库一步到位），
   同时保留"基线 + 追加"两段结构，兼容从旧库升级上来的场景。

append-only 的机械表达比 wuu 更严（差异登 ``docs/research/port-ledger.md``）：
``session_messages`` 加两个触发器——禁改写正文/序号/角色，禁在会话仍存在时删单行；
会话级联删除放行（``thread/delete`` 是 protocol.md §3 在册方法）。
"""

from __future__ import annotations

import contextlib
import pathlib
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

__all__ = [
    "DB_FILE_NAME",
    "connect",
    "configure",
    "ensure_column",
    "migrate",
    "now_text",
    "table_exists",
    "write_txn",
]


def now_text() -> str:
    """时间列的统一口径：UTC ISO8601 文本（wuu 用 ``timeText`` 存 UTC 文本）。

    单点定义的理由与其余一致：创建序、``delivered_at`` 判据、``updated_at`` 排序共用一把
    尺子，两处各算各的时间会让"谁更晚"变成不确定的事。
    """
    return datetime.now(UTC).isoformat()


#: 库文件名照 wuu ``dbFileName``（``sessions.sqlite3``）。
DB_FILE_NAME = "sessions.sqlite3"

_BUSY_TIMEOUT_MS = 5000

#: 基线建表：A 阶段权威表。刻意**不建**不做/后置表（agentthread 线程图、participants、
#: project_work、plugin_*、inference_journal_*）——scope 纪律见 scan-wuu-kernel §8。
_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        entries INTEGER NOT NULL DEFAULT 0,
        cwd TEXT NOT NULL DEFAULT '',
        forked_from_id TEXT NOT NULL DEFAULT '',
        forked_from_turn_id TEXT NOT NULL DEFAULT '',
        forked_from_item_id TEXT NOT NULL DEFAULT '',
        pinned_at TEXT,
        folder_id TEXT NOT NULL DEFAULT '',
        archived_at TEXT,
        worktree_path TEXT NOT NULL DEFAULT '',
        worktree_base_head TEXT NOT NULL DEFAULT '',
        worktree_base_repo TEXT NOT NULL DEFAULT '',
        owner TEXT NOT NULL DEFAULT '',
        visibility TEXT NOT NULL DEFAULT '',
        parent_id TEXT NOT NULL DEFAULT '',
        context_source TEXT NOT NULL DEFAULT '',
        creation_request_id TEXT NOT NULL DEFAULT '',
        instructions TEXT NOT NULL DEFAULT '',
        request_context_json TEXT NOT NULL DEFAULT '',
        tool_policy_json TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sessions_cwd ON sessions(cwd)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at, id)",
    """
    CREATE TABLE IF NOT EXISTS session_messages (
        session_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        display_content TEXT NOT NULL DEFAULT '',
        origin TEXT NOT NULL DEFAULT '',
        origin_id TEXT NOT NULL DEFAULT '',
        cause TEXT NOT NULL DEFAULT '',
        presentation_kind TEXT NOT NULL DEFAULT '',
        related_session_id TEXT NOT NULL DEFAULT '',
        read_only INTEGER NOT NULL DEFAULT 0,
        phase TEXT NOT NULL DEFAULT '',
        provider_item_id TEXT NOT NULL DEFAULT '',
        provider_item_model TEXT NOT NULL DEFAULT '',
        client_id TEXT NOT NULL DEFAULT '',
        hidden INTEGER NOT NULL DEFAULT 0,
        steered INTEGER NOT NULL DEFAULT 0,
        reasoning_content TEXT NOT NULL DEFAULT '',
        content_parts_json TEXT NOT NULL DEFAULT '',
        images_json TEXT NOT NULL DEFAULT '',
        files_json TEXT NOT NULL DEFAULT '',
        tool_calls_json TEXT NOT NULL DEFAULT '',
        discovered_tools_json TEXT NOT NULL DEFAULT '',
        tool_call_id TEXT NOT NULL DEFAULT '',
        tool_invocation_id TEXT NOT NULL DEFAULT '',
        tool_result_kind TEXT NOT NULL DEFAULT '',
        tool_result_json TEXT NOT NULL DEFAULT '',
        finish_reason TEXT NOT NULL DEFAULT '',
        stop_reason TEXT NOT NULL DEFAULT '',
        truncated INTEGER NOT NULL DEFAULT 0,
        name TEXT NOT NULL DEFAULT '',
        at TEXT,
        input_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        context_tokens INTEGER NOT NULL DEFAULT 0,
        cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
        cache_read_tokens INTEGER NOT NULL DEFAULT 0,
        provider TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (session_id, seq),
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_session_messages_role"
    " ON session_messages(session_id, role, seq)",
    """
    CREATE TABLE IF NOT EXISTS session_controls (
        session_id TEXT PRIMARY KEY,
        manager_id TEXT NOT NULL DEFAULT '',
        revision INTEGER NOT NULL DEFAULT 0,
        state TEXT NOT NULL DEFAULT 'active',
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_inbox (
        client_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        related_session_id TEXT NOT NULL DEFAULT '',
        cause TEXT NOT NULL DEFAULT '',
        content TEXT NOT NULL,
        wake INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        delivered_at TEXT,
        controls_json TEXT NOT NULL DEFAULT '[]',
        work_id TEXT NOT NULL DEFAULT '',
        work_revision INTEGER NOT NULL DEFAULT 0,
        work_version INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_session_inbox_pending"
    " ON session_inbox(session_id, delivered_at, created_at)",
    """
    CREATE TABLE IF NOT EXISTS held_user_work (
        session_id TEXT NOT NULL,
        position INTEGER NOT NULL,
        id TEXT NOT NULL,
        origin TEXT NOT NULL,
        message_json TEXT NOT NULL,
        runtime_json TEXT NOT NULL,
        PRIMARY KEY (session_id, id),
        UNIQUE (session_id, position),
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_history_retractions (
        session_id TEXT NOT NULL,
        from_seq INTEGER NOT NULL,
        through_seq INTEGER NOT NULL,
        PRIMARY KEY (session_id, from_seq, through_seq),
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_history_checkpoints (
        session_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        kind TEXT NOT NULL,
        through_seq INTEGER NOT NULL,
        replacement_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (session_id, version),
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_compaction_notes (
        session_id TEXT NOT NULL,
        provider_key TEXT NOT NULL,
        markdown TEXT NOT NULL,
        covered_messages INTEGER NOT NULL,
        covered_hash TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (session_id, provider_key),
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    )
    """,
    # append-only 的机械表达（data-model §4）：正文/序号/角色/归属会话不得改写。
    """
    CREATE TRIGGER IF NOT EXISTS session_messages_no_rewrite
    BEFORE UPDATE OF content, display_content, seq, role, session_id ON session_messages
    BEGIN
        SELECT RAISE(
            ABORT,
            'session_messages is append-only: append a new revision instead of rewriting history'
        );
    END
    """,
    # 会话仍存在时不得删单行；会话级联删除时父行已消失，WHEN 条件为假 → 放行。
    """
    CREATE TRIGGER IF NOT EXISTS session_messages_no_row_delete
    BEFORE DELETE ON session_messages
    FOR EACH ROW
    WHEN EXISTS (SELECT 1 FROM sessions WHERE id = OLD.session_id)
    BEGIN
        SELECT RAISE(ABORT, 'delete the session, not individual history rows');
    END
    """,
)

#: 基线之外的追加列：结构照 wuu ``migrateSchema`` 的"CREATE + addColumnIfMissing"两段式，
#: 让从旧库升上来的路径也补齐（B-126 的根因就在这里：只抄 CREATE 会漏列）。
_COLUMN_ADDITIONS: tuple[tuple[str, str, str], ...] = (
    ("session_inbox", "controls_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("session_inbox", "work_id", "TEXT NOT NULL DEFAULT ''"),
    ("session_inbox", "work_revision", "INTEGER NOT NULL DEFAULT 0"),
    ("session_inbox", "work_version", "INTEGER NOT NULL DEFAULT 0"),
    ("session_messages", "presentation_kind", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "creation_request_id", "TEXT NOT NULL DEFAULT ''"),
)


def _uri(path: pathlib.Path) -> str:
    """Windows 路径必须归一成 ``file:`` URI（wuu ``sqliteDSN`` L1215-1221 同调）。

    ``as_uri()`` 产出 ``file:///C:/...``，与 Go 侧 ``/C:/...`` 等价；关键是**不能**把
    ``D:\\x\\y`` 原样丢给 ``sqlite3.connect(uri=True)``——那会被当成相对路径。
    """
    return path.as_uri()


def configure(conn: sqlite3.Connection) -> None:
    """照 wuu ``configureDB`` 的取值逐条设置（顺序也照：先 auto_vacuum 再 journal_mode）。"""
    conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")


def connect(path: pathlib.Path) -> sqlite3.Connection:
    """打开（必要时创建）会话库并配好 PRAGMA。

    ``isolation_level=None`` 关掉隐式事务：写事务统一走 :func:`write_txn` 的
    ``BEGIN IMMEDIATE``（等价 Go 侧 ``_txlock=immediate``）。父目录不存在时先建，
    与 wuu 打开 store 目录的行为一致。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_uri(path), uri=True, isolation_level=None)
    conn.row_factory = sqlite3.Row
    configure(conn)
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """表存在性探测（wuu 在 inbox/journal 路径上先探再查，避免老库直接报错）。"""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1", (table,)
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"].lower() for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
    *,
    assume_missing: bool = False,
) -> None:
    """缺列才加；**并发加列撞车必须当成功**（B-125）。

    两个宿主（桌面 sidecar 与 CLI）共享同一会话库并同时迁移时，"我查到缺列"与"我执行
    ADD COLUMN"之间对方可能已经加过。wuu 的处理是：报 ``duplicate column name`` 就当成功
    （``addColumnIfMissing`` L2067-2073 的注释原文即此）。照搬这个容忍，否则第二次启动
    会直接失败。

    ``assume_missing=True`` 跳过存在性检查，走的正是上面那条竞态路径——它是并发场景下
    唯一会被执行的分支，所以必须可单独调用、可被测试咬住。
    """
    if not assume_missing and column.lower() in _table_columns(conn, table):
        return
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" in str(exc).lower():
            # 别的宿主抢先加好了，这不是故障（B-125）。
            # 负向已实测：去掉本行则报 `duplicate column name: work_version`。
            return
        raise


@contextlib.contextmanager
def write_txn(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """``BEGIN IMMEDIATE`` 写事务：进入即取写锁，异常整体回滚。

    这是 ``_txlock=immediate`` 的 Python 等价物，也是 seq 单点分配、held_work 整表替换
    的原子性前提。进程内串行由调用方（SessionStore）的锁负责，跨进程串行由
    ``state.locks.StoreLock`` 负责。
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def migrate(conn: sqlite3.Connection) -> None:
    """建表 + 加索引/触发器 + 追加列；可重复执行（幂等）。"""
    for statement in _SCHEMA_STATEMENTS:
        conn.execute(statement)
    for table, column, definition in _COLUMN_ADDITIONS:
        if not table_exists(conn, table):  # pragma: no cover - 基线刚建过，正常不会命中
            continue
        ensure_column(conn, table, column, definition)
