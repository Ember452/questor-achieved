# gesta —— 模块设计篇（M2.1）

状态: 随开工落盘 | 2026-10-11 | provenance: `# Reimplements wuu@wuu-main internal/agentthread/store.go — pitfalls: B-45 B-46 B-74`

## 职责与边界

会话记录落盘与回放：append-only JSONL 唯一真相源（`<sessions>/<thread_id>.jsonl`）、
记录流 fold 出当前状态、可丢弃可重建的 JSON 摘要索引、工具结果 O_EXCL 落盘 + 2KB 预览。
契约源头是 `data-model.md` v1.1；本篇只记存储决策。

## 落盘形状

- 行 = `_Record` 信封 `{seq, kind, payload, recorded_at}`；seq 会话内全局递增
  （Event.seq 同源，断线恢复锚点），turn 序号单独计数——**两者都由 store 在锁内分配，
  调用方不可指定**（B-45：先持久化定序）。
- kind 八种：thread.created/renamed/flagged、turn.created、run.created、run.status、
  item.appended、event.appended；fold 时 `run.status` 仍过 transitions 白名单——
  篡改的历史在回放时爆炸而不是被静默接受。
- 读侧容忍：空行与解析失败行跳过（B-74）；追加永远 O_APPEND 整行（架构测试
  `test_gesta_append_only` 机械保证 gesta 全包无截断写模式）。
- 索引 `sessions/threads.json`：temp+rename 原子替换的摘要缓存，损坏即重建不修复；
  SQLite 搜索索引按 B-46 属 M4（偏离已在 development-plan 留痕）。

## 锁与并发

所有读-改-写持 `state.store_lock(sessions_dir)` 单把锁（wuu 同款）；纯读者不拿锁。
M2.1 体量下够用，锁粒度留门：将来按线程分锁只是边界搬运。

## 对应测试

unit：`test_gesta_transitions / test_gesta_store / test_schema_bindings`；
adversarial：`test_gesta_tail_tolerance`（B-74）、`test_gesta_concurrent_append`
（三写者跨进程）、`test_gesta_delete_active`（活跃拒删/拒归档）；
integration：`test_gesta_roundtrip`（落盘可回放）；
architecture：`test_gesta_append_only`、`test_status_transition_single_entry`。
