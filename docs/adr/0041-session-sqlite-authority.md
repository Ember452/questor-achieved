# ADR-0041 — 会话存储权威源 = SQLite 库（改判 JSONL 唯一真相源）

状态: accepted
日期: 2026-10-14 | 关联: 取代 ADR-0013/0017/0025 中"SQLite 仅可丢弃索引"结论、`data-model.md` §5、B-46、`docs/research/phase0-wuu-sqlite-schema.md`

## 结论

照 wuu：**SQLite 为会话权威库**——`sessions`、`session_messages`、`session_controls`、`session_inbox`、`held_user_work`、`session_history_{retractions,checkpoints}`、`session_driver_checkpoints`、`session_compaction_notes`、`inference_journal_runtimes`（表清单见 `phase0-wuu-sqlite-schema.md`）。**JSONL 降为可选导出镜像**。append-only"不可改写历史"用 `(session_id, seq)` 主键 + 触发器禁 UPDATE/DELETE 表达，不再靠"文件不可变"承载。

## 理由与取舍

- wuu 的 **inbox 幂等（client_id）、held_user_work 整表事务、崩溃恢复、租约锁**全长在 SQLite；硬拆成"JSONL 真相 + SQLite 索引"会丢掉母本验证过的并发正确性，正是"造轮子的坑"。
- 纯 Go 驱动 `modernc.org/sqlite` → Python `sqlite3` 可 1:1 移植 schema/事务/自定义函数（`create_function` 替代 `wuu_history_content`）。
- 取舍：放弃"文件级不可改写"作为审计的第一表达，改由表约束 + 导出镜像兜。

## 被否决的选项

- **JSONL 唯一真相源 + SQLite 仅索引**：即被本次转向推翻的旧立场（现 data-model §5）。
- **百表 SQLite 单体**：EvoFlow 反面（B-46），只建 10 张核心表，不铺 123 表。

## 适用条件与失效条件

**适用**：单用户本地、桌面单库。**触发重评审**：若出现"必须文件级不可改写"的硬合规要求 → 增加 JSONL 双写镜像作为不可变副本（不改权威源结论）。
