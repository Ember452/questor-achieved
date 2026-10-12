"""Anthropic messages 协议：请求体装配 + 流翻译（wire 形状按实测/文档构造，假端点回放）。"""

from __future__ import annotations

import json

import pytest
from pydantic import SecretStr

from questor.prompts import system_assembly
from questor.providers.errors import ProtocolError, QuotaExceededError
from questor.providers.protocols.anthropic import build_anthropic_body, system_blocks
from questor.providers.registry import create_model
from questor.providers.resilience import ResilientModel
from questor.providers.spec import ModelSpec, ProtocolName, resolve_capabilities
from questor.schemas.llm import (
    Message,
    ModelRequest,
    PromptAssembly,
    StreamDelta,
    StreamEnd,
    StreamThinking,
    StreamToolCall,
    ToolCall,
    ToolResultBlock,
)
from questor.testenv.fake_endpoint import FakeEndpoint, error_response, sse_response


def _spec(
    *,
    context_window: int | None = None,
    api_key: str | None = None,
    max_retries: int = 0,
) -> ModelSpec:
    return ModelSpec(
        protocol=ProtocolName.ANTHROPIC_MESSAGES,
        model="probe-model",
        base_url="https://example.invalid",
        api_key=SecretStr(api_key) if api_key else None,
        context_window=context_window,
        max_retries=max_retries,
    )


def _request(
    *,
    messages: list[Message] | None = None,
    prompt: PromptAssembly | None = None,
    tools: list[dict[str, object]] | None = None,
    thinking: bool = False,
    max_output_tokens: int = 1000,
) -> ModelRequest:
    return ModelRequest(
        messages=messages or [Message(role="user", content="数一下")],
        prompt=prompt
        or system_assembly(project_rules="repo rules", environment="cwd=/tmp date=2026-10-12"),
        max_output_tokens=max_output_tokens,
        tools=tools
        or [{"name": "read", "description": "read a file", "input_schema": {"type": "object"}}],
        thinking=thinking,
    )


async def _drain(model: ResilientModel, request: ModelRequest) -> list[object]:
    return [event async for event in model.stream(request)]


def _ev(kind: str, **fields: object) -> tuple[str, str]:
    """构造一帧 Anthropic 风格 SSE（``event:`` 与 ``data.type`` 同源）。"""
    return (kind, json.dumps({"type": kind, **fields}))


# ---- 请求体装配 ----


def test_cache_marker_lands_on_last_cacheable_block_only() -> None:
    """B-81 的正向断言：断点落在稳定前缀末块，易变的 environment 块绝不能带标记。"""
    prompt = system_assembly(project_rules="rules", environment="cwd=/tmp")
    blocks = system_blocks(prompt, supports_cache=True)
    marked = [index for index, block in enumerate(blocks) if "cache_control" in block]
    assert marked == [prompt.cache_boundary - 1]
    assert "cache_control" not in blocks[-1]


def test_no_cache_marker_when_endpoint_lacks_capability() -> None:
    prompt = system_assembly()
    blocks = system_blocks(prompt, supports_cache=False)
    assert all("cache_control" not in block for block in blocks)


