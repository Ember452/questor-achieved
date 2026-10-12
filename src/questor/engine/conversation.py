"""会话内存形状与用量锚点（FlowCoder conversation.py 的最小重写）。

消息形状本身住在 :mod:`questor.schemas.llm`（单一来源——providers 与 context 读的是
同一个 `Message`，不是各自复刻一份）；本模块只负责**会话级**的追加与用量锚点。

M2.3 边界：跨 turn resume / 压缩 / 历史重建在 :mod:`questor.context`，本模块只提供
它们要读的锚点与尾部估算。
"""

from __future__ import annotations

from questor.schemas.llm import (
    CHARS_PER_TOKEN,
    LLMUsage,
    Message,
    Role,
    ToolCall,
    ToolResultBlock,
    estimate_tokens,
)

__all__ = [
    "CHARS_PER_TOKEN",
    "Conversation",
    "Message",
    "Role",
    "ToolCall",
    "ToolResultBlock",
    "estimate_tokens",
]


class Conversation:
    """turn 内的对话历史 + 用量锚点（真实 API 用量优先，尾部字符估算兜底，B-28）。"""

    def __init__(self, history: list[Message] | None = None) -> None:
        #: 历史只追加不就地改写（`Message` 是 frozen 的，改写只能产生新对象）
        self.history: list[Message] = list(history or [])
        self.baseline_tokens = 0
        self.anchor_count = 0  # 记锚点时的消息数（锚点后的消息才走估算）

    def add_user(self, content: str) -> None:
        self.history.append(Message(role="user", content=content))

    def add_assistant(self, content: str, tool_calls: list[ToolCall]) -> None:
        self.history.append(Message(role="assistant", content=content, tool_calls=tool_calls))

    def add_tool_results(self, results: list[ToolResultBlock]) -> None:
        self.history.append(Message(role="user", content="", tool_results=results))

    def record_usage_anchor(self, usage: LLMUsage) -> None:
        """真实 API 用量锚点：锚点内的 tokens 信任 API 值，锚点后追加的消息才走估算。

        缓存分量必须一起计入基线——只读缓存的那部分 token 同样占窗口，忽略它会让
        压缩阈值永远晚于真实压力（B-28 的另一半）。
        """
        self.baseline_tokens = usage.total_input() + usage.output_tokens
        self.anchor_count = len(self.history)

    def replace_history(self, messages: list[Message]) -> None:
        """压缩后整体换成新视图，并把用量锚点清零。

        不清零就不对：旧锚点的 `anchor_count` 指的是压缩前的消息数，拿它算尾部会得出
        错总量，而阈值错方向的后果是"该压时不压"（B-28）。
        """
        self.history = list(messages)
        self.baseline_tokens = 0
        self.anchor_count = 0

    def current_tokens(self) -> int:
        tail = estimate_tokens(self.history[self.anchor_count :])
        return self.baseline_tokens + tail
