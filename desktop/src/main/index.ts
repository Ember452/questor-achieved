// Questor Electron 主进程入口（ADR-0030/0032）。
// 职责严格收缩为纯壳：窗口、sidecar 生命周期、能力声明、图标与打包。
// 不含业务判断（overview §14："GUI 能力必须经协议可达"）。
// B3 在 whenReady 里 resolveQuestorCommand + startSidecar；B4 已包上 lifecycle_lock
// 与 bumpState（per home 单点串行拉起与单调 generation 记录）；B5 接上 closure-scoped
// spawnSidecar 工厂 + armRestartPolicy（fail-open backoff）+ before-quit killTree；
// B6 会挂 ipcMain.handle 与桥。

import { app, BrowserWindow } from "electron";
import { fileURLToPath } from "node:url";
import { armRestartPolicy, killTree } from "./child-shutdown";
import { bumpState } from "./sidecar-state";
import { withLifecycleLock } from "./sidecar-lock";
import { resolveQuestorCommand } from "./questor-command";
import { resolveQuestorHome } from "./questor-home";
import { startSidecar, type SidecarHandle } from "./sidecar";

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

// B5：closure-scoped sidecar 工厂。`activeHandle` 与 `shuttingDown` 同模块顶——
// before-quit 会置 shuttingDown=true 防止关窗与 respawn 竞态。
let activeHandle: SidecarHandle | null = null;
let shuttingDown = false;

async function spawnSidecar(): Promise<void> {
  if (shuttingDown) return;
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
    activeHandle = handle;
    console.log(`[sidecar] pid=${handle.pid} cmd=${cmd.command} home=${home}`);
    handle.stderr.on("data", (chunk: Buffer) =>
      console.error(`[sidecar] ${chunk.toString("utf8")}`),
    );
    handle.exited.then((r) => console.warn(`[sidecar] exited`, r));
    // B5 fail-open：非零 exit → backoff 后 respawn；超 maxRetries=3 后停。
    // R-13: B5 阶段仅 console.warn；B6 换成 webContents.send("qst:sidecar-state", ...)
    armRestartPolicy(handle, {
      backoffMs: [500, 2000, 8000],
      maxRetries: 3,
      onRespawn: () => {
        void spawnSidecar();
      },
      onBudgetExhausted: (info) => {
        console.warn(
          `[sidecar] restart budget exhausted (fail-open), retries=${info.retries}`,
        );
      },
    });
  } catch (err) {
    // fail-open：sidecar 拉不起来时窗口照开，renderer 侧会看到无 sidecar 缺席；
    // B6 会广播 sidecar-state 给 renderer 显式提示。
    console.error("[sidecar] failed to start:", (err as Error).message);
  }
}

app.whenReady().then(async () => {
  await spawnSidecar();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  // Windows/Linux 全窗口关闭即退；macOS 保留 dock 常驻（本项目不主用 mac，语义照 wuu）。
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", (e) => {
  if (activeHandle && !shuttingDown) {
    shuttingDown = true;
    e.preventDefault();
    void (async () => {
      try {
        await killTree(activeHandle as SidecarHandle, { graceMs: 20_000 });
      } catch (err) {
        console.error("[sidecar] killTree failed:", err);
      }
      activeHandle = null;
      app.exit(0);
    })();
  }
});
