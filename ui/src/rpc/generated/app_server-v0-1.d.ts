/* 由 src/questor/schemas 生成（src/questor/schemas/app_server/v0-1.json）。禁止手写编辑——改动走 schema 与契约文档。 */

/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "Id".
 */
export type Id = string;
/**
 * UTC ISO-8601
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "Timestamp".
 */
export type Timestamp = string;
/**
 * 与 model/v1.json#/$defs/PermissionMode 保持一致（护栏测试校验）
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "PermissionMode".
 */
export type PermissionMode = "read_only" | "standard" | "unconfined";
/**
 * 与 model/v1.json#/$defs/RunStatus 保持一致；steered/waiting 是 running 的旁态
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "RunStatus".
 */
export type RunStatus = "queued" | "running" | "steered" | "waiting" | "completed" | "failed" | "cancelled";
/**
 * 与 model/v1.json#/$defs/AcceptanceStatus 保持一致（data-model §3.2）
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "AcceptanceStatus".
 */
export type AcceptanceStatus = "proposed" | "accepted_by_user" | "executing" | "reported" | "verified" | "regressed";
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ProtocolVersion".
 */
export type ProtocolVersion = "qst-app-server/v0.1";
/**
 * 编排任务状态机（data-model §3.3，ADR-0025）
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
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
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalStatus".
 */
export type GoalStatus = "idle" | "running" | "paused" | "completed" | "failed" | "cancelled";
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "EvidenceVerdict".
 */
export type EvidenceVerdict = "verified" | "mismatch" | "unverified";

/**
 * qst-app-server/v0.1 跨进程信封与方法契约（真相源：docs/architecture/protocol.md v1.1）。错误码是字符串；能力 opt-in；版本号只标记破坏性变化（ADR-0028）。$defs 里每个方法/通知族都有 Params/Result/Notification 形状，护栏 test_schemas_method_families 逐项对账；跨进程 DTO 与 model/v1.json 字段一致。
 */
