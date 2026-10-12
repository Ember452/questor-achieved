"""data-model.md 的 pydantic v2 绑定——只做绑定，JSON Schema（model/v1.json）仍是唯一真相源。

一致性由 ``tests/unit/test_schema_bindings.py`` 机械核对（required 字段集、枚举值、
id 与时间戳 pattern 必须与 v1.json 逐字一致）；漂移即红。所有实体 frozen +
``extra="forbid"``：append-only 纪律在模型层的第一道表达（改历史 = 建新记录）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# ---- 通用约定（data-model §1；pattern 与 v1.json $defs 逐字一致） ----

Id = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
Timestamp = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")]


def utc_timestamp_now() -> Timestamp:
    """当前 UTC 时间的 ISO-8601 秒级字符串（data-model §1 的时间戳形状）。"""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Entity(BaseModel):
    """实体基类：frozen（写入后不可变）+ 禁未知字段（对齐 additionalProperties: false）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PermissionMode(StrEnum):
    """权限三档（overview §9）；三档限制写域，绝不用于隐藏过程。"""

    READ_ONLY = "read_only"
    STANDARD = "standard"
    UNCONFINED = "unconfined"


class RunStatus(StrEnum):
    """运行状态（data-model §3.1）；迁移白名单唯一入口在 questor.gesta.transitions。"""

    QUEUED = "queued"
    RUNNING = "running"
    STEERED = "steered"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AcceptanceStatus(StrEnum):
    """验收状态（data-model §3.2）。"""

    PROPOSED = "proposed"
    ACCEPTED_BY_USER = "accepted_by_user"
    EXECUTING = "executing"
    REPORTED = "reported"
    VERIFIED = "verified"
    REGRESSED = "regressed"


class ItemKind(StrEnum):
    """Item 的六种最小可审计单元（data-model §2）。"""

    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CITATION = "citation"
    ANNOTATION = "annotation"
    DELIVERABLE = "deliverable"


class Origin(StrEnum):
    """输入来源：用户直发或插话（插话挂原 turn，不新开，data-model §2 Turn）。"""

    USER = "user"
    STEER = "steer"


class Workspace(_Entity):
    id: Id
    name: str
    root_paths: Annotated[list[str], Field(min_length=1)]
    revision: Annotated[int, Field(ge=0)]
    created_at: Timestamp


class Thread(_Entity):
    id: Id
    workspace_id: Id
    title: str | None = None
    engine_id: Id
    permission_mode: PermissionMode
    pinned: bool
    archived: bool
    created_at: Timestamp
    updated_at: Timestamp


class ForkOrigin(_Entity):
    thread_id: Id
    turn_seq: Annotated[int, Field(ge=1)]
    mode: Literal["local", "worktree"]


class Turn(_Entity):
    id: Id
    thread_id: Id
    seq: Annotated[int, Field(ge=1)]
    origin: Origin
    fork_from: ForkOrigin | None = None
    created_at: Timestamp


class RunUsage(_Entity):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = None


class Run(_Entity):
    id: Id
    turn_id: Id
    engine_id: Id
    permission_mode: PermissionMode
    workspace_revision_start: Annotated[int | None, Field(ge=0)] = None
    workspace_revision_end: Annotated[int | None, Field(ge=0)] = None
    status: RunStatus
    usage: RunUsage | None = None
    #: 编排绑定（data-model v1.3 / ADR-0025）：所属 Task/Goal；独立会话直接发起的 run 两者皆空
    task_id: Id | None = None
    goal_id: Id | None = None
    created_at: Timestamp


class ItemEvidence(_Entity):
    claimed: str
    recorded_output_ref: str


class Item(_Entity):
    id: Id
    run_id: Id
    kind: ItemKind
    payload: dict[str, Any]
    evidence: ItemEvidence | None = None
    created_at: Timestamp


class Event(_Entity):
    seq: Annotated[int, Field(ge=1)]
    type: str
    run_id: Id
    turn_id: Id
    payload: dict[str, Any]
    created_at: Timestamp


__all__ = [
    "AcceptanceStatus",
    "Event",
    "ForkOrigin",
    "Id",
    "Item",
    "ItemEvidence",
    "ItemKind",
    "Origin",
    "PermissionMode",
    "Run",
    "RunStatus",
    "RunUsage",
    "Thread",
    "Timestamp",
    "Turn",
    "Workspace",
    "utc_timestamp_now",
]
