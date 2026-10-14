# phase0-wuu-sqlite-schema —— wuu 会话存储实测 + Questor SQLite 权威库草案

> 本表原为 Phase 0 前置扫描产物（曾 0 字节空文件，2026-10-14 Phase 1 回填）。
> 实测来源：`wuu@wuu-main internal/session/session.go#L1214-1470`（连接串/PRAGMA/migrateSchema 全部
> CREATE）、`internal/session/inbox.go`（幂等 SQL）、`internal/session/held_user_work.go`（整表替换事务）。
> 每行带 wuu 文件:行号锚，可复核。喂 ADR-0041（会话 SQLite 权威）与 data-model.md。

## 1. 引擎与并发/持久化设置（移植到 Python 必须照搬的硬语义）

| 设置 | 值 | 锚点 | 理由/移植注意 |
| --- | --- | --- | --- |
| 引擎 | SQLite（file: URI） | session.go:1221 | Python 侧用 `sqlite3`/`aiosqlite`；URI 模式开启 |
| `journal_mode` | **WAL** | session.go:1233 | 读写并发；WAL 需同目录 `-wal/-shm`，网络盘/OneDrive 目录有锁风险，装机路径须避 |
| `synchronous` | NORMAL | :1234 | WAL 下安全且快 |
| `busy_timeout` | 5000 ms | :1223, :1235 | 连接串也带 `_pragma=busy_timeout(5000)`；避免多进程"database is locked" |
| `foreign_keys` | ON | :1224, :1236 | 级联删除生效 |
| `auto_vacuum` | INCREMENTAL | :1232 | 配 `PRAGMA incremental_vacuum`（model_input_receipt.go:269）回收 |
| `_txlock` | **immediate** | session.go:1225 | 写事务开始即取锁，避免 deferred 事务读升级死锁——并发写关键 |
| Windows 路径 URI | `C:\…` → `/C:/…` | :1215-1220 | `filepath.ToSlash` + 前导 `/` + `file` scheme；Python 侧 `pathlib().as_uri()` 等价 |

**文件权限**：session.go:1144 注释——SQLite 用数据库文件 mode 派生 WAL 文件权限；questor 侧 atomicFile 的 0600 尽力而为（Windows ACL 差异见 scan-wuu-windows）。

## 2. A 阶段权威表（Questor 会话库必建）

所有会话子表 `FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE`。

### 2.1 `sessions`（会话根，session.go:1249-1274）
`id TEXT PK`、`created_at`/`updated_at TEXT NOT NULL`、`title`/`summary`/`cwd`、`entries INTEGER`、
`forked_from_id`/`forked_from_turn_id`/`forked_from_item_id`（分叉链）、`pinned_at`/`archived_at`（可空时间戳）、
`folder_id`、`worktree_path`/`worktree_base_head`/`worktree_base_repo`（worktree 记录）、
**扩展性缝（§1.7 保留不删）**：`owner`、`visibility`、`parent_id`（将来接多用户/组织/子会话，靠这些列扩）、
`context_source`、`creation_request_id`、`instructions`、`request_context_json`、`tool_policy_json`。
索引：`idx_sessions_cwd(cwd)`、`idx_sessions_updated(updated_at, id)`。

### 2.2 `session_messages`（append-only 真相源，:1284-1328）
PK `(session_id, seq)`；`seq INTEGER`（**每会话稳定地址**，即 ThreadItem.seq）。列含：
`role`、`content`/`display_content`、`origin`/`origin_id`/`cause`/`presentation_kind`/`related_session_id`
（**出处与 role 分离**，P1-5 的持久侧）、`read_only`、`phase`、`provider_item_id`/`provider_item_model`、
`client_id`（**幂等键，与 inbox 关联**）、`hidden`、`steered`、`reasoning_content`/`reasoning_blocks_json`、
`provider_items_json`、`content_parts_json`、`images_json`/`files_json`、`tool_calls_json`/`discovered_tools_json`、
`tool_call_id`/`tool_invocation_id`/`tool_result_kind`/`tool_result_json`、`finish_reason`/`stop_reason`/`truncated`、
`name`、`at`、`input/output/context/cache_creation/cache_read_tokens INTEGER`、`provider`/`model`。
索引：`idx_session_messages_role(session_id, role, seq)`。
**append-only 表达**：主键 `(session_id,seq)` 单调、不改写历史；wuu 未用触发器禁 UPDATE/DELETE，
但 Questor data-model.md 采"表约束 + 触发器禁改写 content"作机械表达（更严，见下移植取舍）。

### 2.3 `session_controls`（会话级控制/接管，:1330-1335）
`session_id TEXT PK`、`manager_id`、`revision INTEGER`（**修订号/接管栅栏**）、`state`。

