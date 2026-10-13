// desktop 侧 vitest：node 环境（主进程逻辑、无 DOM）；include 只到 tests/。
// 与 ui/vitest.config.ts 互不影响（两个 package、两份 lockfile，per ADR-0032 §结论 4）。
// cacheDir 每次启动写不同目录名：Windows 上 vitest 5 的 mtime 检测有
// 精度丢失，同目录下的旧 transform 会 hit、让改后源码看不到。
// 临时方案：每次 run 用随机 cacheDir（无跨 run 缓存复用、启动略慢）；
// 待 vitest 上游修好后进 B9 completion 时回收。
import { defineConfig } from "vitest/config";

const cacheNamespace = `vitest-cache-${process.pid}`;

export default defineConfig({
  cacheDir: `node_modules/.vitest/${cacheNamespace}`,
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
