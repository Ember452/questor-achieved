// Track A 面板测共用夹具（ADR-0031）：FileDiff 样本 + mockTurnDiff。
// 形状严格对齐 `ui/src/rpc/generated/app_server-v0-1`：
//   DiffHunk { old_start, old_lines, new_start, new_lines, body }
//   FileDiff { path, created, hunks, content_fingerprint, byte_size, unified }
//
// mockTurnDiff 走 `vi.spyOn(client, "call")`——不 mock 传输本身，只 mock 客户端方法的返回，
// 保持 `client` 单例引用不变（A6/A7/A8 面板组件仍从 `../rpc/client` 拿 client）。
import { vi } from "vitest";
import { client } from "../rpc/client";
import type { DiffHunk, FileDiff } from "../rpc/generated/app_server-v0-1";

const HUNK_A: DiffHunk = {
  old_start: 1,
  old_lines: 3,
  new_start: 1,
  new_lines: 4,
  body: [" context", "-old", "+new", "+new2", " context"],
};
const HUNK_B: DiffHunk = {
  old_start: 20,
  old_lines: 1,
  new_start: 21,
  new_lines: 2,
  body: ["-tail", "+tail2", "+tail3"],
};

export const SAMPLE_DIFF_MULTI_HUNK: FileDiff = {
  path: "src/foo.py",
  created: false,
  byte_size: 2048,
  content_fingerprint: "abc123def456",
  unified:
    "@@ -1,3 +1,4 @@\n context\n-old\n+new\n+new2\n context\n@@ -20,1 +21,2 @@\n-tail\n+tail2\n+tail3\n",
  hunks: [HUNK_A, HUNK_B, HUNK_A],
};

export const SAMPLE_DIFF_EMPTY: FileDiff[] = [];

/** 100+ hunks 触发默认折叠（B-103 与行为规格 §1）。 */
export const SAMPLE_DIFF_LARGE_HUNKS: FileDiff = {
  ...SAMPLE_DIFF_MULTI_HUNK,
  hunks: Array.from({ length: 120 }, () => HUNK_A),
};

/**
 * mock `client.call("review/turn_diff", ...)` 的返回。返回一个 restore 句柄。
 * 其它 method 直接抛错——防止夹具悄悄放过本不该走的调用。
 */
export function mockTurnDiff(diffs: FileDiff[]): () => void {
  const spy = vi.spyOn(client, "call").mockImplementation(((method: string) => {
    if (method === "review/turn_diff") return Promise.resolve({ diffs });
    throw new Error(`unexpected method: ${method}`);
  }) as never);
  return () => spy.mockRestore();
}
