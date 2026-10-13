// 单桥 fanout：一次 window.questorHost.onServerEvent 订阅、内部向 Set<listener> 分发。
// 照 wuu-main/desktop/src/renderer/ServerEvents.ts (21 行) 重写：
//   - `disconnect ??= host.onServerEvent(broadcast)`：第一个 listener 时建立唯一桥；
//   - 最后一个 listener 走时 `disconnect?.(); disconnect = undefined`：拆桥防 preload 侧
//     listener 泄漏。
// 事件身份与顺序由 preload → webContents.send → 本 fanout 三层保证；不做二次合批
// （合批在 desktop/main/renderer-batcher.ts 已完成，per B-117）。
import type { Notification } from "./generated/app_server-v0-1";
import "./questor-host"; // 触发 declare global  augmentation

type Handler = (n: Notification) => void;

let listeners: Set<Handler> | null = null;
let disconnect: (() => void) | undefined;

function broadcast(n: Notification): void {
  for (const l of listeners ?? []) {
    try {
      l(n);
    } catch (err) {
      // 单个回调抛错不影响其他订阅者——与 WebSocketTransport.dispatchNotification 同形。
      console.error("通知回调抛错（不影响其他订阅者）", err);
    }
  }
}

export function subscribeServerEvents(handler: Handler): () => void {
  if (!listeners) listeners = new Set();
  listeners.add(handler);
  if (disconnect === undefined && typeof window !== "undefined" && window.questorHost) {
    disconnect = window.questorHost.onServerEvent(broadcast);
  }
  const current = listeners;
  return () => {
    current.delete(handler);
    if (current.size === 0 && disconnect !== undefined) {
      disconnect();
      disconnect = undefined;
      listeners = null;
    }
  };
}

/** 仅供测试：清 fanout 单例状态。 */
export function __resetFanoutForTests(): void {
  if (disconnect !== undefined) disconnect();
  disconnect = undefined;
  listeners = null;
}
