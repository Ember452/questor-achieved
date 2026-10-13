// 护栏 B-118：server-initiated request 的 public id 桥接、pending 匹配、
// turn/started 落 sessionOwners——三条断言咬住桥的关键不变量。
import { describe, expect, it } from "vitest";
import { PassThrough } from "node:stream";
import { AppServerBridge } from "../src/main/app-server-bridge";
import type { SidecarHandle } from "../src/main/sidecar";

interface FakeHandle {
  handle: SidecarHandle;
  writtenFrames: () => Record<string, unknown>[];
  pushStdoutFrame: (obj: Record<string, unknown>) => void;
}

function makeFakeHandle(): FakeHandle {
  const stdin = new PassThrough();
  const stdout = new PassThrough();
  const stderr = new PassThrough();
  const written: Record<string, unknown>[] = [];
  stdin.on("data", (chunk: Buffer) => {
    const text = chunk.toString("utf8");
    for (const line of text.split("\n")) {
      const trimmed = line.trim();
      if (trimmed) written.push(JSON.parse(trimmed) as Record<string, unknown>);
    }
  });
  const exited = new Promise<{
    code: number | null;
    signal: NodeJS.Signals | null;
  }>(() => {
    /* never resolves in unit tests */
  });
  const handle = {
    pid: 1234,
    stdin,
    stdout,
    stderr,
    exited,
    kill: (_sig?: NodeJS.Signals): void => {
      /* no-op */
    },
  } as unknown as SidecarHandle;
  return {
    handle,
    writtenFrames: () => written,
    pushStdoutFrame: (obj) => stdout.write(JSON.stringify(obj) + "\n"),
  };
}

describe("AppServerBridge (B-118)", () => {
  it("pending 匹配：dispatchRequest 写帧、result 帧回来按 id resolve", async () => {
    const fake = makeFakeHandle();
    const bridge = new AppServerBridge();
    bridge.attach(fake.handle);

    const promise = bridge.dispatchRequest("thread/create", { title: "T1" });
    // 观察 stdin 已写入的帧。
    await Promise.resolve();
    const frames = fake.writtenFrames();
    expect(frames).toHaveLength(1);
    expect(frames[0]).toMatchObject({ method: "thread/create", params: { title: "T1" } });
    const sentId = frames[0].id as string;
    expect(sentId).toMatch(/^req-\d+$/);

    fake.pushStdoutFrame({ id: sentId, result: { thread_id: "th-1" } });
    const result = await promise;
    expect(result).toEqual({ thread_id: "th-1" });
  });

  it("`turn/started` 通知落 sessionOwners、snapshot 返回 threadId 集", async () => {
    const fake = makeFakeHandle();
    const bridge = new AppServerBridge();
    bridge.attach(fake.handle);

    const seen: unknown[] = [];
    bridge.onEvent((e) => seen.push(e));

    fake.pushStdoutFrame({
      method: "turn/started",
      params: { thread_id: "th-42", turn_id: "t-1" },
    });
    // 事件在 stdout data 回调里同步分发；microtask 让 PassThrough 落数据。
    await new Promise((resolve) => setImmediate(resolve));
    expect(bridge.runningThreadsSnapshot()).toEqual([{ threadId: "th-42" }]);
    expect(seen).toHaveLength(1);
    const evt = seen[0] as { kind: string };
    expect(evt.kind).toBe("notification");
  });

  it("server-initiated request 用 server-request-${N} public id 桥接（内核真实 id 不外泄）", async () => {
    const fake = makeFakeHandle();
    const bridge = new AppServerBridge();
    bridge.attach(fake.handle);

    const seen: unknown[] = [];
    bridge.onEvent((e) => seen.push(e));

    // 内核真实 id 是 "kernel-req-7"——bridge 应替换为 "server-request-1" 才发给 renderer。
    fake.pushStdoutFrame({
      id: "kernel-req-7",
      method: "permission/ask",
      params: { what: "delete" },
    });
    await new Promise((resolve) => setImmediate(resolve));
    expect(seen).toHaveLength(1);
    const evt = seen[0] as {
      kind: string;
      message: { id: string; method: string };
    };
    expect(evt.kind).toBe("server-request");
    expect(evt.message.id).toBe("server-request-1");
    expect(evt.message.id).not.toBe("kernel-req-7");
    expect(evt.message.method).toBe("permission/ask");

    // renderer 用 public id 回 result → bridge 换成 serverID 写回 stdin。
    bridge.respondToServerRequest("server-request-1", { approved: true });
    await Promise.resolve();
    const frames = fake.writtenFrames();
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({ id: "kernel-req-7", result: { approved: true } });
  });
});
