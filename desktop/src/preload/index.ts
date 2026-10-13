// preload：contextBridge 白名单出口。B6 起扩到 6 方法（含 R-13 新增的
// onSidecarState 通道）；任何"业务方法"直出即违反纯壳纪律（overview §14）；
// 一切业务调用统一走 request("qst:xxx")。
// 事件与 notification 类型在此 inline 定义、不跨包 import ui 侧（两份 package
// lockfile 独立，per ADR-0032 §结论 4）；结构上应与 ui/src/rpc/generated 里对应
// 的 Notification 保持兼容——Phase E 若要严格 shared types 会开新 ADR。
import { contextBridge, ipcRenderer } from "electron";

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };
type JsonObject = { [k: string]: Json };

interface Notification {
  method: string;
  params?: unknown;
}

type ServerEvent = Notification;

type SidecarStateEvent =
  | { kind: "up"; pid: number }
  | {
      kind: "down";
      code: number | null;
      signal: string | null;
      willRetry: boolean;
    }
  | {
      kind: "budget-exhausted";
      retries: number;
      lastCode: number | null;
      lastSignal: string | null;
    };

const api = {
  request: <T = JsonObject>(method: string, params?: JsonObject) =>
    ipcRenderer.invoke("qst:request", method, params) as Promise<T>,
  respondToServerRequest: (id: string, result: unknown) =>
    ipcRenderer.invoke("qst:respond-server-request", id, result) as Promise<void>,
  rejectServerRequest: (id: string, message: string) =>
    ipcRenderer.invoke("qst:reject-server-request", id, message) as Promise<void>,
  getSnapshot: () =>
    ipcRenderer.invoke("qst:snapshot") as Promise<{ threadId: string }[]>,
  onServerEvent: (handler: (event: ServerEvent) => void): (() => void) => {
    const listener = (
      _e: Electron.IpcRendererEvent,
      payload: ServerEvent,
    ) => handler(payload);
    ipcRenderer.on("qst:server-event", listener);
    return () => ipcRenderer.removeListener("qst:server-event", listener);
  },
  onSidecarState: (
    handler: (state: SidecarStateEvent) => void,
  ): (() => void) => {
    const listener = (
      _e: Electron.IpcRendererEvent,
      payload: SidecarStateEvent,
    ) => handler(payload);
    ipcRenderer.on("qst:sidecar-state", listener);
    return () => ipcRenderer.removeListener("qst:sidecar-state", listener);
  },
};

contextBridge.exposeInMainWorld("questorHost", api);
