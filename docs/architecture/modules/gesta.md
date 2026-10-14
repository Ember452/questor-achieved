# gesta —— 模块设计篇（Phase 2a 已移植：SQLite 会话权威库）

状态: 新库已落地（2026-10-14，Phase 2a 批次 1）；旧 JSONL 路径仍在工作树内、随 serve 重写同批移出
provenance: `# Ported from wuu@2026.10.6 internal/session/{session.go,inbox.go,held_user_work.go}`
行为规格: `docs/specs/behavior-gesta-wuu.md`（蓝本已从 `internal/agentthread` 改指 `internal/session`）
契约: `docs/architecture/data-model.md` v2.0（**SQLite 为会话权威库**，ADR-0041）

## 职责与边界

会话真相的**唯一**存放地：谁在跑、说过什么、插过什么话、崩在哪。它不参与"接下来做什么"
的判断（那是 `engine`），也不决定"能不能做"（那是 `limen`），只保证**发生过的事不会变形**。

三柱归属：**可验证**的地基（声称能指回记录）＋**可干预**的地基（inbox 与 held_user_work
让运行中的插话与排队输入在重启后不丢、不重）。

不做的事（划界，防"顺手也存一份"）：

- 不存工作区盘态真相 → Review 的 `git diff` 归壳侧 GitService（ADR-0045）。
- 不存权限判定结果之外的"信任状态" → 门在 `limen`，这里只落 `session_controls` 的接管栅栏事实。
- 不做搜索大盘/FTS/多用户作用域 → 组织、编排、租约类表随对应 Phase 或不做（port-ledger 登记）。

## 文件与各自的一条主线

| 文件 | 只管这件事 | 母本锚点 |
| --- | --- | --- |
| `schema.py` | 连接、PRAGMA、建表、增量迁移、`BEGIN IMMEDIATE` 写事务 | `session.go::sqliteDSN/configureDB/migrateSchema/addColumnIfMissing` |
| `session_store.py` | 会话行与历史行的读写、控制面 revision | `session.go::insertSessionTx/appendHistoryRecordTx` |
| `inbox.py` | 待投递输入的幂等入队、送达判定、控制复判 | `inbox.go::insertInbox/PendingInbox/validateInboxControls` |
| `held_work.py` | 未决输入的整表替换与序号压缩 | `held_user_work.go::ReplaceHeldUserWork/DeleteHeldUserWork` |
| `records.py` | 行 ↔ 对象映射（正文仍用 `schemas/message.py`） | `session_messages` 列集 + `providers/types.go` 的 Origin≠Role |
| `errors.py` | 存储层错误族（业务拒绝 vs 库坏了分得开） | `ErrSessionNotFound`/`ErrControlChanged` |

## 落盘形状

- 表：`sessions`、`session_messages`、`session_controls`、`session_inbox`、`held_user_work`、
  `session_history_{retractions,checkpoints}`、`session_compaction_notes`。刻意不建
  不做/后置表（`participants`、`project_work`、`plugin_*`、`inference_journal_*`）。
- PRAGMA 照母本：WAL、`synchronous=NORMAL`、`busy_timeout=5000`、`foreign_keys=ON`、
  `auto_vacuum=INCREMENTAL`；Go 侧 `_txlock=immediate` 的 Python 等价物是
  `isolation_level=None` + `write_txn()` 显式 `BEGIN IMMEDIATE`。
- `session_messages` 主键 `(session_id, seq)`：**seq 由 store 在追加事务内**
  `COALESCE(MAX(seq),0)+1` 分配，调用方自带号直接吃 `SequenceRejected`（B-45 单点分配）。
- 正文权威载体是 `content_parts_json`（一个 `ChatMessage.parts` 的 JSON 数组）；
  `content`/`display_content`/`tool_calls_json` 是**投影**，供搜索与人读。读回只有一条
  重建路径，避免"投影各算各的"（B-85 同型）。`input_text`/`display_content` 只在
  投影与 parts 拼接不一致时才还原成非 None（同一段文本不留两份真相）。
- append-only 的机械表达：两个触发器——禁改写 `content/display_content/seq/role/session_id`；
  禁在**所属会话仍存在时**删单行。会话级联删除放行（`thread/delete` 是 protocol.md §3 在册方法），
  靠 `WHEN EXISTS(SELECT 1 FROM sessions WHERE id=OLD.session_id)` 区分这两件事。
- 边界字段照母本保留、不删也不建机制：`sessions.owner/visibility/parent_id`（§1.7 多租户留缝）。

