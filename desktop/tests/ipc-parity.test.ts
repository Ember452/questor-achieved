// 护栏 B-116：preload 的每个 ipcRenderer.invoke/sendSync/on channel x
// 都必须在 main 侧找到 ipcMain.handle/on/webContents.send 的对偶。
// R-09：desktop 是 `"type": "module"` ESM——不用 `__dirname`（未定义），
// 统一走 `import.meta.url` + fileURLToPath。
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const preloadSrc = readFileSync(
  fileURLToPath(new URL("../src/preload/index.ts", import.meta.url)),
  "utf8",
);
const mainDir = fileURLToPath(new URL("../src/main", import.meta.url));
const mainSrcs = readdirSync(mainDir)
  .filter((f) => f.endsWith(".ts"))
  .map((f) => readFileSync(`${mainDir}/${f}`, "utf8"))
  .join("\n");

function extractAll(re: RegExp, src: string): string[] {
  return [...src.matchAll(re)].map((m) => m[1]);
}

const invoke = extractAll(/ipcRenderer\.invoke\(\s*"([^"]+)"/g, preloadSrc);
const sendSync = extractAll(/ipcRenderer\.sendSync\(\s*"([^"]+)"/g, preloadSrc);
const listen = extractAll(/ipcRenderer\.on\(\s*"([^"]+)"/g, preloadSrc);
const handles = extractAll(/ipcMain\.handle\(\s*"([^"]+)"/g, mainSrcs);
const onHandlers = extractAll(/ipcMain\.on\(\s*"([^"]+)"/g, mainSrcs);
const sends = extractAll(/webContents\.send\(\s*"([^"]+)"/g, mainSrcs);

describe("IPC channel parity (B-116)", () => {
  // 底线：B6 完成后 preload 里应至少四个 invoke channel + 两个 on channel。
  // 若 preload 被清空，`for (const ch of invoke)` 会空跑、下面的对偶断言全绿——
  // 这条 baseline 咬住"preload 里的 plumbing 真的存在"。
  it("preload exposes at least 4 invoke channels and 2 on channels", () => {
    expect(invoke.length).toBeGreaterThanOrEqual(4);
    expect(listen.length).toBeGreaterThanOrEqual(2);
    expect(new Set(invoke).size).toBe(invoke.length);
    expect(new Set(listen).size).toBe(listen.length);
  });

  it("every ipcRenderer.invoke has a matching ipcMain.handle", () => {
    for (const ch of invoke) {
      expect(handles, `ipcMain.handle 缺对偶：${ch}`).toContain(ch);
    }
  });

  it("every ipcRenderer.sendSync has a matching ipcMain.on", () => {
    for (const ch of sendSync) {
      expect(onHandlers, `ipcMain.on 缺对偶：${ch}`).toContain(ch);
    }
  });

  it("every ipcRenderer.on has a matching webContents.send", () => {
    for (const ch of listen) {
      expect(sends, `webContents.send 缺对偶：${ch}`).toContain(ch);
    }
  });

  it("required B6 channels are present: qst:request/respond/reject/snapshot/server-event/sidecar-state", () => {
    for (const ch of [
      "qst:request",
      "qst:respond-server-request",
      "qst:reject-server-request",
      "qst:snapshot",
    ]) {
      expect(handles, `main 缺 handle：${ch}`).toContain(ch);
      expect(invoke, `preload 缺 invoke：${ch}`).toContain(ch);
    }
    for (const ch of ["qst:server-event", "qst:sidecar-state"]) {
      expect(sends, `main 缺 send：${ch}`).toContain(ch);
      expect(listen, `preload 缺 on：${ch}`).toContain(ch);
    }
  });
});
