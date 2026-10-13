// Electron 三段构建配置（ADR-0032）。main / preload 走 Node 侧、renderer 走 Chromium 侧。
// B6 split 6：renderer.root 切 `../ui`——一套前端代码两宿主（structure.md §7）。
// 不复制 ui/ 源码进 desktop；electron-vite 会读 ui/vite.config.ts 里的
// @vitejs/plugin-react / @tailwindcss/vite 插件、把构建产物落到 desktop/out/renderer。
import { defineConfig } from "electron-vite";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

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
    // B2 占位是 `src/renderer`；B6 完成后指 `../ui`、复用 ui 项目根与它的 vite config。
    // electron-vite 5 硬验：renderer 段必须显式给 rollupOptions.input（它在 configResolved
    // 里捕不到自动扫描的 index.html），因为 root 已跳到 `../ui`、扫不到 `desktop/src/renderer`。
    root: "../ui",
    build: {
      outDir: fileURLToPath(new URL("out/renderer", import.meta.url)),
      emptyOutDir: true,
      rollupOptions: {
        // electron-vite 5 的 findInput(root) 从 `process.cwd()` 扫 `src/renderer/index.html`、
        // 捕不到则报"rollupOptions.input is required"；root 已跳 `../ui` 时需显式指。
        // 写 `"index.html"` 相对 config.root 解析到 `../ui/index.html`（absolute 同价），
        // 不用 fileURLToPath(import.meta.url) 是因 electron-vite 先 esbuild bundle config、
        // import.meta.url 会并非指向本文件。
        input: resolve(process.cwd(), "../ui/index.html"),
      },
    },
    server: {
      // vite dev 默认 `fs.allow` 只开 root 与 workspace root（=cwd）；root 指 `../ui` 后
      // electron-vite 会往上一层回到仓根，把 desktop/ 与 ui/ 都圈进来。
      // https://vitejs.dev/config/server-options#server-fs-allow
      fs: { allow: ["..", "../ui"] },
    },
  },
});
