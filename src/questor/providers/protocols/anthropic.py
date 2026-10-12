"""Anthropic messages 协议：请求体装配 + SSE 帧翻译（自建 wire 层，ADR-0016）。

形状参照 FlowCoder `client/core.py` 的 `AnthropicClient` 与
`providers/anthropic_streaming.py`（语义对照，未搬代码）；三处刻意不同：

1. **缓存断点打在稳定前缀末块**（FlowCoder 把 system 拼成一整串、无断点——B-81）；
2. **thinking 独立成 :class:`StreamThinking`**（FlowCoder 把推理聚合成 ThinkingComplete，
   中途不可见；本项目要求过程可摊开）；
3. **工具参数解析失败不静默**：终局是 ``max_tokens`` 视为截断丢弃并记日志，否则上抛
   :class:`ProtocolError`（FlowCoder 的 ``response.failed`` 被白名单静默丢弃是反例）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from questor.providers.errors import ProtocolError
from questor.providers.http import build_client, open_sse_stream
from questor.providers.spec import ModelCapabilities, ModelSpec
from questor.providers.sse import SSEEvent
from questor.schemas.llm import (
    LLMUsage,
    Message,
    ModelRequest,
    StreamDelta,
    StreamEnd,
    StreamEvent,
    StreamThinking,
    StreamToolCall,
    ToolCall,
)

__all__ = ["AnthropicMessagesClient", "build_anthropic_body", "system_blocks"]

logger = logging.getLogger(__name__)

MESSAGES_PATH = "/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def system_blocks(prompt: Any, *, supports_cache: bool) -> list[dict[str, Any]]:
    """system 块 → Anthropic 文本块；缓存断点只打在**最后一个可缓存块**上。

    ``supports_cache`` 来自能力声明：端点不支持时整串照发、不打断点（诚实降级）。
    """
    blocks: list[dict[str, Any]] = []
    marker_index = prompt.cache_boundary - 1 if supports_cache and prompt.cache_boundary else -1
    for index, block in enumerate(prompt.blocks):
        entry: dict[str, Any] = {"type": "text", "text": block.text}
        if index == marker_index:
            entry["cache_control"] = {"type": "ephemeral"}
        blocks.append(entry)
    return blocks


def to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """会话历史 → Anthropic 消息块（tool_result 归 user、tool_use 归 assistant）。"""
    out: list[dict[str, Any]] = []
    for message in messages:
        blocks: list[dict[str, Any]] = []
        if message.role == "user":
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            for result in message.tool_results:
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": result.tool_use_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                )
        else:
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            for call in message.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                )
        if not blocks:
            continue  # 空消息不发送：Anthropic 对空 content 直接 400
        out.append({"role": message.role, "content": blocks})
    return out


def build_anthropic_body(
    request: ModelRequest,
    *,
    model: str,
    max_output_tokens: int,
    supports_cache: bool,
    thinking: bool,
    temperature: float | None,
) -> dict[str, Any]:
    """装配一次 `/v1/messages` 请求体。"""
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_output_tokens,
        "system": system_blocks(request.prompt, supports_cache=supports_cache),
        "messages": to_anthropic_messages(request.messages),
        "stream": True,
    }
    if request.tools:
        body["tools"] = request.tools
    if temperature is not None:
        body["temperature"] = temperature
    if request.thinking and thinking:
        # 推理预算：留出正文空间，取输出上限的一半（Anthropic 要求 budget < max_tokens）
        body["thinking"] = {"type": "enabled", "budget_tokens": max(1024, max_output_tokens // 2)}
    return body


class _ToolBlock:
    """一个进行中的 tool_use 块：累积 ``input_json_delta`` 的分片。"""

    __slots__ = ("tool_id", "name", "parts", "broken")

    def __init__(self, tool_id: str, name: str) -> None:
        self.tool_id = tool_id
        self.name = name
        self.parts: list[str] = []
        self.broken = False


class AnthropicMessagesClient:
    """实现 :class:`questor.engine.model.ModelPort` 的 Anthropic messages 客户端。

    ``client`` 参数是测试接缝（注入 ``httpx.MockTransport`` 的假端点）；缺省时自建并在
    :meth:`aclose` 关闭——HTTP 客户端生命周期必须收口（B-83）。
    """

    def __init__(
        self,
        spec: ModelSpec,
        capabilities: ModelCapabilities,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._spec = spec
        self._capabilities = capabilities
        self._client = client if client is not None else build_client()
        self._owns_client = client is None
        self._closed = False

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    @property
    def model(self) -> str:
        return self._spec.model

    async def aclose(self) -> None:
        """关闭自持的 HTTP 客户端；注入的客户端由注入方负责（不越权关闭）。幂等。"""
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        api_key = self._spec.api_key.get_secret_value() if self._spec.api_key else ""
        headers = {
            "anthropic-version": ANTHROPIC_VERSION,
            "accept": "text/event-stream",
            "content-type": "application/json",
        }
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        body = build_anthropic_body(
            request,
            model=self._spec.model,
            max_output_tokens=request.max_output_tokens,
            supports_cache=self._capabilities.supports_prompt_cache,
            thinking=self._capabilities.supports_thinking,
            temperature=self._spec.temperature,
        )
        url = self._spec.base_url.rstrip("/") + MESSAGES_PATH
        async for event in self._translate(
            open_sse_stream(
                self._client,
                url,
                body=body,
                headers=self._headers(),
                first_event_timeout_s=self._spec.first_event_timeout_s,
                request_timeout_s=self._spec.request_timeout_s,
            )
        ):
            yield event

    async def _translate(self, frames: AsyncIterator[SSEEvent]) -> AsyncIterator[StreamEvent]:
        """帧 → StreamEvent；用量在 message_start（输入侧）与 message_delta（输出侧）分两段到达。"""
        input_tokens = output_tokens = 0
        cache_read = cache_creation = reasoning_tokens = 0
        stop_reason = "end_turn"
        blocks: dict[int, _ToolBlock] = {}
        pending_broken: list[_ToolBlock] = []

        async for frame in frames:
            payload = _decode(frame.data)
            if payload is None:
                continue
            kind = frame.event or str(payload.get("type", ""))
            if kind == "message_start":
                usage = _mapping(payload.get("message"), "usage")
                input_tokens = int(usage.get("input_tokens", 0) or 0)
                cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)
                cache_creation = int(usage.get("cache_creation_input_tokens", 0) or 0)
            elif kind == "content_block_start":
                block = _mapping(payload, "content_block")
                if block.get("type") == "tool_use":
                    blocks[_index(payload)] = _ToolBlock(
                        str(block.get("id", "")), str(block.get("name", ""))
                    )
            elif kind == "content_block_delta":
                delta = _mapping(payload, "delta")
                delta_type = delta.get("type")
                if delta_type == "text_delta":
                    yield StreamDelta(text=str(delta.get("text", "")))
                elif delta_type == "thinking_delta":
                    # 推理 token 不单列（Anthropic 把它计入输出侧），这里只保证推理过程可见
                    yield StreamThinking(text=str(delta.get("thinking", "")))
                elif delta_type == "input_json_delta":
                    block = blocks.get(_index(payload))
                    if block is not None:
                        block.parts.append(str(delta.get("partial_json", "")))
            elif kind == "content_block_stop":
                block = blocks.pop(_index(payload), None)
                if block is not None:
                    arguments = _parse_arguments(block)
                    if arguments is None:
                        block.broken = True
                        pending_broken.append(block)
                        continue
                    yield StreamToolCall(
                        call=ToolCall(id=block.tool_id, name=block.name, arguments=arguments)
                    )
            elif kind == "message_delta":
                delta = _mapping(payload, "delta")
                if delta.get("stop_reason"):
                    stop_reason = str(delta["stop_reason"])
                usage = _mapping(payload, "usage")
                output_tokens = int(usage.get("output_tokens", 0) or 0)
            elif kind == "message_stop":
                if pending_broken and stop_reason != "max_tokens":
                    names = ", ".join(block.name for block in pending_broken)
                    raise ProtocolError(f"工具参数流不完整且非截断终局（{names}）")
                if pending_broken:
                    logger.warning(
                        "max_tokens 截断导致工具参数不完整，丢弃未完成的调用：%s",
                        ", ".join(block.name for block in pending_broken),
                    )
                yield StreamEnd(
                    stop_reason=stop_reason,
                    usage=LLMUsage(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cache_read=cache_read,
                        cache_creation=cache_creation,
                        reasoning_tokens=reasoning_tokens,
                    ),
                )
                return
            elif kind == "error":
                error = _mapping(payload, "error")
                raise ProtocolError(
                    f"端点在流中报错：{error.get('type')} {error.get('message', '')}"
                )
            elif kind in ("ping", ""):
                continue
            # 未知事件类型：忽略但保留终局判定（各家扩展事件不该炸掉一次运行）

        raise ProtocolError("Anthropic 流在 message_stop 之前结束（缺少终局事件）")


def _decode(data: str) -> dict[str, Any] | None:
    if not data or data == "[DONE]":
        return None
    try:
        parsed = json.loads(data)
    except ValueError as exc:
        raise ProtocolError(f"SSE data 不是合法 JSON：{exc}") from exc
    if not isinstance(parsed, dict):
        raise ProtocolError(f"SSE data 不是对象：{type(parsed).__name__}")
    return parsed


def _index(payload: dict[str, Any]) -> int:
    return int(payload.get("index", 0) or 0)


def _mapping(container: Any, key: str) -> dict[str, Any]:
    if not isinstance(container, dict):
        return {}
    value = container.get(key)
    return value if isinstance(value, dict) else {}


def _parse_arguments(block: _ToolBlock) -> dict[str, object] | None:
    raw = "".join(block.parts)
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    return {str(key): value for key, value in parsed.items()}
