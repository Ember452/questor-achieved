"""协议工厂：`ModelSpec` → 可用客户端（唯一装配入口 :func:`create_model`）。

工厂负责三件事，别处不得重复：协议选择、能力解析（B-82 的三档来源）、韧性包裹
（B-84 的零交付重试窗口）。消费方（cli/serve 装配点）只认这一个入口。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from questor.providers.protocols.anthropic import AnthropicMessagesClient
from questor.providers.protocols.openai_chat import OpenAIChatCompletionsClient
from questor.providers.resilience import ResilientModel
from questor.providers.spec import ModelCapabilities, ModelSpec, ProtocolName, resolve_capabilities

__all__ = ["KNOWN_PROTOCOLS", "ProviderClient", "create_model", "provider_for_protocol"]

#: 协议 → 客户端类。新增协议在此登记一行即可（protocols/ 目录的说明同源）
_CLIENT_TYPES: dict[ProtocolName, Callable[..., Any]] = {
    ProtocolName.ANTHROPIC_MESSAGES: AnthropicMessagesClient,
    ProtocolName.OPENAI_CHAT_COMPLETIONS: OpenAIChatCompletionsClient,
}

#: providers 侧对"内核可见客户端"的形状约定（真正的 port 归 engine 定义，R1）
ProviderClient = AnthropicMessagesClient | OpenAIChatCompletionsClient

KNOWN_PROTOCOLS = tuple(sorted(protocol.value for protocol in _CLIENT_TYPES))


def provider_for_protocol(protocol: ProtocolName) -> Callable[..., Any]:
    """取协议对应的客户端类；未知协议显式报错，不静默回落到"最像的那一个"。"""
    try:
        return _CLIENT_TYPES[protocol]
    except KeyError as exc:
        raise ValueError(
            f"未知协议 {protocol!r}（可用: {', '.join(KNOWN_PROTOCOLS)}）；"
            "新协议需在 protocols/ 落地并在此登记"
        ) from exc


def create_model(
    spec: ModelSpec,
    *,
    client: httpx.AsyncClient | None = None,
    capabilities: ModelCapabilities | None = None,
) -> ResilientModel:
    """按 spec 构造 provider 客户端并包上韧性层。

    ``client`` 是测试接缝（注入 ``httpx.MockTransport`` 的假端点）；注入的客户端
    由注入方负责关闭，:meth:`ResilientModel.aclose` 只关自持的（B-83）。
    ``capabilities`` 允许装配点覆盖解析结果（例如配置里显式声明窗口），缺省时按
    "配置 > 协议声明 > 保守默认"解析。
    """
    inner = provider_for_protocol(spec.protocol)(
        spec, capabilities or resolve_capabilities(spec), client=client
    )
    return ResilientModel(inner, max_retries=spec.max_retries)
