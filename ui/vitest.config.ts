// Vitest 配置（ADR-0031 引入）：happy-dom DOM 环境 + React 测试库；setup 只装 jest-dom 匹配器。
// 与 vite.config.ts 分离：vite 管构建，vitest 管测；共享 @vitejs/plugin-react 让 JSX/TSX 编译一致。
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/testing/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
