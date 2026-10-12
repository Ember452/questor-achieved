# ADR-0025 — 编排域：Task/Plan/Goal 实体、状态机与独立 append-only store

状态: accepted
日期: 2026-10-12 | 关联: `docs/plans/development-plan.md` M4、`docs/specs/behavior-orchestration-ef.md`、
`docs/architecture/data-model.md` v1.3、`docs/architecture/overview.md` §6 §7 §12、`B-38` `B-39` `B-43`

## 结论

`orchestration` 是**独立的有界上下文**：Task / Plan / Goal 三种实体、任务状态机、以及编排门，
全部住在 `src/questor/orchestration/`；其持久化自持一套 **append-only JSONL**
（`<home>/orchestration/tasks.jsonl` + 可重建索引），**不写进线程会话正文**。
任务状态机单独成模块 `orchestration/transitions.py`，形态与 `gesta/transitions.py` 同构
（声明式白名单表 + 单点 `transition()` + 未知状态 fail closed），由新守卫
`tests/architecture/test_orchestration_transition_single_entry.py` 保证"只有 orchestration 能 import 它"。
编排门（gate）返回**结构化错误载荷**（`error_code` / `message` / `hint`），不抛异常、不用中间件注入。

## 理由与取舍

- **单一职责**：`gesta` 的职责是"会话记录与验收导出"（`overview.md` §6），把 Task/Plan/Goal 塞进
  线程 JSONL，会让会话格式被编排域的反向需求牵着走——看板要跨线程聚合、Goal 要跨轮长跑、
  将来多 Agent 要任务树，这些都不是"一次对话"的形状。
- **扩展代价是搬运而非重写**：独立 store 的形态直接搬 `gesta/store.py` 的成熟范式
  （残尾容忍 B-74、temp+rename、`state` 原子写与跨进程锁），因此重复的是**已验证的边界策略**，
  不是重新发明。加状态/加记录 kind 的成本落在一张表上。
- **状态机声明式**：加状态是"改数据"而不是"改分支"；`REVIEWED → EXECUTING（打回重做）`
  正是 M4 出口链"打回→重做"的一环，与 `overview.md` §7 验收状态机在编排侧对应。
- **结构化错误 vs 异常**：沿用 `B-43`——门返回载荷，模型可读、可重试；异常会变成"静默失败"
  或"整个 run 失败"，而编排门的语义是"这一步先别做，去做前置动作"。

## 被否决的选项

- **挂进 gesta 的编排记录 kind**：与线程生命周期耦合，看板跨线程查询要在 fold 全量线程正文上做，
  且新 kind 会污染会话格式；仅作为"独立 store 维护成本超预期"时的备选（见失效条件）。
- **用 SQLite 存编排实体**：`overview.md` §7 已定"SQLite 只作可丢弃可重建的索引，不承载真相源"；
  编排状态若进 SQLite 就会变成第二真相源。
- **状态机与 `Run` 状态机合并成一个**：`Run` 是"一次引擎执行"（queued→running→终态），
  任务是"一个编排单元"（含规划、待审、打回），两者生命周期不同，合并会造出一张谁都读不懂的迁移表。
- **模型侧编排动作走 limen**：limen 是**写域权限门**（磁盘/进程边界），编排门是**领域门**
  （先有计划、先有授权）；`behavior-orchestration-ef.md` §2 明确两者在 EvoFlow 里也是分开的两层。

## 适用条件与失效条件

- **前提**：编排实体与线程解耦；本机单用户、无鉴权（`principal` 仅传递）。
- **失效信号**：① 独立 store 的重复维护成本超过收益（两套 append-only 机制持续漂移）→ 退化为此
  ADR 的被否决选项一（挂 gesta 记录 kind），须新 ADR 记录；② 编排门出现跨进程/跨用户语义 →
  须重新评审（当前门是进程内的确定性判定）。
