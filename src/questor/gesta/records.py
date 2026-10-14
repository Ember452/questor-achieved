"""gesta 的记录形状（会话库的行 ↔ Python 对象；单一来源仍是 ``schemas/message.py``）。

为什么不是"再造一套消息模型"：会话正文的权威形状是 Phase 1 落下的
:class:`questor.schemas.message.ChatMessage`（一切重写挂靠的第一前置件）。本模块只做
**存储侧的封装**：把 ``ChatMessage`` 加上 seq、用量、停止信号这些只有落库才需要的字段，
读写两端共用同一个模型，避免"存储一套形状、协议一套形状"（AGENTS §三；B-85 同型）。

``content_parts_json`` 是 parts 的权威载体；``content`` / ``tool_calls_json`` 等列是
**投影**，供搜索与人读，读回一律走 parts 重建（两条路不得互相矛盾）。

# Ported from wuu@2026.10.6 internal/session/session.go（session_messages 列集）、
# internal/providers/types.go（ChatMessage.Origin 与 Role 正交）——形状照搬，未搬代码。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from questor.schemas.message import ChatMessage

__all__ = [
    "Control",
    "HeldOrigin",
    "HeldUserWorkEntry",
    "InboxMessage",
    "MessageUsage",
    "SessionControls",
    "SessionInfo",
    "StoredMessage",
]

#: 未决输入的两种出处（协议侧对应 ``turn/queue`` 与 ``turn/steer``）。
#: 值域在这里单点定义；存储层负责拒绝域外值（照 wuu，校验发生在写入侧而非建模侧，
#: 这样坏值会以 :class:`~questor.gesta.errors.HeldWorkInvalid` 上浮，而不是 pydantic 的
#: 通用校验错——用户看到的必须是"哪一条输入的哪个字段不合法"）。
HeldOrigin = Literal["queue", "steer"]
HELD_ORIGINS: tuple[str, ...] = ("queue", "steer")

#: ``session_controls.state`` 值域（A 阶段只用 active/user_controlled；
#: 接管仲裁的完整状态集随 Phase 3 的 activity 扩，扩展走加值不加表）。
CONTROL_STATES: tuple[str, ...] = ("active", "user_controlled")


class _Record(BaseModel):
    """记录基类：禁未知字段（列名漂移必须显式失败，不是静默丢一列）。"""

    model_config = ConfigDict(extra="forbid")


class MessageUsage(_Record):
    """一条记录的用量事实（token 口径照 wuu ``TokenUsage``；缓存命中量也占窗口，B-28）。"""

    input_tokens: int = 0
    output_tokens: int = 0
    context_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


class StoredMessage(_Record):
    """``session_messages`` 的一行：消息本体 + 只有落库才需要的元数据。

    ``seq`` 由 store 在追加事务内分配；**调用方传入 seq 会被拒绝**（单点分配，B-45）。
    """

    message: ChatMessage
    seq: int | None = None
    phase: str = ""
    provider_item_id: str = ""
    finish_reason: str = ""
    stop_reason: str = ""
    truncated: bool = False
    hidden: bool = False
    steered: bool = False
    name: str = ""
    at: str | None = None
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    context_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def usage(self) -> MessageUsage:
        """用量视图（compact 阈值与 ``turn/usage`` 都从这里取，不各算各的）。"""
        return MessageUsage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            context_tokens=self.context_tokens,
            cache_creation_tokens=self.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens,
        )


class SessionInfo(_Record):
    """``sessions`` 行。

    ``owner``/``visibility``/``parent_id`` 是 §1.7 的**边界字段**：现在不建多用户机制，
    但删掉它们就等于把"将来接组织/租户"这条路焊死（母计划 §1.7 明写"只做别焊死"）。
    """

    id: str
    title: str = ""
    summary: str = ""
    cwd: str = ""
    created_at: str = ""
    updated_at: str = ""
    entries: int = 0
    pinned_at: str | None = None
    archived_at: str | None = None
    folder_id: str = ""
    forked_from_id: str = ""
    forked_from_turn_id: str = ""
    forked_from_item_id: str = ""
    worktree_path: str = ""
    worktree_base_head: str = ""
    worktree_base_repo: str = ""
    owner: str = ""
    visibility: str = ""
    parent_id: str = ""
    context_source: str = ""
    instructions: str = ""


class SessionControls(_Record):
    """``session_controls`` 行：接管栅栏与修订号（ADR-0005）。"""

    session_id: str
    manager_id: str = ""
    revision: int = 0
    state: str = "active"


class Control(_Record):
    """插话携带的一条控制栅栏：消费时按当前 ``session_controls`` 复判（B-129）。"""

    session_id: str
    manager_id: str = ""
    revision: int = 0
    state: str = "active"


class InboxMessage(_Record):
    """``session_inbox`` 行：host→会话的待投递输入。

    ``delivered_at`` 由"client_id 是否已落入持久历史"决定，**不是入队时间**（B-127）。
    """

    client_id: str
    session_id: str
    content: str
    related_session_id: str = ""
    cause: str = ""
    wake: bool = True
    created_at: str = ""
    delivered_at: str | None = None
    controls: list[Control] = Field(default_factory=list)
    work_id: str = ""
    work_revision: int = 0
    work_version: int = 0


class HeldUserWorkEntry(_Record):
    """``held_user_work`` 行：运行中未消费的排队/插话输入（重启重建的依据，B-65）。

    ``position`` 由整表替换时的枚举下标写入，读回时带回；调用方构造时可省略。
    ``origin`` 故意保持 ``str``：值域校验发生在写入侧，坏值要报成
    :class:`~questor.gesta.errors.HeldWorkInvalid` 而不是通用校验错。
    """

    id: str
    origin: str
    message_json: str
    runtime_json: str = "{}"
    session_id: str = ""
    position: int = 0
