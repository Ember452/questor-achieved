// 护栏 B-108 generation 单调性与 crash 残尾容错。
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { bumpState, readState } from "../src/main/sidecar-state";

let home = "";
beforeEach(async () => {
  home = await mkdtemp(join(tmpdir(), "questor-desktop-"));
});
afterEach(async () => {
  await rm(home, { recursive: true, force: true });
});

describe("generation 单调性（B-108）", () => {
  it("空 home 首次 bumpState → generation=1", async () => {
    expect(await readState(home)).toBeNull();
    const s = await bumpState(home, {
      pid: 111,
      startedAt: new Date().toISOString(),
    });
    expect(s.generation).toBe(1);
    expect((await readState(home))?.pid).toBe(111);
  });

  it("连续两次 bumpState → generation 递增", async () => {
    await bumpState(home, { pid: 1, startedAt: "2026-01-01T00:00:00Z" });
    const s = await bumpState(home, { pid: 2, startedAt: "2026-01-01T00:00:01Z" });
    expect(s.generation).toBe(2);
  });

  it("state 文件损坏（残尾）时 readState 回退到 .bak", async () => {
    await bumpState(home, { pid: 42, startedAt: "2026-01-01T00:00:00Z" });
    await bumpState(home, { pid: 43, startedAt: "2026-01-01T00:00:01Z" });
    // 模拟 crash 残尾：把主 runtime_state.json 截半（`.bak` 完好 → 回退到 pid=42）。
    await writeFile(join(home, "desktop", "runtime_state.json"), '{"gener');
    const s = await readState(home);
    expect(s).not.toBeNull();
    expect(s?.pid).toBe(42);
  });
});
