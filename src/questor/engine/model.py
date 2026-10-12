"""ModelPort：内核定义的模型接口（R1——providers 注册实现，循环不按厂商分支）。

形状在 M2.3 定死（ADR-0016/0018）：入参是一个**请求对象**而不是位置参数串，
新字段（thinking、缓存边界、输出上限）不再需要改签名；出参是 `schemas.llm` 里的
流事件族。类型住在 `schemas` 这一无依赖层，好让 providers 不必反向 import 内核。

**预算归调用方**（M2.3 改过一处 M2.2 设计）：输出上限由 `ModelRequest.max_output_tokens`
逐次携带，不再用 `set_max_output_tokens` 钩子改写客户端内部状态——同一个数字只能有一处
真相，且并发共享一个客户端时逐请求携带才是正确的（B-08）。

`aclose` 是生命周期收口点（B-83）：HTTP 客户端不关就会漏连接，而"谁创建谁关闭"
的边界必须由 port 说清楚。

`InboxPort` 是 M3a-3 给 engine 看的最小插话面：一个 `async drain()` 方法。engine 不
反向 import habena（避免结构 §5 中 engine 白名单外依赖），运行时传入 `HabenaInbox`
实例即可。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from questor.schemas.habena import SteerMessage
from questor.schemas.llm import (
    LLMUsage,
    ModelCapabilities,
    ModelRequest,
    StreamDelta,
    StreamEnd,
    StreamEvent,
    StreamThinking,
    StreamToolCall,
    ToolCall,
)

__all__ = [
    "LLMResponse",
    "InboxPort",
    "ModelPort",
    "ModelRequest",
    "StreamDelta",
    "StreamEnd",
    "StreamEvent",
    "StreamThinking",
    "StreamToolCall",
    "ToolCall",
]


@dataclass(frozen=True)
class LLMResponse:
    """一次模型响应的聚合结果（由循环从流事件拼装）。"""

    text: str = ""
    thinking: str = ""
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    stop_reason: str = "end_turn"
    usage: LLMUsage = field(default_factory=LLMUsage)


@runtime_checkable
class ModelPort(Protocol):
    """模型客户端端口：能力声明 + 逐请求流式调用 + 生命周期收口。

    三项都是必备：漏 `aclose` 会漏连接（只在长跑里显形，B-83）；漏 `capabilities`
    则预算只能靠猜（B-82）。
    """

    @property
    def capabilities(self) -> ModelCapabilities: ...

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]: ...

    async def aclose(self) -> None: ...


@runtime_checkable
class InboxPort(Protocol):
    """插话收件箱端口（M3a-3）：engine 只看 drain()，不反向 import habena。

    实现方：`questor.habena.HabenaInbox`。engine 依赖 habena 会破结构 §5 白名单
    且形成环（habena 允许 import engine）；本 port 把两侧隔开，运行时传入实例。
    """

    async def drain(self) -> list[SteerMessage]: ...
