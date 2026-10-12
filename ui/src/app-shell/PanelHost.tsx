// PanelHost：视图注册表唯一消费点。新加面板只在 registry 追加，不改本文件（护栏咬住）。
// 面板族名统一订阅由 store 层做，PanelHost 只负责渲染当前 panel 与切换器。

import { PANELS, resolvePanel } from "../panels/registry";
import { useWorkbenchStore } from "../state/workbenchStore";

export function PanelHost() {
  const activePanel = useWorkbenchStore((s) => s.activePanel);
  const setActivePanel = useWorkbenchStore((s) => s.setActivePanel);
  const threadId = useWorkbenchStore((s) => s.activeSessionId);
  const activeTurnId = useWorkbenchStore((s) => s.activeTurnId);
  const panel = resolvePanel(activePanel);
  const Component = panel?.component;

  return (
    <aside
      aria-label="workspace-panel"
      className="hidden w-96 shrink-0 flex-col border-l border-border bg-surface md:flex"
    >
      <header className="border-b border-border px-3 py-2 text-ui-sm">
        {panel ? panel.title : "工作区面板（M3）"}
      </header>
      <div className="min-h-0 flex-1 overflow-auto">
        {Component ? (
          <Component threadId={threadId} activeTurnId={activeTurnId} />
        ) : (
          <div className="p-3 text-ui-xs text-foreground-subtlest">
            从下方挑一个面板：Review 显示写时算的 diff，Files 显示工作区内容。
          </div>
        )}
      </div>
      <nav className="flex border-t border-border">
        {PANELS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setActivePanel(p.id)}
            className={`px-3 py-1 text-ui-xs ${activePanel === p.id ? "bg-surface text-foreground" : "text-foreground-subtle"}`}
          >
            {p.title}
          </button>
        ))}
      </nav>
    </aside>
  );
}
