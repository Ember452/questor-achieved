# Questor 架构总览（overview）

版本: v1.0（母本对齐转向：wuu 单锚、复用优先、交付可安装 exe）| 更新: 2026-10-14 | 状态: 待用户评审
关联: `AGENTS.md`（纪律）、`docs/adr/0037~0045`（转向裁决）、`structure.md`（物理布局）、`data-model.md`（数据契约真相源）、`protocol.md`（协议真相源）、`docs/plans/`（波次计划）

> **本文只讲语义与约束**；物理布局看 `structure.md`，数据/协议契约各看其真相源文件。任一方越界复述对方内容，评审打回。
> **一句话定位**：Questor 是以 wuu 为母本重做的**可审计个人 AI Agent 工作站**，交付一个双击安装的 Windows 桌面应用；过程全摊开、随时能插手、跑完能验收。

## 1. 三柱与优先级（不变）

**可见 → 可干预 → 可验证**。冲突时按此序让位；透明度恒为最大，分级的是写域。新功能服务不了任一柱就不做。

**不是什么**（防 scope 漂移，逐项登记、不移植=决定非遗漏）：多用户 SaaS / 组织排班·岗位值班 / 给别人二开的 Agent 框架 / LLM tracing 大盘 / 模型评测榜单。**长任务编排与验收看板属后期 Phase 6**（ADR-0043）。

## 2. 母本与复用（本次转向核心）

唯一母本 = **wuu**（MIT）；**复用优先**：逐文件把 wuu 已验证逻辑翻译/移植进 Python，以 wuu 测试当验收 oracle（ADR-0037）。EvoFlow 仅 Phase 6 长任务层的**规格来源**（读设计不搬码，ADR-0038/0043）；FlowCoder/AfterMatter 退出参照系。**现有 questor 代码全部废弃**，只带走坑与决策作知识；禁复用旧码（AGENTS §〇 硬红线 + import 护栏）。

## 3. 分层

```
CLI / Electron 壳(desktop/src/renderer)
        │  app-server 协议（词表照 wuu，ADR-0042；传输 stdio JSONL）
serve（分发/租约/反向RPC） → engine（手写循环/turn/run/item 事件）
        ├ tools（注册表+执行+结果）→ limen（唯一权限门）
        ├ context（压缩）  ├ gesta（SQLite 会话权威 ADR-0041）  ├ habena（插话/接管）
        └ providers（模型客户端）
横切：state/config/secrets/schemas/capability/worktree/workspaces
后置 Phase 6：orchestration/vigilia/evidence
```

## 4. 语义唯一来源（详见 AGENTS §三）

循环/事件=**来源 wuu、所有权本项目手写**；权限门=wuu boundary；会话存储=**SQLite 权威**；协议词表=**wuu app-server**；Review/diff=**双源（内核 tool-time + 壳侧 GitService）**；编排/验收=后置、规格 EvoFlow。交叉处只允许 adapter，禁两套真相。

## 5. 权限模型（照 wuu 语义）

单一权威门 `limen`：**从可达性推导、绝不从信任推导**；三档 `read_only / standard / unconfined`（限"能碰什么"，不限"显示多少"）；审批只能收紧不能提权；敏感路径守卫三档全开（unconfined 也不解除）；脱敏独立于逃生阀恒开；fail-closed。**Windows 无 OS 写隔离**：standard 档 = 路径门 + Job Object 进程树 + 敏感守卫，**如实标注**（ADR-0007）；AppContainer 列为后期升级（ADR-0039）。

## 6. 模块职责登记

以 `structure.md §2`「模块 ↔ wuu/Evo 源 ↔ 波次」表为准；新增模块先在此 + structure 登记一行再建目录（R5）。

## 7. 数据契约 / 协议契约

- 数据模型真相源 = `data-model.md`（Run⊃Turn/Item 层级、SQLite 权威库、状态机、append-only、revision、UTF-16 选中定位）。
- 协议真相源 = `protocol.md`（wuu app-server 方法/通知词表、stdio JSONL、64MiB 帧、反向 RPC、`initialize`）。
- 二者是「契约三件」之二，**先于当期波次定稿**（AGENTS §七首要）；改动先改文档并递增版本，代码跟随。

## 8. 扩展接缝（§1.7，只留边界不投机）

6 条必保缝：agentengine 薄契约 / tools 注册表+Surface+ToolExposure / 传输无关协议 / 声明式加性演进(ADR-0028) / limen 单门+ToolKind / run·turn·item 数据形状。留门只落边界（数据形状/进程边界/路径单点/能力声明），**禁**为"将来"提前建 registry/基类/config 开关。多租户等"后期可能加"项：保留边界字段（session `owner/visibility`）+ 作用域单点解析，**不焊死也不现在搭**。

## 9. 交付与波次

目标物 = **可安装 Windows exe**（`electron-builder` NSIS + 冻结 Python sidecar，计划 §1.6）。波次：Phase 0 文档/契约重立基 → P1 接缝安全带 → P2 可跑竖切(2a headless/2b 前端+exe门槛1) → P3 补齐 → P4 可验证+Windows硬化+exe门槛3 → P5 优化 → P6 长任务层。**每阶段先扫母本、以 wuu 帧序列等价性为出口判据**（AGENTS §五）。

## 10. 风险与诚实

wuu Windows 无沙箱/无 PTY（后端）→ 逻辑边界 + Electron 侧 node-pty；`securefs` 0o600 在 Win 假安全 → ACL/DPAPI；`credentialstore` 硬编码 macOS-only → 放开走 wincred；协议无代码生成 → 由 `schemas` 生成 TS 修正；本机无 Go → oracle 软模式（读 wuu 测试断言，运行期行为标盲区）。逐条见计划 §9 缺陷台账 + `port-ledger`。

## 11. 未决项（转向后仍开）

1. ~~协议词表取齐~~ 已定 ADR-0042；2. ~~会话权威源~~ 已定 ADR-0041；3. provider 是否要接 Codex 订阅/OAuth（现 MVP 收敛 2 家，Phase 6 前重评）；4. web 宿主何时做（Phase 5 按 wuu renderer-reuse 评估）；5. ~~C19 approval/request~~ **已定（Phase 1 实测）**：采**收紧型** `approve_for_me`（模型审阅的 turn-scoped 审批，`internal/appserver/approve_for_me.go` + `internal/approvefor/review.go:13-18`），Decision 五态 `allow/deny/unsure/failed/cancelled`（=B-56），`HardDenyReason` 先判、超时/失败 **fail-closed**，**非 per-command 逐个弹窗**。
