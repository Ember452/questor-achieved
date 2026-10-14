# behavior-gesta-wuu —— wuu 会话存储行为规格（Questor `gesta` 蓝本）

来源：wuu `internal/session/{session.go,inbox.go,held_user_work.go}` + `internal/storelock/*`。
扫描日期 2026-10-14（Phase 2a 开工前置扫描），行号当日以 `Read` 核实到函数本体。
Questor 模块归属：`gesta`（会话权威库）、`state`（路径/锁/原子写，保留侧）。
契约约束见 `docs/architecture/data-model.md` v2.0（**SQLite 为会话权威库**，ADR-0041）与
`docs/adr/0041-session-sqlite-authority.md`。

> **本文件的旧版本已被推翻**：旧版蓝本是 wuu `internal/agentthread/store.go`（JSONL + threads.json
> 索引），而 `agentthread` 是**多-agent 线程图**、属"不做"清单（`scan-wuu-kernel` §8），且
> "JSONL 唯一真相源"的立场已由 ADR-0041 改判。会话真相在 wuu 里集中在 `internal/session`；
> `gesta` 这个模块名与 wuu 的 `agentthread` 无对应关系（旧 provenance 注记一并作废）。

---

## 1. 连接与持久化设置（库打开即定，不容 per-call 漂移）

- **输入**：会话库文件路径（Questor：`state.paths` 解析出的 sessions 库）。
- **输出**：可用的连接/引擎句柄，PRAGMA 全部生效。
- **边界行为**：
  - DSN 带 `_pragma=busy_timeout(5000)`、`_pragma=foreign_keys(1)`、`_txlock=immediate`
    （`internal/session/session.go::sqliteDSN` L1214-1228）——**写事务开始即取锁**，
    避免 deferred 事务"读升级写"死锁；`busy_timeout` 挡多进程 `database is locked`。
  - 连接后再设一遍：`auto_vacuum=INCREMENTAL`、`journal_mode=WAL`、`synchronous=NORMAL`、
    `busy_timeout=5000`、`foreign_keys=ON`（`configureDB` L1230-1244）。
  - Windows 路径必须先归一成 `/C:/...` 再拼 `file:` URI（L1215-1221 注释明写）。
- **证据**：`internal/session/session.go::sqliteDSN#L1214-1228`、`::configureDB#L1230-1244`。
- **坑**：无新增（WAL/busy_timeout 属既有性能与并发前提）。

### Questor 采纳决定
沿用全部取值。Python 侧用标准库 `sqlite3`（**不引 aiosqlite**，新依赖需 ADR）：
URI 由 `pathlib.Path.as_uri()` 生成后追加 pragma 查询串；`isolation_level=None` +
显式 `BEGIN IMMEDIATE` 复刻 `_txlock=immediate`；写路径走**专用写线程 + 队列串行化**
（asyncio 事件循环内禁止阻塞 IO，AGENTS §四；B-90 同源纪律），只读连接各自独立、
禁用 `check_same_thread=False` 共享连接。

## 2. 建表与增量迁移（基线 CREATE + 追加列，两阶段都要抄）

- **输入**：已打开的库。
- **输出**：`sessions` / `session_messages` / `session_controls` / `session_inbox` /
  `held_user_work` / `session_history_{retractions,checkpoints}` / `session_compaction_notes` /
  `session_model_input_receipts` / `session_driver_checkpoints` 就位，列集合＝基线 + 迁移追加。
- **边界行为**：
  - 会话子表一律 `FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE`
    （`migrateSchema` L1246-1436）。
  - **`session_inbox` 的 CREATE 只有 8 列**；`controls_json/work_id/work_revision/work_version`
    由迁移追加（L2005-2018）。照抄 CREATE 会写出 `no such column` 的 SQL——
    **建表列集必须以写入方 INSERT 的列集为准**（`insertInbox` L59 写 11 列）。
  - 加列前先 `PRAGMA table_info(table)` 查存在（`schemaMigration::addColumnIfMissing` L2058-2076）；
    已存在即跳过。
  - **并发迁移容忍**：注释原文"Multiple workspace app-servers share one sessions DB and
    migrate concurrently; treat a racing ADD as success when the column landed"——
    `ALTER TABLE ... ADD COLUMN` 报 `duplicate column name` 时**必须当成功**（L2067-2073）。
  - schema 检查只在**一次迁移内**共享缓存；每次开库重新读 schema，以覆盖"外部恢复/
    另一进程已迁移"的情形（L2022-2024 注释）。
- **证据**：`internal/session/session.go::migrateSchema#L1246-1436`、
  `::schemaMigration.addColumnIfMissing#L2058-2076`、`::migrateSchema 追加段#L2005-2018`。
- **坑**：**B-125**（并发 ADD COLUMN 竞态）、**B-126**（基线 CREATE ≠ 全列，须按写入列集建）。

### Questor 采纳决定
沿用两阶段（基线 DDL + `ensure_column` 迁移），并沿用"竞态 ADD 视为成功"的容忍。
Questor 额外**加严**（`data-model.md` §4 立场）：`session_messages` 用**触发器**禁
`UPDATE`/`DELETE` content，把 append-only 从"约定"升级为机械保证（旧 JSONL 路线靠
AST 禁 truncating 模式表达，现在靠库内触发器）。

