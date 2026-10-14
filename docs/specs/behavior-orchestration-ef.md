# behavior-orchestration-ef —— EvoFlow 编排与验收行为规格（Questor `orchestration` 蓝本）

来源：EvoFlow `backend/packages/harness/evoflow/collab/`。扫描日期 2026-10-11。
Questor 模块归属：`orchestration`（Plan/Goal/看板/验收与打回）。

---

## 1. 任务状态机白名单（`collab/state_transitions.py`）

`ALLOWED_TRANSITIONS` 显式白名单（`state_transitions.py#L45-84`），全表：

```
INBOX     → PENDING / COMPLETED(用户自勾) / CANCELLED
PENDING   → PLANNING / PLANNED / EXECUTING(直跑) / CANCELLED
PLANNING  → PLANNED / FAILED(规划失败) / CANCELLED
PLANNED   → PLANNING(重新规划) / EXECUTING / CANCELLED
EXECUTING → PAUSED / COMPLETED(免审) / REVIEWED(完成待审) / FAILED / CANCELLED
PAUSED    → EXECUTING(恢复) / CANCELLED
REVIEWED  → COMPLETED(审核通过) / EXECUTING(打回重做) / CANCELLED
COMPLETED → ∅（终态）
FAILED    → EXECUTING(重试)
CANCELLED → ∅（终态）
```

- **边界行为**：非法迁移抛 `InvalidStateTransitionError`（`#L86-90,L116-130`）；
  `can_transition` 对未知状态返回空集（fail closed，`#L102-114`）；
  任务状态 ↔ CollabPhase **双向映射**函数成对存在（`#L147-159`）；
  迁移 Hook 注册表按 `(from, to)` 键注册（`#L177-208`）。
- **坑**：B-38（Hook 异常只 `print` 吞掉，`#L208-224`）、B-39（`evoflow/plans/` 是模型套餐
  目录，与任务 plan 撞名——Questor 禁止重载领域词）。

### Questor 采纳决定
白名单表驱动 + fail closed 沿用；`REVIEWED → EXECUTING（打回重做）` 正是 overview §7
验收状态机的编排侧对应物；Hook 异常必须走 logging 并传播给观测面。

## 2. 编排门："工具返回错误，而非中间件注入"（`collab/supervisor_plan_gate.py`，全 204 行）

模块 docstring 原文：*"Plan-collaboration prechecks for supervisor tool actions
(tool returns errors, not middleware injection)"*（`#L1`）。

- **三类动作清单**（frozenset）：
  - `_PLAN_REQUIRED_ACTIONS`：create_task / create_task_with_subtasks / create_subtask /
    create_subtasks / set_task_planned——须先有落库 Plan（`#L20-28`）；
  - `_PLAN_REDUNDANT_SETUP_ACTIONS`：plan Steps 已同步子任务后**禁止再批量建任务**
    （`#L31-40`，错误文案给出替代路径"用 supervisor(start_execution) 派发"）；
  - `_EXEC_AUTH_REQUIRED_ACTIONS`：start_execution / retry_subtask / interrupt_subtask /
    steer_subtask / continue_subtask_session / peer_send / complete_subtask——**须用户
    「开始执行」授权**（`#L43-55`）。
- **错误载荷形状**：`{success:false, action, error_code, message, hint}`，错误码
  `need_plan_first` / `need_execution_authorization` / `plan_subtasks_already_synced`
  （`#L93-108,L164-193`）；hint 指导模型下一步动作。
- **边界行为**：非严格 plan 协作线程直接放行（`#L153-154`）；授权判定双路（磁盘
  bound_task_id + 任务存储 `is_task_execution_authorized`，`#L111-138`）。
- **坑**：B-43（门返回的是**结构化错误载荷**而非异常——模型可读、可重试，Questor 编排门沿用）。

### Questor 采纳决定
`orchestration` 的破坏性编排门**沿用此模式**：动作清单 frozenset + 门函数返回结构化错误
载荷（含 hint），不用中间件注入拦截。审批中间件（`agents/middlewares/tool_approval_middleware.py`
+ `tool_approval_executor.py`）与人工门工具（`agents/human_gate_tools.py`）是**另一层**
（工具级审批，LangGraph 耦合只参照）——两层职责在 EvoFlow 里也是分开的。

## 3. 人工门（`agents/human_gate_tools.py`，LangGraph 耦合，只参照语义）

- **语义**：人工门 = graph turn 结束（`goto END`）直到用户在界面或对话行动；**与用户点
  Stop（run 取消）不是一回事**（`#L1-8` docstring 明言）。
- **门种类**：`clarification` / `tool_approval`；审批类工具名从风险分级表
  `TOOL_RISK_LEVELS`（≠RISK_AUTO 者）自动派生，不手工维护（`#L20-26`）。
- **Transcript 规则**：发出 gate ToolMessage 时**立即 persist 固定 seq**，保证用户的
  跟进行（澄清答复/批准）排在它之后（`#L14-16`）。
- **坑**：B-45（gate 消息先持久化定序）。

### Questor 采纳决定
"人工门 ≠ 取消"的语义区分收进 overview 状态机（waiting 旁态 vs cancelled 终态）；
gate 消息定序规则收进 gesta append-only 语义；LangGraph 的 goto=END 机制不借鉴。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-38 | orchestration | 状态迁移 Hook 的异常不得只 print 吞掉，必须 logging 并上浮观测面 | `collab/state_transitions.py#L208-224` |
| B-39 | orchestration | 禁止重载领域词命名（EvoFlow `evoflow/plans/` 是模型套餐，与任务 plan 撞名） | `packages/harness/evoflow/plans/`（catalog/bindings/adapters）目录实存 |
| B-43 | orchestration | 编排门返回结构化错误载荷（error_code/message/hint）而非抛异常——模型可读可重试 | `collab/supervisor_plan_gate.py#L93-108` |
| B-45 | gesta | gate/审批类消息必须先持久化定序，用户的跟进行才能排在后面 | `agents/human_gate_tools.py#L14-16` |
