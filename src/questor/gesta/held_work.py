"""held_user_work —— 运行中未决输入（queue/steer）的整表替换与序号压缩。

# Ported from wuu@2026.10.6 internal/session/held_user_work.go — pitfalls: B-65 B-128
# 逐函数对应：``ReplaceHeldUserWork``→:func:`replace`、``LoadHeldUserWork``→:func:`load`、
# ``DeleteHeldUserWork``→:func:`delete`。

这是"可干预柱"能在崩溃后重建的地基：core 重启后按这张表恢复未消费的排队/插话输入（B-65）。

本模块最容易写错的一条是 B-128：删掉一条后要把后续 position 往前挪，
**直接** ``position = position - 1`` 会撞 ``UNIQUE(session_id, position)``（目标位还被占着）。
wuu 的写法是两段 UPDATE：先把后移者 ``-position-1`` 取负躲开冲突，再 ``-position-2`` 归正。
两段必须落在同一事务里——中间态暴露出去就等于把约束形同虚设。
"""

from __future__ import annotations

import sqlite3

from questor.gesta.errors import GestaError, HeldWorkInvalid
from questor.gesta.records import HELD_ORIGINS, HeldUserWorkEntry
from questor.gesta.session_store import SessionStore

__all__ = ["delete", "load", "replace"]


def _validate(entries: list[HeldUserWorkEntry]) -> None:
    """形状校验：缺 id / 缺正文或运行时 JSON / origin 越界都拒绝。

    值域校验放在**存储层**而不是模型层（照 wuu）：坏值要报成"第几条的哪个字段不合法"，
    而不是 pydantic 的通用校验错——调用方拿到的是可解释的失败。
    """
    for position, entry in enumerate(entries):
        if not entry.id.strip():
            raise HeldWorkInvalid(f"held_user_work 第 {position} 条：id 必填")
        if entry.origin not in HELD_ORIGINS:
            raise HeldWorkInvalid(
                f"held_user_work {entry.id!r}：origin 必须是 {HELD_ORIGINS} 之一，"
                f"收到 {entry.origin!r}"
            )
        if not entry.message_json or not entry.runtime_json:
            raise HeldWorkInvalid(f"held_user_work {entry.id!r}：message 与 runtime 都必填")


def replace(store: SessionStore, session_id: str, entries: list[HeldUserWorkEntry]) -> None:
    """整表替换某会话的未决输入；``position`` 由传入顺序决定（调用方给序，不给号）。

    校验放在写入之前（与 wuu 的事务内校验可观测结果一致，但少一次无谓的 DELETE）：
    任一条不合法就**完全不改动**既有表，不会出现"旧的已删、新的只进一半"。
    """
    _validate(entries)

    def _apply(conn: sqlite3.Connection) -> None:
        try:
            conn.execute("DELETE FROM held_user_work WHERE session_id = ?", (session_id,))
            for position, entry in enumerate(entries):
                conn.execute(
                    "INSERT INTO held_user_work(session_id, position, id, origin, message_json,"
                    " runtime_json) VALUES (?,?,?,?,?,?)",
                    (
                        session_id,
                        position,
                        entry.id,
                        entry.origin,
                        entry.message_json,
                        entry.runtime_json,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            # 只剩"目标会话不存在"这一种情况：FK 生效是配置要求，不得静默吞
            raise GestaError(f"held_user_work 替换失败（目标会话可能不存在）：{exc}") from exc

    store.write(_apply)


def load(store: SessionStore, session_id: str) -> list[HeldUserWorkEntry]:
    """按 position 序读回未决输入（消费顺序即此顺序）。"""
    rows = store.query(
        "SELECT position, id, origin, message_json, runtime_json FROM held_user_work"
        " WHERE session_id = ? ORDER BY position",
        (session_id,),
    )
    return [
        HeldUserWorkEntry(
            session_id=session_id,
            position=int(row["position"]),
            id=row["id"],
            origin=row["origin"],
            message_json=row["message_json"],
            runtime_json=row["runtime_json"],
        )
        for row in rows
    ]


def delete(store: SessionStore, session_id: str, entry_id: str) -> bool:
    """删掉一条并压缩序号；不存在时返回 ``False``（wuu 用 (found, err) 表达，不抛错）。"""
    if not session_id.strip() or not entry_id.strip():
        raise HeldWorkInvalid("held_user_work 删除需要 session_id 与 id")

    def _apply(conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT position FROM held_user_work WHERE session_id = ? AND id = ?",
            (session_id, entry_id),
        ).fetchone()
        if row is None:
            return False
        position = int(row["position"])
        conn.execute(
            "DELETE FROM held_user_work WHERE session_id = ? AND id = ?", (session_id, entry_id)
        )
        # B-128：先取负躲开 UNIQUE(session_id, position)，再统一归正。顺序不可反。
        # 实测说明（诚实标注）：本机的朴素 `position - 1` 写法**测不出红**——SQLite 不保证
        # UPDATE 的扫描序，但常见执行计划按升序逐行处理，低位恰好先被释放。
        # 取负两步法是母本写明并分两段执行的防御写法（held_user_work.go L138-147 注释原文），
        # 本仓照搬；该条坑因此是“防御性语义”而非“本仓已观测故障”，不得写成后者。
        conn.execute(
            "UPDATE held_user_work SET position = -position - 1"
            " WHERE session_id = ? AND position > ?",
            (session_id, position),
        )
        conn.execute(
            "UPDATE held_user_work SET position = -position - 2"
            " WHERE session_id = ? AND position < 0",
            (session_id,),
        )
        return True

    return store.write(_apply)
