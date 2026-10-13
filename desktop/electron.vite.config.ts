// Electron 三段构建配置（ADR-0032）。main / preload 走 Node 侧、renderer 走 Chromium 侧。
// B2 阶段 renderer 用本地占位 index.html；B6 完成后 renderer.root 会切到 "../ui"，
// 直接复用 ui/ 构建产物（structure.md §7 一套前端两宿主）。
import { defineConfig } from "electron-vite";
import { fileURLToPath } from "node:url";

export default defineConfig({
  main: {
    build: {
      lib: {
        entry: "src/main/index.ts",
        formats: ["es"],
        fileName: () => "index",
      },
      outDir: "out/main",
      emptyOutDir: true,
    },
  },
  preload: {
    build: {
      lib: {
        entry: "src/preload/index.ts",
        formats: ["cjs"],
        fileName: () => "index",
      },
      outDir: "out/preload",
      emptyOutDir: true,
    },
  },
  renderer: {
    root: "src/renderer",
    build: {
      outDir: fileURLToPath(new URL("out/renderer", import.meta.url)),
      emptyOutDir: true,
    },
  },
});
