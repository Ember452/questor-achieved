"""测试基建：脚本化模型（实现 :class:`questor.engine.model.ModelPort`）。

与 fake_keyring 的 contextmanager 模式不同：fake model 经**构造注入**给 Engine
（ModelPort 是内核 port，无全局注册表可安装/恢复），所以是普通类 + 可断言的
``requests``/``max_output_tokens`` 记录。错误语义对齐真实后端：脚本耗尽时显式
报错而不是静默复用最后一轮（掩盖测试假设错误）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from questor.engine.conversation import Message
from questor.engine.model import StreamDelta, StreamEnd, StreamToolCall, ToolCall


@dataclass(frozen=True)
class ScriptedTurn:
    """一轮脚本化响应：文本（按 delta_splits 切片）+ 工具调用 + 终局。"""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    stop_reason: str = "end_turn"
    input_tokens: int = 10
    output_tokens: int = 5
    delta_splits: int = 2


class FakeModel:
    """按脚本逐轮回放；记录每次请求供测试断言。"""

    def __init__(self, turns: Sequence[ScriptedTurn]) -> None:
        self._turns = list(turns)
        self._index = 0
        self.requests: list[tuple[list[Message], str, list[dict[str, object]]]] = []
        self.max_output_tokens: int | None = None

    def stream(
        self, messages: list[Message], system: str, tools: list[dict[str, object]]
    ) -> AsyncIterator[StreamDelta | StreamToolCall | StreamEnd]:
        if self._index >= len(self._turns):
            raise AssertionError(
                f"FakeModel 脚本耗尽（第 {self._index} 轮被请求，脚本只有 {len(self._turns)} 轮）"
            )
        turn = self._turns[self._index]
        self._index += 1
        self.requests.append((list(messages), system, list(tools)))

        async def _generate() -> AsyncIterator[StreamDelta | StreamToolCall | StreamEnd]:
            pieces = _split_text(turn.text, turn.delta_splits)
            for piece in pieces:
                if piece:
                    yield StreamDelta(text=piece)
            for call in turn.tool_calls:
                yield StreamToolCall(call=call)
            yield StreamEnd(
                stop_reason=turn.stop_reason,
                input_tokens=turn.input_tokens,
                output_tokens=turn.output_tokens,
            )

        return _generate()

    def set_max_output_tokens(self, tokens: int) -> None:
        """B-08 提钩：记录调用，测试断言上限被提过。"""
        self.max_output_tokens = tokens


def _split_text(text: str, parts: int) -> list[str]:
    if parts <= 1 or not text:
        return [text]
    size = max(1, len(text) // parts)
    return [text[i : i + size] for i in range(0, len(text), size)]
