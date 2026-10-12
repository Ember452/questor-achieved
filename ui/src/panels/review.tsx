// Review 面板：`review/turn_diff` 拿该 turn 覆盖的结构化 diff（B-66/B-93：写时算，
// 不吃事后重扫），逐文件渲染 unified 文本。M4 会加 @pierre/diffs 做双栏 diff；
// M3 用 <pre> + 颜色 class 保持"可见 > 好看"（AGENTS 铁律 3）。

import { useEffect, useState } from "react";
import { client } from "../rpc/client";
import type { FileDiff } from "../rpc/generated/app_server-v0-1";
import type { PanelProps } from "./registry";

export function ReviewPanel({ threadId, activeTurnId }: PanelProps) {
  const [diffs, setDiffs] = useState<FileDiff[]>([]);
  const [error, setError] = useState<string | null>(null);

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

  if (!threadId || !activeTurnId) {
    return (
      <div className="p-3 text-ui-xs text-foreground-subtlest">
        尚未选择 turn — 起一轮任务后这里显示写工具执行时刻算好的真实 diff。
      </div>
    );
  }
  if (error) return <div className="p-3 text-ui-xs text-red-500">err: {error}</div>;
  if (diffs.length === 0)
    return <div className="p-3 text-ui-xs text-foreground-subtlest">该 turn 无写工具调用</div>;

  return (
    <div className="overflow-auto text-ui-xs">
      {diffs.map((d, i) => (
        <section key={`${d.path}-${i}`} className="border-b border-border py-2">
          <header className="flex items-center gap-2 px-3 font-mono">
            <span className="text-foreground">{d.path}</span>
            <span className="text-foreground-subtlest">
              {d.created ? "new" : "modified"} · {d.byte_size}B · {d.hunks.length} hunks
            </span>
            <span className="text-foreground-subtlest">#{d.content_fingerprint}</span>
          </header>
          <pre className="mt-1 whitespace-pre bg-surface px-3 py-1 text-foreground-subtle">
            {d.unified || "(no changes)"}
          </pre>
        </section>
      ))}
    </div>
  );
}
