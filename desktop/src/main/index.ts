// Questor Electron 主进程入口（ADR-0030/0032）。
// 职责严格收缩为纯壳：窗口、sidecar 生命周期、能力声明、图标与打包。
// 不含业务判断（overview §14："GUI 能力必须经协议可达"）。
// B2 阶段只开一个空窗；B3 会在 whenReady 里加 resolveQuestorCommand + startSidecar，
// B6 会挂 ipcMain.handle 与 sidecar 桥。

import { app, BrowserWindow } from "electron";
import { fileURLToPath } from "node:url";

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: false,
    webPreferences: {
      // electron-vite 把 preload 编为 CJS，产物名 `index.cjs`；main 里拼射时需同步。
      preload: fileURLToPath(new URL("../preload/index.cjs", import.meta.url)),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.once("ready-to-show", () => win.show());
  const rendererUrl = process.env["ELECTRON_RENDERER_URL"];
  if (rendererUrl) {
    void win.loadURL(rendererUrl);
  } else {
    void win.loadFile(fileURLToPath(new URL("../renderer/index.html", import.meta.url)));
  }
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  // Windows/Linux 全窗口关闭即退；macOS 保留 dock 常驻（本项目不主用 mac，语义照 wuu）。
  if (process.platform !== "darwin") app.quit();
});
