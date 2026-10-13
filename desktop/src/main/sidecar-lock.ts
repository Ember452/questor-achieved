// lifecycle_lock 防并发拉起。
// provenance: 参照 EvoFlow evopanel/src-tauri/src/commands/backend.rs 的 lifecycle_lock
//   语义；与 questor state/storelock 同形，在 TS 侧独立实现（不能 import Python）。
// B-109：两个桌面壳同开或 respawn 竞态下，同 home 只允许一个进程拉起 sidecar。
// 用 O_CREAT|O_EXCL（`wx` flag）独占创建立锁；获不到 → 50 ms 退避重试直到 5 s；
// 释放走 `unlinkSync`。本项目 Phase U 简化：孤儿锁（进程 crash 未释放）由下一次
//   获锁的 5 s 超时后运维手动清；mtime 心跳判定属 M8 remote/relay 场景，此处不留门。
import fs from "node:fs";
import { join } from "node:path";

const LOCK_DIR = "desktop";
const LOCK_FILE = ".lifecycle.lock";
const DEFAULT_TIMEOUT_MS = 5_000;
const DEFAULT_POLL_INTERVAL_MS = 50;

export async function withLifecycleLock<T>(
  home: string,
  fn: () => Promise<T>,
  opts: { timeoutMs?: number; pollIntervalMs?: number } = {},
): Promise<T> {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const pollIntervalMs = opts.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const dir = join(home, LOCK_DIR);
  const lockPath = join(dir, LOCK_FILE);
  fs.mkdirSync(dir, { recursive: true });

  const deadline = Date.now() + timeoutMs;
  let acquired = false;
  while (!acquired) {
    try {
      const fd = fs.openSync(lockPath, "wx");
      fs.closeSync(fd);
      acquired = true;
    } catch (error) {
      if (!isExistError(error)) throw error;
      if (Date.now() >= deadline) {
        throw new Error(
          `lifecycle lock busy: ${lockPath} (timeout ${timeoutMs} ms)`,
        );
      }
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    }
  }

  try {
    return await fn();
  } finally {
    try {
      fs.unlinkSync(lockPath);
    } catch {
      /* 已被外部清或权限受限：不掩盖 fn 结果 */
    }
  }
}

function isExistError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    (error as { code?: string }).code === "EEXIST"
  );
}
