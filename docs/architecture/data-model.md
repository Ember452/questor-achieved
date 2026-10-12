# Questor 核心数据契约（data-model）

版本: v1.3 | 更新: 2026-10-12 | 状态: accepted（M1 定稿；v1.1 补 queued→cancelled，见 ADR-0014；
v1.2 补上下文工程记录，见 ADR-0017；v1.3 补编排域 Task/Plan/Goal/Evidence 与 Run 的编排绑定，见 ADR-0025/0027）
关联: `overview.md` §7（草案出处）、`protocol.md`（跨进程边界）、`docs/specs/`（行为规格）、
`src/questor/schemas/model/` 与 `src/questor/schemas/orchestration/`（本契约的 JSON Schema 物化）

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

编排域（v1.3，独立 store，见 §5；不写进线程正文——ADR-0025）
Goal (1) ──< Task (N) ──< Task（子任务，DAG 依赖）
              │
              └── Plan (N) ── Task（由定稿 Plan 的步骤同步派生）
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
| `task_id` / `goal_id` | string? | 编排绑定（v1.3）：本 run 所属的 Task / Goal；独立会话直接发起的 run 两者皆空（加性字段，见 ADR-0025） |

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

### 编排实体（v1.3，ADR-0025）

编排实体住**独立 append-only store**（§5），id 与时间戳沿用 §1 通用约定。

**Plan** —— 先澄清→可修订→定稿才执行的可修订计划。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | |
| `thread_id` | string? | 来源会话（模型提议计划时所在线程） |
| `goal_id` | string? | 归属长跑目标 |
| `requirement_revision` | integer | 需求修订号（≥1）；**递增即自动作废既有验收**（追加作废记录，不改写） |
| `status` | string | `drafting` / `proposed` / `finalized` / `superseded` |
| `steps` | object[] | 有序步骤 `{id, title, status, task_id?}`；定稿后可同步派生 Task |
| `created_at` / `updated_at` | string | |

**Task** —— 看板任务单元。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | |
| `thread_id` | string? | 执行该任务的会话 |
| `goal_id` | string? | 归属长跑目标 |
| `plan_id` | string? | 由哪份计划派生 |
| `title` | string | |
| `status` | string | 状态机见 §3.3 |
| `parent_task_id` | string? | 子任务树 |
| `depends_on` | string[] | DAG 依赖边（前置任务 id） |
| `acceptance` | object | `{status: 验收状态（§3.2）, requirement_revision, evidence_ids: []}` |
| `run_id` | string? | 绑定的一次引擎执行 |
| `created_at` / `updated_at` | string | |

**Goal** —— 后台自驱长跑目标。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | |
| `thread_id` | string | 承载会话 |
| `objective` | string | 目标的一句话描述 |
| `status` | string | `idle` / `running` / `paused` / `completed` / `failed` / `cancelled` |
| `max_rounds` | integer? | 轮次上限（长跑止损） |
| `round_count` | integer | 已跑轮次 |
| `deadline` | string? | 时长上限（UTC ISO-8601） |
| `created_at` / `updated_at` | string | |

**Evidence** —— 声称的检查与当时录得的真实输出（§3.4，ADR-0027）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | |
| `subject_type` | string | `run` / `task` / `turn` |
| `subject_id` | string | |
| `claimed` | string | 声称做的检查（模型/工具报告） |
| `recorded_output_ref` | string | 指向具体记录条目（Item/Event id 或 spill 回链）——**核对结论必须可追溯** |
| `verdict` | string | `verified` / `mismatch` / `unverified`（无记录即 `unverified`，不臆断） |
| `created_at` | string | |

## 3. 状态机

### 3.1 运行状态机

```
queued → running → completed | failed | cancelled
   │        │
   │        ├── steered（旁态：插话在下一个工具边界被消费后回 running）
   │        └── waiting（旁态：等插话/审批；恢复后回 running）
   └── cancelled（尚未起跑的运行可被取消，不经 running）
```

- 终态仅 `completed | failed | cancelled`；`steered` / `waiting` 是 `running` 的**旁态**，
  旁态间迁移必须经由 running；queued 可直接取消（v1.1，ADR-0014）——不得伪造 running
  起点再取消；
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

### 3.3 编排任务状态机（v1.3，ADR-0025）

```
inbox    → pending / completed(用户自勾) / cancelled
pending  → planning / planned / executing(直跑) / cancelled
planning → planned / failed(规划失败) / cancelled
planned  → planning(重新规划) / executing / cancelled
executing→ paused / completed(免审) / reviewed(完成待审) / failed / cancelled
paused   → executing(恢复) / cancelled
reviewed → completed(审核通过) / executing(打回重做) / cancelled
completed→ ∅（终态）
failed   → executing(重试)
cancelled→ ∅（终态）
```

- 白名单**表驱动**、未知状态 fail closed，单点入口在 `orchestration/transitions.py`
  （形态同 §3.1 的运行状态机）；`reviewed → executing` 即"打回重做"，与 §3.2 验收状态机在编排侧对应；
- 破坏性编排动作（建任务、派发执行）须先过**编排门**：先有落库 Plan（`need_plan_first`）、
  先有用户"开始执行"授权（`need_execution_authorization`）；门返回结构化错误载荷而非异常（B-43）；
- **状态迁移只允许状态机驱动**，旁路写入视为契约破坏（架构测试强制）。

### 3.4 证据核对（v1.3，ADR-0027）

- `Evidence.verdict` 只取 `verified` / `mismatch` / `unverified`；**没有记录支持的结论一律 `unverified`**，
  不臆断打分（诚实呈现铁律）；
- 结论必带 `recorded_output_ref`，能指向具体 Item/Event/spill；
- 证据只**追加**，绝不改写被核对的原文（append-only）；复跑核验不在本轮（overview §2），留待 M5。

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
| 编排实体 | `~/.questor/orchestration/tasks.jsonl` | **独立 append-only JSONL 唯一真相源**（Task/Plan/Goal/Evidence 记录）；索引可重建；不写进线程正文（ADR-0025） |
| 工作文件（粘贴长文本/图片） | `~/.questor/files/` | 带过期，清理与历史快照分离 |
| 工具结果落盘 | 会话目录内 `<tool_use_id>.txt` | O_EXCL 幂等写（B-24），预览 2KB 回链 |
| 上下文工程记录 | 会话正文 JSONL 内的 `context.boundary` / `context.replacements` 记录 | **与正文同流、append-only**（ADR-0017）：压缩边界与替换决策均只追加不改写；它们是内核的上下文事实，**不是 ItemKind**，对外可见性走 `notice/compact` 事件族（protocol §4） |
| 配置 | `~/.questor/config.toml` + 项目 `config.example.toml` | 分层 strip 用户专属安全字段（B-58） |

- 索引分词预留 CJK bigram 兼容（B-48）；不引入消息队列、不依赖云；
- 断线恢复靠 JSONL 的 `seq` 锚点 + 事件重放（**不重放工具执行**，断流中被中断的工具
  绝不重放，结果可能未知）。
