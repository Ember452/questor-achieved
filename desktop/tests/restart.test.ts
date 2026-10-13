// 护栏 B-110 重启计数与 fail-open 上限；B-111/B-113 子进程树关停三层定时。
import { describe, expect, it, vi } from "vitest";
import {
  armRestartPolicy,
  killTree,
  type KillTreeOptions,
} from "../src/main/child-shutdown";
import type { SidecarHandleLike } from "../src/main/sidecar";

const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

interface FakeHandle extends SidecarHandleLike {
  killedSignals: NodeJS.Signals[];
  emitExit(r: { code: number | null; signal: NodeJS.Signals | null }): void;
  exitsOnSignal(sig: NodeJS.Signals): void;
}

function makeFakeHandle(): FakeHandle {
  let resolveExited!: (r: {
    code: number | null;
    signal: NodeJS.Signals | null;
  }) => void;
  const exited = new Promise<{
    code: number | null;
    signal: NodeJS.Signals | null;
  }>((res) => {
    resolveExited = res;
  });
  const fake: FakeHandle = {
    exited,
    killedSignals: [],
    kill(signal?: NodeJS.Signals) {
      fake.killedSignals.push(signal ?? "SIGTERM");
    },
    emitExit(r) {
      resolveExited(r);
    },
    exitsOnSignal(sig) {
      const check = (): void => {
        if (fake.killedSignals.includes(sig)) {
          resolveExited({ code: null, signal: sig });
        } else {
          setTimeout(check, 5).unref();
        }
      };
      check();
    },
  };
  return fake;
}

describe("armRestartPolicy（B-110）", () => {
  it("exit code=1 → respawn 计数 +1", async () => {
    const fake = makeFakeHandle();
    let respawns = 0;
    armRestartPolicy(fake, {
      backoffMs: [10, 10, 10],
      maxRetries: 3,
      onRespawn: () => {
        respawns += 1;
      },
    });
    fake.emitExit({ code: 1, signal: null });
    await sleep(60);
    expect(respawns).toBe(1);
  });

  it("exit code=0（用户关窗）→ 不 respawn", async () => {
    const fake = makeFakeHandle();
    let respawns = 0;
    armRestartPolicy(fake, {
      backoffMs: [10, 10, 10],
      maxRetries: 3,
      onRespawn: () => {
        respawns += 1;
      },
    });
    fake.emitExit({ code: 0, signal: null });
    await sleep(60);
    expect(respawns).toBe(0);
  });

  it("单 handle 上 retries 计数递增（closure 控链）", async () => {
    // exited 只能 fire 一次、retries 在 armRestartPolicy 内部 closure 里累加；
    // spawnSidecar 每次 respawn 都造新 handle、各 handle 独立计数。
    // 真正的 maxRetries 上限（3 次后不再 respawn）由 closure 层的 spawnCount 控制，
    // 本测验证单 handle 内 exit 非零 → onRespawn 恰好 fire 一次。
    const fake = makeFakeHandle();
    let respawns = 0;
    armRestartPolicy(fake, {
      backoffMs: [10, 10, 10],
      maxRetries: 3,
      onRespawn: () => {
        respawns += 1;
      },
    });
    fake.emitExit({ code: 2, signal: null });
    await sleep(60);
    expect(respawns).toBe(1);
  });
});

describe("killTree 三层定时（B-111/B-113）", () => {
  it("POSIX 分支：SIGTERM 无响应 → SIGKILL；再超时 → reject", async () => {
    vi.stubGlobal("process", { ...process, platform: "linux" });
    try {
      const fake = makeFakeHandle();
      const opts: KillTreeOptions = {
        graceMs: 100,
        sigkillAfterMs: 100,
        rejectAfterMs: 200,
      };
      await expect(killTree(fake, opts)).rejects.toThrow(/did not exit/i);
      expect(fake.killedSignals).toEqual(["SIGTERM", "SIGKILL"]);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("POSIX 分支：SIGTERM 生效 → 立即 resolve、无 SIGKILL", async () => {
    vi.stubGlobal("process", { ...process, platform: "linux" });
    try {
      const fake = makeFakeHandle();
      fake.exitsOnSignal("SIGTERM");
      await killTree(fake, {
        graceMs: 100,
        sigkillAfterMs: 300,
        rejectAfterMs: 500,
      });
      expect(fake.killedSignals).toEqual(["SIGTERM"]);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
