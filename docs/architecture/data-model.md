# Questor 核心数据契约（data-model）

版本: v1.0 | 更新: 2026-10-11 | 状态: accepted（M1 定稿）
关联: `overview.md` §7（草案出处）、`protocol.md`（跨进程边界）、`docs/specs/`（行为规格）、
`src/questor/schemas/model/`（本契约的 JSON Schema 物化）

**本文件是数据模型的唯一真相源**。改动必须先改本文并递增版本号，代码与 schema 跟随。
schema 为纯 JSON Schema（Python pydantic 只做绑定，前端类型由生成而来，禁止手写 DTO）。

---

## 1. 通用约定

- 所有 id 为小写字母数字与连字符（`^[a-z0-9][a-z0-9-]*$`），由服务端生成；
- 时间戳一律 UTC ISO-8601 字符串（`2026-10-11T08:30:00Z`）；
- 所有实体带 `created_at`；可变实体带 `updated_at`；
- 枚举值用小写字符串；跨进程字段命名 snake_case；
- 会话正文 append-only：**任何字段一旦写入不得改写**，修订只追加新记录
  （需求改版 = 新修订，验收作废 = 追加作废记录）。

## 2. 实体与层级

```
Workspace (1) ──< Thread (N) ──< Turn (N) ──< Run (N) ──< Item (N)
                                    │
                                    └──< Event（对外推送，只追加）
```

### Workspace

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 工作区 id |
| `name` | string | 显示名 |
| `root_paths` | string[] | 注册根路径集合（可达性推导的输入，`limen` 消费） |
| `revision` | integer | 工作区修订号（§4），单调递增 |
| `created_at` | string | |

### Thread

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | |
| `workspace_id` | string | |
| `title` | string? | 可重命名 |
| `pinned` / `archived` | bool | 归档运行中拒绝（wuu 语义） |
| `engine_id` | string | 创建时绑定，**不静默切换**（未知引擎显式报错） |
| `permission_mode` | string | `read_only` / `standard` / `unconfined`；来自用户配置，仓库配置不可设定（B-58） |
| `created_at` / `updated_at` | string | |

### Turn

一次用户输入触发的完整交互单元。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | |
| `thread_id` | string | |
| `seq` | integer | 会话内序号（gate 消息先持久化定序，B-45） |
| `origin` | string | `user` / `steer`（steered 消息挂原 turn，不新开） |
| `fork_from` | object? | `{thread_id, turn_seq, mode: local\|worktree}`（分叉溯源） |

### Run

一次引擎执行。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | |
| `turn_id` | string | |
| `engine_id` | string | 冗余记录执行引擎 |
| `permission_mode` | string | 执行时快照 |
| `workspace_revision_start` / `_end` | integer? | 修订号绑定（§4） |
| `status` | string | 状态机见 §3 |
| `usage` | object? | `{input_tokens, output_tokens, cost_usd?}` 累计 |

### Item

Run 产出的最小可审计单元。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | |
| `run_id` | string | |
| `kind` | string | `message` / `tool_call` / `tool_result` / `citation` / `annotation` / `deliverable` |
| `payload` | object | 按 kind 定义；tool_result 含**写时刻 diff**（B-66） |
| `evidence` | object? | 可验证柱：声称的检查与当时录得输出的绑定 |

### Event

对外推送（SSE/WS/NDJSON 通知的统一形状），只追加不可改写。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `seq` | integer | 会话内全局递增（重连续传锚点） |
| `type` | string | 见 protocol.md §4 事件族 |
| `run_id` / `turn_id` | string | 归属 |
| `payload` | object | |
| `created_at` | string | |

## 3. 状态机

### 3.1 运行状态机

```
queued → running → completed | failed | cancelled
             │
             ├── steered（旁态：插话在下一个工具边界被消费后回 running）
             └── waiting（旁态：等插话/审批；恢复后回 running）
```

- 终态仅 `completed | failed | cancelled`；`steered` / `waiting` 是 `running` 的**旁态**，
  旁态间迁移必须经由 running；
- **状态迁移只允许状态机驱动**，旁路写入视为契约破坏（架构测试强制）；
- 取消 → 停进程树（先校验身份防 PID 复用，B-16 同族）→ 已落盘改动不丢 → `cancelled` 终态。

### 3.2 验收状态机

```
proposed → accepted_by_user → executing → reported → verified | regressed
```

- 需求改版递增 `requirement_revision` 并**自动作废**既有验收（追加作废记录，不改写）；
- `reported` 的结论必须能指向具体 Item/Event 证据（`evidence` 字段）；
- **没有复跑也不轻信**：`verified` 的依据是"声称的检查与当时录得的真实输出并排核对"
  （overview §12 M5）。

## 4. 工作区修订号

- 每次可能改变磁盘状态的动作（工具写/命令执行/接管操作）产生新修订，`revision` 单调递增；
- `search` 分页、Review 的"某一轮 diff"、选中文字的源定位都**绑定修订号**；
  不匹配一律拒绝并返回新修订号，不给过期结果；
- 文件内容指纹 = 内容双哈希（opaque identity，非信任校验）；
- 选中定位保存**原始字节 offset**（处理 BOM/混合换行）。

## 5. 存储

| 内容 | 位置 | 性质 |
| --- | --- | --- |
| 会话正文 | `~/.questor/sessions/<thread_id>.jsonl` | **append-only JSONL，唯一真相源** |
| 搜索索引 | `~/.questor/index/`（SQLite） | **可丢弃可重建**，损坏即重建不修复 |
| 工作文件（粘贴长文本/图片） | `~/.questor/files/` | 带过期，清理与历史快照分离 |
| 工具结果落盘 | 会话目录内 `<tool_use_id>.txt` | O_EXCL 幂等写（B-24），预览 2KB 回链 |
| 配置 | `~/.questor/config.toml` + 项目 `config.example.toml` | 分层 strip 用户专属安全字段（B-58） |

- 索引分词预留 CJK bigram 兼容（B-48）；不引入消息队列、不依赖云；
- 断线恢复靠 JSONL 的 `seq` 锚点 + 事件重放（**不重放工具执行**，断流中被中断的工具
  绝不重放，结果可能未知）。
