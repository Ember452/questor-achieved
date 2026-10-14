"""gesta —— 会话权威库（SQLite）+ 验收导出（overview §6、data-model v2.0、ADR-0041）。

三柱归属：**可验证**的地基——会话正文 append-only、可回放，"它说做完了"能指回当时的记录；
同时是**可干预**的地基（inbox 幂等投递 + held_user_work 未决输入，运行中插话重启不丢）。

会话真相源 = 本模块下的 SQLite 库（``schema``/``session_store``/``inbox``/``held_work``）；
``store.py``/``writer.py`` 是**旧 JSONL 世界**，仍被未重写的 engine/serve 依赖，随
Phase 2a 的 serve 重写同批移出工作树（处置与理由见 ``docs/research/port-ledger.md``
"Phase 2a · gesta" 段）。两存期间**新代码一律用新门面**，旧门面只服务旧调用方。

# Ported from wuu@2026.10.6 internal/session/{session.go,inbox.go,held_user_work.go}
# 行为规格：docs/specs/behavior-gesta-wuu.md；契约：docs/architecture/data-model.md v2.0
"""

from __future__ import annotations

from questor.gesta import held_work, inbox
from questor.gesta.errors import (
    ControlChanged,
    ControlInvalid,
    GestaError,
    HeldWorkInvalid,
    InboxInvalid,
    RevisionConflict,
    SequenceRejected,
    SessionBusy,
    SessionExists,
    SessionNotFound,
    StoreCorrupted,
)
from questor.gesta.records import (
    CONTROL_STATES,
    HELD_ORIGINS,
    Control,
    HeldUserWorkEntry,
    InboxMessage,
    MessageUsage,
    SessionControls,
    SessionInfo,
    StoredMessage,
)
from questor.gesta.schema import DB_FILE_NAME
from questor.gesta.session_store import SessionStore, default_db_path
from questor.gesta.store import (  # 旧 JSONL 世界，随 serve 重写同批移出
    ThreadNotFound,
    ThreadStoreError,
    ThreadView,
    ToolResultSpill,
    add_item,
    add_run,
    add_turn,
    append_event,
    create_thread,
    delete_thread,
    list_threads,
    load_thread,
    rebuild_index,
    rename_thread,
    set_thread_flags,
    spill_tool_result,
    transition_run,
)
from questor.gesta.transitions import InvalidTransition, transition
from questor.gesta.writer import ThreadWriter

__all__ = [
    # —— 新：SQLite 权威库（Phase 2a 起的唯一写路径）——
    "DB_FILE_NAME",
    "SessionStore",
    "default_db_path",
    "inbox",
    "held_work",
    "StoredMessage",
    "MessageUsage",
    "SessionInfo",
    "SessionControls",
    "InboxMessage",
    "HeldUserWorkEntry",
    "Control",
    "HELD_ORIGINS",
    "CONTROL_STATES",
    "GestaError",
    "SessionNotFound",
    "SessionExists",
    "SessionBusy",
    "ControlChanged",
    "ControlInvalid",
    "InboxInvalid",
    "HeldWorkInvalid",
    "StoreCorrupted",
    "RevisionConflict",
    "SequenceRejected",
    # —— 旧：JSONL 世界（仅服务尚未重写的调用方，Phase 2a 同批移出）——
    "InvalidTransition",
    "ThreadNotFound",
    "ThreadStoreError",
    "ThreadView",
    "ThreadWriter",
    "ToolResultSpill",
    "add_item",
    "add_run",
    "add_turn",
    "append_event",
    "create_thread",
    "delete_thread",
    "list_threads",
    "load_thread",
    "rebuild_index",
    "rename_thread",
    "set_thread_flags",
    "spill_tool_result",
    "transition",
    "transition_run",
]
