# ADR-0045 — Review/diff 双源归属：工作区盘态真相归壳侧 GitService，内核不出 review/turn_diff

状态: accepted
日期: 2026-10-14 | 关联: 改判 ADR-0005（被否决项③）与 ADR-0035（方案 A）、`overview.md` §14、`docs/research/phase0-wuu-*.md`、`behavior-review-fidelity-wuu.md §0`

## 结论

照 wuu **双源分工**：
1. **内核**只在写/编辑工具结果里内嵌 **tool-time diff**（`difflib`/`git diff` 复刻 `internal/tools/diff.go`），供模型与工具结果用；
2. **Review 面板**的"工作区盘上真相"由 **Electron 主进程 `GitService` 直接跑 `git diff`**（含 untracked，复刻 `desktop/src/main/gitService.ts`）；
3. **内核不新增 `review/turn_diff` / `review/workspace_diff` 协议方法**（wuu 根本没有）。
放宽 `overview §14` 为：「过程事件（读写/命令/delta）必须经协议可达；**工作区盘态真相允许壳侧只读 git 采集**」。

## 理由与取舍

- 三柱之"可验证"要的是**盘上真实状态**；AI 跑格式化命令或 `git apply` 时，内核"当时算好的那份"是空的——壳侧读盘更诚实。
- 与母本形态一致，避免自造一套内核 git 采集（wuu 没有 = 移植时无蓝本 = 又造轮子）。
- 取舍：破"壳绝不含业务判断"的纯粹性——但"只读 git 采集盘态"不是业务裁决，不违"模型提议、工具裁决"。

## 被否决的选项

- **内核出 workspace diff**：母本无此方法、要净新增 git 采集进内核、且拿不到 untracked 的盘态实时性。
- **壳保持绝对空壳、diff 只从内核来**：回答不了"它说改完了，盘上到底变成什么"。

## 适用条件与失效条件

**适用**：桌面 Electron 宿主。**触发重评审**：若安全模型禁止主进程跑 git → 回到"内核 review/workspace_diff"方案，需新 ADR 并补内核 git 采集能力。
