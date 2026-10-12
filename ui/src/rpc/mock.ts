// mock 协议服务：M3 真接后降级为**测试替身**（vitest 未接入，本文件暂只作 fixtures 供
// storybook / 未来的 UI 冒烟测试复用）。生产代码禁止 import 本模块——AppShell /
// ConversationPane / Sidebar 都走 rpc/client（AGENTS §五"前端跟随"的落地形式）。

import type { ThreadDTO } from "./generated/app_server-v0-1";

/** 一份份 ThreadDTO 样本；组件测里 import 作初始 store 状态。 */
export const sampleThreads: ThreadDTO[] = [
  {
    id: "demo-001",
    workspace_id: "ws-demo",
    title: "修复 calculator 的进位 bug",
    engine_id: "questor-engine",
    permission_mode: "standard",
    pinned: true,
    archived: false,
    created_at: "2026-10-11T08:30:00Z",
    updated_at: "2026-10-11T08:30:00Z",
  },
  {
    id: "demo-002",
    workspace_id: "ws-demo",
    title: "整理 docs 目录结构",
    engine_id: "questor-engine",
    permission_mode: "standard",
    pinned: false,
    archived: false,
    created_at: "2026-10-11T07:12:00Z",
    updated_at: "2026-10-11T07:12:00Z",
  },
];
