// rpc 传输抽象：一套契约两个宿主（桌面 stdio 与浏览器 WS 各实现一份）。
// 上层 client.ts 只认 Transport 接口，不直接依赖 WebSocket 或 stdio；
// M3c-1 落 WebSocketTransport；桌面 SidecarTransport 随 ADR-0024 桌面壳一起推后。

import type { Notification } from "./generated/app_server-v0-1";

export type Json = string | number | boolean | null | Json[] | { [k: string]: Json };
export type JsonObject = { [k: string]: Json };

export interface ResponseFrame {
  id: string;
  result?: JsonObject;
  error?: { code: string; message: string; model_next_action?: string | null };
}

export type NotificationHandler = (n: Notification) => void;
export type ResponseHandler = (r: ResponseFrame) => void;

export interface Transport {
  /** 发一帧请求，返回按 `id` 关联的响应 Promise（result 或 throw error）。 */
  request(method: string, params: JsonObject): Promise<JsonObject>;
  /** 订阅服务端推送的通知；返回 unsubscribe。 */
  onNotification(handler: NotificationHandler): () => void;
  close(): void;
}
