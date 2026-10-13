// IpcTransport：Transport 契约的 Electron preload 桥实现（B6 R-01）。
// 方法名严格对齐 ui/src/rpc/transport.ts::Transport 现有形状（request/onNotification/close），
// 不改 Transport 契约、不动 WebSocketTransport；`window.questorHost` 缺失时
// isElectronHost() 返 false → client.ts 构造函数走 WebSocketTransport 分支
// → 浏览器路径 12 测零改（用户停止条件 #3）。
// R-12：Phase U 无消费方，`respondToServerRequest`/`rejectServerRequest`/`getSnapshot`
// 挂在 window.questorHost 上但不进 Transport——未来 Phase E 审批 UI 会直调
// `window.questorHost.respondToServerRequest(...)`。
import type { JsonObject, NotificationHandler, Transport } from "./transport";
import type { QuestorHostApi } from "./questor-host";
import { subscribeServerEvents } from "./server-events-fanout";

export function isElectronHost(): boolean {
  return typeof window !== "undefined" && !!window.questorHost;
}

export class IpcTransport implements Transport {
  constructor(private host: QuestorHostApi) {}

  request(method: string, params: JsonObject): Promise<JsonObject> {
    return this.host.request<JsonObject>(method, params);
  }

  onNotification(handler: NotificationHandler): () => void {
    return subscribeServerEvents(handler);
  }

  close(): void {
    // IPC 无连接概念；preload 桥常驻、由 main 侧 killTree 管 sidecar 生命周期。
  }
}