## 并发与锁（三层，顺序只在一处定义）

1. **写线程串行**：每个 `SessionStore` 自带一个写线程 + 任务队列。这不是投机抽象——
   `sqlite3` 连接**不得跨线程使用**（本仓实测 `ProgrammingError`），而 engine 会经
   `asyncio.to_thread` 从多个工作线程写同一库（对应 wuu 的 `storeWriteMu` 那一层）。
2. **多进程互斥**：写线程每笔事务持一次 `state.locks.StoreLock`（`.store.lock`，
   Windows `LockFileEx` / POSIX `flock`，释放不删文件，B-71）。
3. **库内**：`BEGIN IMMEDIATE` 进入即取写锁，避开 deferred 读升级死的经典形态。

读者走**线程局部连接**，不进写队列也不拿锁（WAL 允许读者与写者并存）——
否则"读一段历史"能把写堵住。

取消语义沿用 `StoreLock` 的诚实声明：同步阻塞原语，协程取消不打断等待线程，
上界就是超时；需要快断的调用方传短超时并把 `LockTimeoutError` 上浮成用户可见错误。

## inbox 与 held_work 的关键取舍

- **送达判据是"client_id 已落入持久历史"**，不是入队时间（B-127）。负向已实测：
  改成"入队即写 `delivered_at`"，两条用例当场红。
- 控制栅栏复判发生在**消费时**（B-129）：A 阶段只落 `session_controls` 那一半
  （manager/revision/state 全等才放行），`project_work` 分支属不做的编排面。
- `held_user_work` 整表替换是一个事务；校验前置到写入之前（可观测结果与母本一致，
  少一次无谓 DELETE）。删除后的序号压缩照搬母本"先取负再归正"两段 UPDATE；
  **诚实标注**：本机把这段换成朴素 `position-1` 测不出红（SQLite 不保证 UPDATE 扫描序，
  常见计划按升序先释放低位），所以它是母本防御性写法，不是本仓已观测故障（B-128 按此登记）。
- 迁移的并发容忍：`ADD COLUMN` 撞 `duplicate column name` 当成功（B-125），
  且列集"基线 CREATE + 追加"两段都在（B-126——本仓实现过程中真的以
  `KeyError: 'delivered_at'` 撞过一次，读写列集已拆开）。

## 旧 JSONL 世界（过渡期，随 serve 重写同批移出）

`store.py` / `writer.py` / `transitions.py` 仍是旧 engine/serve/cli/habena 的依赖，
本轮**没有**强行拆走——一次性搬空会造出断 import 红潮，逼出"改测试迁就删除"的倒挂
（延迟清理策略，母计划 §12-B）。它们的立场（JSONL 唯一真相源 + 可重建索引）与本篇
的 SQLite 权威**是新旧两个世界的并存，不是同一系统两套真相**；Phase 2a 批次 5 重写 serve
时随旧 `serve/` 一同物理移出，旧实现留下的已验证知识（B-45 定序、B-74 残尾容忍、
写者游标的失效检测思路）由本篇与新测试承接。

## 对应测试

新增（Phase 2a 批次 1，共 41 条）：

- `tests/unit/test_gesta_sqlite_schema.py`：PRAGMA 取值、必建表齐且**不建**后置表、
  写入列集满足（B-126）、边界列在、append-only 触发器（负向已实测）、级联删除、
  迁移幂等与竞态容忍（B-125，负向已实测）。
- `tests/unit/test_gesta_session_store.py`：seq 单点分配与自带号被拒、4 线程并发不重号不断号、
  消息逐字段无损回读、Origin≠Role、投影列派生性、revision 单点递增与值域。
- `tests/unit/test_gesta_inbox.py`：前置校验、B-63 幂等、B-127 送达判据与重启不重投、
  创建序、settle、targets、wake/cause 持久、B-129 消费时复判。
- `tests/unit/test_gesta_held_work.py`：整表替换与位序、origin 两值域、必填校验、
  失败即整体不改、B-128 压缩后连续无空洞、按会话隔离、重启重建。
- `tests/adversarial/test_gesta_concurrent_write.py`：两个 store 共写一库不丢不重、
  锁竞争超时与"释放不删文件"（B-71）、送达判定不回弹。

旧 JSONL 侧测试（`test_gesta_store` / `test_gesta_writer` / `test_gesta_tail_tolerance` /
`test_gesta_concurrent_append` / `test_gesta_roundtrip` / `test_gesta_append_only` 等）
仍绿，随批次 5 的旧实现一并处置。
