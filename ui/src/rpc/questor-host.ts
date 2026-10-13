// QuestorHostApi 类型与 window 声明（B6 R-01/R-12）。
// 单独文件避免 ipc-transport ↔ server-events-fanout 的 circular import。
// ui/ 与 desktop/preload 各持一份 inline 定义（两份 package 独立 lockfile，
// ADR-0032 §结论 4）；结构一致、Phase E 若要 promote shared types 会另开 ADR。
import type { Notification } from "./generated/app_server-v0-1";
import type { JsonObject } from "./transport";

export interface QuestorHostApi {
  request<T = JsonObject>(method: string, params?: JsonObject): Promise<T>;
  onServerEvent(handler: (n: Notification) => void): () => void;
  onSidecarState(handler: (state: unknown) => void): () => void;
  respondToServerRequest(id: string, result: unknown): Promise<void>;
  rejectServerRequest(id: string, message: string): Promise<void>;
  getSnapshot(): Promise<{ threadId: string }[]>;
}

declare global {
  interface Window {
    questorHost?: QuestorHostApi;
  }
}
