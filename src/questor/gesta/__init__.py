"""gesta —— 会话记录与验收导出（overview §6）。

三柱归属：**可验证**的地基——会话正文 append-only JSONL 唯一真相源，
落盘可回放，"它说做完了"能指回当时的记录。

# Reimplements wuu@wuu-main internal/agentthread/store.go — pitfalls: B-45 B-46 B-74
# 行为规格：docs/specs/behavior-gesta-wuu.md；契约：docs/architecture/data-model.md v1.1
"""

from __future__ import annotations

from questor.gesta.store import (
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
