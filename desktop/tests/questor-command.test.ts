// 护栏 B-114：绝不从 workspace 找 bin/questor，也不 PATH 兜底。
// wuu issue #8 同形坑（Linux ELF 落 macOS spawn ENOEXEC）。
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { resolveQuestorCommand } from "../src/main/questor-command";

let sandbox = "";
beforeEach(() => {
  sandbox = join(tmpdir(), `qc-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  mkdirSync(sandbox, { recursive: true });
});
afterEach(() => {
  rmSync(sandbox, { recursive: true, force: true });
});

describe("resolveQuestorCommand", () => {
  it("QUESTOR_DESKTOP_CORE env 显式覆盖", () => {
    const cmd = resolveQuestorCommand(
      { QUESTOR_DESKTOP_CORE: "/custom/core" },
      sandbox,
      undefined,
    );
    expect(cmd.command).toBe("/custom/core");
    expect(cmd.args).toEqual([]);
    expect(cmd.cwd).toBe(sandbox);
  });

  it("USE_UV_RUN=1 + 有 pyproject.toml → uv run sourceRoot", () => {
    writeFileSync(join(sandbox, "pyproject.toml"), "[project]\nname='questor'\n");
    const cmd = resolveQuestorCommand(
      { QUESTOR_DESKTOP_USE_UV_RUN: "1" },
      sandbox,
      undefined,
    );
    expect(cmd.command).toBe("uv");
    expect(cmd.args).toEqual([
      "run",
      "--directory",
      sandbox,
      "questor",
      "serve",
      "stdio",
    ]);
    expect(cmd.cwd).toBe(sandbox);
  });

  it("B-114 关键：workspace 里有假 bin/questor 也不能被 resolve，无 env 无打包 → throw", () => {
    const bin = join(sandbox, "bin");
    mkdirSync(bin, { recursive: true });
    writeFileSync(join(bin, "questor"), "#!/bin/sh\necho stale\n");
    expect(() => resolveQuestorCommand({}, sandbox, undefined)).toThrow(
      /desktop core is missing/,
    );
  });

  it("resourcesPath/bin/questor-core.exe 存在 → 用它", () => {
    const res = join(sandbox, "Resources", "bin");
    mkdirSync(res, { recursive: true });
    const exe = join(res, "questor-core.exe");
    writeFileSync(exe, "");
    const cmd = resolveQuestorCommand({}, sandbox, join(sandbox, "Resources"));
    expect(cmd.command).toBe(exe);
    // R-07：packaged 约定为专用 shim，默认 serve stdio 已内联；args 保持 []。
    expect(cmd.args).toEqual([]);
  });
});