def test_tool_results_travel_in_user_message_and_calls_in_assistant() -> None:
    """Anthropic 的硬约束：tool_result 属 user、tool_use 属 assistant，且配对不可拆。"""
    request = _request(
        messages=[
            Message(role="user", content="读一下"),
            Message(role="assistant", content="", tool_calls=[ToolCall("t1", "read", {"p": "a"})]),
            Message(role="user", content="", tool_results=[ToolResultBlock("t1", "body", False)]),
        ]
    )
    body = build_anthropic_body(
        request,
        model="m",
        max_output_tokens=1000,
        supports_cache=False,
        thinking=False,
        temperature=None,
    )
    roles = [entry["role"] for entry in body["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert body["messages"][1]["content"][0]["type"] == "tool_use"
    assert body["messages"][2]["content"][0]["type"] == "tool_result"
    assert body["messages"][2]["content"][0]["is_error"] is False


def test_empty_message_is_dropped_instead_of_sending_blank_content() -> None:
    """空 content 会被端点 400 拒；装配层直接丢掉无块消息（而不是发出去再猜原因）。"""
    body = build_anthropic_body(
        _request(messages=[Message(role="user", content="")]),
        model="m",
        max_output_tokens=1000,
        supports_cache=False,
        thinking=False,
        temperature=None,
    )
    assert body["messages"] == []


def test_thinking_only_sent_when_both_call_and_endpoint_opt_in() -> None:
    """推理需要两个条件同时成立：本次调用要（request.thinking）且端点支持（能力声明）。
    只满足一个就不发 `thinking` 字段——向不支持的端点发未知字段会被 400 拒。"""
    request = _request(thinking=True)
    with_support = build_anthropic_body(
        request,
        model="m",
        max_output_tokens=4000,
        supports_cache=True,
        thinking=True,
        temperature=None,
    )
    endpoint_no_support = build_anthropic_body(
        request,
        model="m",
        max_output_tokens=4000,
        supports_cache=True,
        thinking=False,
        temperature=None,
    )
    call_opt_out = build_anthropic_body(
        _request(thinking=False),
        model="m",
        max_output_tokens=4000,
        supports_cache=True,
        thinking=True,
        temperature=None,
    )
    assert with_support["thinking"]["type"] == "enabled"
    assert with_support["thinking"]["budget_tokens"] < with_support["max_tokens"]
    assert "thinking" not in endpoint_no_support
    assert "thinking" not in call_opt_out


# ---- 流翻译 ----


async def test_stream_yields_deltas_thinking_tool_call_and_usage_in_order() -> None:
    usage_start = {
        "input_tokens": 900,
        "cache_read_input_tokens": 640,
        "cache_creation_input_tokens": 100,
    }
    frames = [
        _ev("message_start", message={"usage": usage_start}),
        _ev(
            "content_block_start",
            index=0,
            content_block={"type": "thinking", "thinking": ""},
        ),
        _ev(
            "content_block_delta",
            index=0,
            delta={"type": "thinking_delta", "thinking": "想想"},
        ),
        _ev("content_block_stop", index=0),
        _ev("content_block_start", index=1, content_block={"type": "text"}),
        _ev(
            "content_block_delta",
            index=1,
            delta={"type": "text_delta", "text": "结果是"},
        ),
        _ev("content_block_stop", index=1),
        _ev(
            "content_block_start",
            index=2,
            content_block={"type": "tool_use", "id": "tu1", "name": "read"},
        ),
        _ev(
            "content_block_delta",
            index=2,
            delta={"type": "input_json_delta", "partial_json": '{"path":'},
        ),
        _ev(
            "content_block_delta",
            index=2,
            delta={"type": "input_json_delta", "partial_json": ' "a.py"}'},
        ),
        _ev("content_block_stop", index=2),
        _ev(
            "message_delta",
            delta={"stop_reason": "tool_use"},
            usage={"output_tokens": 77},
        ),
        _ev("message_stop"),
    ]
    endpoint = FakeEndpoint()
    endpoint.responses.append(sse_response(frames))
    model = create_model(_spec(api_key=None), client=endpoint.client())

    events = await _drain(model, _request())

    assert [type(event) for event in events] == [
        StreamThinking,
        StreamDelta,
        StreamToolCall,
        StreamEnd,
    ]
    call = events[2]
    assert isinstance(call, StreamToolCall)
    assert call.call.id == "tu1"
    assert call.call.arguments == {"path": "a.py"}
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert end.stop_reason == "tool_use"
    assert (end.usage.input_tokens, end.usage.output_tokens) == (900, 77)
    # 缓存分量必须单独带出来，否则成本与缓存收益两头算不清
    assert (end.usage.cache_read, end.usage.cache_creation) == (640, 100)


async def test_missing_message_stop_raises_instead_of_silent_end_turn() -> None:
    """流被截但没终局事件——绝不能默认成 end_turn 让上层以为"答完了"。"""
    endpoint = FakeEndpoint()
    endpoint.responses.append(
        sse_response([("message_start", '{"type":"message_start","message":{"usage":{}}}')])
    )
    model = create_model(_spec(), client=endpoint.client())

    with pytest.raises(ProtocolError, match="缺少终局事件"):
        await _drain(model, _request())


async def test_in_stream_error_frame_becomes_protocol_error() -> None:
    endpoint = FakeEndpoint()
    endpoint.responses.append(
        sse_response(
            [
                ("message_start", '{"type":"message_start","message":{"usage":{}}}'),
                ("error", '{"type":"error","error":{"type":"overloaded_error","message":"busy"}}'),
            ]
        )
    )
    model = create_model(_spec(), client=endpoint.client())

    with pytest.raises(ProtocolError, match="overloaded_error"):
        await _drain(model, _request())


async def test_truncated_tool_args_are_dropped_not_raised() -> None:
    """max_tokens 截断时参数分片注定不完整：丢弃并由终局 max_tokens 驱动续写，而不是炸掉运行。"""
    frames = [
        _ev("message_start", message={"usage": {}}),
        _ev(
            "content_block_start",
            index=0,
            content_block={"type": "tool_use", "id": "tu", "name": "write"},
        ),
        _ev(
            "content_block_delta",
            index=0,
            delta={"type": "input_json_delta", "partial_json": '{"content": "trunc'},
        ),
        _ev("content_block_stop", index=0),
        _ev(
            "message_delta",
            delta={"stop_reason": "max_tokens"},
            usage={"output_tokens": 8},
        ),
        _ev("message_stop"),
    ]
    endpoint = FakeEndpoint()
    endpoint.responses.append(sse_response(frames))
    model = create_model(_spec(), client=endpoint.client())

    events = await _drain(model, _request())

    assert not any(isinstance(event, StreamToolCall) for event in events)
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert end.stop_reason == "max_tokens"


def _measured_402_body() -> bytes:
    """实测响应体（2026-10-12）：欠费却把 type/code 写成请求错——分类必须跟状态码。"""
    return (
        b'{"error":{"message":"Insufficient Balance",'
        b'"type":"unknown_error","code":"invalid_request_error"}}'
    )


async def test_status_code_beats_misleading_body() -> None:
    """实测形态：402 的 body 写着 invalid_request_error，分类必须跟状态码。"""
    endpoint = FakeEndpoint()
    endpoint.responses.append(error_response(402, body=_measured_402_body()))
    model = create_model(_spec(), client=endpoint.client())

    with pytest.raises(QuotaExceededError):
        await _drain(model, _request())


async def test_request_carries_the_callers_output_ceiling() -> None:
    """上限由请求携带（B-08 的新形状）：客户端不再存可变状态，并发共享一个客户端也不会串话。"""
    endpoint = FakeEndpoint()
    endpoint.responses.append(sse_response([("message_stop", '{"type":"message_stop"}')]))
    model = create_model(_spec(), client=endpoint.client())

    await _drain(model, _request(max_output_tokens=32_000))

    assert endpoint.bodies[0]["max_tokens"] == 32_000


async def test_capabilities_come_from_resolution_not_model_name() -> None:
    spec = _spec(context_window=200_000)
    endpoint = FakeEndpoint()
    endpoint.responses.append(sse_response([("message_stop", '{"type":"message_stop"}')]))
    model = create_model(spec, client=endpoint.client())
    assert model.capabilities == resolve_capabilities(spec)
    assert model.capabilities.context_window == 200_000
