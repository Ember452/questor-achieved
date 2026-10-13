// Renderer ↔ Main ↔ Sidecar NDJSON 桥。
// 照 wuu-main/desktop/src/main/appServerClients.ts::AppServerClient 简化到单 client
// （Questor 起步一 shell 一 workspace，多 client MRU 属后续）；**重写实现加 provenance**。
// B-118：server-initiated request 用 `server-request-${N}` public id 桥接，
// 不暴露内核真实 id（避免 renderer 直接拿真 id 发回时与内核内部 ID 空间发生漂移）。
// attach/detach 语义：B5 的 spawnSidecar 会 respawn 新 handle；bridge 作 module-level
// singleton、attach(newHandle) 换接但不丢 sessionOwners/pending 等长跑状态。
import type { SidecarHandle } from "./sidecar";
import { writeFrame } from "./sidecar";

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };
type JsonObject = { [k: string]: Json };

interface Pending {
  resolve: (v: JsonObject) => void;
  reject: (e: unknown) => void;
  method: string;
}

export type AppServerClientEvent =
  | { kind: "notification"; message: { method: string; params?: unknown } }
  | {
      kind: "server-request";
      message: { id: string; method: string; params?: unknown };
    }
  | { kind: "server-exit"; code: number | null; message: string };

export class AppServerBridge {
  private nextRequestID = 1;
  private nextRouteID = 1;
  private pending = new Map<string, Pending>();
  private serverRequestRoutes = new Map<string, { serverID: string }>();
  private sessionOwners = new Set<string>();
  private eventListeners = new Set<(evt: AppServerClientEvent) => void>();
  private stdoutBuf = "";
  private currentHandle: SidecarHandle | null = null;
  private stdoutListener?: (chunk: Buffer) => void;
  private stderrListener?: (chunk: Buffer) => void;

  attach(handle: SidecarHandle): void {
    this.detach();
    this.currentHandle = handle;
    this.stdoutListener = (chunk: Buffer) => this.onStdout(chunk);
    handle.stdout.on("data", this.stdoutListener);
    // questor 侧已保证 stderr 洁净、不污染 stdout（B-87）；主进程另在 main/index.ts
    // 里挂 console.error forwarding，bridge 自己只吞 stderr 保证不阻流。
    this.stderrListener = () => {
      /* sink */
    };
    handle.stderr.on("data", this.stderrListener);
    // F1（审查）：sidecar 死亡时必须把在途 pending 全部 reject + 发 server-exit 事件，
    // 否则 renderer 的 dispatchRequest Promise 永久悬挂（假死 spinner）。
    // 旧 handle 的 exited 回调在新 attach 后靠 currentHandle 比较自行作废。
    void handle.exited.then((r) => {
      if (this.currentHandle !== handle) return;
      const reason = `sidecar exited (code=${r.code} signal=${r.signal ?? "none"})`;
      for (const l of this.eventListeners) {
        l({ kind: "server-exit", code: r.code, message: reason });
      }
      this.detach();
    });
  }

  detach(): void {
    if (!this.currentHandle) return;
    if (this.stdoutListener) {
      this.currentHandle.stdout.off("data", this.stdoutListener);
    }
    if (this.stderrListener) {
      this.currentHandle.stderr.off("data", this.stderrListener);
    }
    this.currentHandle = null;
    // F1：先拒掉所有在途请求与未应答的 server-request，再清归属表——
    // 新 sidecar 认不得旧 id，留着只会让 renderer 永久等待。
    for (const p of this.pending.values()) {
      p.reject(new Error("sidecar detached; request did not complete"));
    }
    this.pending.clear();
    this.serverRequestRoutes.clear();
    // 审查 F5：run/status 协议形状只带 {status}、无 run/thread 身份（见 pitfalls B-122），
    // 无法按终态精确移除单个归属——保守立场：bridge 换接（detach）时全清，
    // snapshot 宁缺勿滥（诚实呈现铁律）。
    this.sessionOwners.clear();
  }

