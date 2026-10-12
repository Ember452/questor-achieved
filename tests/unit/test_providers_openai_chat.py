"""OpenAI chat/completions 协议：转换、端点规范化与流翻译。

这一条协议要接的是"所有自称 OpenAI 兼容的端点"，所以断言重点放在
**各家形状差异**上：usage 只在尾帧、推理字段名不一、`[DONE]` 后不留空行。
"""

from __future__ import annotations

import json
from typing import cast

import pytest

from questor.prompts import system_assembly
from questor.providers.errors import ProtocolError
from questor.providers.protocols.openai_chat import (
    OpenAIChatCompletionsClient,
    _chat_endpoint,
    build_chat_body,
    to_chat_messages,
    to_chat_tools,
)
from questor.providers.spec import ModelSpec, ProtocolName, resolve_capabilities
from questor.schemas.llm import (
    Message,
    ModelRequest,
    StreamDelta,
    StreamEnd,
    StreamThinking,
    StreamToolCall,
    ToolCall,
    ToolResultBlock,
)
from questor.testenv.fake_endpoint import FakeEndpoint, sse_response


def _spec() -> ModelSpec:
    return ModelSpec(
        protocol=ProtocolName.OPENAI_CHAT_COMPLETIONS,
        model="probe-model",
        base_url="https://example.invalid/v1",
        max_retries=0,
    )


def _request(messages: list[Message] | None = None) -> ModelRequest:
    return ModelRequest(
        messages=messages or [Message(role="user", content="hi")],
        prompt=system_assembly(project_rules="rules", environment="cwd=/tmp"),
        max_output_tokens=1000,
        tools=[{"name": "read", "description": "read", "input_schema": {"type": "object"}}],
    )


def _client(endpoint: FakeEndpoint) -> OpenAIChatCompletionsClient:
    return OpenAIChatCompletionsClient(
        _spec(), resolve_capabilities(_spec()), client=endpoint.client()
    )


# ---- 转换 ----


def test_system_text_is_one_leading_message_and_tool_results_become_tool_role() -> None:
    """chat/completions 没有块结构：system 只有一条，工具结果按 tool_call_id 回指。"""
    messages = to_chat_messages(
        [
            Message(role="user", content="读一下"),
            Message(role="assistant", content="", tool_calls=[ToolCall("c1", "read", {"p": "a"})]),
            Message(role="user", content="", tool_results=[ToolResultBlock("c1", "text", False)]),
        ],
        system_text="rules",
    )
    assert messages[0] == {"role": "system", "content": "rules"}
    assert [entry["role"] for entry in messages] == ["system", "user", "assistant", "tool"]
    call = messages[2]["tool_calls"][0]
    assert call["id"] == "c1"
    assert json.loads(call["function"]["arguments"]) == {"p": "a"}
    assert messages[3]["tool_call_id"] == "c1"


def test_tools_are_wrapped_and_unnamed_tools_are_dropped() -> None:
    wrapped = to_chat_tools(
        [
            {"name": "read", "description": "d", "input_schema": {"type": "object"}},
            {"description": "no name"},
        ]
    )
    assert len(wrapped) == 1
    assert wrapped[0]["type"] == "function"
    assert wrapped[0]["function"]["parameters"] == {"type": "object"}


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://h.example/v1", "https://h.example/v1/chat/completions"),
        ("https://h.example/v1/", "https://h.example/v1/chat/completions"),
        ("https://h.example", "https://h.example/chat/completions"),
        # 已给完整路径的端点不再拼一次（拼成 /v1/chat/completions/chat/completions 是常见错）
        ("https://h.example/v1/chat/completions", "https://h.example/v1/chat/completions"),
    ],
)
def test_endpoint_normalisation_does_not_double_append(base_url: str, expected: str) -> None:
    assert _chat_endpoint(base_url) == expected


def test_include_usage_is_requested() -> None:
    """不带 stream_options.include_usage，流式下就拿不到 usage，预算锚点永远是字符估算。"""
    body = build_chat_body(_request(), model="m", max_output_tokens=1000, temperature=None)
    assert body["stream_options"] == {"include_usage": True}
    assert body["max_tokens"] == 1000


# ---- 流翻译 ----


def _frame(**payload: object) -> tuple[str | None, str]:
    """OpenAI 流式帧只有 ``data:`` 行，没有 ``event:``。"""
    return (None, json.dumps(payload))


