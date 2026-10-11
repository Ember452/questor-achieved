"""会话内存形状与用量锚点（FlowCoder conversation.py 的最小重写）。

M2.2 边界：会话是 **turn 作用域**——每个 run 从空会话开始（历史重建/压缩/
跨 turn resume 随 M2.3 context 落地，见设计篇留痕）。Message 只有 user/assistant
两个角色 + 工具块；工具结果聚成一条 content 为空的 user 消息（FlowCoder 同款）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from questor.engine.constants import CHARS_PER_TOKEN

Role = str  # "user" | "assistant"


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class ToolCall:
    """模型请求的一次工具调用（会话历史的组成部分；model 层复用同一形状）。"""

    id: str
    name: str
    arguments: dict[str, object]


@dataclass
class Message:
    role: Role
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResultBlock] = field(default_factory=list)


def estimate_tokens(messages: list[Message]) -> int:
    """字符估算（锚点后的尾部用）；锚点内的真实用量见 Conversation.current_tokens。"""
    chars = sum(len(m.content) for m in messages)
    return int(chars / CHARS_PER_TOKEN)


class Conversation:
    """turn 内的对话历史 + 用量锚点（真实 API 用量优先，尾部字符估算兜底）。"""

    def __init__(self) -> None:
        self.history: list[Message] = []
        self.baseline_tokens = 0
        self.anchor_count = 0  # 记锚点时的消息数（锚点后的消息才走估算）

    def add_user(self, content: str) -> None:
        self.history.append(Message(role="user", content=content))

    def add_assistant(self, content: str, tool_calls: list[ToolCall]) -> None:
        self.history.append(Message(role="assistant", content=content, tool_calls=tool_calls))

    def add_tool_results(self, results: list[ToolResultBlock]) -> None:
        self.history.append(Message(role="user", content="", tool_results=results))

    def record_usage_anchor(self, input_tokens: int, output_tokens: int) -> None:
        """真实 API 用量锚点：锚点内的 tokens 信任 API 值，锚点后追加消息走估算。"""
        self.baseline_tokens = input_tokens + output_tokens
        self.anchor_count = len(self.history)

    def current_tokens(self) -> int:
        tail = estimate_tokens(self.history[self.anchor_count :])
        return self.baseline_tokens + tail