## 3. 历史追加与 seq 单点分配（append-only 的写路径）

- **输入**：会话 id + 一条 `HistoryRecord`（role/content/tool_calls/usage/…）。
- **输出**：返回分配到的 `seq`——**该记录在会话内的稳定地址**。
- **边界行为**：
  - seq 在**追加事务内**分配：`SELECT COALESCE(MAX(seq),0)+1 FROM session_messages WHERE session_id=?`
    （`appendHistoryRecordTx` L2305-2309）。调用方不得自带 seq，也不得在事务外算。
  - PK 是 `(session_id, seq)`；索引 `idx_session_messages_role(session_id, role, seq)`（L1326-1329）。
  - 列集里 **`origin`/`origin_id`/`cause`/`related_session_id` 与 `role` 分离**（L1290-1294）：
    provider 角色与产品出处是两件事（Phase 1 契约 P1-5 的持久侧）。
  - `client_id` 列（L1299）是 inbox 幂等判据的落点——历史里带 client_id，inbox 才能判定"已送达"。
  - 用量列（`input/output/context/cache_creation/cache_read_tokens`，L1319-1323）随记录落库，
    供 `turn/usage` 与 compact 阈值复核。
- **证据**：`internal/session/session.go::appendHistoryRecordTx#L2305-2309`、
  `migrateSchema` 的 `session_messages` CREATE#L1284-1329。
- **坑**：B-45（gate/审批类消息先持久化定序，用户跟进行才能排后）沿用；seq 单点分配是其实现前提。

### Questor 采纳决定
沿用。`SessionStore.append_message()` 必须在同一事务内取号，且写路径全程经"单写线程 +
`BEGIN IMMEDIATE`"；`content` 改写由触发器拒绝（负向验证：`UPDATE session_messages SET content=…`
必须抛库错）。

## 4. inbox 幂等投递与"送达"判据（可干预柱的地基）

- **输入**：`InboxMessage{ClientID, SessionID, Content, Wake, Controls, WorkID/Revision/Version, …}`。
- **输出**：入队成功；或重复 `client_id` 时**静默 no-op**。
- **边界行为**：
  - 入队：`INSERT OR IGNORE INTO session_inbox(...) VALUES(...)`（`insertInbox` L59-60）——
    同 client_id 重复入队天然去重（B-63）。
  - 前置校验：client_id 或 session_id 去空后为空 → 直接报错（L49-51），不静默吞。
  - **送达判据不是"入队即已投"**：`UPDATE session_inbox SET delivered_at=? WHERE session_id=?
    AND delivered_at IS NULL AND EXISTS(SELECT 1 FROM session_messages m WHERE
    m.session_id=session_inbox.session_id AND m.client_id=session_inbox.client_id)`
    （`PendingInbox` L92-94）——**client_id 出现在目标持久历史**才算送达；
    所以崩溃/重启后重试投递不会重复注入同一条用户输入。
  - 取未决：`WHERE session_id=? AND delivered_at IS NULL ORDER BY created_at, rowid`（L99-100）
    ——**创建序**消费，`rowid` 作同时间戳的定序兜底。
  - `SettleInbox`（L66-81）：只记"已处理"而不投递内容，用 `ON CONFLICT(client_id) DO UPDATE
    SET delivered_at=excluded.delivered_at`——让后续重试变 no-op。
  - `InboxHas`/`InboxTargets` 在表不存在时**先探测再查**（`storeTableExists`，L128/L154），
    不因老库无表而炸。
  - 控制栅栏 `validateInboxControls`（L175-235）：消费前在**历史追加事务内**复核
    `session_controls` 的 `manager_id/revision/state==active`，不符即 `ErrControlChanged`；
    注释原文"a sender can be stopped while a prompt hook runs after the earlier admission check"
    ——**准入检查与消费之间会漂移，必须在消费时复判**。
- **证据**：`internal/session/inbox.go::insertInbox#L46-62`、`::SettleInbox#L64-81`、
  `::PendingInbox#L83-119`、`::validateInboxControls#L173-235`。
- **坑**：B-63 沿用；**B-127**（送达判据必须是"client_id 已落入持久历史"，否则重启重复注入）。

### Questor 采纳决定
沿用全部五条。控制栅栏（`Controls`/`project_work`）在 A 阶段只保留 **`session_controls`
的 revision/manager/state 复判**这一半（接管仲裁属 Phase 3 的 `activity`，`project_work`
属不做的编排面），但"消费时复判而非准入时判定一次"这条纪律现在就落，避免 Phase 3 重写。

## 5. held_user_work 整表替换与 position 压缩（queue/steer 的重启重建）

