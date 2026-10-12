"""内核事件 → 协议通知（protocol.md §4 事件族的唯一映射处）。

映射集中在一处是有意的：事件名散在 handler 里就会漂到与 schema 不一致（这正是
`tests/architecture/test_serve_names_are_contracted.py` 要防的）。`delta` 与
`thinking` 是**传输态**：不发正文之外的第二种真相，也不落盘。
"""

from __future__ import annotations

from questor.engine.events import (
    AgentEvent,
    CompactNotice,
    Delta,
    RunStatus,
    ToolCallCompleted,
    ToolCallStarted,
    Usage,
)
from questor.serve.envelope import Notification

__all__ = ["PROTOCOL_NOTIFICATIONS", "notification_of"]

#: 本模块可能产出的通知族名（护栏测试拿它逐字对照 app_server schema 与 protocol §4）
PROTOCOL_NOTIFICATIONS = frozenset(
    {
        "delta",
        "item/started",
        "item/completed",
        "turn/usage",
        "run/status",
        "notice/compact",
    }
)


def notification_of(event: AgentEvent) -> Notification | None:
    """一个内核事件 → 零或一条通知；不属于协议事件族的返回 ``None``。

    故意不发的三类：
    - `Thinking`：protocol §4 里没有推理族名，族名要连呈现与持久化形状一起定（M3）；
      本期靠 CLI 与 `notice/compact` 旁证保持可见，不为它造一个契约外名字。
    - `LoopCompleted` / `LoopFailed`：终态事实已由 `run/status` 通知给出，再发一条就是两套真相。
    - `Converging`：预算收敛是循环内部节拍（与 delta 同一取舍）。
    """
    if isinstance(event, Delta):
        return Notification("delta", {"text": event.text})
    if isinstance(event, ToolCallStarted):
        return Notification(
            "item/started",
            {
                "tool_use_id": event.tool_use_id,
                "name": event.name,
                "arguments": event.arguments,
            },
        )
    if isinstance(event, ToolCallCompleted):
        return Notification(
            "item/completed",
            {
                "tool_use_id": event.tool_use_id,
                "name": event.name,
                "is_error": event.is_error,
                "elapsed_s": event.elapsed_s,
            },
        )
    if isinstance(event, Usage):
        return Notification(
            "turn/usage",
            {
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "cache_read": event.cache_read,
                "cache_creation": event.cache_creation,
            },
        )
    if isinstance(event, RunStatus):
        return Notification("run/status", {"status": event.status})
    if isinstance(event, CompactNotice):
        return Notification(
            "notice/compact",
            {
                "kind": event.kind,
                "before_tokens": event.before_tokens,
                "after_tokens": event.after_tokens,
                "reason": event.reason,
            },
        )
    return None  # TurnStarted/Thinking/Converging/Loop* 不入协议族（见 docstring）
