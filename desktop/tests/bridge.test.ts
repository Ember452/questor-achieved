// 护栏 B-118：server-initiated request 的 public id 桥接、pending 匹配、
// turn/started 落 sessionOwners——三条断言咬住桥的关键不变量。
// 审查回归：F1（detach/exit 必须 reject 在途请求）、F6（坏帧不炸穿）、
// B-122（detach 清归属表）。
import { describe, expect, it, vi } from "vitest";
import { PassThrough } from "node:stream";
import {
  AppServerBridge,
  type AppServerClientEvent,
} from "../src/main/app-server-bridge";
import type { SidecarHandle } from "../src/main/sidecar";

interface FakeHandle {
  handle: SidecarHandle;
  writtenFrames: () => Record<string, unknown>[];
  pushStdoutFrame: (obj: Record<string, unknown>) => void;
  pushRaw: (text: string) => void;
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
    pushRaw: (text) => stdout.write(text),
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

  it("detach 后在途请求被 reject、不让 renderer 永久悬挂（审查 F1）", async () => {
    const fake = makeFakeHandle();
    const bridge = new AppServerBridge();
    bridge.attach(fake.handle);
    const promise = bridge.dispatchRequest("thread/list", {});
    bridge.detach();
    await expect(promise).rejects.toThrow(/detached/);
    // 新请求在 detach 后直接拒（"sidecar not attached"）而不是默默入队。
    await expect(bridge.dispatchRequest("thread/list", {})).rejects.toThrow(/not attached/);
  });

  it("sidecar exit → 广播 server-exit + 在途请求被拒（审查 F1 集成面）", async () => {
    const stdin = new PassThrough();
    const stdout = new PassThrough();
    const stderr = new PassThrough();
    let exitNow!: (r: { code: number | null; signal: NodeJS.Signals | null }) => void;
    const exited = new Promise<{ code: number | null; signal: NodeJS.Signals | null }>(
      (res) => {
        exitNow = res;
      },
    );
    const handle = {
      pid: 1,
      stdin,
      stdout,
      stderr,
      exited,
      kill: () => undefined,
    } as unknown as SidecarHandle;
    const bridge = new AppServerBridge();
    bridge.attach(handle);
    const seen: AppServerClientEvent[] = [];
    bridge.onEvent((e) => seen.push(e));
    const promise = bridge.dispatchRequest("thread/list", {});
    exitNow({ code: 1, signal: null });
    await expect(promise).rejects.toThrow(/detached/);
    await new Promise((resolve) => setImmediate(resolve));
    expect(seen.map((e) => e.kind)).toContain("server-exit");
  });

  it("非法 NDJSON 行被丢弃、后续正常帧继续处理（审查 F6）", async () => {
    const fake = makeFakeHandle();
    const bridge = new AppServerBridge();
    bridge.attach(fake.handle);
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const seen: AppServerClientEvent[] = [];
    bridge.onEvent((e) => seen.push(e));
    fake.pushRaw("{ not json\n");
    fake.pushStdoutFrame({ method: "notice/compact", params: { kind: "started" } });
    await new Promise((resolve) => setImmediate(resolve));
    expect(seen).toHaveLength(1);
    expect(seen[0]?.kind).toBe("notification");
    expect(errSpy).toHaveBeenCalledOnce();
    errSpy.mockRestore();
  });

  it("detach 后归属表清空、snapshot 宁缺勿滥（B-122 当前保守立场）", async () => {
    const fake = makeFakeHandle();
    const bridge = new AppServerBridge();
    bridge.attach(fake.handle);
    fake.pushStdoutFrame({
      method: "turn/started",
      params: { thread_id: "th-keep", turn_id: "t1" },
    });
    await new Promise((resolve) => setImmediate(resolve));
    expect(bridge.runningThreadsSnapshot()).toHaveLength(1);
    bridge.detach();
    expect(bridge.runningThreadsSnapshot()).toEqual([]);
  });
});
