"""OpenAI chat/completions 协议：请求体装配 + SSE 帧翻译（ADR-0016 的第二条协议）。

这一条协议覆盖面最广（OpenAI 本体、vLLM、Ollama、Together、Azure 兼容端点…），
因此它的教训是"各家字段不一致"，实现按三处刻意的保守处理：

1. **无缓存断点概念**：能力声明 ``supports_prompt_cache=False``，system 块拼成单条消息
   并如实标注（不假装与 Anthropic 等价保护，ADR-0018）；
2. **推理字段名不统一**：`reasoning_content`（DeepSeek/Qwen 系）与 `reasoning` 都采，
   采不到就没有 StreamThinking——不猜；
3. **usage 可能在末尾独立 chunk**（需 ``stream_options.include_usage``）也可能没有；
   缺失时终局用量为 0 而非报错（预算侧另有字符估算兜底，B-28）。
"""

from __future__ import annotations

import json
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

__all__ = [
    "OpenAIChatCompletionsClient",
    "build_chat_body",
    "to_chat_messages",
    "to_chat_tools",
]

CHAT_COMPLETIONS_PATH = "/chat/completions"

#: finish_reason → StreamEnd.stop_reason（收敛到内核使用的词表，未知原样透传）
_STOP_REASON_MAP = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_calls": "tool_use",
    "length": "max_tokens",
    "content_filter": "end_turn",
}


def to_chat_messages(messages: list[Message], system_text: str) -> list[dict[str, Any]]:
    """会话历史 → chat/completions 消息数组（system 只有一条，置于首位）。"""
    out: list[dict[str, Any]] = []
    if system_text:
        out.append({"role": "system", "content": system_text})
    for message in messages:
        if message.role == "user":
            for result in message.tool_results:
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.tool_use_id,
                        "content": result.content,
                    }
                )
            if message.content:
                out.append({"role": "user", "content": message.content})
            continue
        entry: dict[str, Any] = {"role": "assistant", "content": message.content or None}
        if message.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in message.tool_calls
            ]
        if message.content or message.tool_calls:
            out.append(entry)
    return out


def to_chat_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """工具层 canonical 的 anthropic 平铺形状 → OpenAI function 包装。"""
    wrapped: list[dict[str, Any]] = []
    for tool in tools:
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            continue  # 无名字的工具不可寻址，宁缺勿造
        wrapped.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(tool.get("description", "")),
                    "parameters": tool.get("input_schema", {}),
                },
            }
        )
    return wrapped


def build_chat_body(
    request: ModelRequest,
    *,
    model: str,
    max_output_tokens: int,
    temperature: float | None,
) -> dict[str, Any]:
    """装配一次 `/chat/completions` 请求体。"""
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_output_tokens,
        "messages": to_chat_messages(request.messages, request.prompt.text),
        "stream": True,
        # 没有这一项，OpenAI 兼容端点在流式下不回 usage，预算锚点就永远是字符估算
        "stream_options": {"include_usage": True},
    }
    tools = to_chat_tools(request.tools)
    if tools:
        body["tools"] = tools
    if temperature is not None:
        body["temperature"] = temperature
    return body


class _CallSlot:
    """一个进行中的工具调用（按 ``index`` 归位，id/name 只在首个分片出现）。"""

    __slots__ = ("call_id", "name", "parts", "seen")

    def __init__(self) -> None:
        self.call_id = ""
        self.name = ""
        self.parts: list[str] = []
        self.seen = False

    @property
    def complete(self) -> bool:
        return bool(self.call_id and self.name)


