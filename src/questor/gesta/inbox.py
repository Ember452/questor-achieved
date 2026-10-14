"""inbox —— host→会话的待投递输入：幂等入队、历史侧送达判据、消费时控制复判。

# Ported from wuu@2026.10.6 internal/session/inbox.go — pitfalls: B-63 B-127 B-129
# 逐函数对应：``insertInbox``→:func:`enqueue`、``SettleInbox``→:func:`settle`、
# ``PendingInbox``→:func:`pending`、``InboxTargets``→:func:`targets`、
# ``InboxHas``→:func:`has`、``validateInboxControls``→:func:`validate_controls`。

本模块最容易被写错的一条（B-127）：**送达判据不是入队时间，而是"这条输入的
``client_id`` 已经出现在目标会话的持久历史里"**。写成"入队即已投"的实现在单测里看不出来，
但崩溃/重启重试投递时会把同一条用户输入再注入一次——用户看到的是自己说过的话凭空多一遍。

A 阶段只移植控制栅栏的 **``session_controls`` 复判**那一半；``project_work`` 分支属不做的
编排面（scan-wuu-kernel §8），差异与理由登 ``docs/research/port-ledger.md``。
"""

from __future__ import annotations

import json
import sqlite3

from questor.gesta.errors import ControlChanged, GestaError, InboxInvalid
from questor.gesta.records import Control, InboxMessage
from questor.gesta.schema import now_text
from questor.gesta.session_store import SessionStore

__all__ = ["enqueue", "has", "pending", "settle", "targets", "validate_controls"]

_WRITE_COLUMNS = (
    "client_id,session_id,related_session_id,cause,content,wake,created_at,"
    "controls_json,work_id,work_revision,work_version"
)
#: 读取列集不等于写入列集（本模块刚踩中 B-126：拿 INSERT 的列单去 SELECT，
#: ``delivered_at`` 直接 KeyError）。送达时间是投递判据的一部分，读侧必须拿到它。
_READ_COLUMNS = f"{_WRITE_COLUMNS},delivered_at"


def _require_ids(message: InboxMessage) -> None:
    """缺 id 必须显式拒绝（wuu inbox.go L49-51 同调）。

    ``client_id`` 就是幂等键本身：为空时 ``INSERT OR IGNORE`` 会把所有消息折叠成同一行，
    静默丢掉后来的每一条输入。
    """
    if not message.client_id.strip():
        raise InboxInvalid("inbox 消息必须带 client_id（它是幂等判据）")
    if not message.session_id.strip():
        raise InboxInvalid("inbox 消息必须带目标 session_id")


def _encode_controls(controls: list[Control]) -> str:
    return json.dumps([control.model_dump(mode="json") for control in controls], ensure_ascii=False)


def _decode_controls(encoded: str | None) -> list[Control]:
    if not encoded or encoded == "[]":
        return []
    raw = json.loads(encoded)
    return [Control.model_validate(item) for item in raw]


def enqueue(store: SessionStore, message: InboxMessage) -> None:
    """记录一条待投递输入；同 ``client_id`` 重复入队是 no-op（B-63）。

    重复入队**不覆盖**首次内容——``INSERT OR IGNORE`` 的语义就是"已经有这条了"，
    改内容会让"同一 client_id 的两次提交"变成两个不同事实。
    """
    _require_ids(message)
    created_at = message.created_at or now_text()
    params = (
        message.client_id,
        message.session_id,
        message.related_session_id,
        message.cause,
        message.content,
        1 if message.wake else 0,
        created_at,
        _encode_controls(message.controls),
        message.work_id,
        message.work_revision,
        message.work_version,
    )

    def _insert(conn: sqlite3.Connection) -> None:
        try:
            # 不写 ``delivered_at``：入队不是送达（B-127）
            conn.execute(
                f"INSERT OR IGNORE INTO session_inbox({_WRITE_COLUMNS})"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                params,
            )
        except sqlite3.IntegrityError as exc:
            # 只剩"目标会话不存在"这一种完整性错误：FK 生效是配置要求，不得静默吞
            raise GestaError(f"inbox 入队失败（目标会话可能不存在）：{exc}") from exc

    store.write(_insert)


