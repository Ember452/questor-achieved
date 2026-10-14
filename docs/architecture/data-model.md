# Questor 数据模型（data-model）——会话与运行契约真相源

版本: v2.0（会话存储改判 SQLite 权威，ADR-0041；diff 双源，ADR-0045；对齐 wuu 层级/状态集）| 更新: 2026-10-14 | 状态: 待用户评审
关联: `ADR-0041`（SQLite 权威）、`ADR-0045`（diff 双源）、`ADR-0005`（revision）、`ADR-0014`（运行状态迁移）、`docs/research/phase0-wuu-sqlite-schema.md`（表清单事实源）、`protocol.md`

> 本文件是「数据模型」契约三件之一，改动先改本文并递增版本。表级/字段级细节以 `phase0-wuu-sqlite-schema.md` 为准，本文定实体、状态机、权威源、不可改写约束。

## 1. 四层实体（照 wuu，别混层）

```
Thread  一个会话（绑一个引擎 + 一个工作区；永不静默换引擎）
 Run    一次 agent 调用的"控制与观测边界"（引用而非复制下面的 Turn）
  Turn  一次用户输入引发的一轮对话（开始时定死 model/provider；携 Kind）
   Step  一轮 model 往返（循环内部概念，不对外暴露）
    Item 一个可见产物单元（文字/推理/工具调用，带 delta/replace 流式增量）
```
> 常见错误：把 Run 当"一次 model 往返"（错，那是 Step）；把 turn 与 run 混一层。移植时按此对齐持久化 seq 与 `LoopResult`。

## 2. 会话存储权威源 = SQLite（ADR-0041）

**SQLite 为会话权威库**（`sessions` / `session_messages` / `session_controls` / `session_inbox` / `held_user_work` / `session_history_{retractions,checkpoints}` / `session_driver_checkpoints` / `session_compaction_notes` / `inference_journal_runtimes`；完整建表见 `phase0-wuu-sqlite-schema.md`）。**JSONL 降为可选导出镜像**，不再是真相源。
- 驱动 `modernc.org/sqlite`(Go) → Python `sqlite3`/`aiosqlite` 1:1 移植 schema/事务/WAL/自定义函数（`create_function` 复刻 `wuu_history_content`）。
- 权限位由 POSIX 0600 改 **NTFS ACL**（Windows，port-ledger 记）。

## 3. 状态机

### 3.1 turn / run（可干预）
- **held_user_work**：`origin ∈ {queue, steer}`——steer=运行中改道、queue=排队；对应协议 `turn/steer|unsteer|queue|dequeue|requeue|update-queued`。
- **run 状态**（照 wuu 集，补 ADR-0014）：`accepted / running / completed / failed / interrupted / timed_out / cancelled`；`queued→cancelled` 迁移补录。取消/中断**仍结算**（不受取消影响的落账，否则丢工具结果，B-89）。
- **inbox 幂等**（`session_inbox.client_id` + `INSERT OR IGNORE`）：delivered 判据 = client_id 已落入目标持久历史；重启可重试不重复注入（B-63）。

### 3.2 编排/验收（**Phase 6 后置**，ADR-0043）
TaskStatus / CollabPhase 双状态机、迁移留痕、验收打回、evidence——A 阶段不建，此处仅占位指向 Phase 6 规格（EvoFlow 读设计、围自研 run 重写）。

## 4. append-only 与不可改写（可验证柱）

- `session_messages (session_id, seq)` 主键、append-only；"不可改写历史"用**表约束 + 触发器禁 UPDATE/DELETE content** 表达（替代旧"JSONL 文件不可变"立场）。
- 需求改版/验收作废 → 只追加新修订，不改写；`HistoryRewritten=true` 时走 `session_history_retractions/checkpoints` 的替换区间记录，不物理删。
- 原始会话/prompt 全文/真实绝对路径永不进出机数据与 fixture（AGENTS §四 红线）。

## 5. revision 与 diff 双源（ADR-0045 / ADR-0005）

- **工作区修订号** `session_controls.revision`：单点递增，绑定读/写快照。
- **diff 双源分工**：① 内核在写/编辑工具结果内嵌 **tool-time diff**（`tools/diff.go` 形状）；② Review 面板的**工作区盘态真相由 Electron 主进程 GitService 跑 `git diff`**（含 untracked）。**内核不新增 `review/turn_diff`**。协议对象携 `dirty` / `changed_files`（wuu 已有形状），Review 面板据此呈现。

## 6. 选中/批注定位

源定位 = **UTF-16 code units in rendered DOM**（照 wuu，跨端一致）+ 修订号绑定；**不再用"字节 offset"**（wuu 明确 UTF-16，混用会两端互操作错位）。

## 7. 上下文记录（transcript 事实）

上下文工程事实（压缩边界、大结果落盘引用、discovered_tools 已加载态等）作为 append-only 记录进会话库（`content_parts_json` / `discovered_tools_json` / `session_history_checkpoints` / `session_compaction_notes`），随新实现更新版本（ADR-0017 语义随存储改判重述）。

## 8. 与代码/前端的接缝

- `schemas/model/` = 本文件实体的 JSON Schema 真相源 → 生成 TS（`packages/protocol`）；前端**不镜像会话/运行/权限真相**，只存 UI-local。
- 跨边界数据一律 pydantic v2，禁裸 dict（AGENTS §四）。
