// WebSocketTransport：M3b-3 的 WS 端点在浏览器/桌面对等的客户端实现。
// 一条连接 = 一个 pending Map<id, resolver> + 一个通知回调集合。
// 帧形式与 envelope.py 严格一致（`id` + `method` + `params`；响应 `id` + `result`/`error`；
// 通知 `method` + `params` 不带 id），因此 parse 分岔按 "method 有无 + id 有无" 判。

import type { Notification } from "../rpc/generated/app_server-v0-1";
import type {
  JsonObject,
  NotificationHandler,
  ResponseFrame,
  Transport,
} from "./transport";

interface Pending {
  resolve: (value: JsonObject) => void;
  reject: (err: Error) => void;
}

let counter = 0;
function nextId(): string {
  counter += 1;
  return `c${counter.toString(36)}-${Date.now().toString(36)}`;
}

export class WebSocketTransport implements Transport {
  private ws: WebSocket;
  private pending = new Map<string, Pending>();
  private handlers = new Set<NotificationHandler>();
  private ready: Promise<void>;

  constructor(url: string = deriveDefaultUrl()) {
    this.ws = new WebSocket(url);
    this.ready = new Promise((resolve, reject) => {
      this.ws.addEventListener("open", () => resolve());
      this.ws.addEventListener("error", () => reject(new Error("WebSocket 连接失败")));
    });
    this.ws.addEventListener("message", (ev) => this.onMessage(ev));
    this.ws.addEventListener("close", () => this.onClose());
  }

  async request(method: string, params: JsonObject): Promise<JsonObject> {
    await this.ready;
    const id = nextId();
    const frame = JSON.stringify({ id, method, params });
    const promise = new Promise<JsonObject>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
    this.ws.send(frame);
    return promise;
  }

  onNotification(handler: NotificationHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  close(): void {
    try {
      this.ws.close();
    } catch {
      /* 已关闭 → 忽略 */
    }
  }

  private onMessage(ev: MessageEvent<string>): void {
    let frame: Record<string, unknown>;
    try {
      frame = JSON.parse(ev.data) as Record<string, unknown>;
    } catch {
      return; // 非 JSON 帧直接丢弃（服务端不会发这种，出现说明中间层被污染）
    }
    const id = typeof frame.id === "string" ? frame.id : null;
    const method = typeof frame.method === "string" ? frame.method : null;
    if (id !== null && method === null) {
      this.dispatchResponse(id, frame);
      return;
    }
    if (method !== null && id === null) {
      this.dispatchNotification(frame as unknown as Notification);
    }
    // 反向请求帧（带 id 且带 method）本期不消费：审批弹窗属 Phase E
  }

  private dispatchResponse(id: string, frame: Record<string, unknown>): void {
    const pending = this.pending.get(id);
    if (!pending) return;
    this.pending.delete(id);
    if (frame.error) {
      const err = frame.error as { code: string; message: string };
      pending.reject(new Error(`${err.code}: ${err.message}`));
    } else {
      pending.resolve((frame.result ?? {}) as JsonObject);
    }
  }

  private dispatchNotification(note: Notification): void {
    for (const handler of this.handlers) {
      try {
        handler(note);
      } catch (err) {
        console.error("通知回调抛错（不影响其他订阅者）", err);
      }
    }
  }

  private onClose(): void {
    const err = new Error("WebSocket 连接已关闭");
    for (const [, pending] of this.pending) pending.reject(err);
    this.pending.clear();
  }
}

function deriveDefaultUrl(): string {
  // 浏览器：与页面同源，协议换成 ws / wss；端口由 uvicorn 决定（默认 8765 时同源不适用，
  // 走 vite proxy 或显式传参；本函数只覆盖"uvicorn 同时伺服 ui/dist"的场景）。
  const proto = globalThis.location?.protocol === "https:" ? "wss:" : "ws:";
  const host = globalThis.location?.host ?? "127.0.0.1:8765";
  return `${proto}//${host}/ws`;
}
