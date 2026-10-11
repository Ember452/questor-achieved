// 会话工作台状态（zustand v5——显式选 v5，参照项目 evopanel 是 v4 写法，不混用）。
// M1 骨架：数据来自 rpc/mock（协议真接后换 rpc/client，组件不动）。

import { create } from "zustand";

export interface SessionSummary {
  id: string;
  title: string;
  pinned: boolean;
  updatedAt: string;
}

export interface WorkbenchState {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  setActive: (id: string) => void;
}

export const useWorkbenchStore = create<WorkbenchState>((set) => ({
  sessions: [],
  activeSessionId: null,
  setActive: (id) => set({ activeSessionId: id }),
}));