export interface QuestorAppServer {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "Request".
 */
export interface Request {
  id: string;
  /**
   * 方法名，具体形状见 $defs.<Method>Params
   */
  method: string;
  params?: {};
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "Response".
 */
export interface Response {
  id: string;
  result?: {} | null;
  error?: ErrorPayload;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ErrorPayload".
 */
export interface ErrorPayload {
  /**
   * 字符串错误码（非 JSON-RPC 数值码）
   */
  code:
    | "boundary_denied"
    | "need_execution_authorization"
    | "need_plan_first"
    | "stale_revision"
    | "protocol_version_mismatch"
    | "unknown_method"
    | "invalid_params"
    | "internal_error";
  message: string;
  /**
   * limen 方言：指导模型下一步动作
   */
  model_next_action?: string | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "Notification".
 */
export interface Notification {
  method: string;
  params?: {};
}
/**
 * 跨进程可见 Thread（字段与 model/v1.json#/$defs/Thread 一致，护栏 test_schema_bindings 对账）
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadDTO".
 */
export interface ThreadDTO {
  id: Id;
  workspace_id: Id;
  title?: string | null;
  engine_id: Id;
  permission_mode: PermissionMode;
  pinned: boolean;
  archived: boolean;
  created_at: Timestamp;
  updated_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "WorkspaceDTO".
 */
export interface WorkspaceDTO {
  id: Id;
  name: string;
  /**
   * @minItems 1
   */
  root_paths: [string, ...string[]];
  revision: number;
  created_at: Timestamp;
}
/**
 * 一段 unified diff 的变更块（review.compute_diff 产出）
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "DiffHunk".
 */
export interface DiffHunk {
  old_start: number;
  old_lines: number;
  new_start: number;
  new_lines: number;
  body: string[];
}
/**
 * 一个文件的完整变更（写时算、随 Item.payload 落盘）
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "FileDiff".
 */
export interface FileDiff {
  path: string;
  created: boolean;
  hunks: DiffHunk[];
  content_fingerprint: string;
  byte_size: number;
  unified: string;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "InitializeParams".
 */
export interface InitializeParams {
  client_version: string;
  capabilities: {
    reverse_rpc?: {
      methods?: string[];
    } | null;
    /**
     * opt-in，不声明不启用
     */
    deferred_notification_content?: boolean;
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "InitializeResult".
 */
export interface InitializeResult {
  protocol_version: ProtocolVersion;
  status: "ready" | "needs_setup";
  issues: string[];
  build: {
    version: string;
    commit: string;
  };
  host: {
    os: string;
    arch: string;
  };
  /**
   * 本机归属标识；本期仅传递与回显（ADR-0020），不含鉴权
   */
  principal: string;
  threads: Id[];
  permissions: {
    mode: PermissionMode;
    sandboxed?: boolean;
  };
  engines: {
    id: Id;
    status: "unsupported" | "error" | "empty" | "ready";
  }[];
  feature_flags: string[];
  max_concurrency: number;
  methods: string[];
  notification_families: string[];
  client_capabilities: {};
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadCreateParams".
 */
export interface ThreadCreateParams {
  id?: Id;
  workspace_id?: Id;
  title?: string | null;
  engine_id?: Id;
  permission_mode?: PermissionMode;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadCreateResult".
 */
export interface ThreadCreateResult {
  thread: ThreadDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadListParams".
 */
export interface ThreadListParams {}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadListResult".
 */
export interface ThreadListResult {
  threads: ThreadDTO[];
  principal: string;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadRenameParams".
 */
export interface ThreadRenameParams {
  thread_id: Id;
  title: string;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadRenameResult".
 */
export interface ThreadRenameResult {
  thread: ThreadDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadArchiveParams".
 */
export interface ThreadArchiveParams {
  thread_id: Id;
  archived: boolean;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadArchiveResult".
 */
export interface ThreadArchiveResult {
  thread: ThreadDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadDeleteParams".
 */
export interface ThreadDeleteParams {
  thread_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadDeleteResult".
 */
export interface ThreadDeleteResult {
  deleted: boolean;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadShowParams".
 */
export interface ThreadShowParams {
  thread_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadShowResult".
 */
export interface ThreadShowResult {
  thread: ThreadDTO;
  turns?: {}[];
  items?: {}[];
  events?: {}[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadForkParams".
 */
export interface ThreadForkParams {
  thread_id: Id;
  new_thread_id?: Id;
  workspace_id?: Id;
  mode?: "local" | "worktree";
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ThreadForkResult".
 */
export interface ThreadForkResult {
  thread: ThreadDTO;
  mode: "local" | "worktree";
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnStartParams".
 */
export interface TurnStartParams {
  thread_id: Id;
  user_text: string;
  resume?: boolean;
  client_id?: string;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnStartResult".
 */
export interface TurnStartResult {
  thread_id: Id;
  accepted: boolean;
  origin: "user" | "steer";
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnSteerParams".
 */
export interface TurnSteerParams {
  thread_id: Id;
  /**
   * 幂等键（B-63）
   */
  client_id: string;
  content: string;
  /**
   * 空=旧客户端兼容放行；非空不匹配当前 turn=拒绝（B-64）
   */
  expected_turn_id?: string | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnSteerResult".
 */
export interface TurnSteerResult {
  accepted: boolean;
  thread_id: Id;
}
/**
 * iteration 起点消费插话时发（B-67/94）；client_id 回链供宿主幂等判重
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnSteeredNotification".
 */
export interface TurnSteeredNotification {
  method: "turn/steered";
  params: {
    thread_id: Id;
    client_id: string;
    content: string;
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnQueueParams".
 */
export interface TurnQueueParams {
  thread_id: Id;
  client_id: string;
  content: string;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnQueueResult".
 */
export interface TurnQueueResult {
  accepted: boolean;
  thread_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnDequeueParams".
 */
export interface TurnDequeueParams {
  thread_id: Id;
  client_id: string;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnDequeueResult".
 */
export interface TurnDequeueResult {
  removed: boolean;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "RunStopParams".
 */
export interface RunStopParams {
  thread_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "RunStopResult".
 */
export interface RunStopResult {
  thread_id: Id;
  cancelling: boolean;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "SessionControlParams".
 */
export interface SessionControlParams {
  thread_id: Id;
  action: "take_over" | "pause" | "release";
  /**
   * CAS 栅栏：stale 进程不能撤销人的接管（overview §12）
   */
  expected_revision?: number | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "SessionControlResult".
 */
export interface SessionControlResult {
  holder: "user" | "agent";
  revision: number;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "WorkspaceStatusParams".
 */
export interface WorkspaceStatusParams {
  workspace_id?: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "WorkspaceStatusResult".
 */
export interface WorkspaceStatusResult {
  workspaces: WorkspaceDTO[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "WorkspaceRevisionParams".
 */
export interface WorkspaceRevisionParams {
  workspace_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "WorkspaceRevisionResult".
 */
export interface WorkspaceRevisionResult {
  revision: number;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ReviewTurnDiffParams".
 */
export interface ReviewTurnDiffParams {
  thread_id: Id;
  turn_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ReviewTurnDiffResult".
 */
export interface ReviewTurnDiffResult {
  diffs: FileDiff[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "FilesReadParams".
 */
export interface FilesReadParams {
  path: string;
  workspace_id?: Id;
  expected_revision?: number | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "FilesReadResult".
 */
export interface FilesReadResult {
  content: string;
  revision: number;
  content_fingerprint: string;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "FilesListParams".
 */
export interface FilesListParams {
  path?: string;
  workspace_id?: Id;
  recursive?: boolean;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "FilesListEntry".
 */
export interface FilesListEntry {
  kind: "file" | "dir";
  path: string;
  size?: number | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "FilesListResult".
 */
export interface FilesListResult {
  entries: FilesListEntry[];
  revision: number;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ContentReadParams".
 */
export interface ContentReadParams {
  thread_id: Id;
  tool_use_id: string;
  offset?: number | null;
  limit?: number | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ContentReadResult".
 */
export interface ContentReadResult {
  content: string;
  truncated: boolean;
  next_offset?: number | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "AttachmentReadParams".
 */
export interface AttachmentReadParams {
  thread_id: Id;
  attachment_id: string;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "AttachmentReadResult".
 */
export interface AttachmentReadResult {
  content_b64: string;
  mime: string;
  filename: string;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "SessiontraceGetParams".
 */
export interface SessiontraceGetParams {
  thread_id: Id;
  turn_id?: string | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnTraceDTO".
 */
export interface TurnTraceDTO {
  turn_id: Id;
  seq: number;
  origin: "user" | "steer";
  run_ids: Id[];
  items: {}[];
  events: {}[];
}
/**
 * 给定 turn_id 时返回单 trace；否则返回整线程的 turns 列表
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "SessiontraceGetResult".
 */
export interface SessiontraceGetResult {
  trace?: TurnTraceDTO | null;
  turns?: TurnTraceDTO[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "DeltaNotification".
 */
export interface DeltaNotification {
  method: "delta";
  params: {
    text: string;
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ItemStartedNotification".
 */
export interface ItemStartedNotification {
  method: "item/started";
  params: {
    tool_use_id: string;
    name: string;
    arguments?: {};
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ItemCompletedNotification".
 */
export interface ItemCompletedNotification {
  method: "item/completed";
  params: {
    tool_use_id: string;
    name: string;
    is_error: boolean;
    elapsed_s?: number;
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TurnUsageNotification".
 */
export interface TurnUsageNotification {
  method: "turn/usage";
  params: {
    input_tokens: number;
    output_tokens: number;
    cache_read: number;
    cache_creation: number;
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "RunStatusNotification".
 */
export interface RunStatusNotification {
  method: "run/status";
  params: {
    status: RunStatus;
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "NoticeCompactNotification".
 */
export interface NoticeCompactNotification {
  method: "notice/compact";
  params: {
    kind: "started" | "compacted" | "noop" | "failed" | "breaker_open";
    before_tokens?: number | null;
    after_tokens?: number | null;
    reason?: string | null;
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "PlanStepDTO".
 */
export interface PlanStepDTO {
  id: Id;
  title: string;
  status: "pending" | "in_progress" | "done";
  task_id?: string | null;
}
/**
 * 可修订计划（data-model v1.3 Plan，ADR-0025）
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "PlanDTO".
 */
export interface PlanDTO {
  id: Id;
  thread_id?: string | null;
  goal_id?: string | null;
  requirement_revision: number;
  status: "drafting" | "proposed" | "finalized" | "superseded";
  steps: PlanStepDTO[];
  created_at: Timestamp;
  updated_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskAcceptanceDTO".
 */
export interface TaskAcceptanceDTO {
  status: AcceptanceStatus;
  requirement_revision: number;
  evidence_ids: Id[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskDTO".
 */
export interface TaskDTO {
  id: Id;
  thread_id?: string | null;
  goal_id?: string | null;
  plan_id?: string | null;
  title: string;
  status: TaskStatus;
  parent_task_id?: string | null;
  depends_on: Id[];
  acceptance: TaskAcceptanceDTO;
  run_id?: string | null;
  created_at: Timestamp;
  updated_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalDTO".
 */
export interface GoalDTO {
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
 * 声称的检查 vs 当时录得的真实输出（ADR-0027）
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "EvidenceDTO".
 */
export interface EvidenceDTO {
  id: Id;
  subject_type: "run" | "task" | "turn";
  subject_id: Id;
  claimed: string;
  recorded_output_ref: string;
  verdict: EvidenceVerdict;
  created_at: Timestamp;
}
/**
 * 值守触发器（vigilia，ADR-0026）：声明式数据
 *
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ScheduleDTO".
 */
export interface ScheduleDTO {
  id: Id;
  trigger_kind: "once" | "interval" | "cron";
  enabled: boolean;
  once_fired: boolean;
  interval_seconds?: number | null;
  cron?: string | null;
  next_fire_at?: string | null;
  /**
   * task 目标（M5）；为 null 时走 thread 目标
   */
  task_id?: string | null;
  /**
   * thread 目标的会话；task 目标为任务所属线程
   */
  thread_id?: string | null;
  created_at: Timestamp;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskCreateParams".
 */
export interface TaskCreateParams {
  title: string;
  thread_id?: Id;
  goal_id?: Id;
  plan_id?: Id;
  parent_task_id?: Id;
  depends_on?: Id[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskCreateResult".
 */
export interface TaskCreateResult {
  task: TaskDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskListParams".
 */
export interface TaskListParams {
  thread_id?: Id;
  goal_id?: Id;
  workspace_id?: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskListResult".
 */
export interface TaskListResult {
  tasks: TaskDTO[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskShowParams".
 */
export interface TaskShowParams {
  task_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskShowResult".
 */
export interface TaskShowResult {
  task: TaskDTO;
  plan?: PlanDTO | null;
  evidence?: EvidenceDTO[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskPlanParams".
 */
export interface TaskPlanParams {
  plan_id?: Id;
  thread_id?: Id;
  goal_id?: Id;
  steps: {
    id?: Id;
    title: string;
  }[];
  finalize?: boolean;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskPlanResult".
 */
export interface TaskPlanResult {
  plan: PlanDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskStartParams".
 */
export interface TaskStartParams {
  task_id: Id;
  /**
   * 用户「开始执行」授权；缺省 false → 编排门拒绝
   */
  authorized?: boolean;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskStartResult".
 */
export interface TaskStartResult {
  task: TaskDTO;
  run_id?: string | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskPauseParams".
 */
export interface TaskPauseParams {
  task_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskPauseResult".
 */
export interface TaskPauseResult {
  task: TaskDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskResumeParams".
 */
export interface TaskResumeParams {
  task_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskResumeResult".
 */
export interface TaskResumeResult {
  task: TaskDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskReviewParams".
 */
export interface TaskReviewParams {
  task_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskReviewResult".
 */
export interface TaskReviewResult {
  task: TaskDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskRejectParams".
 */
export interface TaskRejectParams {
  task_id: Id;
  reason?: string | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskRejectResult".
 */
export interface TaskRejectResult {
  task: TaskDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskRetryParams".
 */
export interface TaskRetryParams {
  task_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskRetryResult".
 */
export interface TaskRetryResult {
  task: TaskDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskCompleteParams".
 */
export interface TaskCompleteParams {
  task_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskCompleteResult".
 */
export interface TaskCompleteResult {
  task: TaskDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalCreateParams".
 */
export interface GoalCreateParams {
  thread_id: Id;
  objective: string;
  max_rounds?: number | null;
  deadline?: string | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalCreateResult".
 */
export interface GoalCreateResult {
  goal: GoalDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalListParams".
 */
export interface GoalListParams {
  thread_id?: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalListResult".
 */
export interface GoalListResult {
  goals: GoalDTO[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalShowParams".
 */
export interface GoalShowParams {
  goal_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalShowResult".
 */
export interface GoalShowResult {
  goal: GoalDTO;
  tasks?: TaskDTO[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalStartParams".
 */
export interface GoalStartParams {
  goal_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalStartResult".
 */
export interface GoalStartResult {
  goal: GoalDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalStopParams".
 */
export interface GoalStopParams {
  goal_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalStopResult".
 */
export interface GoalStopResult {
  goal: GoalDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ScheduleCreateParams".
 */
export interface ScheduleCreateParams {
  trigger_kind: "once" | "interval" | "cron";
  /**
   * interval 必填
   */
  interval_seconds?: number | null;
  /**
   * cron 必填：5 字段表达式（分 时 日 月 周）
   */
  cron?: string | null;
  /**
   * UTC 秒级时刻；缺省为立即到点
   */
  next_fire_at?: string | null;
  /**
   * thread 目标：到点在它起一轮（与 prompt 同时必填）
   */
  thread_id?: string | null;
  /**
   * thread 目标那轮的用户文本指令
   */
  prompt?: string | null;
  /**
   * task 目标（M5）：到点派发该任务执行；给了即以 task 为准，不再需 thread_id+prompt
   */
  task_id?: string | null;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ScheduleCreateResult".
 */
export interface ScheduleCreateResult {
  schedule: ScheduleDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ScheduleListParams".
 */
export interface ScheduleListParams {}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ScheduleListResult".
 */
export interface ScheduleListResult {
  schedules: ScheduleDTO[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ScheduleEnableParams".
 */
export interface ScheduleEnableParams {
  schedule_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ScheduleEnableResult".
 */
export interface ScheduleEnableResult {
  schedule: ScheduleDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ScheduleDisableParams".
 */
export interface ScheduleDisableParams {
  schedule_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "ScheduleDisableResult".
 */
export interface ScheduleDisableResult {
  schedule: ScheduleDTO;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "EvidenceGetParams".
 */
export interface EvidenceGetParams {
  subject_type: "run" | "task" | "turn";
  subject_id: Id;
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "EvidenceGetResult".
 */
export interface EvidenceGetResult {
  evidence: EvidenceDTO[];
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "TaskStatusNotification".
 */
export interface TaskStatusNotification {
  method: "task/status";
  params: {
    task_id: Id;
    status: TaskStatus;
    title?: string | null;
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "PlanUpdatedNotification".
 */
export interface PlanUpdatedNotification {
  method: "plan/updated";
  params: {
    plan_id: Id;
    requirement_revision: number;
    status: "drafting" | "proposed" | "finalized" | "superseded";
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "GoalStatusNotification".
 */
export interface GoalStatusNotification {
  method: "goal/status";
  params: {
    goal_id: Id;
    status: GoalStatus;
    round_count: number;
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "EvidenceReportedNotification".
 */
export interface EvidenceReportedNotification {
  method: "evidence/reported";
  params: {
    evidence_id: Id;
    subject_type: "run" | "task" | "turn";
    subject_id: Id;
    verdict: EvidenceVerdict;
    recorded_output_ref: string;
  };
}
/**
 * This interface was referenced by `QuestorAppServer`'s JSON-Schema
 * via the `definition` "NoticeScheduleNotification".
 */
export interface NoticeScheduleNotification {
  method: "notice/schedule";
  params: {
    schedule_id: Id;
    kind: "once" | "interval" | "cron";
    outcome: "fired" | "skipped" | "disabled";
  };
}
