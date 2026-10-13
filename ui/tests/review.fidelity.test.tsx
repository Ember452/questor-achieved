// Track A A7 还原度测：@pierre/diffs 双栏替换 <pre>（ADR-0031 + 行为规格 §2）。
// 覆盖坑：B-103（头尾 hunk 完整、交给渲染器的数据不截断）、B-106（暗色色对随主题切换、不反相）。
//
// 环境实测结论（happy-dom + @pierre/diffs v1.5.2），决定了断言层次：
//   - <FileDiff/> 挂载一个 <diffs-container> 自定义元素，happy-dom 会升级它并把结构渲染进 shadowRoot；
//     light DOM 的 textContent 始终为空，testing-library 也不穿透 shadow。
//   - @pierre/diffs 的行文本由 shiki 异步高亮后才落进 shadow，测试环境里不可靠 → 不断言渲染后的行文本；
//     改在封装契约层断言"交给 @pierre 的 FileDiffMetadata 是否含首尾两个 hunk 的完整行"（这才是 B-103 的
//     真实回归面：截断 bug 会丢尾 hunk）。主题映射走同步的 :host style（color-scheme 可靠）。
import { afterEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ReviewPanel } from "../src/panels/review";
import { buildFileDiff } from "../src/panels/review.diff-view";
import { SAMPLE_DIFF_MULTI_HUNK, mockTurnDiff } from "../src/testing/fixtures";

let restore: (() => void) | null = null;
afterEach(() => {
  restore?.();
  restore = null;
  document.documentElement.classList.remove("dark");
});

describe("B-103 双栏 diff 头尾完整", () => {
  it("封装把完整 unified 交给 @pierre/diffs：首尾两个 hunk 的行内容都在，未截断", () => {
    const meta = buildFileDiff(SAMPLE_DIFF_MULTI_HUNK);
    expect(meta).toBeDefined();
    // 两个 hunk 都保留——只喂首块 / 丢尾块的截断 bug 会让此断言变红。
    expect((meta as unknown as { hunks: unknown[] }).hunks.length).toBeGreaterThanOrEqual(2);
    const flat = JSON.stringify(meta);
    // 头 hunk（@@ -1,3 +1,4 @@）：上下文 + 末行新增 new2
    expect(flat).toContain("context");
    expect(flat).toContain("new2");
    // 尾 hunk（@@ -20,1 +21,2 @@）：tail / tail3
    expect(flat).toContain("tail");
    expect(flat).toContain("tail3");
  });

  it("ReviewPanel 用 @pierre/diffs 自定义元素渲染 diff，<pre> 已被替换", async () => {
    restore = mockTurnDiff([SAMPLE_DIFF_MULTI_HUNK]);
    const { container } = render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
    await waitFor(() => expect(screen.getByText("src/foo.py")).toBeInTheDocument());
    // 双栏渲染入口挂载了 @pierre/diffs 的自定义元素容器（<pre> 分支不再存在）。
    await waitFor(() => expect(container.querySelector("diffs-container")).not.toBeNull());
    expect(container.querySelector(".qst-review-card-pre")).toBeNull();
  });
});

describe("B-106 暗色 diff 色对（随主题切换、不反相）", () => {
  it("html.dark 时封装把主题映射到 @pierre/diffs 暗色（color-scheme: dark）", async () => {
    document.documentElement.classList.add("dark");
    restore = mockTurnDiff([SAMPLE_DIFF_MULTI_HUNK]);
    const { container } = render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
    await waitFor(() => expect(screen.getByText("src/foo.py")).toBeInTheDocument());
    // 封装层把 .dark 显式落到容器 data-diff-theme（可观察契约，脱离上游 CSS 细节也稳）。
    await waitFor(() => {
      const view = container.querySelector("[data-diff-theme]");
      expect(view?.getAttribute("data-diff-theme")).toBe("dark");
    });
    // 并把同一主题真正传给 @pierre/diffs（暗色色对生效，非硬编码亮色反相）。
    await waitFor(() => {
      const html = container.querySelector("diffs-container")?.shadowRoot?.innerHTML ?? "";
      expect(html).toMatch(/color-scheme:\s*dark/);
    });
  });

  it("无 .dark 时映射为亮色（证明确实随主题切换，而非写死）", async () => {
    restore = mockTurnDiff([SAMPLE_DIFF_MULTI_HUNK]);
    const { container } = render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
    await waitFor(() => expect(screen.getByText("src/foo.py")).toBeInTheDocument());
    await waitFor(() => {
      const view = container.querySelector("[data-diff-theme]");
      expect(view?.getAttribute("data-diff-theme")).toBe("light");
    });
  });
});
