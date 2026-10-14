"""ChatMessage / Role / Part / FinishReason —— 一切重写挂靠的第一前置件。

对应 protocol.md §2 与 behavior-protocol-wuu §5。

# Reimplements wuu@wuu-main internal/providers/types.go（ChatMessage.Role/.Origin 分离、
# FinishReason 归一表 NormalizeFinishReason L101-146）语义——形状与归一规则照搬，未搬代码。
# 线格式真相 = Go json tag；本模块是 Python 侧的 pydantic 绑定 + 归一实现。

为何 pydantic 而非 dataclass：这是跨语言接缝的**校验边界**，需要 `extra="forbid"` 机械拒绝
未知键（防 Provider 凭据/身份字段误上线，port-ledger P1-4）与序列化别名控制（snake_case）。
frozen 承接 append-only 纪律：改历史 = 建新记录，不在模型层原地 mutate。

Origin ≠ Role（port-ledger P1-5，types.go:313/321）：`role` 是 provider 侧角色（喂模型的
user/assistant/system/tool）；`origin` 是产品出处（如插件生成的 query 仍投影 role=user，但
保留可审计的非用户作者）。两字段**独立**，不得合并——否则审计柱丢证据。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ChatMessage",
    "FinishReason",
    "ImagePart",
    "MessageRole",
    "Part",
    "ReasoningPart",
    "TextPart",
    "ToolCallPart",
    "ToolResultPart",
    "normalize_finish_reason",
]


class _Contract(BaseModel):
    """契约基类：frozen（写入后不可变）+ 禁未知字段（对齐 Go 结构体逐字段映射，防凭据误入）。"""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class MessageRole(StrEnum):
    """provider 侧角色（喂模型的 role），与 :attr:`ChatMessage.origin`（产品出处）正交。

    锚 wuu ``ChatMessage.Role``（types.go:313）——线上一串小写值，此处枚举收紧合法集。
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class TextPart(_Contract):
    """正文片段。"""

    type: Literal["text"] = "text"
    text: str


class ReasoningPart(_Contract):
    """思维链片段（provider 侧隐藏推理，Kimi 等需回放；可带签名证据）。"""

    type: Literal["reasoning"] = "reasoning"
    text: str
    signature: str | None = None


class ToolCallPart(_Contract):
    """模型请求的一次工具调用。arguments 是原始 JSON 字符串（不预解析，保 provider 逐字节回放）。"""

    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: str = ""
    provider_item_id: str | None = None


class ToolResultPart(_Contract):
    """一次工具调用的结果。tool_call_id 关联回 :class:`ToolCallPart`（配对不得被插话切断）。"""

    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    content: str = ""
    is_error: bool = False


class ImagePart(_Contract):
    """图片片段。data 为 base64；media_type 必填（provider 需要 MIME 分派）。"""

    type: Literal["image"] = "image"
    media_type: str
    data: str


Part = Annotated[
    TextPart | ReasoningPart | ToolCallPart | ToolResultPart | ImagePart,
    Field(discriminator="type"),
]


class ChatMessage(_Contract):
    """一条会话消息：role + parts 序列 + 与 role 正交的 origin。

    锚 wuu ``ChatMessage``（types.go:312-345）的跨语言可见子集。provider 原生身份
    （ProviderItemID 等）与仅 host 侧的字段（steered/hidden）不进本契约（不上线）。
    """

    role: MessageRole
    parts: list[Part] = Field(default_factory=list)
    # 产品出处（与 role 正交）：如 "plugin" / "user" / "schedule"，及出处实体 id。
    origin: str | None = None
    origin_id: str | None = None
    # client_id 关联渲染器意图与持久化用户项（B-63 幂等键）。
    client_id: str | None = None
    name: str | None = None
    # 展示文本与输入文本可不同（插件生成的 wake 消息：气泡通用、prompt 具体）。
    display_content: str | None = None
    input_text: str | None = None


class FinishReason(StrEnum):
    """provider 中立"为何结束"的稳定语义值（锚 providers/types.go:103-114）。

    ``continue`` 是循环语义（再来一轮、无客户端工具调用），不由归一函数产出但属枚举集。
    """

    STOP = "stop"
    CONTINUE = "continue"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"
    UNKNOWN = "unknown"


_STOP_SET = frozenset({"stop", "end_turn", "stop_sequence", "completed"})
_LENGTH_SET = frozenset({"length", "max_tokens", "max_output_tokens"})
_TOOL_SET = frozenset({"tool_calls", "tool_use", "function_call"})
_FILTER_SET = frozenset({"content_filter", "refusal"})
_ERROR_SET = frozenset({"error", "failed"})


def normalize_finish_reason(stop_reason: str, truncated: bool, has_tool_calls: bool) -> str:
    """把各家停止信号归一到 :class:`FinishReason`（照 types.go:116-146 的映射表，不拷代码）。

    返 ``FinishReason`` 成员值串；空输入且无工具调用返 ``""``（无结束信号）。逐条对齐：
    - ``truncated`` 最先判 → ``length``；
    - 入参先 lower+strip（大小写不敏感，Go ``strings.ToLower(strings.TrimSpace(...))``）；
    - 未知/空一律：有工具调用 → ``tool_calls``，否则 unknown（空且无工具 → ``""``）。
    """
    reason = (stop_reason or "").strip().lower()
    if truncated:
        return FinishReason.LENGTH
    if reason in _STOP_SET:
        return FinishReason.TOOL_CALLS if has_tool_calls else FinishReason.STOP
    if reason in _LENGTH_SET:
        return FinishReason.LENGTH
    if reason in _TOOL_SET:
        return FinishReason.TOOL_CALLS
    if reason in _FILTER_SET:
        return FinishReason.CONTENT_FILTER
    if reason in _ERROR_SET:
        return FinishReason.ERROR
    if reason == "":
        return FinishReason.TOOL_CALLS if has_tool_calls else ""
    return FinishReason.TOOL_CALLS if has_tool_calls else FinishReason.UNKNOWN
