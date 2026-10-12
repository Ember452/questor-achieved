"""orchestration —— 编排域（Plan / Goal / 看板 / 验收与打回）。

承担柱子：**可干预 + 可验证**。它是有界上下文：Task/Plan/Goal/Evidence 住**独立**
append-only store（ADR-0025），状态机单点入口（`transitions.py`），破坏性编排动作过
**编排门**（`gate.py`，返回结构化错误载荷 B-43）。

语义规格来自 EvoFlow `collab/`（`docs/specs/behavior-orchestration-ef.md`）。
与 `vigilia` 的分工：vigilia 管"什么时候跑"，orchestration 管"跑什么、跑到哪一步、
谁来验收"；依赖方向 `orchestration → vigilia`（structure §5）。

# Reimplements evoflow@<tag> collab/state_transitions.py + supervisor_plan_gate.py
#   — pitfalls: B-43（B-38/B-39 经 M4 裁定为 moot，见 docs/specs/pitfalls.md）
"""

from __future__ import annotations

from questor.orchestration.acceptance import (
    InvalidAcceptanceTransition,
)
from questor.orchestration.board import BoardEdge, BoardView, build_board, has_cycle, open_tasks
from questor.orchestration.gate import (
    EXEC_AUTHORIZATION_ACTIONS,
    PLAN_REDUNDANT_SETUP_ACTIONS,
    PLAN_REQUIRED_ACTIONS,
    GateResult,
    evaluate,
)
from questor.orchestration.goal import (
    create_goal,
    fail_goal,
    get_goal,
    is_expired,
    record_round,
    round_instruction,
    start_goal,
    stop_goal,
)
from questor.orchestration.plan import (
    finalize_plan,
    get_plan,
    plan_task_ids,
    propose_plan,
    revise_plan,
)
from questor.orchestration.service import OrchestrationService
from questor.orchestration.store import (
    OrchestrationStoreError,
    OrchestrationView,
    TaskNotFound,
    add_evidence,
    add_task,
    invalidate_acceptances,
    list_tasks,
    load_view,
    rebuild_index,
    transition_acceptance,
    transition_task,
    update_task,
)
from questor.orchestration.tasks import (
    complete_task,
    create_task,
    get_task,
    mark_step_done,
    pause_task,
    reject_task,
    resume_task,
    retry_task,
    review_task,
    start_task,
    sync_subtasks_from_plan,
)
from questor.orchestration.transitions import (
    InvalidTaskTransition,
    allowed_targets,
    is_terminal,
    transition,
)

__all__ = [
    "EXEC_AUTHORIZATION_ACTIONS",
    "PLAN_REDUNDANT_SETUP_ACTIONS",
    "PLAN_REQUIRED_ACTIONS",
    "BoardEdge",
    "BoardView",
    "GateResult",
    "InvalidAcceptanceTransition",
    "InvalidTaskTransition",
    "OrchestrationStoreError",
    "OrchestrationService",
    "OrchestrationView",
    "TaskNotFound",
    "add_evidence",
    "add_task",
    "allowed_targets",
    "build_board",
    "complete_task",
    "create_goal",
    "create_task",
    "evaluate",
    "fail_goal",
    "finalize_plan",
    "get_goal",
    "get_plan",
    "get_task",
    "has_cycle",
    "invalidate_acceptances",
    "is_expired",
    "is_terminal",
    "list_tasks",
    "load_view",
    "mark_step_done",
    "open_tasks",
    "pause_task",
    "plan_task_ids",
    "propose_plan",
    "rebuild_index",
    "record_round",
    "reject_task",
    "resume_task",
    "retry_task",
    "review_task",
    "revise_plan",
    "round_instruction",
    "start_goal",
    "start_task",
    "stop_goal",
    "sync_subtasks_from_plan",
    "transition",
    "transition_acceptance",
    "transition_task",
    "update_task",
]
