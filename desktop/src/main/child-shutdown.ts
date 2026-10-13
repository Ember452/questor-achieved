// 关停语义（B-113：等 exit 事件、不等 pipe close）+ fail-open 重启策略。
// provenance: 严格照 wuu-main/desktop/src/main/childShutdown.ts 三层定时与
//   requestStop 优雅钩子语义；重写实现（AGENTS §二 (a) 边界层）。
// Windows 上 Node child.kill 语义：SIGTERM 与 SIGKILL 都是 TerminateProcess、等价；
//   killTree 在 win32 分支下**不重复发 SIGKILL**（避免误导 reviewer 以为双发有效）。
// R-13：B5 阶段 onBudgetExhausted 只 console.warn；B6 IPC 起来后走广播。
import type { SidecarHandleLike } from "./sidecar";

export interface KillTreeOptions {
  requestStop?: () => Promise<void>;
  graceMs?: number;
  sigkillAfterMs?: number;
  rejectAfterMs?: number;
}

export async function killTree(
  handle: SidecarHandleLike,
  opts: KillTreeOptions = {},
): Promise<void> {
  const graceMs = opts.graceMs ?? 20_000;
  const sigkillAfterMs = opts.sigkillAfterMs ?? 3_000;
  const rejectAfterMs = opts.rejectAfterMs ?? 5_000;
  const isWindows = process.platform === "win32";

  const timers: ReturnType<typeof setTimeout>[] = [];
  const exitedInTime = await new Promise<boolean>((resolve) => {
    handle.exited.then(() => resolve(true));

    const sigtermTimer = setTimeout(() => {
      try {
        handle.kill("SIGTERM");
      } catch {
        /* already gone */
      }
    }, graceMs);
    sigtermTimer.unref();
    timers.push(sigtermTimer);

    if (!isWindows) {
      const sigkillTimer = setTimeout(() => {
        try {
          handle.kill("SIGKILL");
        } catch {
          /* already gone */
        }
      }, graceMs + sigkillAfterMs);
      sigkillTimer.unref();
      timers.push(sigkillTimer);
    }

    const finalTimer = setTimeout(() => resolve(false), graceMs + rejectAfterMs);
    finalTimer.unref();
    timers.push(finalTimer);

    // 协议级优雅停机（走 `session/control stop`）；失败退回 SIGTERM，timer 会兵底 SIGKILL。
    if (opts.requestStop) {
      void Promise.resolve(opts.requestStop()).catch(() => {
        try {
          handle.kill("SIGTERM");
        } catch {
          /* already gone */
        }
      });
    }
  });

  for (const t of timers) clearTimeout(t);
  if (!exitedInTime) {
    throw new Error("Child process did not exit after shutdown (killTree timeout)");
  }
}

export interface RestartPolicyOptions {
  backoffMs: number[];
  maxRetries: number;
  onRespawn: () => void;
  onBudgetExhausted?: (info: {
    retries: number;
    lastCode: number | null;
    lastSignal: string | null;
  }) => void;
}

export function armRestartPolicy(
  handle: SidecarHandleLike,
  opts: RestartPolicyOptions,
): void {
  let retries = 0;
  void handle.exited.then((r) => {
    if (r.code === 0) return; // 正常退出（用户关窗）不重启
    if (retries >= opts.maxRetries) {
      opts.onBudgetExhausted?.({
        retries,
        lastCode: r.code,
        lastSignal: r.signal,
      });
      return;
    }
    const wait = opts.backoffMs[Math.min(retries, opts.backoffMs.length - 1)];
    retries += 1;
    const t = setTimeout(() => opts.onRespawn(), wait);
    t.unref();
  });
}
