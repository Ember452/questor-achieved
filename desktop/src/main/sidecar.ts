// Sidecar 生命周期：以 stdio NDJSON 与 Python `questor serve stdio` 通信。
// provenance: 参照 wuu-main/desktop/src/main/appServerClients.ts 的 stdio 管道模式，
// 与 EvoFlow evopanel/src-tauri/src/commands/backend.rs 的 sidecar generation 语义；
// **重写实现**——不拷贝任一上游代码。对应 AGENTS §二 (a) 类边界层。
// B-113：killTree（Task B5）会显式等 exit 事件而非 pipe close，本文件只负责
// 把子进程三管道与 exited promise 暴露出去，不管停机时序。
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";

export interface SidecarHandleLike {
  exited: Promise<{ code: number | null; signal: NodeJS.Signals | null }>;
  kill(signal?: NodeJS.Signals): void;
}

export interface SidecarHandle extends SidecarHandleLike {
  pid: number;
  stdin: NodeJS.WritableStream;
  stdout: NodeJS.ReadableStream;
  stderr: NodeJS.ReadableStream;
}

export async function startSidecar(opts: {
  command: string;
  args: string[];
  cwd?: string;
  env?: NodeJS.ProcessEnv;
}): Promise<SidecarHandle> {
  const child: ChildProcessWithoutNullStreams = spawn(opts.command, opts.args, {
    env: { ...process.env, ...opts.env },
    cwd: opts.cwd,
    stdio: ["pipe", "pipe", "pipe"],
    // Windows: 隐藏控制台窗口（Electron 打包后必需）。
    windowsHide: true,
  });
  if (child.pid === undefined) {
    throw new Error("spawn failed: no pid assigned (Windows B-77 类似坑：进程启动即失败)");
  }
  const exited = new Promise<{ code: number | null; signal: NodeJS.Signals | null }>(
    (resolve) => child.once("exit", (code, signal) => resolve({ code, signal })),
  );
  return {
    pid: child.pid,
    stdin: child.stdin,
    stdout: child.stdout,
    stderr: child.stderr,
    exited,
    kill: (signal) => {
      child.kill(signal);
    },
  };
}

export function writeFrame(handle: SidecarHandle, obj: unknown): void {
  const line = JSON.stringify(obj) + "\n";
  handle.stdin.write(line);
}

/** 读一行 NDJSON 帧；单行 JSON 上限由 overview §8 定义，超限 reject 不 truncate。 */
export function readFrame(handle: SidecarHandle): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const rl = createInterface({ input: handle.stdout, crlfDelay: Infinity });
    let done = false;
    rl.once("line", (line) => {
      done = true;
      rl.close();
      try {
        resolve(JSON.parse(line));
      } catch (err) {
        reject(new Error(`sidecar NDJSON parse: ${(err as Error).message}`));
      }
    });
    handle.exited.then((r) => {
      if (!done) {
        rl.close();
        reject(new Error(`sidecar exited before frame: code=${r.code} signal=${r.signal}`));
      }
    });
  });
}
