"""ModelPort：内核定义的模型接口（R1——providers M2.3 注册实现，循环不按厂商分支）。

流式事件的最小集（providers 负责把各家 SDK 的增量装配成这些形状）：
``StreamDelta``（正文增量）→ ``StreamToolCall``（完整工具调用，M2.2 粒度）→
``StreamEnd``（终局 + 用量）。thinking/delta 组装等复杂形态随 providers 物化。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from questor.engine.conversation import Message, ToolCall  # noqa: F401 —— ToolCall 再导出

__all__ = ["LLMResponse", "ModelPort", "StreamDelta", "StreamEnd", "StreamToolCall", "ToolCall"]


@dataclass(frozen=True)
class StreamDelta:
    text: str


@dataclass(frozen=True)
class StreamToolCall:
    call: ToolCall


@dataclass(frozen=True)
class StreamEnd:
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens" | ...
    input_tokens: int = 0
    output_tokens: int = 0


StreamEvent = StreamDelta | StreamToolCall | StreamEnd


@dataclass(frozen=True)
class LLMResponse:
    """一次模型响应的聚合结果（由循环从流事件拼装）。"""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class ModelPort(Protocol):
    """模型客户端端口。set_max_output_tokens 是 max_tokens 恢复的提钩（B-08）。"""

    def stream(
        self, messages: list[Message], system: str, tools: list[dict[str, object]]
    ) -> AsyncIterator[StreamEvent]: ...

    def set_max_output_tokens(self, tokens: int) -> None: ...
