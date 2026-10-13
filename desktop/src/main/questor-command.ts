// Questor 桌面核解析，严格照 wuu-main/desktop/src/main/wuuCommand.ts:29-46 重写。
// 优先级：QUESTOR_DESKTOP_CORE env → QUESTOR_DESKTOP_USE_UV_RUN=1 + sourceRoot
//   → 打包 Resources/bin/questor-core[.exe] → throw。
// **绝不** fall back 到 PATH 里的 questor（独立 CLI 装的可能版本漂移）。
// **绝不** inspect appPath 下的 bin/questor——wuu issue #8 血泪坑（B-114：
//   用户把 questor 仓库本身开成 workspace、`make build` 产的 Linux ELF
//   落到 macOS/Windows 会 spawn ENOEXEC）。
// R-07 约定：packaged questor-core.exe 是专用 shim，默认 serve stdio 已内联；
//   args 保持 []。若未来换通用 CLI 打包（PyInstaller 全量），需切成 ["serve","stdio"]
//   并回写 ADR-0032 §失效条件。
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";

export interface QuestorCommand {
  command: string;
  args: string[];
  cwd: string;
}

export function resolveQuestorCommand(
  env: NodeJS.ProcessEnv,
  appPath: string,
  resourcesPath?: string,
): QuestorCommand {
  if (env.QUESTOR_DESKTOP_CORE) {
    return { command: env.QUESTOR_DESKTOP_CORE, args: [], cwd: appPath };
  }
  if (env.QUESTOR_DESKTOP_USE_UV_RUN === "1") {
    const sourceRoot = findSourceRoot(appPath);
    if (sourceRoot) {
      return {
        command: "uv",
        args: ["run", "--directory", sourceRoot, "questor", "serve", "stdio"],
        cwd: sourceRoot,
      };
    }
  }
  const packaged = resolvePackagedCore(resourcesPath);
  if (packaged) {
    return { command: packaged, args: [], cwd: appPath };
  }
  throw new Error("questor desktop core is missing; reinstall the desktop app");
}

/** 从 appPath 往上找最近的含 pyproject.toml 的祖先目录，作为 uv run 的 sourceRoot。 */
function findSourceRoot(start: string): string | undefined {
  let dir = resolve(start);
  for (let i = 0; i < 8; i++) {
    if (existsSync(join(dir, "pyproject.toml"))) return dir;
    const parent = resolve(dir, "..");
    if (parent === dir) return undefined;
    dir = parent;
  }
  return undefined;
}

function resolvePackagedCore(resourcesPath: string | undefined): string | undefined {
  if (!resourcesPath) return undefined;
  for (const candidate of [
    join(resourcesPath, "bin", "questor-core"),
    join(resourcesPath, "bin", "questor-core.exe"),
  ]) {
    if (existsSync(candidate)) return candidate;
  }
  return undefined;
}
