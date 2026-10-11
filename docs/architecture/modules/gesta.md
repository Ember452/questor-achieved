# gesta —— 模块设计篇（M2.1 / M2.2 热路径）

状态: 随开工落盘 | 更新: 2026-10-11（M2.2 热路径决策） | provenance: `# Reimplements wuu@wuu-main internal/agentthread/store.go — pitfalls: B-45 B-46 B-74`

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

## 热路径决策（M2.2 前置项，2026-10-11 裁决：增量摘要 + 游标句柄 + 保留全局锁）

**问题**：M2.1 的写路径每次追加做**两次**全量 JSONL 重读（写前定序一次、写后刷索引
一次），且持单把 sessions 目录级跨进程锁——engine 一轮 run 高频 `add_item`/`append_event`
时这是 O(全文件) × 2/次的热路径瓶颈。

**方法（三层，全部不改变对外契约）**：

1. **增量摘要**：写路径去掉第二次全量 load——fold 逻辑抽成可变的 `_FoldState`
   （`apply(record)` 逐条折入），追加后对新记录再 `apply` 一次即可增量构造索引摘要，
   省掉整次重读。模块级函数保持"每调用一次全量 fold"的语义（跨调用正确性优先）。
2. **ThreadWriter 游标句柄**（`gesta/writer.py`，engine 高频追加的入口）：
   `open()` 做**唯一一次**全量 fold，缓存 `(折叠状态, 文件字节数)`；此后每次追加先
   `stat` 校验文件大小——
   - 一致 → 游标权威，直接 O(1) 追加（seq = 游标 + 1）；
   - 变大 → 其他进程追加过，从缓存字节偏移读尾部**增量同步**（append-only 保证
     旧偏移前缀永不变，所以偏移读是安全的）；残尾容忍与全量读同一套 `_parse_line`；
   - 变小 → append-only 被外部破坏，显式抛 `ThreadStoreError`（诚实失败）。
3. **残尾不粘接**：追加前若文件不以 `\n` 结尾（崩溃半行），以 `\n` 前缀起新行——
   残尾留待读侧跳过，追加永不与残尾拼成一行（否则会把残尾和新记录一起毁掉）。

**被否决的方案**：
- *per-thread 锁*：并发度最高，但 `threads.json` 索引跨线程一致性要另设计
  （多把锁下"读全部条目→改一条→写回"不再是原子的），且偏离 wuu 单 store 锁蓝本、
  需重新验证全部对抗场景。M2.2 单用户工作站的争用瓶颈在"同线程高频追加"，
  游标句柄已把它降到 O(1)，全局锁的串行化成本（微秒级临界区）不再是问题。
  留门：锁粒度是边界问题，将来分锁是搬运不是重写。
- *跨进程 seq 租约/心跳*：为"多进程同时高频写同一线程"设计——没有这个真实场景
  （单工作站单核心进程写 + 偶发外部读者），stat 校验已覆盖偶发交叉。

**取消语义**（state.StoreLock.acquire）：支持 per-call `timeout` 覆盖；诚实声明
`asyncio.to_thread` 的协程取消不中断等待线程，上界即超时——engine 对热路径传短超时，
`LockTimeoutError` 上浮为用户可见错误。

## 锁与并发

所有读-改-写持 `state.store_lock(sessions_dir)` 单把锁（wuu 同款）；纯读者不拿锁。
ThreadWriter 的跨进程一致性 = 全局锁（写写互斥）+ stat 校验（游标失守检测）+
增量同步（恢复权威）三件套；句柄不持文件描述符、不是跨进程共享对象。

## 对应测试

unit：`test_gesta_transitions / test_gesta_store / test_gesta_writer / test_schema_bindings`；
adversarial：`test_gesta_tail_tolerance`（B-74）、`test_gesta_concurrent_append`
（三写者跨进程）、`test_gesta_delete_active`（活跃拒删/拒归档）；
integration：`test_gesta_roundtrip`（落盘可回放）；
architecture：`test_gesta_append_only`、`test_status_transition_single_entry`。
writer 专项：`test_gesta_writer`（游标一致性、外部追加重同步、残尾不粘接、
截断爆炸、双句柄交替写）+ `test_state_locks::test_per_call_timeout_override`。
