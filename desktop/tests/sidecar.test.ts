// Sidecar NDJSON 契约测：用 Node 自身（process.execPath）起一个 stdin echo /
// stderr 分离的假 sidecar，避免依赖 Python 在 PATH（R-05；Windows CI runner
// 常只有 py launcher 而无 python 别名）。
// 真实 `uv run questor serve stdio` 集成走 Task B3 Step 11 的 [real-terminal] 手动验收。
import { describe, expect, it } from "vitest";
import { readFrame, startSidecar, writeFrame } from "../src/main/sidecar";

describe("sidecar NDJSON", () => {
  it("write + read 往返 JSON 帧", async () => {
    // 假 sidecar：readline 一行 → 原样 stdout.write 一行。
    const handle = await startSidecar({
      command: process.execPath,
      args: [
        "-e",
        "const rl=require('node:readline').createInterface({input:process.stdin});" +
          "rl.on('line',(l)=>process.stdout.write(l+'\\n'));",
      ],
    });
    try {
      writeFrame(handle, { id: "r1", method: "ping", params: {} });
      const reply = (await readFrame(handle)) as { id: string; method: string };
      expect(reply.id).toBe("r1");
      expect(reply.method).toBe("ping");
    } finally {
      handle.kill();
      await handle.exited;
    }
  }, 10_000);

  it("stdout 洁净：stderr 独立通道", async () => {
    const handle = await startSidecar({
      command: process.execPath,
      args: [
        "-e",
        "process.stderr.write('log-line\\n');" +
          "process.stdout.write(JSON.stringify({ok:1})+'\\n');",
      ],
    });
    try {
      const errChunks: string[] = [];
      handle.stderr.on("data", (c: Buffer) => errChunks.push(c.toString("utf8")));
      const frame = (await readFrame(handle)) as { ok: number };
      expect(frame.ok).toBe(1);
      // stderr 至少含 log-line（不要求已 exit，只要求数据落到 stderr 通道）。
      const errText = errChunks.join("");
      expect(errText).toContain("log-line");
    } finally {
      handle.kill();
      await handle.exited;
    }
  }, 10_000);
});
