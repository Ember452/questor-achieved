// crash-safe 写盘：mkdir -p → O_EXCL temp sibling → fchmodSync(mode) → fsyncSync → rename。
// 严格照 wuu-main/desktop/src/main/atomicFile.ts:13-67，重写。temp 命名
// `.basename.pid.uuid.tmp` 保证多进程不撞；mode 与被覆盖前一致（缺省 0o600）；
// text/buffer 共享 writeCore。
// B-115：只做 writeFile+rename 而无 fsync，崩溃时 rename 可能已发生但字节仍在页缓存里。
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import { basename, dirname, join } from "node:path";

type AtomicWriteOptions = { defaultMode?: number };

function writeCore(
  path: string,
  payload: string | Buffer,
  encoding: BufferEncoding | undefined,
  options: AtomicWriteOptions,
): void {
  const directory = dirname(path);
  fs.mkdirSync(directory, { recursive: true });

  let mode = options.defaultMode ?? 0o600;
  try {
    mode = fs.statSync(path).mode & 0o777;
  } catch (error) {
    if (!isMissingFileError(error)) throw error;
  }

  const temporaryPath = join(
    directory,
    `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`,
  );
  let descriptor: number | undefined;
  try {
    descriptor = fs.openSync(
      temporaryPath,
      fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY,
      mode,
    );
    fs.fchmodSync(descriptor, mode);
    if (typeof payload === "string") {
      fs.writeFileSync(descriptor, payload, encoding ?? "utf8");
    } else {
      fs.writeFileSync(descriptor, payload);
    }
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    fs.renameSync(temporaryPath, path);
  } catch (error) {
    if (descriptor !== undefined) {
      try {
        fs.closeSync(descriptor);
      } catch {
        /* preserve write error */
      }
    }
    try {
      fs.rmSync(temporaryPath, { force: true });
    } catch {
      /* preserve write error */
    }
    throw error;
  }
}

export function writeTextFileAtomicSync(
  path: string,
  text: string,
  options: AtomicWriteOptions = {},
): void {
  writeCore(path, text, "utf8", options);
}

export function writeBufferFileAtomicSync(
  path: string,
  data: Buffer,
  options: AtomicWriteOptions = {},
): void {
  writeCore(path, data, undefined, options);
}

function isMissingFileError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    (error as { code?: string }).code === "ENOENT"
  );
}
