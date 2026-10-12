// 视图注册表骨架（ADR-0020：接口面提前，M3 落骨架，E1 只补面板与主题）。
//
// **护栏**：新面板只能在此登记，不得改 AppShell / PanelHost 外壳。
// `tests/architecture/test_no_hardcoded_panel_case.py` 用 AST 扫外壳源码不得出现
// `"review"` / `"files"` 字面 case——违反即红。
//
// M3c 只落 Review 与 Files 两块真接面板；Terminal 与 Browser 面板推后
// （plan §"明确不做" + ADR-0024）。

import type { ComponentType } from "react";
import type { Notification } from "../rpc/generated/app_server-v0-1";
import { BoardPanel } from "./board";
import { FilesPanel } from "./files";
import { ReviewPanel } from "./review";

export interface PanelProps {
  threadId: string | null;
  activeTurnId: string | null;
}

export interface PanelDescriptor {
  id: string;
  title: string;
  /** 面板真正渲染前订阅的通知族名；PanelHost 用它做统一订阅（避免每面板各订各的）。 */
  requiredNotifications: readonly string[];
  component: ComponentType<PanelProps>;
}

/** 单一登记表：新加面板只在此追加一条，AppShell/PanelHost 不动（护栏咬住）。 */
export const PANELS: readonly PanelDescriptor[] = [
  {
    id: "review",
    title: "Review",
    requiredNotifications: ["item/completed", "run/status"],
    component: ReviewPanel,
  },
  {
    id: "files",
    title: "Files",
    requiredNotifications: ["item/completed"],
    component: FilesPanel,
  },
  {
    id: "board",
    title: "Board",
    requiredNotifications: ["task/status", "plan/updated"],
    component: BoardPanel,
  },
];

export function resolvePanel(id: string | null): PanelDescriptor | null {
  if (id === null) return null;
  return PANELS.find((p) => p.id === id) ?? null;
}

/** 面板族名合起来的并集；ConversationPane 用它给所有面板统一订阅通知。 */
export function unionRequiredNotifications(ids: readonly string[]): Set<string> {
  const out = new Set<string>();
  for (const id of ids) {
    const panel = resolvePanel(id);
    if (panel) for (const name of panel.requiredNotifications) out.add(name);
  }
  return out;
}

export type { Notification };
