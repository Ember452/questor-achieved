"""AgentEvent：循环对外吐出的事件（消费方 = serve/cli/UI；持久化映射在同文件）。

事件名逐字对齐 protocol.md §4 的事件族：``delta`` / ``item/started`` /
``item/completed`` / ``turn/usage`` / ``run/status``。``turn/queued`` 等旁态族随
M3 habena；``notice/compact`` 随 M2.3 context。

持久化边界（单一真相纪律）：``delta`` 是**传输态**——正文以 message Item 为
唯一真相，delta 不落盘（重复存储制造两套真相）；``TurnStarted``/``Converging``/
``LoopCompleted``/``LoopFailed`` 是循环内部节拍，其事实已由 run 状态与 message
Item 承载。落盘的事件族 = ``item/started`` / ``item/completed`` / ``turn/usage``
/ ``run/status``（``event_type_of`` 返回 "internal" 者不落盘）。
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
class Thinking:
    """推理增量（可见柱：过程不得为了好看而隐去）。

    与 ``Delta`` 同为**传输态**，不落盘；协议侧的事件族名要等 M3 前端真接时连呈现与
    持久化形状一起定（现在先占住内核语义，避免事后改 port）——因此 ``event_type_of``
    暂归 "internal"，并在 development-plan 留痕。
    """

    text: str


@dataclass(frozen=True)
class CompactNotice:
    """压缩通知（`notice/compact`）：started/compacted/noop/breaker_open/failed。

    不落盘为 Event——压缩真相是 `context.boundary` 记录（ADR-0017），事件是推送态；
    两边各存一转会漂移（与 delta 同一取舍）。
    """

    kind: str
    before_tokens: int = 0
    after_tokens: int = 0
    reason: str = ""


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
    #: 缓存命中/新建分量：只报 input/output 就看不出一条运行到底省了多少（B-28 的观测面）
    cache_read: int = 0
    cache_creation: int = 0


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


@dataclass(frozen=True)
class SteerConsumed:
    """插话消费通知（turn/steered）：iteration 起点前从 inbox.drain() 拿到、写入
    会话历史并落 Origin.STEER 消息 Item 后发出（B-67/94）。

    不落盘为 Event：正文侧的 steered Item 才是真相（与 delta 同一取舍）；
    client_id 回链供宿主幂等判重（B-63）。
    """

    thread_id: str
    client_id: str
    content: str


AgentEvent = (
    TurnStarted
    | Delta
    | Thinking
    | ToolCallStarted
    | ToolCallCompleted
    | Usage
    | RunStatus
    | CompactNotice
    | Converging
    | LoopCompleted
    | LoopFailed
    | SteerConsumed
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
    if isinstance(event, CompactNotice):
        return "notice/compact"
    if isinstance(event, SteerConsumed):
        return "turn/steered"
    return "internal"  # TurnStarted/Thinking/Converging/Loop* 是循环内部节拍，不单独入协议族
