"""thread / turn / run / item 四族的 param·result·notification 形状（protocol.md §3/§4）。

# Reimplements wuu@wuu-main internal/appserver/protocol.go#L1428-2632 —— 逐字段取 Go json tag：
#   方法 param/result：ThreadStart #L1428/#L1556、ThreadResume #L1577、TurnStart #L1967/#L1998、
#   TurnSteer #L2095/#L2106、TurnQueue #L2051/#L2072、QueuedTurn #L2064、RunStart #L2006/#L2016、
#   RunInterrupt #L2026/#L2031。通知：ThreadStarted #L2145、TurnStarted #L2178、TurnCompleted
#   #L2250、TurnUsage #L2232、ItemStarted #L2570、ItemCompleted #L2577、AgentMessageDelta #L2591、
#   AgentMessageReplace #L2598、ToolCallOutput #L2626。
# pitfalls: B-63（client_id 幂等）B-64（expected_turn_id）B-66（写时 diff 随 result）

`turn/steer` 的 `expected_turn_id` **必填非 Optional**（wuu 无 omitempty，#L2100）：
空串=旧客户端兼容放行、非空不匹配当前 turn=拒（B-64）。`turn/start`/`queue` 的 `client_id`
是幂等键（B-63）。`images`/`files` 用不透明 list[dict]（base64 附件形状随 Phase 2 收紧）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from questor.schemas.app_server.entities import Run, Thread, ThreadItem, Turn

__all__ = [
    "AgentMessageDeltaNotification",
    "AgentMessageReplaceNotification",
    "ItemCompletedNotification",
    "ItemStartedNotification",
    "QueuedTurn",
    "RunInterruptParams",
    "RunInterruptResult",
    "RunStartParams",
    "RunStartResult",
    "ThreadResumeParams",
    "ThreadStartedNotification",
    "ThreadStartParams",
    "ThreadStartResult",
    "ToolCallOutputNotification",
    "TurnCompletedNotification",
    "TurnQueueParams",
    "TurnQueueResult",
    "TurnStartedNotification",
    "TurnSteerParams",
    "TurnSteerResult",
    "TurnStartParams",
    "TurnStartResult",
    "TurnUsageNotification",
    # 补齐对话面通知（names.py 声明的 thread/resumed、turn/held、run/started|updated、
    # item/reasoning/*、item/toolCall/delta）——消除"声明了但无模型"的子集缺口。
    "ReasoningDeltaNotification",
    "ReasoningReplaceNotification",
    "ToolCallDeltaNotification",
    "ThreadResumedNotification",
    "TurnHeldNotification",
    "RunStartedNotification",
    "RunUpdatedNotification",
]


class _Req(BaseModel):
    """请求 param 基类：可变态（构造期），extra=forbid 拒未知键。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _Notif(BaseModel):
    """通知 payload 基类：frozen + extra=forbid。"""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


# ---------------- thread ----------------


class ThreadStartParams(_Req):
    model_options: dict[str, str] | None = None
    # project / 其余可选项随 thread 面 handler 移植补（不凭猜扩必填）。


class ThreadStartResult(_Notif):
    thread: Thread


class ThreadResumeParams(_Req):
    session_id: str | None = None
    response_only: bool = False


class ThreadStartedNotification(_Notif):
    thread: Thread


# ---------------- turn ----------------


class TurnStartParams(_Req):
    thread_id: str
    prompt: str
    client_id: str | None = None
    images: list[dict[str, Any]] | None = None
    files: list[dict[str, Any]] | None = None
    permission_mode: str | None = None


class TurnStartResult(_Notif):
    turn: Turn


class TurnSteerParams(_Req):
    thread_id: str
    prompt: str
    expected_turn_id: str  # 必填（B-64）；空串=兼容放行
    client_id: str | None = None
    images: list[dict[str, Any]] | None = None
    files: list[dict[str, Any]] | None = None