def settle(store: SessionStore, client_id: str, session_id: str) -> None:
    """记"已处理"而不投递内容，让后续对同一 client_id 的重试变 no-op（wuu L64-81）。"""
    if not client_id.strip() or not session_id.strip():
        raise InboxInvalid("inbox settle 需要 client_id 与 session_id")
    now = now_text()

    def _apply(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO session_inbox(client_id,session_id,content,created_at,"
            "delivered_at) VALUES (?,?, '', ?, ?)"
            " ON CONFLICT(client_id) DO UPDATE SET delivered_at=excluded.delivered_at",
            (client_id, session_id, now, now),
        )

    store.write(_apply)


def _settle_delivered(conn: sqlite3.Connection, session_id: str) -> None:
    """B-127 的本体：client_id 已落入持久历史 ⇒ 标送达。"""
    conn.execute(
        "UPDATE session_inbox SET delivered_at = ?"
        " WHERE session_id = ? AND delivered_at IS NULL"
        " AND EXISTS (SELECT 1 FROM session_messages m"
        "             WHERE m.session_id = session_inbox.session_id"
        "               AND m.client_id = session_inbox.client_id)",
        (now_text(), session_id),
    )


def pending(store: SessionStore, session_id: str) -> list[InboxMessage]:
    """先把已落历史的标送达，再按创建序返回其余（wuu ``PendingInbox`` L83-119）。

    送达判定与读取是一起的（判完立刻查），否则调用方会拿到"其实已经投过了"的旧行。
    """

    def _settle(conn: sqlite3.Connection) -> None:
        _settle_delivered(conn, session_id)

    store.write(_settle)
    rows = store.query(
        f"SELECT {_READ_COLUMNS} FROM session_inbox"
        " WHERE session_id = ? AND delivered_at IS NULL ORDER BY created_at, rowid",
        (session_id,),
    )
    return [_to_message(row) for row in rows]


def _to_message(row: dict) -> InboxMessage:
    return InboxMessage(
        client_id=row["client_id"],
        session_id=row["session_id"],
        related_session_id=row["related_session_id"] or "",
        cause=row["cause"] or "",
        content=row["content"],
        wake=bool(row["wake"]),
        created_at=row["created_at"],
        delivered_at=row["delivered_at"],
        controls=_decode_controls(row["controls_json"]),
        work_id=row["work_id"] or "",
        work_revision=int(row["work_revision"]),
        work_version=int(row["work_version"]),
    )


def targets(store: SessionStore) -> list[str]:
    """列出仍有未决输入的会话 id（创建侧的"谁该被叫醒"，按 id 稳定序）。"""
    rows = store.query(
        "SELECT DISTINCT session_id FROM session_inbox"
        " WHERE delivered_at IS NULL ORDER BY session_id"
    )
    return [row["session_id"] for row in rows]


def has(store: SessionStore, client_id: str) -> bool:
    """该 client_id 是否已被记录（送达与否都算"见过"）。"""
    rows = store.query(
        "SELECT EXISTS (SELECT 1 FROM session_inbox WHERE client_id = ?) AS found",
        (client_id,),
    )
    return bool(rows and rows[0]["found"])


def validate_controls(store: SessionStore, client_id: str) -> None:
    """消费前复判控制栅栏（B-129）：入队时判一次不够。

    wuu 注释原文：a sender can be stopped while a prompt hook runs after the earlier
    admission check——发送方可能在"已经准入"之后被接管，所以真正消费那一刻必须再看一次
    ``session_controls`` 的 manager/revision/state。未知 client_id 是无操作（照 wuu
    ``ErrNoRows`` → 返回 nil 的分支），不报错。
    """
    rows = store.query(
        "SELECT controls_json, work_id, work_revision, work_version, cause, session_id"
        " FROM session_inbox WHERE client_id = ?",
        (client_id,),
    )
    if not rows:
        return
    row = rows[0]
    controls = _decode_controls(row["controls_json"])
    for control in controls:
        current = store.query(
            "SELECT manager_id, revision, state FROM session_controls WHERE session_id = ?",
            (control.session_id,),
        )
        if not current:
            raise ControlChanged(f"控制所属会话 {control.session_id!r} 已不存在")
        state = current[0]
        if (
            state["manager_id"] != control.manager_id
            or int(state["revision"]) != control.revision
            or state["state"] != "active"
        ):
            raise ControlChanged(
                f"会话 {control.session_id!r} 的控制权已变更（接管栅栏不匹配），"
                f"拒绝消费 {client_id!r}"
            )
