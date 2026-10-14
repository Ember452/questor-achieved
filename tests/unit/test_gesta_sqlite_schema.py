"""gesta SQLite 库结构与迁移（Phase 2a 批次 1；behavior-gesta-wuu §1 §2）。

蓝本：wuu ``internal/session/session.go`` 的 ``sqliteDSN``/``configureDB``/``migrateSchema``/
``schemaMigration.addColumnIfMissing``。这里断言的是**库的形状**与两条易漏的迁移纪律：

- B-126：``session_inbox`` 的 CREATE 只有 8 列，另外 4 列由迁移追加；照抄 CREATE
  会让写入方在运行期才炸 —— 所以断言"写入列集 ⊆ 实际列集"。
- B-125：多宿主并发迁移时 ``ADD COLUMN`` 撞车必须当成功。

append-only 的机械表达也在这一层：``data-model.md`` §4 采"触发器禁 UPDATE/DELETE content"
（比 wuu 更严，差异已登 port-ledger）。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from questor.gesta.schema import connect, migrate

_INBOX_WRITE_COLUMNS = {
    "client_id",
    "session_id",
    "related_session_id",
    "cause",
    "content",
    "wake",
    "created_at",
    "delivered_at",
    # 下面四列在 wuu 里不在 CREATE 语句内，由迁移追加（B-126 的坑源）
    "controls_json",
    "work_id",
    "work_revision",
    "work_version",
}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _open(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "sessions.sqlite3")
    migrate(conn)
    return conn


def test_connection_pragmas_match_wuu(tmp_path: Path) -> None:
    """PRAGMA 取值照 wuu configureDB：WAL/NORMAL/busy_timeout 5000/foreign_keys/增量 vacuum。

    少一条就会在 sidecar 与 CLI 并发写时爆 ``database is locked`` 或让级联删除失效。
    """
    conn = _open(tmp_path)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2  # INCREMENTAL
    finally:
        conn.close()


def test_migrate_creates_authority_tables(tmp_path: Path) -> None:
    """A 阶段必建表齐（data-model §2；driver checkpoint/receipt 留表位属后置）。"""
    conn = _open(tmp_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for expected in (
            "sessions",
            "session_messages",
            "session_controls",
            "session_inbox",
            "held_user_work",
            "session_history_retractions",
            "session_history_checkpoints",
            "session_compaction_notes",
        ):
            assert expected in tables, f"缺表 {expected}"
        # 不做/后置表不得提前建（scope 纪律：agentthread 线程图、编排、插件、远程租约）
        for absent in ("participants", "participant_runs", "project_work", "plugin_turn_lifecycle"):
            assert absent not in tables
    finally:
        conn.close()


def test_inbox_write_column_set_is_satisfied(tmp_path: Path) -> None:
    """B-126：写入方用到的列必须在迁移后真实存在（照抄 CREATE 会漏 4 列）。"""
    conn = _open(tmp_path)
    try:
        missing = _INBOX_WRITE_COLUMNS - _columns(conn, "session_inbox")
        assert not missing, f"session_inbox 缺列 {sorted(missing)}——写入方会运行期炸"
    finally:
        conn.close()


def test_sessions_keeps_boundary_columns(tmp_path: Path) -> None:
    """§1.7 缝 6 / 多租户"不焊死"：owner/visibility/parent_id 三列必须保留（只留边界不建机制）。"""
    conn = _open(tmp_path)
    try:
        assert {"owner", "visibility", "parent_id"} <= _columns(conn, "sessions")
        assert {"session_id", "manager_id", "revision", "state"} <= _columns(
            conn, "session_controls"
        )
        assert {"session_id", "seq", "role", "content", "client_id", "origin"} <= _columns(
            conn, "session_messages"
        )
    finally:
        conn.close()


def test_append_only_trigger_rejects_history_rewrites(tmp_path: Path) -> None:
    """append-only 用库内触发器表达（比 wuu 更严，port-ledger 登记）：改写与删除正文必须被拒。"""
    conn = _open(tmp_path)
    try:
        conn.execute("INSERT INTO sessions(id, created_at, updated_at) VALUES ('s1', 't', 't')")
        conn.execute(
            "INSERT INTO session_messages(session_id, seq, role, content)"
            " VALUES ('s1', 1, 'user', '原文')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE session_messages SET content='改掉' WHERE session_id='s1'")
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM session_messages WHERE session_id='s1' AND seq=1")
        conn.rollback()
        # 新记录追加永远允许（append-only 只挡改写，不挡增长）
        conn.execute(
            "INSERT INTO session_messages(session_id, seq, role, content)"
            " VALUES ('s1', 2, 'user', '再来')"
        )
        assert conn.execute("SELECT COUNT(*) FROM session_messages").fetchone()[0] == 2
    finally:
        conn.close()


def test_cascade_delete_removes_child_rows(tmp_path: Path) -> None:
    """foreign_keys ON + ON DELETE CASCADE：删会话不留孤儿子表行（否则审计面出幽灵消息）。

    这条同时钉住一个真实冲突：单纯“禁 DELETE 正文”的触发器会把会话级联删除一起挡死
    （而 ``thread/delete`` 是 protocol.md §3 在册方法）。触发器因此带 WHEN 条件：
    父会话还在时不得删行，父会话正在被删时放行级联。
    """
    conn = _open(tmp_path)
    try:
        conn.execute("INSERT INTO sessions(id, created_at, updated_at) VALUES ('s1','t','t')")
        conn.execute(
            "INSERT INTO session_messages(session_id, seq, role, content)"
            " VALUES ('s1',1,'user','x')"
        )
        conn.execute(
            "INSERT INTO session_inbox(client_id, session_id, content, created_at) "
            "VALUES ('c1','s1','hi','t')"
        )
        # 会话还在 → 直接删单行必须被拒（第二道 append-only 防线）
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM session_messages WHERE session_id='s1' AND seq=1")
        # 会话级联删除必须放行
        conn.execute("DELETE FROM sessions WHERE id='s1'")
        assert conn.execute("SELECT COUNT(*) FROM session_messages").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM session_inbox").fetchone()[0] == 0
    finally:
        conn.close()


def test_migrate_is_repeatable_and_tolerates_racing_add_column(tmp_path: Path) -> None:
    """B-125：重复迁移幂等；且“列已被另一个宿主加过”必须当成功而不是启动失败。

    单线程无法自然重现“PRAGMA 查后、ALTER 前”被别人抢下，所以 ensure_column 留了一个
    ``assume_missing`` 入口——它正是并发路径（本方已判定为缺列）：走它两次，第二次
    必碰 ``duplicate column name``，必须被吐掉而不是报给启动流程。
    """
    path = tmp_path / "sessions.sqlite3"
    conn = connect(path)
    migrate(conn)
    migrate(conn)  # 幂等：第二次全程走"已存在即跳过"
    conn.close()

    conn = connect(path)
    migrate(conn)
    ensure = _ensure_column_for(conn)
    ensure("session_inbox", "work_version", "INTEGER NOT NULL DEFAULT 0", assume_missing=True)
    try:
        ensure("session_inbox", "work_version", "INTEGER NOT NULL DEFAULT 0", assume_missing=True)
    except sqlite3.OperationalError as exc:
        pytest.fail(f"并发 ADD COLUMN 竞态未被容忍，本进程启动失败：{exc}")
    assert "work_version" in _columns(conn, "session_inbox")
    conn.close()


def _ensure_column_for(conn: sqlite3.Connection):
    """绑好 conn 的 ``schema.ensure_column``（延迟导入：未实现时报错清晰，而不是收集期炸）。"""
    from functools import partial

    from questor.gesta.schema import ensure_column

    return partial(ensure_column, conn)
