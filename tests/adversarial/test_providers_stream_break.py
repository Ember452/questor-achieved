"""对抗：流中途断连时不得重放，也不得伪造完成（B-84 的端到端形态）。

与 `tests/unit/test_providers_resilience.py` 的分工：那份用脚本化 provider 验判据本身；
这份从真实 HTTP 层出发（httpx 假端点 + 断连的字节流），验证**没有任何一层**会在
交付过正文之后偷偷重来一次。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from questor.prompts import system_assembly
from questor.providers.errors import LLMTimeoutError, NetworkError
from questor.providers.registry import create_model
from questor.providers.spec import ModelSpec, ProtocolName
from questor.schemas.llm import Message, ModelRequest, StreamDelta, StreamEnd
from questor.testenv.fake_endpoint import FakeEndpoint, broken_stream_response, sse_response


def _spec(*, first_event_timeout_s: float = 5.0, max_retries: int = 3) -> ModelSpec:
    return ModelSpec(
        protocol=ProtocolName.ANTHROPIC_MESSAGES,
        model="probe-model",
        base_url="https://example.invalid",
        first_event_timeout_s=first_event_timeout_s,
        request_timeout_s=5.0,
        max_retries=max_retries,
    )


def _request() -> ModelRequest:
    return ModelRequest(
        messages=[Message(role="user", content="继续")],
        prompt=system_assembly(),
        max_output_tokens=1000,
        tools=[],
    )


def _message_start() -> bytes:
    return (
        b'event: message_start\ndata: {"type":"message_start",'
        b'"message":{"usage":{"input_tokens":10}}}\n\n'
    )


def _text_delta(text: str) -> bytes:
    payload = json.dumps(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}
    )
    return b"event: content_block_delta\ndata: " + payload.encode() + b"\n\n"


async def test_mid_stream_disconnect_is_not_replayed() -> None:
    """断在正文之后：一次请求、若干已交付增量、错误上抛——绝不重发第二次请求。"""
    endpoint = FakeEndpoint()
    endpoint.responses.append(
        broken_stream_response(
            [_message_start(), _text_delta("第一句"), _text_delta("第二句")],
            httpx.ReadError("connection reset"),
        )
    )
    model = create_model(_spec(), client=endpoint.client())

    delivered: list[object] = []
    with pytest.raises(NetworkError):
        async for event in model.stream(_request()):
            delivered.append(event)

    assert [type(event) for event in delivered] == [StreamDelta, StreamDelta]
    assert len(endpoint.requests) == 1, "交付过事件后重放会让同一轮出现两份正文（B-84）"


async def test_pre_first_event_failure_may_be_retried() -> None:
    """首帧之前的失败可安全整体重试：脚本=第一次断连、第二次成功。"""
    endpoint = FakeEndpoint()
    endpoint.responses.append(broken_stream_response([], httpx.ConnectError("refused")))
    endpoint.responses.append(
        sse_response(
            [
                (
                    "message_start",
                    json.dumps(
                        {"type": "message_start", "message": {"usage": {"input_tokens": 10}}}
                    ),
                ),
                ("message_stop", json.dumps({"type": "message_stop"})),
            ]
        )
    )
    model = create_model(_spec(max_retries=2), client=endpoint.client())

    events = [event async for event in model.stream(_request())]

    assert len(endpoint.requests) == 2
    assert isinstance(events[-1], StreamEnd)


async def test_stalled_stream_hits_the_first_event_timeout() -> None:
    """连接成功但永远不出首事件——必须有独立于 httpx read 超时的守卫兜住。"""

    class _Stalled(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(5)
            yield b""

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, stream=_Stalled(), headers={"content-type": "text/event-stream"})

    endpoint = FakeEndpoint(handler=handler)
    model = create_model(_spec(first_event_timeout_s=0.05), client=endpoint.client())

    with pytest.raises(LLMTimeoutError, match="首事件"):
        async for _ in model.stream(_request()):
            pass
