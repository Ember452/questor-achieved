// Review 面板：Phase U Track A 高保真还原度（wuu-grade）。
// 参照 wuu-main/desktop/dev/review/renderer.tsx 与 dev/elevation、dev/motion 的观感；
// 行为契约见 docs/specs/behavior-review-fidelity-wuu.md。
// 覆盖坑：B-103 折叠、B-104 已阅 dot 过渡、B-105 fingerprint 短哈希、B-107 空态可见性。
// A7 会把 <pre> 换成 @pierre/diffs 双栏渲染；此处保持"可见 > 好看"（AGENTS 铁律 3）。

import { useEffect, useMemo, useState } from "react";
import { client } from "../rpc/client";
import type { FileDiff } from "../rpc/generated/app_server-v0-1";
import type { PanelProps } from "./registry";
import "./review.css";

// 折叠阈值：hunks 数量超过此值默认折叠，避免大 diff 首屏吞掉视口（行为规格 §1）。
// 集中在此，不散落魔法数（AGENTS §四）。
const LARGE_HUNKS = 100;
const FINGERPRINT_PREFIX = 7;

interface CardState {
  collapsed: boolean;
  read: boolean;
}

export function ReviewPanel({ threadId, activeTurnId }: PanelProps) {
  const [diffs, setDiffs] = useState<FileDiff[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [card, setCard] = useState<Record<string, CardState>>({});

  useEffect(() => {
    if (!threadId || !activeTurnId) {
      setDiffs([]);
      return;
    }
    let cancelled = false;
    setError(null);
    client
      .call("review/turn_diff", { thread_id: threadId, turn_id: activeTurnId })
      .then((r) => {
        if (!cancelled) setDiffs(r.diffs);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [threadId, activeTurnId]);

  // 空态与卡片可见性互斥（B-107）：empty 分支 return 早于 map，卡片永不同时空态共现。
  const empty = useMemo(() => {
    if (!threadId || !activeTurnId)
      return "尚未选择 turn — 起一轮任务后这里显示写工具执行时刻算好的真实 diff。";
    if (diffs.length === 0 && !error) return "该 turn 无写工具调用";
    return null;
  }, [diffs.length, error, threadId, activeTurnId]);

  if (error) return <div className="p-3 text-ui-xs text-red-500">err: {error}</div>;
  if (empty)
    return <div className="p-3 text-ui-xs text-foreground-subtlest">{empty}</div>;

  return (
    <div className="overflow-auto text-ui-xs">
      {diffs.map((d) => {
        const state: CardState = card[d.path] ?? {
          collapsed: d.hunks.length > LARGE_HUNKS,
          read: false,
        };
        return (
          <FileDiffCard
            key={d.path}
            diff={d}
            state={state}
            onChange={(s) => setCard((prev) => ({ ...prev, [d.path]: s }))}
          />
        );
      })}
    </div>
  );
}

function FileDiffCard({
  diff,
  state,
  onChange,
}: {
  diff: FileDiff;
  state: CardState;
  onChange: (s: CardState) => void;
}) {
  const hunkCount =
    diff.hunks.length > LARGE_HUNKS
      ? "100+ hunks"
      : `${diff.hunks.length} hunks`;
  const fingerprintShort = diff.content_fingerprint.slice(0, FINGERPRINT_PREFIX);
  const markRead = () => onChange({ ...state, read: true });

  return (
    <section className="qst-review-card elevation-1">
      <header
        className="qst-review-card-header qst-focus-ring"
        role="button"
        tabIndex={0}
        onClick={markRead}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            markRead();
          }
        }}
      >
        <span className="qst-review-card-path">{diff.path}</span>
        <span className="qst-review-card-meta">
          {diff.created ? "new" : "modified"} · {diff.byte_size}B · {hunkCount}
        </span>
        <span className="qst-review-card-meta">#{fingerprintShort}</span>
        <span
          className="qst-review-read-dot"
          data-read={state.read ? "true" : "false"}
          aria-hidden="true"
        />
      </header>
      {/* 折叠态：body 完全不入 DOM（textContent 不含 hunk header，B-103 语义折叠而非视觉裁剪）。*/}
      {!state.collapsed && (
        <div className="qst-review-card-body">
          <pre className="qst-review-card-pre">{diff.unified || "(no changes)"}</pre>
        </div>
      )}
    </section>
  );
}