class TurnSteerResult(_Notif):
    turn_id: str


class QueuedTurn(_Notif):
    id: str
    thread_id: str
    preview: str | None = None
    image_count: int | None = None
    file_count: int | None = None


class TurnQueueParams(_Req):
    thread_id: str
    prompt: str
    hold: bool = False
    client_id: str | None = None
    images: list[dict[str, Any]] | None = None
    files: list[dict[str, Any]] | None = None
    permission_mode: str | None = None


class TurnQueueResult(_Notif):
    queued: QueuedTurn


class TurnStartedNotification(_Notif):
    thread_id: str
    turn: Turn
    queue_id: str | None = None


class TurnCompletedNotification(_Notif):
    thread_id: str
    turn: Turn
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    context_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cache_read_tokens: int | None = None
    finish_reason: str | None = None
    stop_reason: str | None = None


class TurnUsageNotification(_Notif):
    thread_id: str
    turn_id: str
    input_tokens: int
    output_tokens: int
    model: str | None = None
    context_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cache_read_tokens: int | None = None
    context_window_tokens: int | None = None


# ---------------- run ----------------


class RunStartParams(_Req):
    thread_id: str
    prompt: str
    request: dict[str, Any]  # execution.Request 不透明，Phase 2a 收紧（P1-7）
    images: list[dict[str, Any]] | None = None
    files: list[dict[str, Any]] | None = None
    permission_mode: str | None = None
    output_schema: dict[str, Any] | None = None


class RunStartResult(_Notif):
    run: Run


class RunInterruptParams(_Req):
    run_id: str
    reason: str | None = None


class RunInterruptResult(_Notif):
    run: Run


# ---------------- item ----------------


class ItemStartedNotification(_Notif):
    thread_id: str
    turn_id: str
    item: ThreadItem
    started_at_ms: int


class ItemCompletedNotification(_Notif):
    thread_id: str
    turn_id: str
    item: ThreadItem
    completed_at_ms: int


class AgentMessageDeltaNotification(_Notif):
    thread_id: str
    turn_id: str
    item_id: str
    delta: str


class AgentMessageReplaceNotification(_Notif):
    thread_id: str
    turn_id: str
    item_id: str
    text: str


class ToolCallOutputNotification(_Notif):
    thread_id: str
    turn_id: str
    item_id: str
    delta: str
    tool_result_detail: dict[str, Any] | None = None


class ReasoningDeltaNotification(_Notif):
    """锚 protocol.go#L2605 —— 推理增量（追加态，与 agentMessage/delta 同形）。"""

    thread_id: str
    turn_id: str
    item_id: str
    delta: str


class ReasoningReplaceNotification(_Notif):
    """锚 protocol.go#L2612 —— 推理整体替换态（P1-8 两态之覆盖）。"""

    thread_id: str
    turn_id: str
    item_id: str
    text: str


class ToolCallDeltaNotification(_Notif):
    """锚 protocol.go#L2619 —— 工具入参流（args 逐段追加）。"""

    thread_id: str
    turn_id: str
    item_id: str
    delta: str


class ThreadResumedNotification(_Notif):
    """锚 protocol.go#L2149 —— thread/resumed 携未决/待投输入（HeldUserMessage 内部透传）。"""

    thread: Thread
    held_user_messages: list[dict[str, Any]] | None = None
    pending_user_messages: list[dict[str, Any]] | None = None


class TurnHeldNotification(_Notif):
    """锚 protocol.go#L2203 —— 排队输入因 admission 失败被持留；error 非空=持留原因。"""

    thread_id: str
    messages: list[dict[str, Any]]
    error: str | None = None


class RunStartedNotification(_Notif):
    """锚 protocol.go#L2035。"""

    run: Run


class RunUpdatedNotification(_Notif):
    """锚 protocol.go#L2039 —— 节流通知（非逐 token）。"""

    run: Run
