// mock 协议服务：M1 骨架期用假数据驱动 UI（协议真接后由 rpc/client 替换，组件不动）。
// 形状对齐 src/rpc/generated/ 的类型（data-model/protocol 契约）。

import type { SessionSummary } from "../state/workbenchStore";

export const mockSessions: SessionSummary[] = [
  { id: "demo-001", title: "修复 calculator 的进位 bug", pinned: true, updatedAt: "2026-10-11T08:30:00Z" },
  { id: "demo-002", title: "整理 docs 目录结构", pinned: false, updatedAt: "2026-10-11T07:12:00Z" },
  { id: "demo-003", title: "调研 Tree-sitter 0.22 迁移", pinned: false, updatedAt: "2026-10-10T21:40:00Z" },
];

export const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function fetchSessions(): Promise<SessionSummary[]> {
  await delay(120);
  return mockSessions;
}
