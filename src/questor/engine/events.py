"""AgentEvent：循环对外吐出的事件（消费方 = serve/cli/UI；持久化映射在同文件）。

事件名逐字对齐 protocol.md §4 的事件族：``delta`` / ``item/started`` /
``item/completed`` / ``turn/usage`` / ``run/status``。``turn/queued`` 等旁态族随
M3 habena；``notice/compact`` 随 M2.3 context。持久化映射：
``event_type_of(event)`` 给出应写入 gesta Event.type 的协议名。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurnStarted:
    turn: int


@dataclass(frozen=True)
class Delta:
    text: str


@dataclass(frozen=True)
class ToolCallStarted:
    tool_use_id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ToolCallCompleted:
    tool_use_id: str
    name: str
    output: str
    is_error: bool
    elapsed_s: float


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class RunStatus:
    status: str  # RunStatus.value


@dataclass(frozen=True)
class Converging:
    reason: str


@dataclass(frozen=True)
class LoopCompleted:
    total_turns: int
    final_text: str


@dataclass(frozen=True)
class LoopFailed:
    message: str


AgentEvent = (
    TurnStarted
    | Delta
    | ToolCallStarted
    | ToolCallCompleted
    | Usage
    | RunStatus
    | Converging
    | LoopCompleted
    | LoopFailed
)


def event_type_of(event: AgentEvent) -> str:
    """事件 → protocol.md §4 事件族名（gesta Event.type 的取值）。"""
    if isinstance(event, Delta):
        return "delta"
    if isinstance(event, (ToolCallStarted,)):
        return "item/started"
    if isinstance(event, (ToolCallCompleted,)):
        return "item/completed"
    if isinstance(event, Usage):
        return "turn/usage"
    if isinstance(event, RunStatus):
        return "run/status"
    return "internal"  # TurnStarted/Converging/Loop* 是循环内部节拍，不单独入协议族
