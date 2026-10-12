"""providers 能力声明与保守默认（B-82：不得按厂商标识符硬编码窗口/上限）。"""

from __future__ import annotations

import pytest

from questor.providers.spec import (
    CONSERVATIVE_CONTEXT_WINDOW,
    ModelSpec,
    ProtocolName,
    WindowSource,
    resolve_capabilities,
)


def _spec(
    protocol: ProtocolName = ProtocolName.ANTHROPIC_MESSAGES,
    *,
    model: str = "some-model",
    context_window: int | None = None,
    max_output_tokens: int | None = None,
    supports_thinking: bool | None = None,
    supports_prompt_cache: bool | None = None,
) -> ModelSpec:
    return ModelSpec(
        protocol=protocol,
        model=model,
        base_url="https://example.invalid/v1",
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        supports_thinking=supports_thinking,
        supports_prompt_cache=supports_prompt_cache,
    )


def test_unknown_window_falls_back_to_conservative_and_is_labelled() -> None:
    """没配窗口就用保守下界，且**来源必须标注**——否则上层会把猜值当端点事实。"""
    caps = resolve_capabilities(_spec())
    assert caps.context_window == CONSERVATIVE_CONTEXT_WINDOW
    assert caps.window_source is WindowSource.CONSERVATIVE


def test_explicit_config_wins_over_declaration_and_default() -> None:
    caps = resolve_capabilities(_spec(context_window=200_000, max_output_tokens=32_000))
    assert caps.context_window == 200_000
    assert caps.max_output_tokens == 32_000
    assert caps.window_source is WindowSource.CONFIG


def test_model_name_alone_never_changes_the_window() -> None:
    """B-82 的核心断言：只改型号名不改窗口。FlowCoder 按 `provider_type` 选 500K/128K 的
    做法在这里必须咬不住——两个不同型号名必须得到同一个保守值。"""
    first = resolve_capabilities(_spec(model="claude-opus-4-1"))
    second = resolve_capabilities(_spec(model="gpt-5-mini"))
    assert first.context_window == second.context_window == CONSERVATIVE_CONTEXT_WINDOW


def test_protocol_declares_cache_and_thinking() -> None:
    """缓存断点与推理是**协议属性**（anthropic-messages 有 cache_control / thinking），
    openai-chat-completions 没有等价物——必须如实声明为 False，而不是假装等价。"""
    anthropic = resolve_capabilities(_spec())
    chat = resolve_capabilities(_spec(ProtocolName.OPENAI_CHAT_COMPLETIONS))
    assert anthropic.supports_prompt_cache is True
    assert chat.supports_prompt_cache is False
    assert chat.supports_thinking is False


def test_explicit_capability_override_wins() -> None:
    caps = resolve_capabilities(
        _spec(
            ProtocolName.OPENAI_CHAT_COMPLETIONS,
            supports_prompt_cache=True,
            supports_thinking=True,
        )
    )
    assert (caps.supports_prompt_cache, caps.supports_thinking) == (True, True)


@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_window_is_rejected(value: int) -> None:
    """给定则必须为正数：0 会被当成"窗口是 0"从而每步都触发压缩。"""
    with pytest.raises(ValueError, match="非法"):
        resolve_capabilities(_spec(context_window=value))


def test_non_positive_max_output_is_rejected() -> None:
    with pytest.raises(ValueError, match="非法"):
        resolve_capabilities(_spec(max_output_tokens=0))
