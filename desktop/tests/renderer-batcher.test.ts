// 护栏 B-117：50 ms 合批窗口、控制事件先 flush、raw provider delta 不转发、
// resolveSnapshot 前 flush。四类语义各一条 + 不同 identity 不合批一条 = 5 测。
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  RendererServerEventBatcher,
  type BatchedNotification,
} from "../src/main/renderer-batcher";

function notif(method: string, params?: unknown): BatchedNotification {
  return { method, params };
}

describe("RendererServerEventBatcher (B-117)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("50 ms 内同 identity delta 合并为一", async () => {
    vi.useFakeTimers();
    const emitted: BatchedNotification[] = [];
    const b = new RendererServerEventBatcher((n) => emitted.push(n));
    b.enqueue(notif("item/agentMessage/delta", { thread_id: "t1", turn_id: "x", item_id: "i", text: "a" }));
    b.enqueue(notif("item/agentMessage/delta", { thread_id: "t1", turn_id: "x", item_id: "i", text: "b" }));
    b.enqueue(notif("item/agentMessage/delta", { thread_id: "t1", turn_id: "x", item_id: "i", text: "c" }));
    await vi.advanceTimersByTimeAsync(60);
    expect(emitted).toHaveLength(1);
    expect((emitted[0].params as { text: string }).text).toBe("abc");
  });

  it("不同 identity 的 delta 不合并", async () => {
    vi.useFakeTimers();
    const emitted: BatchedNotification[] = [];
    const b = new RendererServerEventBatcher((n) => emitted.push(n));
    b.enqueue(notif("item/agentMessage/delta", { thread_id: "t1", turn_id: "x", item_id: "i1", text: "a" }));
    b.enqueue(notif("item/agentMessage/delta", { thread_id: "t1", turn_id: "x", item_id: "i2", text: "b" }));
    await vi.advanceTimersByTimeAsync(60);
    expect(emitted).toHaveLength(2);
  });

  it("控制事件（非 delta）先 flush pending、再立即 emit", async () => {
    const emitted: BatchedNotification[] = [];
    const b = new RendererServerEventBatcher((n) => emitted.push(n));
    b.enqueue(notif("item/agentMessage/delta", { thread_id: "t1", turn_id: "x", item_id: "i", text: "a" }));
    b.enqueue(notif("turn/completed", { thread_id: "t1", turn_id: "x" }));
    // 无 fake timer——控制事件应触发 flush 路径、不走 50 ms 等待。
    expect(emitted.length).toBe(2);
    expect(emitted[0].method).toBe("item/agentMessage/delta");
    expect(emitted[1].method).toBe("turn/completed");
  });

  it("raw provider delta (content_delta/thinking_delta/tool_use_delta) 不转发", () => {
    const emitted: BatchedNotification[] = [];
    const b = new RendererServerEventBatcher((n) => emitted.push(n));
    b.enqueue(notif("content_delta", { text: "x" }));
    b.enqueue(notif("thinking_delta", { text: "y" }));
    b.enqueue(notif("tool_use_delta", { input: "z" }));
    b.flush();
    expect(emitted).toHaveLength(0);
  });

  it("resolveSnapshot 前 flush pending delta、防 renderer 重放", async () => {
    const emitted: BatchedNotification[] = [];
    const b = new RendererServerEventBatcher((n) => emitted.push(n));
    b.enqueue(notif("item/agentMessage/delta", { thread_id: "t1", turn_id: "x", item_id: "i", text: "a" }));
    const snapshotReq = Promise.resolve("snapshot-data");
    const resolved = await b.resolveSnapshot(snapshotReq);
    expect(resolved).toBe("snapshot-data");
    // delta 应在 snapshot resolve 前已 flush。
    expect(emitted).toHaveLength(1);
  });
});
