// @pierre/diffs 薄封装（ADR-0031 / 行为规格 §2）——Review 面板唯一 diff 渲染入口。
// review.tsx 只 import 本文件；上游 API 变化只改这里（护栏：diff 面单点）。
//
// 数据流：turn_diff 返回的是 unified 补丁串 → 用 @pierre/diffs 的 processFile 转 FileDiffMetadata
//   → 交给 react <FileDiff/> 渲染双栏。
//   注：同包的 parseDiffFromFile 面向"两份完整文件内容"重算 diff；本项目 per-turn 只有 unified
//   片段（含跨行的多 hunk），用 processFile 保留原始 hunk 结构与行号，不改协议、不丢尾 hunk（B-103）。
//
// 颜色不写 hex 字面量：主题只以 light/dark 名义透传，色对由 @pierre/diffs 主题与 tokens.css
//   的 --color-diff-* 家族共同决定（护栏 ui/tests/design.tokens.test.ts 扫组件源码）。
import { useMemo } from "react";
import { FileDiff } from "@pierre/diffs/react";
import { processFile } from "@pierre/diffs";
import type { FileDiff as ReviewFileDiff } from "../rpc/generated/app_server-v0-1";

// vitest（happy-dom）下关 worker pool：测试环境无 worker 传输，禁用以走主线程高亮（ADR-0031）。
// 生产（vite dev/build）保留 worker pool 的首屏性能。
const IS_TEST = import.meta.env.MODE === "test";

// useTheme 维护 <html> 的 .dark class（见 src/design/useTheme.ts）；本封装按它映射明暗主题。
function resolveTheme(): "light" | "dark" {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

// 把一条 turn_diff 记录转成 @pierre/diffs 的 FileDiffMetadata。
// turn_diff 的 unified 是纯 hunk 片段（无 diff --git 头），直接 processFile 解析后 name 为空、
// 无法按扩展名推断语言 → 行内容不渲染。用 path 合成最小 git 头补上文件名。
// 导出为纯函数：B-103（头尾 hunk 完整）直接断言它交给 @pierre 的元数据是否完整、无截断。
export function buildFileDiff(diff: ReviewFileDiff) {
  if (!diff.unified) return undefined;
  const patch = `diff --git a/${diff.path} b/${diff.path}\n--- a/${diff.path}\n+++ b/${diff.path}\n${diff.unified}`;
  return processFile(patch, { throwOnError: false });
}

export function FileDiffView({ diff }: { diff: ReviewFileDiff }) {
  // 空 unified 显式占位（行为规格 §1 边界：unified === "" → "(no changes)"）。
  const theme = resolveTheme();
  const fileDiff = useMemo(() => buildFileDiff(diff), [diff]);

  if (!diff.unified || !fileDiff) {
    return <div className="qst-review-card-empty">(no changes)</div>;
  }

  return (
    <div className="qst-diff-view" data-diff-theme={theme}>
      <FileDiff
        fileDiff={fileDiff}
        options={{
          themeType: theme,
          // B-103：长行走 wrap 而非横向滚动，头尾不被截断。
          overflow: "wrap",
          // 显示 hunk 分隔（行号元信息），保证每个 hunk 头尾可见。
          hunkSeparators: "metadata",
        }}
        disableWorkerPool={IS_TEST}
      />
    </div>
  );
}
