// Questor Electron 主进程入口（ADR-0030/0032）。
// 职责严格收缩为纯壳：窗口、sidecar 生命周期、能力声明、图标与打包。
// 不含业务判断（overview §14："GUI 能力必须经协议可达"）。
// B3 在 whenReady 里 resolveQuestorCommand + startSidecar；B4 已包上 lifecycle_lock
// 与 bumpState（per home 单点串行拉起与单调 generation 记录）；B5 会接
// killTree + armRestartPolicy；B6 会挂 ipcMain.handle 与桥。

import { app, BrowserWindow } from "electron";
import { fileURLToPath } from "node:url";
import { bumpState } from "./sidecar-state";
import { withLifecycleLock } from "./sidecar-lock";
import { resolveQuestorCommand } from "./questor-command";
import { resolveQuestorHome } from "./questor-home";
import { startSidecar } from "./sidecar";

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

app.whenReady().then(async () => {
  // B3：先只做"拉起来 + 日志"，B4 加 generation/lifecycle_lock，B5 加 fail-open，
  // B6 交给 IPC bridge。
  // 严格照 wuu wuuCommand.ts：绝不用 PATH 找 `questor`、绝不从 workspace 找
  // `bin/questor`（B-114：用户把 questor 仓库本身开成 workspace 会撞 ELF/py 版本坑）。
  try {
    const cmd = resolveQuestorCommand(
      process.env,
      app.getAppPath(),
      process.resourcesPath,
    );
    const home = resolveQuestorHome(process.env);
    // B4：withLifecycleLock 同 home 串行化拉起，bumpState 写单调 generation。
    // 两个桌面壳同开时后启者会等 5 s → 抛 "lifecycle lock busy"（fail-open 到下面 catch）。
    const handle = await withLifecycleLock(home, async () => {
      const h = await startSidecar({
        command: cmd.command,
        args: cmd.args,
        cwd: cmd.cwd,
      });
      await bumpState(home, { pid: h.pid, startedAt: new Date().toISOString() });
      return h;
    });
    console.log(`[sidecar] pid=${handle.pid} cmd=${cmd.command} home=${home}`);
    handle.stderr.on("data", (chunk: Buffer) =>
      console.error(`[sidecar] ${chunk.toString("utf8")}`),
    );
    handle.exited.then((r) => console.warn(`[sidecar] exited`, r));
  } catch (err) {
    // fail-open：sidecar 拉不起来时窗口照开，renderer 侧会看到无 sidecar 缺席；
    // B5 会接上 armRestartPolicy 与重启日志，B6 会广播 sidecar-state 给 renderer。
    console.error("[sidecar] failed to start:", (err as Error).message);
  }
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  // Windows/Linux 全窗口关闭即退；macOS 保留 dock 常驻（本项目不主用 mac，语义照 wuu）。
  if (process.platform !== "darwin") app.quit();
});
