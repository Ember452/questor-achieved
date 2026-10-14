"""四族实体形状：Thread / Turn / Run / ThreadItem + 状态枚举（protocol.md §3/§4 挂靠）。

# Reimplements wuu@wuu-main internal/appserver/protocol.go 实体结构体
#   （Thread #L2367-2415、Turn #L2425-2464、ThreadItem #L2501-2556、TurnError #L2466-2479、
#   TurnStatus/TurnKind/ThreadStatus/WorkspaceKind #L2319-2358；Run=execution.Run 别名 #L2004）。
# 字段名逐一取 Go json tag（snake_case 原生，无需别名）；omitempty → Optional/默认。
# pitfalls: B-66（写时 diff 随结果）、B-93（revision 绑定）；硬语义 P1-3（items nil→[]）。

覆盖范围＝A 阶段 fixture 回放所需的"做"集实体子集；provider 原生身份（ProviderItemID 等）、
remote_content_ref、host-only 的 steered 等**不上线**字段刻意不入模型（extra=forbid 会拒任何
未知键，凭据/内部字段误上线即红，port-ledger P1-4）。完整 execution.Run 内部随 Phase 2a 补（P1-7）。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Wire(BaseModel):
    """线上实体基类：frozen + 禁未知键（逐字段对齐 Go 结构体，防凭据/内部字段误上线）。"""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class ThreadStatus(StrEnum):
    """锚 protocol.go#L2321-2324：仅 `idle` / `in_progress` 两态（实测，非推想）。"""

    IDLE = "idle"
    IN_PROGRESS = "in_progress"


class TurnStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class TurnKind(StrEnum):
    USER = "user"
    INTERNAL = "internal"
    COMPACT = "compact"


class WorkspaceKind(StrEnum):
    PROJECT = "project"
    SCRATCH = "scratch"


class ThreadItemType(StrEnum):
    USER_MESSAGE = "user_message"
    AGENT_MESSAGE = "agent_message"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    CONTEXT_COMPACTION = "context_compaction"
    STREAM_RECONNECT = "stream_reconnect"
    ERROR = "error"


class ThreadItemStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ThreadItem(_Wire):
    """一条会话项（消息/推理/工具调用/压缩/重连/错误的统一载体）。

    `origin`/`origin_id`（产品出处）与 `role`（provider 角色）正交（P1-5）；`arguments`/`result`
    是工具调用的原始 JSON 串；`content_parts` 是带源定位的结构化正文（UTF-16 code units 选中，C6）。
    """

    id: str
    type: ThreadItemType
    seq: int | None = None
    status: ThreadItemStatus | None = None
    role: str | None = None
    text: str | None = None
    name: str | None = None
    arguments: str | None = None
    result: str | None = None
    error: str | None = None
    origin: str | None = None
    origin_id: str | None = None
    terminal: bool = False
    finish_reason: str | None = None
    stop_reason: str | None = None
    content_parts: list[dict[str, Any]] | None = None
    images: list[dict[str, Any]] | None = None
    files: list[dict[str, Any]] | None = None
    summary: str | None = None


class TurnError(_Wire):
    """结构化错误（前端优先读这些、raw message 留诊断）。锚 protocol.go#L2466-2479。"""

    message: str
    code: str | None = None
    category: str | None = None
    provider: str | None = None
    status_code: int | None = None


class Turn(_Wire):
    """一轮对话实体。锚 protocol.go#L2425-2464。

    硬语义（P1-3）：wuu `MarshalJSON` 令 `items` 为 nil 时输出 `[]` 而非 `null`（前端 `for`
    遍历不得收 null）。本模型用 `default_factory=list` + `model_serializer` 保证序列化恒为数组。
    """

    id: str
    items: list[ThreadItem] = Field(default_factory=list)
    status: TurnStatus
    items_view: str = "full"
    kind: TurnKind | None = None
    model_provider: str | None = None
    model: str | None = None
    error: TurnError | None = None
    finish_reason: str | None = None
    stop_reason: str | None = None
    truncated: bool = False
    started_at: str | None = None
    answer_ready_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    context_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cache_read_tokens: int | None = None
    usage_model: str | None = None

    def model_dump_wire(self, **kwargs: Any) -> dict[str, Any]:
        """序列化：items 恒为数组（None→[]），对齐 wuu MarshalJSON。"""
        data = self.model_dump(**kwargs)
        if data.get("items") is None:
            data["items"] = []
        return data


class WorktreeInfo(_Wire):
    path: str
    base_head: str | None = None
    base_repo: str | None = None
    dirty: bool = False
    changed_files: list[str] | None = None


class Thread(_Wire):
    """会话实体。锚 protocol.go#L2367-2415。

    扩展性缝（§1.7-6）：`parent_id`/`project_id`/`folder_id`/`forked_from_*` 保留（将来接
    subagent/多-agent/组织靠这些列扩），A 阶段不建其逻辑但**不删字段**，避免将来焊死。
    """

    id: str
    preview: str
    status: ThreadStatus
    model_provider: str
    model: str
    model_variant: str
    model_effort: str
    permission_mode: str
    cwd: str
    approve_for_me: bool = False
    created_at: str
    updated_at: str
    turns: list[Turn] = Field(default_factory=list)
    speed: str | None = None
    source: str | None = None
    title: str | None = None
    engine_id: str | None = None
    workspace_id: str | None = None
    workspace_kind: WorkspaceKind | None = None
    parent_id: str | None = None
    agent_path: str | None = None
    project_id: str | None = None
    project_role: str | None = None
    pinned: bool = False
    archived: bool = False
    folder_id: str | None = None
    forked_from_id: str | None = None
    forked_from_turn_id: str | None = None
    forked_from_item_id: str | None = None
    worktree: WorktreeInfo | None = None
    latest_completed_turn_id: str | None = None
    history_cursor: str | None = None
    history_paged: bool = False
    read_only: bool = False
    ephemeral: bool = False


class Run(BaseModel):
    """run 作为不透明对象上线（port-ledger P1-7）。

    其内部字段属 `internal/execution` 包，完整形状随 Phase 2a 移植 execution 时逐符号补。
    本阶段只固定"run 能随 `run/start`(result) / `run/started|updated`(通知) 原样往返"：
    已知身份字段类型化，未知内部键用 `extra="allow"` 透传不丢（execution 移植后收紧）。
    注：此处 allow 仅针对**内部不透明**；run 不承载凭据面，与实体基类禁凭据意图不冲突。
    """

    model_config = ConfigDict(frozen=True, extra="allow", populate_by_name=True)

    id: str | None = None
    thread_id: str | None = None
    status: str | None = None
