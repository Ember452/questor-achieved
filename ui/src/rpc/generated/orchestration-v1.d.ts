/* 由 src/questor/schemas 生成（src/questor/schemas/orchestration/v1.json）。禁止手写编辑——改动走 schema 与契约文档。 */

/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "Id".
 */
export type Id = string;
/**
 * UTC ISO-8601
 *
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "Timestamp".
 */
export type Timestamp = string;
/**
 * 编排任务状态机（data-model §3.3，ADR-0025）
 *
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "TaskStatus".
 */
export type TaskStatus =
  | "inbox"
  | "pending"
  | "planning"
  | "planned"
  | "executing"
  | "paused"
  | "reviewed"
  | "completed"
  | "failed"
  | "cancelled";
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "PlanStatus".
 */
export type PlanStatus = "drafting" | "proposed" | "finalized" | "superseded";
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "PlanStepStatus".
 */
export type PlanStepStatus = "pending" | "in_progress" | "done";
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "GoalStatus".
 */
export type GoalStatus = "idle" | "running" | "paused" | "completed" | "failed" | "cancelled";
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "EvidenceSubjectType".
 */
export type EvidenceSubjectType = "run" | "task" | "turn";
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "EvidenceVerdict".
 */
export type EvidenceVerdict = "verified" | "mismatch" | "unverified";
/**
 * 验收状态机（data-model §3.2，ADR-0029）；枚举值与 model/v1.json 逐字一致
 *
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "AcceptanceStatus".
 */
export type AcceptanceStatus = "proposed" | "accepted_by_user" | "executing" | "reported" | "verified" | "regressed";

/**
 * 编排域实体（真相源：docs/architecture/data-model.md v1.4，ADR-0025/0027/0029）。纯 JSON Schema，Python pydantic 只做绑定。
 */
export interface QuestorOrchestration {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "PlanStep".
 */
export interface PlanStep {
  id: Id;
  title: string;
  status: PlanStepStatus;
  task_id?: string | null;
}
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "Plan".
 */
export interface Plan {
  id: Id;
  thread_id?: string | null;
  goal_id?: string | null;
  requirement_revision: number;
  status: PlanStatus;
  steps: PlanStep[];
  created_at: Timestamp;
  updated_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "TaskAcceptance".
 */
export interface TaskAcceptance {
  status: AcceptanceStatus;
  requirement_revision: number;
  evidence_ids: Id[];
}
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "Task".
 */
export interface Task {
  id: Id;
  thread_id?: string | null;
  goal_id?: string | null;
  plan_id?: string | null;
  title: string;
  status: TaskStatus;
  parent_task_id?: string | null;
  depends_on: Id[];
  acceptance: TaskAcceptance;
  run_id?: string | null;
  created_at: Timestamp;
  updated_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "Goal".
 */
export interface Goal {
  id: Id;
  thread_id: Id;
  objective: string;
  status: GoalStatus;
  max_rounds?: number | null;
  round_count: number;
  deadline?: string | null;
  created_at: Timestamp;
  updated_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorOrchestration`'s JSON-Schema
 * via the `definition` "Evidence".
 */
export interface Evidence {
  id: Id;
  subject_type: EvidenceSubjectType;
  subject_id: Id;
  claimed: string;
  recorded_output_ref: string;
  verdict: EvidenceVerdict;
  created_at: Timestamp;
}
