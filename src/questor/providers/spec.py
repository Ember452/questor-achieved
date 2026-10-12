"""模型能力声明与保守默认（B-82：窗口与上限**不得按厂商标识符硬编码**）。

三档来源，优先级从高到低：

1. ``config``——用户在 ``ModelSpec`` 上显式给定的值（装配点从配置层读出）；
2. ``declared``——协议语义本身可推断的能力（如 ``anthropic-messages`` 才有
   ``cache_control`` 断点；这属协议属性，不是"某家模型就是 200K"的型号表）；
3. ``conservative``——两者都没有时的保守兜底，且**如实标注来源**，
   让上层能看出"这个窗口数是猜的下界"而不是"端点告诉我的"。

# Reimplements FlowCoder@flowcoder config.py 的窗口解析语义 — pitfalls: B-82
# 反例参照：FlowCoder `config.py#L127-L157` 按 `provider_type` 字符串选 500K/128K，
# 并在 `agent/core.py#L122` 硬编码 `MAX_TOKENS_CEILING = 64_000`——Questor 拒绝型号表。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import SecretStr

from questor.schemas.llm import ModelCapabilities, WindowSource

__all__ = [
    "CONSERVATIVE_CONTEXT_WINDOW",
    "CONSERVATIVE_MAX_OUTPUT_TOKENS",
    "ModelCapabilities",
    "ModelSpec",
    "ProtocolName",
    "WindowSource",
    "resolve_capabilities",
]

# 保守兜底：不知道端点上限时按小窗口算，宁可多压一次也不要 400（超长被拒）
CONSERVATIVE_CONTEXT_WINDOW = 32_000
CONSERVATIVE_MAX_OUTPUT_TOKENS = 8_000


class ProtocolName(StrEnum):
    """wire 协议标识（一协议一实现文件，见 :mod:`questor.providers.protocols`）。"""

    ANTHROPIC_MESSAGES = "anthropic-messages"
    OPENAI_CHAT_COMPLETIONS = "openai-chat-completions"


@dataclass(frozen=True)
class ModelSpec:
    """一个模型端点的接入参数（由装配点从配置构造；providers 不 import config）。"""

    protocol: ProtocolName
    model: str
    base_url: str
    api_key: SecretStr | None = None
    #: 显式配置的窗口/输出上限（None=未配置，落到声明或保守值）
    context_window: int | None = None
    max_output_tokens: int | None = None
    #: 显式能力覆盖（None=按协议声明推断）
    supports_thinking: bool | None = None
    supports_prompt_cache: bool | None = None
    temperature: float | None = None
    #: 所有 IO 都有超时（AGENTS §五）；首事件超时见下
    request_timeout_s: float = 120.0
    first_event_timeout_s: float = 60.0
    max_retries: int = 2


def resolve_capabilities(spec: ModelSpec) -> ModelCapabilities:
    """按"配置 > 协议声明 > 保守默认"解析能力；非法配置值显式爆炸不猜。"""
    for label, value in (
        ("context_window", spec.context_window),
        ("max_output_tokens", spec.max_output_tokens),
    ):
        if value is not None and value <= 0:
            raise ValueError(f"{label}={value} 非法：给定则必须为正数")

    declared_cache = spec.protocol is ProtocolName.ANTHROPIC_MESSAGES
    declared_thinking = spec.protocol is ProtocolName.ANTHROPIC_MESSAGES

    if spec.context_window is not None:
        window, source = spec.context_window, WindowSource.CONFIG
    else:
        window, source = CONSERVATIVE_CONTEXT_WINDOW, WindowSource.CONSERVATIVE
    max_output = spec.max_output_tokens or CONSERVATIVE_MAX_OUTPUT_TOKENS

    return ModelCapabilities(
        context_window=window,
        max_output_tokens=max_output,
        supports_thinking=declared_thinking
        if spec.supports_thinking is None
        else spec.supports_thinking,
        supports_prompt_cache=declared_cache
        if spec.supports_prompt_cache is None
        else spec.supports_prompt_cache,
        window_source=source,
    )
