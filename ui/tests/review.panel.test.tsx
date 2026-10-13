// Track A Review 面板还原度测（ADR-0031 + 行为规格 behavior-review-fidelity-wuu.md）。
// 五条失败模式对应坑：B-105（fingerprint 短哈希）、B-107（空态可见性）、B-103（100+ hunks 折叠）。
// 断言只到"应当呈现什么"这一层——具体 DOM 结构由 A6 的实现选；测的是可观察契约。
// 用 fireEvent 而非 user-event：本项目未装 user-event（ADR-0031 范围外），
// click 语义用 fireEvent.click 足够，不需要 user-event 的 typed events 模拟。
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ReviewPanel } from "../src/panels/review";
import {
  SAMPLE_DIFF_EMPTY,
  SAMPLE_DIFF_LARGE_HUNKS,
  SAMPLE_DIFF_MULTI_HUNK,
  mockTurnDiff,
} from "../src/testing/fixtures";

let restore: (() => void) | null = null;
afterEach(() => {
  restore?.();
  restore = null;
});

describe("ReviewPanel 可见柱判据", () => {
  it("无 threadId 时显示占位而非卡片（B-107）", () => {
    render(<ReviewPanel threadId={null} activeTurnId={null} />);
    expect(screen.getByText(/尚未选择 turn/)).toBeInTheDocument();
    expect(screen.queryByText(/src\/foo\.py/)).not.toBeInTheDocument();
  });

  it("diffs 为空时显示'该 turn 无写工具调用'（B-107）", async () => {
    restore = mockTurnDiff(SAMPLE_DIFF_EMPTY);
    render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
    await waitFor(() =>
      expect(screen.getByText(/该 turn 无写工具调用/)).toBeInTheDocument(),
    );
  });

  it("多 hunk 时首屏折叠、header 显'100+ hunks'（B-103）", async () => {
    restore = mockTurnDiff([SAMPLE_DIFF_LARGE_HUNKS]);
    const { container } = render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
    await waitFor(() => expect(screen.getByText("src/foo.py")).toBeInTheDocument());
    expect(screen.getByText(/100\+ hunks/)).toBeInTheDocument();
    // 折叠态下 unified 里的 hunk header 不应出现在 DOM 中
    expect(container.textContent).not.toMatch(/@@\s-1,3\s\+1,4\s@@/);
  });

  it("卡片头显示 fingerprint 前 7 位（B-105）", async () => {
    restore = mockTurnDiff([SAMPLE_DIFF_MULTI_HUNK]);
    render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
    await waitFor(() => expect(screen.getByText(/#abc123d/)).toBeInTheDocument());
  });

  it("点击卡片头切换已阅态（B-104 关联的可交互态）", async () => {
    restore = mockTurnDiff([SAMPLE_DIFF_MULTI_HUNK]);
    render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
    const header = await waitFor(() => screen.getByText("src/foo.py"));
    const dot = document.querySelector<HTMLElement>(".qst-review-read-dot");
    expect(dot).not.toBeNull();
    expect(dot!.dataset.read).toBe("false");
    fireEvent.click(header);
    expect(dot!.dataset.read).toBe("true");
  });
});
