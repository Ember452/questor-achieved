// 第一屏工作台骨架：Sidebar（会话列表）+ ConversationPane（对话区）+ PanelHost（工作区面板）。
// **护栏**（B-97）：AppShell 不得出现 `"review"` / `"files"` 等面板名硬编码 case，
// 一切面板通过 panels/registry.ts 的 PANELS 登记；PanelHost 是唯一渲染分发点。

import { ConversationPane } from "./ConversationPane";
import { PanelHost } from "./PanelHost";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  return (
    <div className="flex h-full w-full bg-background text-foreground">
      <Sidebar />
      <ConversationPane />
      <PanelHost />
    </div>
  );
}
