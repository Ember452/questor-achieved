// runtime_state.json 单调 generation + `.bak` crash 残尾容错。
// provenance: 参照 wuu-main/desktop/src/main/appServerClients.ts 的 generation 语义
//   与 EvoFlow evopanel/src-tauri/src/commands/backend.rs 的 state 文件形态；
//   重写实现（AGENTS §二 (a) 边界层）。
// B-115：写路径必须走 atomic-file.ts（O_EXCL temp + fsync + rename）。
// B-108：crash 残尾容错——bumpState 写前把旧文件 rename 成 `.bak`；readState
//   解析主文件失败时回退读 `.bak`，取上一次完整版本。
import { existsSync } from "node:fs";
import { readFile, rename } from "node:fs/promises";
import { join } from "node:path";
import { writeTextFileAtomicSync } from "./atomic-file";

export interface SidecarState {
  generation: number;
  pid: number;
  startedAt: string;
  // Option A（renderer↔main IPC↔sidecar stdio）下无 endpoint 字段——renderer 不直连内核。
  // 预留 future remote/relay 接入时开（属 M8，另开 ADR）。
}

const STATE_DIR = "desktop";
const STATE_FILE = "runtime_state.json";
const STATE_BACKUP = "runtime_state.json.bak";

function statePath(home: string): string {
  return join(home, STATE_DIR, STATE_FILE);
}

function backupPath(home: string): string {
  return join(home, STATE_DIR, STATE_BACKUP);
}

async function parseFile(path: string): Promise<SidecarState | null> {
  if (!existsSync(path)) return null;
  try {
    const raw = await readFile(path, "utf8");
    const parsed = JSON.parse(raw) as Partial<SidecarState>;
    if (
      typeof parsed.generation !== "number" ||
      typeof parsed.pid !== "number" ||
      typeof parsed.startedAt !== "string"
    ) {
      return null;
    }
    return {
      generation: parsed.generation,
      pid: parsed.pid,
      startedAt: parsed.startedAt,
    };
  } catch {
    return null;
  }
}

export async function readState(home: string): Promise<SidecarState | null> {
  const primary = await parseFile(statePath(home));
  if (primary) return primary;
  return parseFile(backupPath(home));
}

export async function bumpState(
  home: string,
  next: Omit<SidecarState, "generation">,
): Promise<SidecarState> {
  const current = await readState(home);
  const generation = (current?.generation ?? 0) + 1;
  const state: SidecarState = { generation, ...next };

  // 有旧文件 → 先 rename 成 `.bak`；atomic 写新文件。
  // rename 失败（旧文件不存在或权限受限）不阻断新写；主文件写盘走 atomic-file。
  const oldPath = statePath(home);
  if (existsSync(oldPath)) {
    try {
      await rename(oldPath, backupPath(home));
    } catch {
      /* 保留旧 `.bak`；atomic 写会覆盖 primary */
    }
  }
  writeTextFileAtomicSync(oldPath, JSON.stringify(state, null, 2) + "\n");
  return state;
}
