# ADR-0017 — 上下文工程事实作为 append-only 记录进会话正文

状态: accepted
日期: 2026-10-12 | 关联: M2.3 / `data-model.md` v1.1 → v1.2（§5 存储表）、B-46 B-24 B-25
B-27 B-85、`gesta/store.py`（fold 的 record kind 分支）、ADR-0012

## 结论

压缩与预算替换这两类"上下文工程事实"**作为会话正文的新 record kind 落盘**，不另开文件：

| record kind | 载荷 | 谁写 | 谁读 |
| --- | --- | --- | --- |
| `context.boundary` | 摘要正文、keep 区间的 seq 范围、`before_tokens`、transcript 引用、重注入清单名 | `context/compact.py`（经 `ThreadWriter`） | `context/rehydrate.py`、`notice/compact` 事件的对照 |
| `context.replacements` | `tool_use_id → 替换后的会话内表示`、落盘文件名、裁剪边界（陈旧裁剪的 turn 序号） | `context/tool_results.py` | `context/rehydrate.py`、验收导出 |

配套裁决：

1. **不扩 `ItemKind`**（`message/tool_call/tool_result/citation/annotation/deliverable` 六项不变），
   因此 `schemas/model/v1.json` 的枚举与前端生成类型不变。
2. **对外可见性只走既有事件族** `notice/compact`（protocol.md §4），事件仍是"推送态"，
   真相仍是正文记录——不出现第二套真相。
3. fold 侧新增分支必须与 `ThreadView` 的只读投影字段同批改（`context_boundaries` /
   `replacements`），并把该要求写成坑 **B-85**（新 kind 未同批登记则 replay 静默丢记录）。
4. 这两个 kind 是**追加**语义：压缩不变成改写，被替换的原文仍在正文里（可审计、可回看）。

## 理由与取舍

- **单一真相源**：data-model §5 已定死"会话正文 JSONL 是唯一真相源、索引可丢弃可重建"。
  FlowCoder 把替换状态放在会话目录的 sidecar `replacement_records.jsonl`
  （`context/replacement.py#L28`），正文与 sidecar 会出现"半写"不一致（正文写了 boundary、
  sidecar 没写 replacement），恢复时谁赢没有答案。B-46 的立场正是拒绝这种分家。
- **可验证柱**：验收导出要能回答"这一段摘要是从哪些记录折出来的"。boundary 在正文里，
  审计链才是闭合的；放在 sidecar 就得额外证明 sidecar 没被换过。
- **代价**：`_FoldState.apply` 的 kind 分支变长、fold 测试面扩大；record kind 不在跨进程契约里
  枚举，所以靠 B-85 的机械护栏（fold 分支与投影字段的对齐测试）兜住，而不是靠协议文档。
  护栏已做负向验证：把 kind 从 `_RECORD_KINDS` 抽掉后，两条守卫当场报红且回放射到空列表。

## 被否决的选项

- **sidecar JSONL（照 FlowCoder）**：与正文形成两个写入点、两套真相，崩溃恢复顺序无定义（违 B-46）。
- **扩 `ItemKind`（如 `compact_boundary`）**：Item 是"对外可审计的最小工作单元"，压缩边界是内核
  的上下文工程事实；扩枚举会连带 v1.json、前端生成类型、Review/trace 渲染一起改，属把内部
  实现细节推到契约面上（overview §14"留门只落在边界"的反面）。
- **只存内存、压缩不落盘**：跨 turn resume 与崩溃恢复无法重建压缩后状态，M2.3 出口判据
  （"压缩后 resume 可恢复"）直接落空。
- **把摘要写成一条新的 user message Item**：会造成"用户说过这段话"的假象，违反 AGENTS 铁律 1
  （诚实呈现）与 append-only 的语义（历史里凭空多出用户消息）。

## 适用条件与失效条件

**适用**：M2.3 起 `context` 的全部落盘需求；后续 `memory`/`skills` 的上下文事实沿用同一判据
（正文记录优先于 sidecar）。
**触发重新评审**：① 出现"压缩边界需要被外部引擎（M6 adapter）直接消费"的真实需求 →
届时按契约升版流程讨论是否进入跨进程形状；② record kind 数量增长使 fold 分支难以维护 →
抽声明式 kind 注册表（须先有第二个同类模块）。