  dispatchRequest(method: string, params: JsonObject): Promise<JsonObject> {
    const handle = this.currentHandle;
    if (!handle) return Promise.reject(new Error("sidecar not attached"));
    const id = `req-${this.nextRequestID++}`;
    return new Promise<JsonObject>((resolve, reject) => {
      this.pending.set(id, { resolve, reject, method });
      writeFrame(handle, { id, method, params });
    });
  }

  respondToServerRequest(publicRouteID: string, result: unknown): void {
    const route = this.serverRequestRoutes.get(publicRouteID);
    if (!route) throw new Error("server request is no longer active");
    this.serverRequestRoutes.delete(publicRouteID);
    if (!this.currentHandle) throw new Error("sidecar not attached");
    writeFrame(this.currentHandle, { id: route.serverID, result });
  }

  rejectServerRequest(publicRouteID: string, message: string): void {
    const route = this.serverRequestRoutes.get(publicRouteID);
    if (!route) throw new Error("server request is no longer active");
    this.serverRequestRoutes.delete(publicRouteID);
    if (!this.currentHandle) throw new Error("sidecar not attached");
    writeFrame(this.currentHandle, {
      id: route.serverID,
      error: { code: "rejected", message },
    });
  }

  runningThreadsSnapshot(): { threadId: string }[] {
    return [...this.sessionOwners].map((threadId) => ({ threadId }));
  }

  onEvent(listener: (evt: AppServerClientEvent) => void): () => void {
    this.eventListeners.add(listener);
    return () => {
      this.eventListeners.delete(listener);
    };
  }

  private onStdout(chunk: Buffer): void {
    this.stdoutBuf += chunk.toString("utf8");
    let nl: number;
    while ((nl = this.stdoutBuf.indexOf("\n")) >= 0) {
      const line = this.stdoutBuf.slice(0, nl).trim();
      this.stdoutBuf = this.stdoutBuf.slice(nl + 1);
      if (!line) continue;
      // F6（审查）：坏帧不得炸穿主进程（data 事件里抛未捕获异常会直接 crash）；
      // 丢弃单行 + console.error 保留现场，不静默。
      let frame: { id?: string; method?: string; params?: unknown; result?: unknown; error?: unknown };
      try {
        frame = JSON.parse(line) as typeof frame;
      } catch (err) {
        console.error(
          `[bridge] 丢弃非法 NDJSON 帧: ${(err as Error).message}; 前 120 字符: ${line.slice(0, 120)}`,
        );
        continue;
      }
      this.handleFrame(frame);
    }
  }

  private handleFrame(msg: {
    id?: string;
    method?: string;
    params?: unknown;
    result?: unknown;
    error?: unknown;
  }): void {
    // 响应帧：有 id、无 method、result/error 至少一个存在。
    if (
      msg.id &&
      msg.method === undefined &&
      (msg.result !== undefined || msg.error !== undefined)
    ) {
      const p = this.pending.get(msg.id);
      if (!p) return;
      this.pending.delete(msg.id);
      if (msg.error) p.reject(msg.error);
      else p.resolve((msg.result ?? {}) as JsonObject);
      return;
    }
    // server-initiated request：id + method 同存 → 桥成 public id，不外泄内核 id。
    if (msg.id && msg.method) {
      const publicID = `server-request-${this.nextRouteID++}`;
      this.serverRequestRoutes.set(publicID, { serverID: msg.id });
      const evt: AppServerClientEvent = {
        kind: "server-request",
        message: { id: publicID, method: msg.method, params: msg.params },
      };
      for (const l of this.eventListeners) l(evt);
      return;
    }
    // 纯 notification：无 id、有 method。`turn/started` 落 sessionOwners。
    if (msg.method) {
      const params = msg.params as { thread_id?: string } | undefined;
      if (msg.method === "turn/started" && params?.thread_id) {
        this.sessionOwners.add(params.thread_id);
      }
      const evt: AppServerClientEvent = {
        kind: "notification",
        message: msg as { method: string; params?: unknown },
      };
      for (const l of this.eventListeners) l(evt);
    }
  }
}