def _delta(**fields: object) -> tuple[str | None, str]:
    return _frame(choices=[{"index": 0, "delta": fields}])


def _finish(reason: str) -> tuple[str | None, str]:
    return _frame(choices=[{"index": 0, "delta": {}, "finish_reason": reason}])


def _tool_fragment(**fragment: object) -> tuple[str | None, str]:
    return _delta(tool_calls=[fragment])


def _usage_only(**usage: object) -> tuple[str | None, str]:
    return _frame(choices=[], usage=usage)


async def test_content_and_reasoning_and_tools_stream_in_order() -> None:
    chunks = [
        _delta(reasoning_content="想想"),
        _delta(content="结果"),
        _tool_fragment(index=0, id="call1", function={"name": "read"}),
        _tool_fragment(index=0, function={"arguments": '{"p"'}),
        _tool_fragment(index=0, function={"arguments": ': "a"}'}),
        _finish("tool_calls"),
        _usage_only(prompt_tokens=42, completion_tokens=7),
        (None, "[DONE]"),
    ]
    endpoint = FakeEndpoint()
    endpoint.responses.append(sse_response(chunks, trailing_blank=False))

    events = [event async for event in _client(endpoint).stream(_request())]

    assert [type(event) for event in events] == [
        StreamThinking,
        StreamDelta,
        StreamToolCall,
        StreamEnd,
    ]
    call = events[2]
    assert isinstance(call, StreamToolCall)
    assert (call.call.id, call.call.name, call.call.arguments) == ("call1", "read", {"p": "a"})
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert end.stop_reason == "tool_use"  # finish_reason=tool_calls 归一到内核词表
    assert (end.usage.input_tokens, end.usage.output_tokens) == (42, 7)


async def test_cached_tokens_land_in_usage() -> None:
    chunks = [
        _delta(content="x"),
        _finish("stop"),
        _usage_only(
            prompt_tokens=100,
            completion_tokens=1,
            prompt_tokens_details={"cached_tokens": 80},
            completion_tokens_details={"reasoning_tokens": 4},
        ),
        (None, "[DONE]"),
    ]
    endpoint = FakeEndpoint()
    endpoint.responses.append(sse_response(chunks))

    events = [event async for event in _client(endpoint).stream(_request())]
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert (end.usage.cache_read, end.usage.reasoning_tokens) == (80, 4)


async def test_length_finish_reason_maps_to_max_tokens() -> None:
    chunks = [_delta(content="半句"), _finish("length"), (None, "[DONE]")]
    endpoint = FakeEndpoint()
    endpoint.responses.append(sse_response(chunks))

    events = [event async for event in _client(endpoint).stream(_request())]
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert end.stop_reason == "max_tokens"


async def test_truncated_tool_call_is_dropped_not_fatal() -> None:
    """length 截断时参数分片必然不完整：丢弃它、由内核的 max_tokens 恢复接手。"""
    chunks = [
        _tool_fragment(index=0, id="c", function={"name": "write", "arguments": '{"content": "un'}),
        _finish("length"),
        (None, "[DONE]"),
    ]
    endpoint = FakeEndpoint()
    endpoint.responses.append(sse_response(chunks))

    events = [event async for event in _client(endpoint).stream(_request())]

    assert not any(isinstance(event, StreamToolCall) for event in events)


async def test_stream_without_terminal_signal_raises() -> None:
    """既没有 [DONE] 也没有 finish_reason：不能默认成"答完了"（会伪造完成状态）。"""
    endpoint = FakeEndpoint()
    endpoint.responses.append(
        sse_response([(None, json.dumps({"choices": [{"index": 0, "delta": {"content": "x"}}]}))])
    )

    with pytest.raises(ProtocolError, match="终局缺失"):
        async for _ in _client(endpoint).stream(_request()):
            pass


def test_registry_maps_the_protocol_to_the_client_class() -> None:
    """注册表是"新增协议只登记一行"的落点；未知协议必须显式报错不静默回落。"""
    from questor.providers.registry import provider_for_protocol  # noqa: PLC0415

    chat_class = provider_for_protocol(ProtocolName.OPENAI_CHAT_COMPLETIONS)
    assert chat_class is OpenAIChatCompletionsClient
    with pytest.raises(ValueError, match="未知协议"):
        provider_for_protocol(cast(ProtocolName, "anthropic-batch"))
