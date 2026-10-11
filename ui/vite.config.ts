import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Questor ui：M1 骨架。宿主差异（Tauri stdio / 网页 WS）由 rpc 层抽象，vite 不感知。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: "dist", emptyOutDir: true },
});
