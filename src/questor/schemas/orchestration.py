"""编排域的记录形状（`data-model.md` §2 v1.3，ADR-0025）。

住 `schemas` 的理由与 `habena.py`/`context.py` 同源：写方是 `orchestration`、落盘与回放
是编排 store、跨进程呈现是 `serve`——三方必须看同一份定义，而不是各自复刻字段。
用 pydantic 而非裸 dataclass：它要经 JSON 往返（写进记录流再 fold 回来），
校验必须在入口处爆炸（AGENTS §四"跨边界数据一律 pydantic v2"）。

全部 frozen + `extra="forbid"`：append-only 纪律在模型层的第一道表达（改历史 = 建新记录）。
本模块**不 import 任何业务模块**（schemas 无依赖，见 structure §5）。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Evidence",
    "EvidenceSubjectType",
    "EvidenceVerdict",
    "Goal",
    "GoalStatus",
    "OrchestrationGateError",
    "Plan",
    "PlanStatus",
    "PlanStep",
    "PlanStepStatus",
    "Task",
    "TaskAcceptance",
    "TaskStatus",
]


class OrchestrationGateError(Exception):
    """编排门拒绝（结构化方言：error_code / message / hint）。

    住 `schemas` 是因为它要跨层：`orchestration`（抛）、`tools`（catch 转工具错误）、
    `serve`（catch 转 ProtocolError）三方都要认识它。`error_code` 取 protocol §7 的
    字符串码（need_plan_first / need_execution_authorization / plan_subtasks_already_synced）。
    """

    def __init__(self, error_code: str, message: str, hint: str = "") -> None:
        self.error_code = error_code
        self.message = message
        self.hint = hint
        super().__init__(f"{error_code}: {message}")


class _Frozen(BaseModel):
    """冻结 + 禁额外字段：与 `schemas/model.py` 的实体同一套纪律。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class TaskStatus(StrEnum):
    """编排任务状态（data-model §3.3）；迁移白名单唯一入口在 orchestration.transitions。"""

    INBOX = "inbox"
    PENDING = "pending"
    PLANNING = "planning"
    PLANNED = "planned"
    EXECUTING = "executing"
    PAUSED = "paused"
    REVIEWED = "reviewed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanStatus(StrEnum):
    """计划状态：先澄清→可修订→定稿才执行。"""

    DRAFTING = "drafting"
    PROPOSED = "proposed"
    FINALIZED = "finalized"
    SUPERSEDED = "superseded"


class PlanStepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class GoalStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvidenceSubjectType(StrEnum):
    RUN = "run"
    TASK = "task"
    TURN = "turn"


class EvidenceVerdict(StrEnum):
    """核对结论；无记录支持一律 UNVERIFIED，不臆断（诚实呈现铁律，ADR-0027）。"""

    VERIFIED = "verified"
    MISMATCH = "mismatch"
    UNVERIFIED = "unverified"


class PlanStep(_Frozen):
    """计划的一步；定稿后可同步派生 Task（`task_id` 回链）。"""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: PlanStepStatus = PlanStepStatus.PENDING
    task_id: str | None = None


class Plan(_Frozen):
    """可修订计划（data-model §2）。

    ``requirement_revision`` 递增即自动作废既有验收：作废表现为**追加**一条作废记录、
    不改写历史（append-only）。
    """

    id: str = Field(min_length=1)
    thread_id: str | None = None
    goal_id: str | None = None
    requirement_revision: int = Field(ge=1)
    status: PlanStatus
    steps: tuple[PlanStep, ...] = ()
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class TaskAcceptance(_Frozen):
    """任务验收绑定（data-model §3.2 验收状态机在编排侧的对应物）。"""

    status: str = "proposed"
    requirement_revision: int = Field(ge=1)
    evidence_ids: tuple[str, ...] = ()


class Task(_Frozen):
    """看板任务单元（data-model §2）。``depends_on`` 承载 DAG 依赖边。"""

    id: str = Field(min_length=1)
    thread_id: str | None = None
    goal_id: str | None = None
    plan_id: str | None = None
    title: str = Field(min_length=1)
    status: TaskStatus
    parent_task_id: str | None = None
    depends_on: tuple[str, ...] = ()
    acceptance: TaskAcceptance
    run_id: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class Goal(_Frozen):
    """后台自驱长跑目标（data-model §2）。"""

    id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    status: GoalStatus
    max_rounds: int | None = Field(default=None, ge=1)
    round_count: int = Field(default=0, ge=0)
    deadline: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class Evidence(_Frozen):
    """声称的检查 vs 当时录得的真实输出（data-model §3.4，ADR-0027）。

    ``recorded_output_ref`` 指向具体记录条目（Item/Event id 或 spill 回链）——
    结论必须可追溯；没有记录支撑就只能是 ``unverified``。
    """

    id: str = Field(min_length=1)
    subject_type: EvidenceSubjectType
    subject_id: str = Field(min_length=1)
    claimed: str
    recorded_output_ref: str
    verdict: EvidenceVerdict
    created_at: str = Field(min_length=1)
