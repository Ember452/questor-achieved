// Sidebar：从 client.call("thread/list") 拉真会话；点一条 = 设为 active。
// M3 起 mock 已降级为测试替身；本文件不再 import mock（AGENTS §五 前端跟随）。

import { useEffect, useState } from "react";
import { client } from "../rpc/client";
import { useWorkbenchStore } from "../state/workbenchStore";

export function Sidebar() {
  const sessions = useWorkbenchStore((s) => s.sessions);
  const activeId = useWorkbenchStore((s) => s.activeSessionId);
  const setActive = useWorkbenchStore((s) => s.setActive);
  const setSessions = useWorkbenchStore((s) => s.setSessions);
  const [newTitle, setNewTitle] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    client
      .call("thread/list", {})
      .then((r) => {
        if (!cancelled) setSessions(r.threads);
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [setSessions]);

  async function createThread() {
    const title = newTitle.trim();
    if (!title) return;
    setErr(null);
    try {
      const r = await client.call("thread/create", {
        workspace_id: "ws-local",
        title,
      });
      setNewTitle("");
      const list = await client.call("thread/list", {});
      setSessions(list.threads);
      setActive(r.thread.id);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <aside
      aria-label="sidebar"
      className="flex w-64 shrink-0 flex-col border-r border-border bg-surface"
    >
      <header className="border-b border-border px-3 py-2 text-ui-sm">会话</header>
      <div className="flex gap-2 border-b border-border p-2">
        <input
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="新会话标题"
          className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1 text-ui-xs"
        />
        <button
          type="button"
          onClick={createThread}
          className="rounded bg-foreground px-2 py-1 text-ui-xs text-background"
        >
          新建
        </button>
      </div>
      {err ? <p className="p-2 text-ui-2xs text-red-500">err: {err}</p> : null}
      <ul className="flex-1 overflow-auto">
        {sessions.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => setActive(s.id)}
              className={`block w-full px-3 py-2 text-left text-ui-xs hover:bg-background ${activeId === s.id ? "bg-background font-semibold" : ""}`}
            >
              {s.pinned ? "★ " : ""}
              {s.title ?? s.id}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
