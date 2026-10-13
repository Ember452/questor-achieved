// Questor Electron 主进程入口（ADR-0030/0032）。
// 职责严格收缩为纯壳：窗口、sidecar 生命周期、能力声明、图标与打包。
// 不含业务判断（overview §14："GUI 能力必须经协议可达"）。
// B3 拉起 sidecar；B4 包 lifecycle_lock + bumpState；B5 接 closure-spawn
// + killTree + armRestartPolicy；B6 挂 ipcMain.handle、batcher、bridge singleton
// 与 sidecar-state 广播（Option A：renderer ↔ main IPC ↔ sidecar stdio）。

import { app, BrowserWindow, ipcMain } from "electron";
import { fileURLToPath } from "node:url";
import { AppServerBridge } from "./app-server-bridge";
import { armRestartPolicy, killTree } from "./child-shutdown";
import { bumpState } from "./sidecar-state";
import { withLifecycleLock } from "./sidecar-lock";
import { resolveQuestorCommand } from "./questor-command";
import { resolveQuestorHome } from "./questor-home";
import { RendererServerEventBatcher } from "./renderer-batcher";
import { startSidecar, type SidecarHandle } from "./sidecar";

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };
type JsonObject = { [k: string]: Json };

type SidecarStateEvent =
  | { kind: "up"; pid: number }
  | { kind: "down"; code: number | null; signal: string | null; willRetry: boolean }
  | { kind: "budget-exhausted"; retries: number; lastCode: number | null; lastSignal: string | null };

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
// B6：bridge 作 module-level singleton、跨 respawn 保留 sessionOwners/pending 长跑状态；
// batcher 同 singleton、webContents.send 到当前活窗口；spawnAttempts 给 willRetry 用。
let activeHandle: SidecarHandle | null = null;
let shuttingDown = false;
let spawnAttempts = 0;
const MAX_SPAWN_ATTEMPTS = 3;

const bridge = new AppServerBridge();
let batcher: RendererServerEventBatcher | null = null;
let ipcRegistered = false;

function broadcastSidecarState(state: SidecarStateEvent): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send("qst:sidecar-state", state);
  }
}

function registerIpcHandlers(): void {
  if (ipcRegistered) return; // whenReady 只会调一次；防止重入。
  ipcRegistered = true;
  ipcMain.handle("qst:request", (_e, method: string, params: JsonObject) =>
    bridge.dispatchRequest(method, params),
  );
  ipcMain.handle(
    "qst:respond-server-request",
    (_e, id: string, r: unknown) => bridge.respondToServerRequest(id, r),
  );
  ipcMain.handle(
    "qst:reject-server-request",
    (_e, id: string, m: string) => bridge.rejectServerRequest(id, m),
  );
  ipcMain.handle("qst:snapshot", () =>
    // F4（审查）：snapshot 前必须 flush 已合批的 delta，否则 renderer 拿到 snapshot
    // 后又会收到已含在 snapshot 里的 delta 重放（B-117 的集成面语义）。
    batcher
      ? batcher.resolveSnapshot(Promise.resolve(bridge.runningThreadsSnapshot()))
      : Promise.resolve(bridge.runningThreadsSnapshot()),
  );
}

function wireBridgeToRenderer(): void {
  if (batcher) return;
  batcher = new RendererServerEventBatcher((evt) => {
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) win.webContents.send("qst:server-event", evt);
    }
  });
  bridge.onEvent((e) => {
    if (e.kind === "notification") {
      batcher?.enqueue(e.message);
    } else if (e.kind === "server-request") {
      // 控制事件不合批：先 flush pending、再直接转发；Phase U 无消费方，仍先接上 plumbing（R-12）。
      batcher?.flush();
      const payload: JsonObject = {
        __kind: "server-request",
        __publicId: e.message.id,
        method: e.message.method,
        params: (e.message.params as JsonObject | undefined) ?? {},
      };
      for (const win of BrowserWindow.getAllWindows()) {
        if (!win.isDestroyed()) win.webContents.send("qst:server-event", payload);
      }
    }
  });
}

async function spawnSidecar(): Promise<void> {
  if (shuttingDown) return;
  // F2（审查）：模块级预算守门——armRestartPolicy 的 retries 是 per-handle 闭包，
  // 每次 respawn 都从 0 计；若不在此卡住，秒退型 crash loop 会无限重开。
  // MAX_SPAWN_ATTEMPTS 的真实执行点就是这一行（B-110）。
  if (spawnAttempts >= MAX_SPAWN_ATTEMPTS) {
    console.warn(
      `[sidecar] restart budget exhausted (fail-open), attempts=${spawnAttempts}`,
    );
    broadcastSidecarState({
      kind: "budget-exhausted",
      retries: spawnAttempts,
      lastCode: null,
      lastSignal: null,
    });
    return;
  }
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
    bridge.attach(handle);
    console.log(`[sidecar] pid=${handle.pid} cmd=${cmd.command} home=${home}`);
    handle.stderr.on("data", (chunk: Buffer) =>
      console.error(`[sidecar] ${chunk.toString("utf8")}`),
    );
    broadcastSidecarState({ kind: "up", pid: handle.pid });
    handle.exited.then((r) => {
      console.warn(`[sidecar] exited`, r);
      broadcastSidecarState({
        kind: "down",
        code: r.code,
        signal: r.signal,
        willRetry:
          r.code !== 0 && spawnAttempts + 1 < MAX_SPAWN_ATTEMPTS,
      });
    });
    // B5 fail-open：非零 exit → backoff 后 respawn；超 maxRetries=3 后停。
    // B6：budget-exhausted 广播给 renderer（R-13），console.warn 保留方便开发机看到。
    armRestartPolicy(handle, {
      backoffMs: [500, 2000, 8000],
      maxRetries: MAX_SPAWN_ATTEMPTS,
      onRespawn: () => {
        spawnAttempts += 1;
        void spawnSidecar();
      },
      onBudgetExhausted: (info) => {
        console.warn(
          `[sidecar] restart budget exhausted (fail-open), retries=${info.retries}`,
        );
        broadcastSidecarState({ kind: "budget-exhausted", ...info });
      },
    });
  } catch (err) {
    // fail-open：sidecar 拉不起来时窗口照开，renderer 侧会看到无 sidecar 缺席；
    // B6 会广播 sidecar-state 给 renderer 显式提示。
    console.error("[sidecar] failed to start:", (err as Error).message);
  }
}

app.whenReady().then(async () => {
  registerIpcHandlers();
  wireBridgeToRenderer();
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
        // F3（审查）：必须传 requestStop——killTree 的定时 SIGTERM 在 graceMs(20s)
        // 之后才发；不传则每次关窗白等 20 秒。Windows 下 SIGTERM 即 TerminateProcess，
        // POSIX 下给 Python 默认优雅退路；timer 只作兜底。
        await killTree(activeHandle as SidecarHandle, {
          graceMs: 20_000,
          requestStop: async () => {
            (activeHandle as SidecarHandle).kill("SIGTERM");
          },
        });
      } catch (err) {
        console.error("[sidecar] killTree failed:", err);
      }
      bridge.detach();
      activeHandle = null;
      app.exit(0);
    })();
  }
});
