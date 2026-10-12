"""providers —— 模型客户端、用量与能力声明（overview §6；矩阵上不得 import 业务模块）。

三柱归属：**可验证**与**可见**的入口之一——用量分量（含缓存与推理）与能力声明必须
如实带出，否则预算与成本两头都算不清。

依赖与选型：自建 wire 层 over httpx，不接厂商 SDK（ADR-0016）；wire 词汇表取自
`questor.schemas.llm`（`ModelPort` 仍归内核定义，R1）。

公开面：:func:`create_model` 是唯一装配入口，其余按名字取用。
"""

from __future__ import annotations

from questor.providers.errors import (
    AuthenticationError,
    EndpointNotFoundError,
    LLMError,
    LLMTimeoutError,
    NetworkError,
    ProtocolError,
    QuotaExceededError,
    RateLimitError,
    RequestError,
    ServerError,
    UnexpectedStatusError,
)
from questor.providers.registry import KNOWN_PROTOCOLS, create_model
from questor.providers.resilience import ResilientModel
from questor.providers.spec import (
    ModelCapabilities,
    ModelSpec,
    ProtocolName,
    WindowSource,
    resolve_capabilities,
)

__all__ = [
    "KNOWN_PROTOCOLS",
    "AuthenticationError",
    "EndpointNotFoundError",
    "LLMError",
    "LLMTimeoutError",
    "ModelCapabilities",
    "ModelSpec",
    "NetworkError",
    "ProtocolError",
    "ProtocolName",
    "QuotaExceededError",
    "RateLimitError",
    "RequestError",
    "ResilientModel",
    "ServerError",
    "UnexpectedStatusError",
    "WindowSource",
    "create_model",
    "resolve_capabilities",
]
