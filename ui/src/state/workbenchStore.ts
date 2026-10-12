// 工作台状态（zustand v5——显式选 v5，参照项目 evopanel 是 v4 写法，不混用）。
// M3c 起：数据来自 rpc/client + WS 通知流；UI-local 状态（面板可见性、主题、草稿）留本地。
// **会话/运行/权限的真相永远在 Python 侧**（ui/README 的边界条款），本 store 只做
// "当前视图的镜像"，不代替正文 JSONL 承担审计角色。

import { create } from "zustand";
import type { ThreadDTO } from "../rpc/generated/app_server-v0-1";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  isStreaming: boolean;
  /** 插话消费出来的消息（payload.steered=True）；UI 用来打"steer"角标。 */
  steered?: boolean;
}

export interface WorkbenchState {
  sessions: ThreadDTO[];
  activeSessionId: string | null;
  activeTurnId: string | null;
  activePanel: string | null;
  runStatus: string | null;
  messages: ChatMessage[];
  setSessions: (s: ThreadDTO[]) => void;
  setActive: (id: string | null) => void;
  setActiveTurn: (id: string | null) => void;
  setActivePanel: (id: string | null) => void;
  setRunStatus: (s: string | null) => void;
  resetMessages: () => void;
  appendMessage: (m: ChatMessage) => void;
  appendDelta: (text: string) => void;
  markLastAssistantDone: () => void;
}

let localSeq = 0;
function nextLocalId(prefix: string): string {
  localSeq += 1;
  return `${prefix}-${localSeq}`;
}

export const useWorkbenchStore = create<WorkbenchState>((set) => ({
  sessions: [],
  activeSessionId: null,
  activeTurnId: null,
  activePanel: null,
  runStatus: null,
  messages: [],
  setSessions: (sessions) => set({ sessions }),
  setActive: (activeSessionId) =>
    set({ activeSessionId, activeTurnId: null, messages: [], runStatus: null }),
  setActiveTurn: (activeTurnId) => set({ activeTurnId }),
  setActivePanel: (activePanel) => set({ activePanel }),
  setRunStatus: (runStatus) => set({ runStatus }),
  resetMessages: () => set({ messages: [] }),
  appendMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
  appendDelta: (text) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant" && last.isStreaming) {
        msgs[msgs.length - 1] = { ...last, text: last.text + text };
      } else {
        msgs.push({
          id: nextLocalId("stream"),
          role: "assistant",
          text,
          isStreaming: true,
        });
      }
      return { messages: msgs };
    }),
  markLastAssistantDone: () =>
    set((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant" && msgs[i].isStreaming) {
          msgs[i] = { ...msgs[i], isStreaming: false };
          break;
        }
      }
      return { messages: msgs };
    }),
}));
