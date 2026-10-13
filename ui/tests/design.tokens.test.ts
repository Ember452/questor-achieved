// 护栏：Track A 的 Review 面板与其就近样式表**不得**出现 diff 相关的 hex 字面量，
// 必须走 `var(--color-diff-*)` token 或 Tailwind 类映射到 token。
//
// 判据：AGENTS §四 护栏测试准入——"让它可以失败的是真实的设计改动，不是随手改个值"。
// 允许失败的两种真实漂移：① 面板代码里塞 hex 绕过 token 单点；② review.css.ts
// 里的过渡/阴影写死色，主题切换时暗色覆盖失效（B-106）。
//
// 对应坑：B-106（暗色色对反相）；A4 落 token 族，本护栏与 A6 的 review.css.ts 一同转绿。
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const read = (rel: string): string => readFileSync(resolve(__dirname, "..", rel), "utf8");

describe("Review 面板 diff 色只走 token", () => {
  // 面板源码里不得出现 hex 字面量（Tailwind 语义类如 `text-red-500` 不在扫查面——
  // 那是 danger 色、非 diff 语义色；真正的 diff add/del 色必须走 token）。
  for (const file of ["src/panels/review.tsx", "src/panels/review.css.ts"]) {
    it(`${file} 无 diff hex 字面量`, () => {
      const src = read(file);
      expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    });
  }
});
