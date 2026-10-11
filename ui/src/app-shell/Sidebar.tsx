// 侧栏：品牌 + 会话分组列表（置顶/最近）+ 底部。数据来自 mock，真接后换 rpc/client。

import { useEffect } from "react";
import { useWorkbenchStore } from "../state/workbenchStore";
import { fetchSessions } from "../rpc/mock";

export function Sidebar() {
  const sessions = useWorkbenchStore((s) => s.sessions);
  const activeSessionId = useWorkbenchStore((s) => s.activeSessionId);
  const setActive = useWorkbenchStore((s) => s.setActive);

  useEffect(() => {
    let cancelled = false;
    fetchSessions().then((list) => {
      if (cancelled) return;
      useWorkbenchStore.setState({ sessions: list });
      if (list.length > 0) setActive(list[0].id);
    });
    return () => {
      cancelled = true;
    };
  }, [setActive]);

  const pinned = sessions.filter((s) => s.pinned);
  const recent = sessions.filter((s) => !s.pinned);

  return (
    <nav aria-label="sessions" className="flex w-64 shrink-0 flex-col border-r border-border bg-sidebar">
      <div className="flex items-center gap-2 px-3 py-3">
        <span className="text-ui-lg font-semibold">Questor</span>
        <span className="text-ui-2xs text-foreground-subtlest">auditable agent workstation</span>
      </div>
      <SessionGroup label="置顶" items={pinned} activeId={activeSessionId} onSelect={setActive} />
      <SessionGroup label="最近" items={recent} activeId={activeSessionId} onSelect={setActive} />
      <div className="mt-auto px-3 py-2 text-ui-2xs text-foreground-subtlest">pre-alpha · M1</div>
    </nav>
  );
}

function SessionGroup({
  label,
  items,
  activeId,
  onSelect,
}: {
  label: string;
  items: ReturnType<typeof useWorkbenchStore.getState>["sessions"];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <section className="px-2 py-1">
      <div className="px-1 py-1 text-ui-2xs tracking-wide text-foreground-subtlest uppercase">{label}</div>
      <ul>
        {items.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => onSelect(s.id)}
              aria-current={s.id === activeId ? "true" : undefined}
              className={`w-full rounded px-2 py-1.5 text-left text-ui-sm hover:bg-surface-hover ${
                s.id === activeId ? "bg-surface-hover" : ""
              }`}
            >
              {s.title}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