### 2.4 `session_inbox`（插话收件箱，幂等，:1346-1357）
`client_id TEXT PK`（幂等主键）、`session_id`、`related_session_id`、`cause`、`content`、
`wake INTEGER DEFAULT 1`、`created_at`、`delivered_at`（可空=未送达）。索引 `idx_session_inbox_pending(session_id, delivered_at, created_at)`。
INSERT 实际列更多（`controls_json,work_id,work_revision,work_version`，inbox.go:59）——由 `schemaMigration` 增量 ALTER 加列，
故**建表列 = 基线 + 迁移追加**；移植时按写入方 INSERT 的列集为准，勿只抄 CREATE。
**幂等/送达 SQL（inbox.go）**：
- 入队：`INSERT OR IGNORE INTO session_inbox(...) VALUES(...)`（:59）——同 `client_id` 重复入队天然去重（B-63）。
- settle：`INSERT OR IGNORE ... ON CONFLICT(client_id) DO UPDATE SET delivered_at=excluded.delivered_at`（:78）。
- 送达判据：`UPDATE session_inbox SET delivered_at=? WHERE session_id=? AND delivered_at IS NULL AND EXISTS(SELECT 1 FROM session_messages m WHERE m.session_id=session_inbox.session_id AND m.client_id=session_inbox.client_id)`（:92-93）——**client_id 落入持久历史即视为已送达**（重启可重试不重复注入）。
- 存在检查：`SELECT EXISTS(SELECT 1 FROM session_inbox WHERE client_id=?)`（:158）。

### 2.5 `held_user_work`（未决工作，重启重建，:1379-1389）
PK `(session_id, id)`、`UNIQUE(session_id, position)`、`origin TEXT`（**仅 `queue`/`steer` 两值**，held_user_work.go:11-12/50）、
`message_json`、`runtime_json`。
**整表替换事务**（held_user_work.go:41-58）：一个事务内先 `DELETE FROM held_user_work WHERE session_id=?`，再按 `position` 序逐条 `INSERT`；
校验 id 必填、origin ∈ {queue,steer} 否则报错。→ core 重启后按此表重建未消费的排队/插话输入（B-65）。

### 2.6 历史压缩/恢复侧（A 阶段相关）
- `session_history_retractions`（:1390-1396）：`(session_id, from_seq, through_seq)`——历史撤回区间。
- `session_history_checkpoints`（:1397-1406）：PK `(session_id, version)`、`kind`、`through_seq`、`replacement_json`、`created_at`——压缩检查点。
- `session_compaction_notes`（:1416-1425）：PK `(session_id, provider_key)`、`markdown`、`covered_messages`、`covered_hash`、`updated_at`——替换上下文体。
- `session_model_input_receipts`（:1426-1436）：PK `(session_id, operation_id)`、`contract_version`、`driver_id`/`driver_version`、`receipt_json`——模型输入凭证（审计）。
- `session_driver_checkpoints`（:1407-1415）：`session_id PK`、`contract_version`、`driver_id`/`driver_version`、`state_json`——长跑驱动检查点（Phase 6 长任务面，A 阶段仅留表位）。

## 3. 后置 / 不做表（登记，非遗漏）

| 表 | 锚 | 处置 |
| --- | --- | --- |
| `session_folders`（:1275） | 组织/文件夹 | 后置（B/UI 组织面） |
| `project_work`（:1336）+`project_work_operations`（:1342） | 多-agent 编排 | 不做 A（Phase 6/后加，缝 6） |
| `participants`（:1437）+`participant_runs`（:1451） | subagent/多-agent | 不做 A |
| `plugin_turn_lifecycle`（:1367）+`_outbox`（:1358） | 插件宿主 | 不做 |
| `inference_journal_*`（:1465+） | 跨进程 liveness 租约/remote | 后置（remote/relay） |
| `session_organization`（session_organization.go） | 多用户/组织 | 后置（缝：保留 owner/visibility/parent_id 列即可） |

## 4. Questor A 阶段库草案（对 wuu 的取舍）

**必建（做）**：`sessions`（含 owner/visibility/parent_id 缝列，不删）、`session_messages`（append-only，PK(session_id,seq)）、
`session_controls`（revision 栅栏）、`session_inbox`（client_id 幂等 + delivered_at + EXISTS 判据）、`held_user_work`
（整表替换事务 + origin 二值）、`session_history_checkpoints`/`session_compaction_notes`（compact 用，Phase 3 落）。
**移植加严**：`session_messages` 用触发器禁 `UPDATE/DELETE content`（data-model.md 立场，替代旧"JSONL 文件不可变"）。
**后置**：driver_checkpoints/model_input_receipts 视 Phase 6/审计需求；组织/编排/插件/journal 表随对应 Phase 或不做。
**JSONL 降镜像**（C3）：会话权威是本 SQLite 库，JSONL 仅可选导出（gesta 旧 JSONL 路线随 Phase 3 让位）。

## 5. 移植风险（Python + Windows）
- WAL + busy_timeout + `_txlock=immediate` 必须照搬，否则 sidecar 与工具并发写会 `database is locked`。
- Windows 路径 URI 归一（`/C:/…`）；`file:` URI 的 pragma 参数编码。
- `schemaMigration` 增量 ALTER 加列（非重建），移植需保留"基线 CREATE + 迁移追加列"的双阶段，勿假设 CREATE 即全列。
- 触发器禁改写：Python `sqlite3` 支持 `CREATE TRIGGER ... BEFORE UPDATE OF content ON ... SELECT RAISE(ABORT,...)`。
