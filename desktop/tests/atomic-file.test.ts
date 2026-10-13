// 护栏 B-115：无 fsync 的 rename 不算 crash-safe。
//   ① 写入后内容新
//   ② 覆盖时 mode 与被覆盖前一致（chmod 0o604 后仍 0o604，POSIX 分支）
//   ③ 目标目录不存在时 mkdir -p 自动建
//   ④ rename 失败时旧文件保持原内容、temp 被清
// Windows 上 NTFS 不实现 POSIX mode bits（Node stat 报 0o666/0o444），
// mode 断言仅非 win32 平台跑——同 wuu atomicFile.test.ts:26-28/34-43。
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import { chmod, mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { writeTextFileAtomicSync } from "../src/main/atomic-file";

let dir = "";
beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "atomic-"));
});
afterAll(async () => {
  await rm(dir, { recursive: true, force: true });
});
describe("atomic write (B-115)", () => {
  it("写入后内容一致", async () => {
    const path = join(dir, "a.txt");
    writeTextFileAtomicSync(path, "hello");
    expect(await readFile(path, "utf8")).toBe("hello");
  });

  it("覆盖时 mode 保留", async () => {
    const path = join(dir, "m.txt");
    writeTextFileAtomicSync(path, "v1");
    await chmod(path, 0o604);
    writeTextFileAtomicSync(path, "v2");
    // Windows: chmod(0o604) 会被 NTFS 归一为 0o666/0o444，POSIX 位不可靠。
    // 仅 POSIX 平台断言精确 mode；Windows 上以 “内容新” 为护栏（上方已测）。
    if (process.platform !== "win32") {
      expect((await stat(path)).mode & 0o777).toBe(0o604);
    }
  });

  it("目录不存在时 mkdir -p 自动建", async () => {
    const path = join(dir, "sub/dir/x.txt");
    writeTextFileAtomicSync(path, "ok");
    expect(await readFile(path, "utf8")).toBe("ok");
  });

  it("rename 失败时旧内容保留、temp 已清", async () => {
    const path = join(dir, "r.txt");
    await writeFile(path, "old\n");
    vi.spyOn(fs, "renameSync").mockImplementationOnce(() => {
      throw new Error("replacement failed");
    });
    expect(() => writeTextFileAtomicSync(path, "new\n")).toThrow(
      "replacement failed",
    );
    expect(await readFile(path, "utf8")).toBe("old\n");
    // temp 已清：目录下不应再有 `.r.txt.<pid>.<uuid>.tmp` 形式的残留。
    const leftovers = (await readdir(dir)).filter((n) => n.startsWith(".r.txt.") && n.endsWith(".tmp"));
    expect(leftovers).toEqual([]);
    vi.restoreAllMocks();
  });
});
