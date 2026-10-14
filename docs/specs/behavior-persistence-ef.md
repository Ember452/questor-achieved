# behavior-persistence-ef —— EvoFlow 持久化行为规格（Questor `gesta` 对照蓝本）

来源：EvoFlow `backend/packages/harness/evoflow/persistence/schema.py`（2191 行，
123 张 `CREATE TABLE`）+ `persistence/chat_message_content.py` + `memory/store.py`。
扫描日期 2026-10-11。Questor 模块归属：`gesta`（对照取舍）。

---

## 1. 存储形态（Questor 的反面/对照教材）

- **三库分置**：app / observability / checkpoints 三类库；单 schema 文件 2191 行、
  123 张 `evoflow_*` 表（`persistence/schema.py` 全文；`wc -l` 与 `grep -c "CREATE TABLE"`
  实测），迁移由 data_layout 层负责。
- **消息正文**：标量列 + **单 JSON blob** `content_json`
  （`{"content", "tool_calls"?, "reasoning"?, "ui"?}`，`persistence/chat_message_content.py#L1,L105-110`）。
- **流镜像**：`evoflow_chat_stream_mirror` + `_meta` 两表单独承载流断线恢复
  （`persistence/schema.py#L449,461`）。
- **坑**：B-46（百表单体 vs Questor 的 JSONL 真相源 + 索引分离）、B-47（流镜像独立位）。

### Questor 采纳决定
Questor 契约（overview §7）已定：会话正文 append-only JSONL 是唯一真相源，SQLite 只做
可丢弃可重建的搜索索引；大内容落盘引用。EvoFlow 的"流镜像表"思想保留——Questor 的事件
持久化在 gesta JSONL 中天然覆盖，协议层再做 deferred content。

## 2. 记忆检索（`memory/store.py`，M7 对照）

- **FTS5 中文**：查询词 OR + 引号包裹 + **CJK bigram**——unicode61 分词器会把中文连成
  整串，bigram 拆字才能命中（`memory/store.py#L557` 注释）。
- **坑**：B-48。

### Questor 采纳决定
M7 记忆/代码索引的 SQLite FTS 实现直接沿用该技巧；M1 的搜索索引 schema 预留 CJK
bigram 兼容（分词器选择写进 data-model.md 存储节）。

## 3. 验收相关状态（与 orchestration 的接缝）

- 任务行与 CollabPhase 双向映射（`collab/state_transitions.py#L147-159`）；plan 落库自动
  同步主任务 + 子任务行，禁止再批量创建（`collab/supervisor_plan_gate.py#L31-40`）——
  存储侧不冗余建行，靠门拦截。
- **坑**：B-38（Hook 异常 print 吞掉）在存储回调路径同样适用。

### Questor 采纳决定
Questor 的验收状态存储以 gesta 记录为准（事件即真相），看板视图是索引投影。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-46 | gesta | 会话正文不做百表 SQLite 单体（EvoFlow 2191 行 schema、123 张 CREATE TABLE）；Questor 用 append-only JSONL 真相源 + SQLite 仅可重建索引 | `persistence/schema.py`（2191 行/123 表）、`persistence/chat_message_content.py#L1` |
| B-47 | gesta | 事件流要有独立镜像/持久化位（EvoFlow `evoflow_chat_stream_mirror` 表）支撑断线恢复 | `persistence/schema.py#L449,461` |
| B-48 | （M7 mcp/记忆） | FTS5 中文检索用 CJK bigram + OR 引号技巧（unicode61 会把中文连成整串） | `memory/store.py#L557` |