- **输入**：`ReplaceHeldUserWork(sessDir, sessionID, entries)`，entries 有序。
- **输出**：该会话的未决输入整表替换；`LoadHeldUserWork` 按 position 序返回。
- **边界行为**：
  - 单事务：`DELETE FROM held_user_work WHERE session_id=?` → 按枚举序逐条 `INSERT`（L41-61）。
  - 校验：`id` 必填、`origin ∈ {queue, steer}` 二值否则报错、`message_json` 与 `runtime_json`
    均非空（L45-55）——**"origin 只有两值"是协议形状**（`turn/steer|queue` 族对应侧）。
  - position 由**枚举下标**决定（调用方给 order，不给 position）。
  - 单条删除后的压缩（`DeleteHeldUserWork` L138-147）：**先 `SET position = -position - 1`
    把后移者取负，再 `SET position = -position - 2` 归正**——注释原文"Negate first so the
    UNIQUE(session_id, position) constraint cannot collide while adjacent positions shift
    down by one"。直接 `position = position - 1` 在 SQLite 不保证 UPDATE 扫描序的前提下
    可能撞上还占着的低位。
  - **本仓实测注（避免误传）**：负向注入成朴素 `position - 1` 后，本机测试**不红**——
    常见执行计划按升序逐行处理，低位恰好先被释放。所以本条是**母本的防御性写法照搬**，
    不得写成"本仓已观测到该故障"（B-128 已按此口径登记）。
  - PK `(session_id, id)` + `UNIQUE(session_id, position)`（L1386-1387）。
- **证据**：`internal/session/held_user_work.go::ReplaceHeldUserWork#L24-66`、
  `::DeleteHeldUserWork#L105-152`、`migrateSchema` CREATE#L1379-1389。
- **坑**：B-65 沿用（双 origin + 整表替换事务 + 重启重建）；**B-128**（position 压缩必须
  先取负再归正，否则撞 UNIQUE）。

### Questor 采纳决定
沿用，含两步取负压缩写法。Python 侧同一事务内完成，失败整体回滚（不留半替换）。

## 6. 跨进程写锁与 Windows 语义（长驻 sidecar + CLI 并发）

- **输入**：store 目录。
- **输出**：拿到独占锁的临界区句柄。
- **边界行为**：
  - 锁文件**释放后不删除**（`internal/storelock/store_lock.go#L33-35`，B-71：删-建会让并发
    进程锁到不同 inode，互斥失效）。
  - Windows 用 `LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK|LOCKFILE_FAIL_IMMEDIATELY, …)`，
    命中 `ERROR_LOCK_VIOLATION` **翻译成"锁被持有"这一确定错误**，而非笼统失败
    （`store_lock_windows.go::tryLockFile` L12-25）；释放走 `UnlockFileEx`（L27-29）。
  - 进程内还有一层 `storeWriteMu`（`sync.Mutex`）：先进程内串行，再拿跨进程锁
    （`EnqueueInbox`/`ReplaceHeldUserWork` 等写路径可见）。
- **证据**：`internal/storelock/store_lock_windows.go#L12-29`、
  `internal/storelock/store_lock.go#L33-35`、`internal/session/inbox.go::EnqueueInbox#L34-43`。
- **坑**：B-71 沿用。

### Questor 采纳决定
沿用两层锁次序；实现直接复用保留侧的 `questor.state.locks.StoreLock`（Windows 非阻塞独占
+ 释放不删文件已落），**不新建第二套锁实现**（AGENTS §三 单一来源；差异若存在须登 port-ledger）。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-45 | gesta | gate/审批类消息必须先持久化定序，用户的跟进行才能排在后面 | wuu `internal/session/session.go::appendHistoryRecordTx#L2305-2309` |
| B-63 | gesta | 插话 client_id 幂等：同 client_id 提交两次只入队一次 | wuu `internal/session/inbox.go::insertInbox#L59` |
| B-65 | gesta | held_user_work 双 origin（queue/steer）落盘，整表替换事务，重启重建 | wuu `internal/session/held_user_work.go#L11-12,L41-61` |
| B-71 | gesta | 锁文件释放后禁止删除——删除-重建会让并发进程锁到不同 inode | wuu `internal/storelock/store_lock.go#L33-35` |
| B-125 | gesta | 多宿主并发迁移时 `ADD COLUMN` 竞态必须把 `duplicate column name` 当成功，否则两个 sidecar/CLI 同开即启动失败 | wuu `internal/session/session.go::addColumnIfMissing#L2067-2073` |
| B-126 | gesta | 照抄 CREATE 语句会漏掉迁移追加列（`session_inbox` CREATE 8 列、INSERT 写 11 列），SQL 运行期才炸——列集必须以写入方为准 | wuu `internal/session/session.go#L1346-1357` 与 `::insertInbox#L59` |
| B-127 | gesta | inbox 送达判据若写成"入队即已投"，崩溃/重启会把同一条用户输入重复注入历史 | wuu `internal/session/inbox.go::PendingInbox#L92-94` |
| B-128 | gesta | held_work 压缩 position 的两段取负写法是母本防御性语义（SQLite 不保证 UPDATE 扫描序）；照搬但不得声称本仓已观测到朴素写法的冲突 | wuu `internal/session/held_user_work.go#L138-147` |
| B-129 | gesta | 准入检查与消费之间控制态会被接管改写，复判必须发生在消费事务内而非入队时一次判定 | wuu `internal/session/inbox.go::validateInboxControls#L173-235` |
