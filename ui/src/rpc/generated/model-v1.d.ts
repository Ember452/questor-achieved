/* 由 src/questor/schemas 生成（src/questor/schemas/model/v1.json）。禁止手写编辑——改动走 schema 与契约文档。 */

/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "Id".
 */
export type Id = string;
/**
 * UTC ISO-8601
 *
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "Timestamp".
 */
export type Timestamp = string;
/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "PermissionMode".
 */
export type PermissionMode = "read_only" | "standard" | "unconfined";
/**
 * 终态 completed|failed|cancelled；steered/waiting 是 running 的旁态
 *
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "RunStatus".
 */
export type RunStatus = "queued" | "running" | "steered" | "waiting" | "completed" | "failed" | "cancelled";
/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "AcceptanceStatus".
 */
export type AcceptanceStatus = "proposed" | "accepted_by_user" | "executing" | "reported" | "verified" | "regressed";
/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "ItemKind".
 */
export type ItemKind = "message" | "tool_call" | "tool_result" | "citation" | "annotation" | "deliverable";
/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "Origin".
 */
export type Origin = "user" | "steer";

/**
 * 核心数据契约实体（真相源：docs/architecture/data-model.md v1.1）。纯 JSON Schema，Python pydantic 只做绑定。
 */
export interface QuestorModel {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "Workspace".
 */
export interface Workspace {
  id: Id;
  name: string;
  /**
   * @minItems 1
   */
  root_paths: [string, ...string[]];
  /**
   * 单调递增，每次可能改变磁盘状态的动作 +1
   */
  revision: number;
  created_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "Thread".
 */
export interface Thread {
  id: Id;
  workspace_id: Id;
  title?: string | null;
  /**
   * 创建时绑定，不静默切换
   */
  engine_id: string;
  permission_mode: PermissionMode;
  pinned: boolean;
  archived: boolean;
  created_at: Timestamp;
  updated_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "Turn".
 */
export interface Turn {
  id: Id;
  thread_id: Id;
  seq: number;
  origin: Origin;
  fork_from?: {
    thread_id: Id;
    turn_seq: number;
    mode: "local" | "worktree";
  } | null;
  created_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "Run".
 */
export interface Run {
  id: Id;
  turn_id: Id;
  engine_id: Id;
  permission_mode: PermissionMode;
  workspace_revision_start?: number | null;
  workspace_revision_end?: number | null;
  status: RunStatus;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    cost_usd?: number | null;
  } | null;
  created_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "Item".
 */
export interface Item {
  id: Id;
  run_id: Id;
  kind: ItemKind;
  payload: {};
  /**
   * 可验证柱：声称的检查与当时录得输出的绑定
   */
  evidence?: {
    claimed?: string;
    recorded_output_ref?: string;
  } | null;
  created_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorModel`'s JSON-Schema
 * via the `definition` "Event".
 */
export interface Event {
  /**
   * 会话内全局递增，重连续传锚点
   */
  seq: number;
  type: string;
  run_id: Id;
  turn_id: Id;
  payload: {};
  created_at: Timestamp;
}
