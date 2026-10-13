// B6 R-01/R-02/R-13 护栏：isElectronHost 语义 + IpcTransport 契约 + fanout 单桥。
// 浏览器路径的 12 测（review.panel/review.fidelity/design.tokens）在本文件之外，
// 用户停止条件 #3——那 12 测必须仍绿——由 `npm --prefix ui run test` 总绿断言。
// 本文件只咬 B6 新加的三条 UI 契约。
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Notification } from "../src/rpc/generated/app_server-v0-1";
import {
  IpcTransport,
  isElectronHost,
} from "../src/rpc/ipc-transport";
import { __resetFanoutForTests } from "../src/rpc/server-events-fanout";
import type { QuestorHostApi } from "../src/rpc/questor-host";

function fakeHost(
  over: Partial<QuestorHostApi> = {},
): QuestorHostApi & { onServerEventCalls: number; unsubCalls: number[] } {
  const unsubCalls: number[] = [];
  let onServerEventCalls = 0;
  return {
    request: async () => ({ ok: 1 }),
    onServerEvent: (handler) => {
      onServerEventCalls += 1;
      const unsub = () => {
        unsubCalls.push(1);
      };
      // expose handler for test-side push
      (fakeHost as unknown as { lastHandler?: (n: Notification) => void }).lastHandler = handler;
      return unsub;
    },
    onSidecarState: () => () => {},
    respondToServerRequest: async () => {},
    rejectServerRequest: async () => {},
    getSnapshot: async () => [],
    ...over,
    // 附加只读诊断字段
    get onServerEventCalls() {
      return onServerEventCalls;
    },
    get unsubCalls() {
      return unsubCalls;
    },
  } as QuestorHostApi & {
    onServerEventCalls: number;
    unsubCalls: number[];
  };
}

describe("isElectronHost (B6 R-02)", () => {
  afterEach(() => {
    delete (window as { questorHost?: QuestorHostApi }).questorHost;
  });
  it("returns false in a browser path (no window.questorHost)", () => {
    expect(isElectronHost()).toBe(false);
  });
  it("returns true once window.questorHost is present (Electron path)", () => {
    (window as { questorHost?: QuestorHostApi }).questorHost = fakeHost();
    expect(isElectronHost()).toBe(true);
  });
});

describe("IpcTransport implements existing Transport contract (B6 R-01)", () => {
  afterEach(() => {
    __resetFanoutForTests();
    delete (window as { questorHost?: QuestorHostApi }).questorHost;
    vi.restoreAllMocks();
  });

  it("request() delegates method + params to host.request and forwards the JSON result", async () => {
    const requestSpy = vi.fn(async () => ({ thread_id: "th-1" }));
    const host = fakeHost({ request: requestSpy as unknown as QuestorHostApi["request"] });
    const transport = new IpcTransport(host);
    const result = await transport.request("thread/create", { title: "T" });
    expect(requestSpy).toHaveBeenCalledWith("thread/create", { title: "T" });
    expect(result).toEqual({ thread_id: "th-1" });
  });

  it("onNotification routes through server-events-fanout single bridge", () => {
    const host = fakeHost();
    // fanout 从 window.questorHost 拿 onServerEvent——测里先装上。
    (window as { questorHost?: QuestorHostApi }).questorHost = host;
    const transport = new IpcTransport(host);
    const seenA: Notification[] = [];
    const seenB: Notification[] = [];
    const unsubA = transport.onNotification((n) => seenA.push(n));
    const unsubB = transport.onNotification((n) => seenB.push(n));
    // 单桥：两个 listener 只应调 host.onServerEvent 一次。
    expect(host.onServerEventCalls).toBe(1);

    // 通过 fakeHost 里保存的 handler 手动推一条通知。
    const holder = fakeHost as unknown as {
      lastHandler?: (n: Notification) => void;
    };
    const pusher = holder.lastHandler;
    expect(pusher).toBeDefined();
    pusher?.({ method: "turn/started", params: { thread_id: "t1" } } as unknown as Notification);
    expect(seenA).toHaveLength(1);
    expect(seenB).toHaveLength(1);

    // 最后一个 listener 走时 bridge 应拆掉：unsub 本身被调用。
    unsubA();
    expect(host.unsubCalls).toHaveLength(0); // bridge 未拆（仍有 seenB）
    unsubB();
    expect(host.unsubCalls).toHaveLength(1); // bridge 拆（最后一个 listener 走）
  });

  it("close() is a no-op (IPC bridge is not connection-oriented)", () => {
    const host = fakeHost();
    const transport = new IpcTransport(host);
    expect(() => transport.close()).not.toThrow();
  });
});
