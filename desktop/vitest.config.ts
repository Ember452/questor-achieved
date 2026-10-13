// desktop 侧 vitest：node 环境（主进程逻辑、无 DOM）；include 只到 tests/。
// 与 ui/vitest.config.ts 互不影响（两个 package、两份 lockfile，per ADR-0032 §结论 4）。
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
