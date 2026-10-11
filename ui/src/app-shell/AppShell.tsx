// 第一屏工作台骨架：Sidebar（会话列表）+ ConversationPane（对话区）+ 工作区面板占位。
// 布局层次参照 wuu AppShell（app-shell > sidebar + conversation-pane + workspace-panel）。

import { useWorkbenchStore } from "../state/workbenchStore";
import { Sidebar } from "./Sidebar";
import { ConversationPane } from "./ConversationPane";

export function AppShell() {
  const activeSessionId = useWorkbenchStore((s) => s.activeSessionId);
  return (
    <div className="flex h-full w-full bg-background text-foreground">
      <Sidebar />
      <ConversationPane />
      {/* 工作区面板占位：M3 实装（react-resizable-panels + Review/Files/Terminal） */}
      <aside
        aria-label="workspace-panel-placeholder"
        className="hidden w-80 shrink-0 border-l border-border bg-surface md:block"
      >
        <div className="p-3 text-ui-xs text-foreground-subtlest">
          工作区面板（M3：Review / Files / Terminal）
        </div>
      </aside>
      {/* 占位消除未用变量告警：activeSessionId 在 M3 面板接真数据时消费 */}
      <span data-active-session={activeSessionId ?? ""} className="hidden" />
    </div>
  );
}