class OpenAIChatCompletionsClient:
    """实现 :class:`questor.engine.model.ModelPort` 的 chat/completions 客户端。"""

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
        """关闭自持的 HTTP 客户端（B-83）。幂等；注入的客户端由注入方负责。"""
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        api_key = self._spec.api_key.get_secret_value() if self._spec.api_key else ""
        headers = {"accept": "text/event-stream", "content-type": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        return headers

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        body = build_chat_body(
            request,
            model=self._spec.model,
            max_output_tokens=request.max_output_tokens,
            temperature=self._spec.temperature,
        )
        url = _chat_endpoint(self._spec.base_url)
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
        slots: dict[int, _CallSlot] = {}
        usage = LLMUsage()
        finish_reason: str | None = None
        terminated = False

        async for frame in frames:
            # [DONE] 是 OpenAI 系的哨兵而非 JSON，必须先拦下来——拿它去 json.loads
            # 会把一个正常终局误报成协议错（各家端点都会发这一帧）。
            if frame.data.strip() == "[DONE]":
                terminated = True
                break
            payload = _decode(frame.data)
            if payload is None:
                continue
            if error := payload.get("error"):
                raise ProtocolError(f"端点在流中报错：{error}")
            usage_payload = payload.get("usage")
            if isinstance(usage_payload, dict):
                usage = _usage_from(usage_payload)
            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices:
                continue  # usage-only chunk：choices 为空只承载用量
            choice = choices[0] if isinstance(choices[0], dict) else {}
            if choice.get("finish_reason"):
                finish_reason = str(choice["finish_reason"])
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                continue
            if delta.get("reasoning_content"):
                yield StreamThinking(text=str(delta["reasoning_content"]))
            elif delta.get("reasoning"):
                yield StreamThinking(text=str(delta["reasoning"]))
            if delta.get("content"):
                yield StreamDelta(text=str(delta["content"]))
            for fragment in delta.get("tool_calls") or []:
                if not isinstance(fragment, dict):
                    continue
                slot = slots.setdefault(int(fragment.get("index", 0) or 0), _CallSlot())
                if fragment.get("id"):
                    slot.call_id = str(fragment["id"])
                function = fragment.get("function")
                if isinstance(function, dict):
                    if function.get("name"):
                        slot.name = str(function["name"])
                    if function.get("arguments"):
                        slot.parts.append(str(function["arguments"]))
                slot.seen = True

        if not terminated and finish_reason is None:
            raise ProtocolError("chat/completions 流既无 [DONE] 也无 finish_reason（终局缺失）")

        for index in sorted(slots):
            slot = slots[index]
            if not slot.complete:
                if finish_reason == "length":
                    continue  # 截断导致的不完整调用：交给上层的 max_tokens 恢复
                raise ProtocolError(f"工具调用分片不完整（index={index}）")
            try:
                arguments = _parse_arguments(slot)
            except ProtocolError:
                if finish_reason != "length":
                    raise
                continue
            yield StreamToolCall(
                call=ToolCall(id=slot.call_id, name=slot.name, arguments=arguments)
            )

        yield StreamEnd(
            stop_reason=_STOP_REASON_MAP.get(finish_reason or "", finish_reason or "end_turn"),
            usage=usage,
        )


def _chat_endpoint(base_url: str) -> str:
    """规范化端点：已含 ``/chat/completions`` 或已带 ``/v1`` 的情形都不重复拼路径。"""
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed
    if trimmed.endswith("/v1"):
        return trimmed + CHAT_COMPLETIONS_PATH
    return trimmed + CHAT_COMPLETIONS_PATH


def _decode(data: str) -> dict[str, Any] | None:
    if not data.strip():
        return None
    try:
        parsed = json.loads(data)
    except ValueError as exc:
        raise ProtocolError(f"SSE data 不是合法 JSON：{exc}") from exc
    return parsed if isinstance(parsed, dict) else None


def _usage_from(payload: dict[str, Any]) -> LLMUsage:
    details = payload.get("completion_tokens_details")
    reasoning = 0
    if isinstance(details, dict):
        reasoning = int(details.get("reasoning_tokens", 0) or 0)
    prompt_details = payload.get("prompt_tokens_details")
    cache_read = 0
    if isinstance(prompt_details, dict):
        # 各家 OpenAI 兼容端点用 cached_tokens 报缓存命中；报不出就是 0（不猜）
        cache_read = int(prompt_details.get("cached_tokens", 0) or 0)
    return LLMUsage(
        input_tokens=int(payload.get("prompt_tokens", 0) or 0),
        output_tokens=int(payload.get("completion_tokens", 0) or 0),
        cache_read=cache_read,
        reasoning_tokens=reasoning,
    )


def _parse_arguments(slot: _CallSlot) -> dict[str, object]:
    raw = "".join(slot.parts)
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise ProtocolError(f"工具参数不是合法 JSON：{exc}") from exc
    if not isinstance(parsed, dict):
        raise ProtocolError(f"工具参数不是对象：{type(parsed).__name__}")
    return {str(key): value for key, value in parsed.items()}
