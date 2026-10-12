"""测试基建：脚本化模型（实现 :class:`questor.engine.model.ModelPort`）。

与 fake_keyring 的 contextmanager 模式不同：fake model 经**构造注入**给 Engine
（ModelPort 是内核 port，无全局注册表可安装/恢复），所以是普通类 + 可断言的
``requests`` 记录。错误语义对齐真实后端：脚本耗尽时显式报错而不是静默复用最后一轮
（掩盖测试假设错误）。

M2.3 形状变化（与 port 同步）：``stream`` 收 :class:`ModelRequest`、产出
:class:`LLMUsage`、暴露 ``capabilities``、支持 ``aclose``；输出上限不再由
`set_max_output_tokens` 钩子改写状态，而是逐请求从 ``request.max_output_tokens``
读回（B-08 的断言点因此变成"下一次请求携带的上限"）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

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
    WindowSource,
)

_DEFAULT_CAPABILITIES = ModelCapabilities(
    context_window=32_000,
    max_output_tokens=8_000,
    supports_thinking=True,
    supports_prompt_cache=True,
    window_source=WindowSource.CONFIG,
)


@dataclass(frozen=True)
class ScriptedTurn:
    """一轮脚本化响应：文本（按 delta_splits 切片）+ 推理 + 工具调用 + 终局。"""

    text: str = ""
    thinking: str = ""
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    stop_reason: str = "end_turn"
    input_tokens: int = 10
    output_tokens: int = 5
    cache_read: int = 0
    cache_creation: int = 0
    delta_splits: int = 2


class FakeModel:
    """按脚本逐轮回放；记录每次请求供测试断言（含被提后的输出上限）。"""

    def __init__(
        self,
        turns: Sequence[ScriptedTurn],
        *,
        capabilities: ModelCapabilities = _DEFAULT_CAPABILITIES,
    ) -> None:
        self._turns = list(turns)
        self._index = 0
        self.requests: list[ModelRequest] = []
        self.closed = False
        self._capabilities = capabilities

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    async def aclose(self) -> None:
        self.closed = True

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        if self._index >= len(self._turns):
            raise AssertionError(
                f"FakeModel 脚本耗尽（第 {self._index} 轮被请求，脚本只有 {len(self._turns)} 轮）"
            )
        turn = self._turns[self._index]
        self._index += 1
        self.requests.append(request)

        async def _generate() -> AsyncIterator[StreamEvent]:
            if turn.thinking:
                yield StreamThinking(text=turn.thinking)
            for piece in _split_text(turn.text, turn.delta_splits):
                if piece:
                    yield StreamDelta(text=piece)
            for call in turn.tool_calls:
                yield StreamToolCall(call=call)
            yield StreamEnd(
                stop_reason=turn.stop_reason,
                usage=LLMUsage(
                    input_tokens=turn.input_tokens,
                    output_tokens=turn.output_tokens,
                    cache_read=turn.cache_read,
                    cache_creation=turn.cache_creation,
                ),
            )

        return _generate()


def _split_text(text: str, parts: int) -> list[str]:
    if parts <= 1 or not text:
        return [text]
    size = max(1, len(text) // parts)
    return [text[i : i + size] for i in range(0, len(text), size)]
