// QuestorClient：Transport 之上的薄壳，把 typed request 与 notification 分派暴露给组件。
// 类型全部从 rpc/generated 引（R4：禁止手写 DTO）；本文件只做参数命名与 method 名字面量。

import type {
  ThreadCreateParams,
  ThreadCreateResult,
  ThreadListParams,
  ThreadListResult,
  TurnStartParams,
  TurnStartResult,
  TurnSteerParams,
  TurnSteerResult,
  ReviewTurnDiffParams,
  ReviewTurnDiffResult,
  FilesReadParams,
  FilesReadResult,
  FilesListParams,
  FilesListResult,
  ThreadShowParams,
  ThreadShowResult,
  InitializeParams,
  InitializeResult,
  SessiontraceGetParams,
  SessiontraceGetResult,
  SessionControlParams,
  SessionControlResult,
  TaskListParams,
  TaskListResult,
  TaskShowParams,
  TaskShowResult,
  TaskStartParams,
  TaskStartResult,
  TaskRejectParams,
  TaskRejectResult,
  TaskReviewParams,
  TaskReviewResult,
  TaskCompleteParams,
  TaskCompleteResult,
  Notification,
  DeltaNotification,
  ItemStartedNotification,
  ItemCompletedNotification,
  TurnUsageNotification,
  TurnSteeredNotification,
  RunStatusNotification,
  NoticeCompactNotification,
  TaskStatusNotification,
  PlanUpdatedNotification,
  GoalStatusNotification,
  EvidenceReportedNotification,
  NoticeScheduleNotification,
} from "./generated/app_server-v0-1";
import type { JsonObject, Transport } from "./transport";
import { IpcTransport, isElectronHost } from "./ipc-transport";
import { WebSocketTransport } from "./websocket-transport";

/** 本会话中 server 可能推的通知 union（按 method 分岔后 params 形状已知）。 */
export type AnyNotification =
  | DeltaNotification
  | ItemStartedNotification
  | ItemCompletedNotification
  | TurnUsageNotification
  | TurnSteeredNotification
  | RunStatusNotification
  | NoticeCompactNotification
  | TaskStatusNotification
  | PlanUpdatedNotification
  | GoalStatusNotification
  | EvidenceReportedNotification
  | NoticeScheduleNotification;

/** 强类型 method → 参/返 形状的映射（新增方法在此登记一行）。 */
export interface Api {
  initialize: { params: InitializeParams; result: InitializeResult };
  "thread/create": { params: ThreadCreateParams; result: ThreadCreateResult };
  "thread/list": { params: ThreadListParams; result: ThreadListResult };
  "thread/show": { params: ThreadShowParams; result: ThreadShowResult };
  "turn/start": { params: TurnStartParams; result: TurnStartResult };
  "turn/steer": { params: TurnSteerParams; result: TurnSteerResult };
  "review/turn_diff": { params: ReviewTurnDiffParams; result: ReviewTurnDiffResult };
  "files/read": { params: FilesReadParams; result: FilesReadResult };
  "files/list": { params: FilesListParams; result: FilesListResult };
  "sessiontrace/get": { params: SessiontraceGetParams; result: SessiontraceGetResult };
  "session/control": { params: SessionControlParams; result: SessionControlResult };
  "task/list": { params: TaskListParams; result: TaskListResult };
  "task/show": { params: TaskShowParams; result: TaskShowResult };
  "task/start": { params: TaskStartParams; result: TaskStartResult };
  "task/review": { params: TaskReviewParams; result: TaskReviewResult };
  "task/reject": { params: TaskRejectParams; result: TaskRejectResult };
  "task/complete": { params: TaskCompleteParams; result: TaskCompleteResult };
}

type MethodName = keyof Api;

export class QuestorClient {
  // 构造函数默认参数分岔（R-02）：
  //   isElectronHost() 返真 → IpcTransport 走 preload 桥（桌面宿主）；
  //   否则 WebSocketTransport（浏览器 12 测零改路径）。
  // 这个分岔只发生在默认参数上——显式传 transport 的注入位不变（测/集成可手动传 fake）。
  constructor(
    private transport: Transport = isElectronHost()
      ? new IpcTransport(window.questorHost!)
      : new WebSocketTransport(),
  ) {}

  /** 强类型请求；method 与 params 都对齐 generated 类型（R4 的机器保证）。 */
  call<M extends MethodName>(method: M, params: Api[M]["params"]): Promise<Api[M]["result"]> {
    return this.transport.request(method, params as unknown as JsonObject) as Promise<
      Api[M]["result"]
    >;
  }

  /** 订阅服务端推送的通知；返回 unsubscribe。 */
  onNotification(handler: (n: AnyNotification) => void): () => void {
    return this.transport.onNotification((n: Notification) =>
      handler(n as unknown as AnyNotification),
    );
  }

  close(): void {
    this.transport.close();
  }
}

export const client = new QuestorClient();
