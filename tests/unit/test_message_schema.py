"""schemas/message.py 契约测：FinishReason 归一表逐行、Origin≠Role 独立、extra=forbid 拒凭据。

覆盖 §1.5 机制 4 的硬语义（FinishReason 归一、Origin≠Role、Provider 凭据不上线）。
每条附负向注入（改一个映射/塞一个未知键即红），验证护栏有齿。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from questor.schemas.message import (
    ChatMessage,
    FinishReason,
    MessageRole,
    normalize_finish_reason,
)


@pytest.mark.parametrize(
    ("stop_reason", "truncated", "has_tool_calls", "expected"),
    [
        # truncated 最先判 length（即使 stop_reason 是 stop）
        ("stop", True, False, FinishReason.LENGTH),
        ("", True, False, FinishReason.LENGTH),
        # stop 族：无工具→stop，有工具→tool_calls
        ("stop", False, False, FinishReason.STOP),
        ("end_turn", False, False, FinishReason.STOP),
        ("stop_sequence", False, False, FinishReason.STOP),
        ("completed", False, False, FinishReason.STOP),
        ("stop", False, True, FinishReason.TOOL_CALLS),
        # length 族
        ("length", False, False, FinishReason.LENGTH),
        ("max_tokens", False, False, FinishReason.LENGTH),
        ("max_output_tokens", False, False, FinishReason.LENGTH),
        # tool 族
        ("tool_calls", False, False, FinishReason.TOOL_CALLS),
        ("tool_use", False, False, FinishReason.TOOL_CALLS),
        ("function_call", False, False, FinishReason.TOOL_CALLS),
        # filter 族
        ("content_filter", False, False, FinishReason.CONTENT_FILTER),
        ("refusal", False, False, FinishReason.CONTENT_FILTER),
        # error 族
        ("error", False, False, FinishReason.ERROR),
        ("failed", False, False, FinishReason.ERROR),
        # 空：无工具→""，有工具→tool_calls
        ("", False, False, ""),
        ("", False, True, FinishReason.TOOL_CALLS),
        # 未知：无工具→unknown，有工具→tool_calls
        ("banana", False, False, FinishReason.UNKNOWN),
        ("banana", False, True, FinishReason.TOOL_CALLS),
        # 大小写不敏感 + 首尾空白（对齐 Go ToLower+TrimSpace）
        ("  STOP  ", False, False, FinishReason.STOP),
        ("Tool_Use", False, False, FinishReason.TOOL_CALLS),
    ],
)
def test_finish_reason_normalization_table(
    stop_reason: str, truncated: bool, has_tool_calls: bool, expected: str
) -> None:
    assert normalize_finish_reason(stop_reason, truncated, has_tool_calls) == expected


def test_truncated_wins_over_tool_calls() -> None:
    """负向：truncated 必须先判——若实现漏了先判，此处会是 tool_calls 而非 length。"""
    assert normalize_finish_reason("tool_use", True, True) == FinishReason.LENGTH


def test_origin_is_independent_from_role() -> None:
    """Origin ≠ Role（port-ledger P1-5）：两字段各存，插件生成消息 role=user 仍留 origin=plugin。"""
    msg = ChatMessage(role=MessageRole.USER, origin="plugin", origin_id="p-1")
    assert msg.role == MessageRole.USER
    assert msg.origin == "plugin"
    assert msg.origin_id == "p-1"


def test_chat_message_forbids_unknown_keys_no_credential_leak() -> None:
    """负向注入：provider 凭据/未知键必须被 extra=forbid 拒（P1-4，防 api_key 误上线）。"""
    with pytest.raises(ValidationError):
        ChatMessage.model_validate(
            {"role": "user", "parts": [], "api_key": "sk-secret-should-never-appear"}
        )


def test_part_discriminator_roundtrip() -> None:
    """Part 判别联合：tool_call/tool_result 按 type 正确还原，arguments 原样保字符串。"""
    msg = ChatMessage.model_validate(
        {
            "role": "assistant",
            "parts": [
                {"type": "text", "text": "hi"},
                {"type": "tool_call", "id": "c1", "name": "read", "arguments": '{"p":1}'},
            ],
        }
    )
    assert msg.parts[0].text == "hi"  # type: ignore[attr-defined]
    assert msg.parts[1].arguments == '{"p":1}'  # type: ignore[attr-defined]
