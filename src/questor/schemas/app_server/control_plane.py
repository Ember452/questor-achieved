"""控制/配置/HITL 面契约：config/read · activity · process · workspace · user-question。

# Reimplements wuu@wuu-main internal/appserver/protocol.go + activity_handlers.go +
#   user_question_handlers.go 的对应结构体（逐字段取 Go json tag）：
#   ConfigReadResult #L500-520 / PermissionSummary #L558-561；
#   ActivitySession #L613-629、ActivityListParams #L631、ActivityListResult #L635、
#   ActivityActionParams/Result #L639/#L644、ActivityReleaseResult(lease_token) #L648-651；
#   activity/started|updated|control_changed|stopped 通知载荷 = ActivitySession
#   （activity_handlers.go:113-127）；ManagedProcessSummary #L1278；
#   Process*Params/Result #L1296-1351；
#   WorkspaceInfo #L1800、WorkspaceListResult #L1806；UserQuestionListParams/Result、
#   Respond/Cancel/HoldParams、ResolveResult（user_question_handlers.go:10-34）。
# pitfalls: B-04（审批 future 超时）B-56（审批五态）；activity 租约+takeoverVersion（§1.5 机制 4）

`ActivitySession.interaction` 与 `user-question` 的 `questions`/`answer` 内部结构分别属
`internal/activity` 与 `internal/pluginhost`（后者涉 plugin 宿主），本 Phase 以不透明透传占位、
随对应 handler 移植逐字段收紧（port-ledger 登记，非静默）；`ConfigReadResult` 各大 summary
同 initialize 面，属 config 面后置。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ActivityActionResult",
    "ActivityActionParams",
    "ActivityListParams",
    "ActivityListResult",
    "ActivityReleaseResult",
    "ActivitySession",
    "ConfigReadResult",
    "ManagedProcessSummary",
    "PermissionSummary",
    "ProcessListParams",
    "ProcessListResult",
    "ProcessReadParams",
    "ProcessReadResult",
    "ProcessResizeParams",
    "ProcessResizeResult",
    "ProcessStopParams",
    "ProcessStopResult",
    "ProcessWriteParams",
    "ProcessWriteResult",
    "UserQuestionCancelParams",
    "UserQuestionHoldParams",
    "UserQuestionListParams",
    "UserQuestionListResult",
    "UserQuestionRequest",
    "UserQuestionRespondParams",
    "UserQuestionResolveResult",
    "WorkspaceInfo",
    "WorkspaceListResult",
]


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


# ---------------- config/read ----------------


class PermissionSummary(_Wire):
    mode: str | None = None
    approve_for_me: bool = False


class ConfigReadResult(_Wire):
    provider: str
    model: str
    max_parallel: int
    config_path: str
    workspace_root: str
    session_dir: str
    permissions: PermissionSummary
    effort: str | None = None
    variant: str | None = None
    # 大 summary（extension_trust/model_profile/tool_surface/… 等）属 config 面后置，透传。
    advanced_settings: dict[str, Any] | None = None
    general_settings: dict[str, Any] | None = None
    providers: list[dict[str, Any]] | None = None
    model_roles: list[dict[str, Any]] | None = None
    model_aliases: dict[str, Any] | None = None


# ---------------- activity（接管仲裁） ----------------


class ActivitySession(_Wire):
    """一条 activity 会话（可干预柱的控制单元）。

    `controller` 是当前控制方；`lease_token`/接管竞态见 :class:`ActivityReleaseResult`。
    `interaction` 属 `internal/activity`，本阶段透传（收紧随 handler）。
    """

    id: str
    kind: str
    thread_id: str
    workdir: str
    state: str
    controller: str
    created_at: str
    updated_at: str
    plugin_id: str | None = None
    target: str | None = None
    process_id: int | None = None
    window_id: int | None = None
    preview: str | None = None
    error: str | None = None
    interaction: dict[str, Any] | None = None


class ActivityListParams(_Req):
    thread_id: str


class ActivityListResult(_Wire):
    activities: list[ActivitySession]


class ActivityActionParams(_Req):
    thread_id: str
    activity_id: str


class ActivityActionResult(_Wire):
    activity: ActivitySession


class ActivityReleaseResult(_Wire):
    activity: ActivitySession
    lease_token: str


# ---------------- process（内嵌终端 worker） ----------------


class ManagedProcessSummary(_Wire):
    id: str
    owner_kind: str
    owner_id: str
    lifecycle: str
    status: str
    pid: int
    command: str
    cwd: str
    started_at: str
    updated_at: str
    tty: bool = False
    stopped_at: str | None = None
    exit_code: int | None = None
    last_error: str | None = None
    input_available: bool = False


class ProcessListParams(_Req):
    thread_id: str


class ProcessListResult(_Wire):
    processes: list[ManagedProcessSummary]


class ProcessStopParams(_Req):
    thread_id: str
    process_id: str


class ProcessStopResult(_Wire):
    process: ManagedProcessSummary


class ProcessReadParams(_Req):
    thread_id: str
    process_id: str
    offset_bytes: int | None = None
    max_bytes: int | None = None
    wait_ms: int | None = None


class ProcessReadResult(_Wire):
    process: ManagedProcessSummary
    output: str
    truncated: bool
    start_offset: int
    end_offset: int
    total_bytes: int
    timed_out: bool


class ProcessWriteParams(_Req):
    thread_id: str
    process_id: str
    input: str


class ProcessWriteResult(_Wire):
    process: ManagedProcessSummary
    bytes_written: int


class ProcessResizeParams(_Req):
    thread_id: str
    process_id: str
    cols: int
    rows: int


class ProcessResizeResult(_Wire):
    process: ManagedProcessSummary


# ---------------- workspace ----------------


class WorkspaceInfo(_Wire):
    name: str
    path: str
    id: str | None = None


class WorkspaceListResult(_Wire):
    workspaces: list[WorkspaceInfo]
    current_id: str | None = None
    current: str | None = None


# ---------------- user-question（HITL） ----------------


class UserQuestionRequest(_Wire):
    """agent 反向提问请求。`questions[]` 内部结构属 pluginhost，透传（收紧随 HITL handler）。"""

    request_id: str
    plugin_id: str
    execution_id: str
    thread_id: str
    turn_id: str
    created_at: str
    questions: list[dict[str, Any]]
    session_id: str | None = None
    actor_id: str | None = None
    call_id: str | None = None
    mode: str | None = None
    expires_at: str | None = None


class UserQuestionListParams(_Req):
    thread_id: str | None = None


class UserQuestionListResult(_Wire):
    questions: list[UserQuestionRequest]


class UserQuestionRespondParams(_Req):
    request_id: str
    # answer 结构属 pluginhost.UserQuestionAnswer（五态映射见 B-56），透传随 handler。
    answer: dict[str, Any]


class UserQuestionCancelParams(_Req):
    request_id: str


class UserQuestionHoldParams(_Req):
    request_id: str


class UserQuestionResolveResult(_Wire):
    request_id: str
    resolved: bool
