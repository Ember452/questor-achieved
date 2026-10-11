# behavior-engine-fc —— FlowCoder 执行核行为规格（Questor `engine` 蓝本）

来源：FlowCoder `src/flowcoder/agent/core.py`（全文 1076 行）+ `agent/budget.py` + `agent/events.py`。
扫描日期 2026-10-11，证据行号以当日文件为准。Questor 模块归属：`engine`（部分条目涉 `habena`）。

---

## 1. run() 入口与 trace 绑定

- **输入**：`ConversationManager`。
- **输出**：`AsyncIterator[AgentEvent]`（异步生成器，TUI/Daemon/CLI 共同消费）。
- **边界行为**：trace_id 缺失时生成新值并 bind 到日志上下文，finally 中 reset（`agent/core.py#L278-287`）。
- **坑**：无。

### Questor 采纳决定
沿用"run() 返回事件异步生成器"的形态；trace 绑定改为 Questor 的 logctx 等价物。

## 2. 一轮 turn 的生命周期（`_run_loop`，每轮八阶段）

每轮顺序（`agent/core.py#L322-701`）：

1. 迭代计数 + 上限判定（`#L326-330`，超限 yield ErrorEvent 后 break）；
2. 预算闸判定（见 §4）；
3. `turn_start` 生命周期 Hook（`#L355`）；
4. 注入外部通知（Team mailbox / notification_fn → 对话，`#L359`、`agent/notifications.py`）；
5. Layer2 压缩检查与执行（见 behavior-context-fc）；
6. `pre_send` Hook → 每轮重建 system prompt（Hook 注入段追加；协调者模式整段替换并附子 Agent 目录，`#L416-434`）→ Plan 模式注入计划提醒并把 plan 文件路径写入权限检查器（`#L437-447`）→ deferred 工具提醒注入（`#L456-463`）→ 生成 tools schema（**预算收敛轮传空数组**，`#L466-467`）；
7. Layer1 按 tool-result 预算生成 api_conv（**不改原始 conversation**，`#L469-474`）→ 流式 LLM 调用（StreamCollector 收集并转发事件，`#L477-482`）→ `post_receive` Hook（`#L484-489`）→ 用量累计 + UsageEvent（`#L491-498`）；
8. 分派：无 tool_call → 完成（见 §3）；有 tool_call → 记录响应 → 按并发安全分区执行（见 §5）→ `turn_end` Hook + TurnComplete（`#L699-701`）。

- **边界行为**：
  - 压缩成功后**重新注入**环境上下文 + 项目指令 + 记忆（`#L389-397`），保证工作集不丢；
  - 压缩返回 None（近期内容不足以生成有效摘要）→ 发 CompactNotification 说明跳过（`#L405-412`）；
  - 压缩返回 str → 视为错误事件（`#L413-414`）；
  - 模型调用 `ExitPlanMode` → 本轮即收敛结束循环（`#L691-697`）。
- **证据**：见各条行号。

### Questor 采纳决定
沿用八阶段顺序与"压缩后重注入"语义；Plan 模式的计划提醒保留，但 plan 文件路径**不走权限检查器字段**（见 behavior-permissions-fc 的决定）。

## 3. 完成语义（无 tool_call）

- **输出**：final response 入对话 → 后台轻量记忆观察（`#L523-526`）→ `turn_end` + `session_end` Hook → 文件历史快照 → `LoopComplete(total_turns)` → break（`#L516-544`）。
- **边界行为**：记忆重提取每 5 轮触发一次（`MEMORY_EXTRACTION_INTERVAL=5`，`#L124-125`、`#L527-530`），用 LLM 从对话提取，走后台任务。
- **证据**：见行号。

### Questor 采纳决定
沿用"无工具调用即收敛"与后台记忆观察；重提取间隔进预算常量表。

## 4. 止损四路（每一轮开头与执行中判定）

| # | 机制 | 行为 | 证据 |
| --- | --- | --- | --- |
| 1 | 轮次硬上限 | 默认 50 轮，超限 ErrorEvent 后终止 | `agent/core.py#L137`（默认值）、`#L326-330` |
| 2 | 四维预算收敛 | token/轮次/时间/成本，判定**纯读累计值无 IO**（`agent/budget.py#L70-91`）；首次超限：注入收敛 user 消息（`converge_message`，`agent/budget.py#L94-96`）并**撤下全部工具 schema**（`core.py#L466-467`），给模型一轮纯文本收尾；收敛轮仍超限**或**收敛轮仍返回工具调用 → 强制结束（`core.py#L341-349`、`#L553-561`） | 见左 |
| 3 | 未知工具熔断 | 连续 ≥3 次未知工具名 → 终止（`core.py#L316`、`#L685-689`）；**并行批刻意不清零计数**，否则"每轮夹一个幻觉调用 + 若干只读调用"永远逃过熔断（`#L619-623`，P0-10 注释）；只有串行路径已知工具执行成功才清零（`#L667-670`） | 见左 |
| 4 | max_tokens 触顶恢复 | 先提升输出上限再注入续写提示，retry_event → `continue` 重调 LLM（`agent/output_recovery.py`，接入点 `core.py#L502-513`）；恢复状态每 run 重置（`#L317`） | 见左 |

- **坑**：B-05（魔法数散布）、B-06（巨型单文件）、B-07（双循环实现漂移，见 §6）。

### Questor 采纳决定
四路全收，两处调整：① 收敛轮**保留只读工具**（FlowCoder 撤光 schema 后模型幻觉调用会零产出强杀——`core.py#L553-561` 正是该失败形态）；② 全部阈值进一张预算常量表（`engine/constants.py`）。

## 5. 工具执行分区（并发安全）

- **输入**：本轮全部 tool_calls + 注册表。
- **行为**：`partition_tool_calls` 按 `is_concurrency_safe` 分批（`agent/tool_execution.py`）；并发批先**逐个**过 pre_tool_use Hook + 权限预检（`core.py#L569-602`），通过者 `asyncio.gather` 并行执行（`#L750-753`），再逐个 post_tool_use；结果**按原始调用顺序**汇总（`#L624-633`）。串行批逐个"Hook → 授权 → 执行 → Hook"（`#L635-683`）。
- **边界行为**：
  - pre_tool_use Hook 可 reject，产出 `hook_rejected_result`（`#L582-586`）；
  - 授权未通过 → 权限错误结果，不执行（`#L595-601`）；
  - 未知工具：`registry.get` 为 None → 错误结果且 `is_unknown=True`（`#L787-791`）；
  - 参数 ValidationError → 错误结果回填对话（`#L831-832`）；
  - 执行异常统一捕获为 `Tool execution error` 错误结果，**循环不崩**（`#L833-834`）。
- **证据**：见行号。

### Questor 采纳决定
沿用"只读并行/写串行"分区与结果按原序汇总；授权改为 limen 单门（见 behavior-limen-wuu.md）。

## 6. 子代理路径：`run_to_completion`（Questor 必须避免的双实现）

- **行为**：非交互执行到完成，不产出事件流，返回最终文本（`agent/core.py#L911-1065`）。
- **边界行为（与交互路径的差异清单）**：**无预算闸**（无 §4-2 的收敛语义）、**无 unknown 熔断**、**无 max_tokens 恢复**、无 Plan 模式分支、工具执行走 `execute_noninteractive_tool_call`（`#L1067-1076`）。两份循环实现并存（L289 vs L911）。
- **坑**：B-07。

### Questor 采纳决定
**拒绝双实现**：子代理与交互路径共用同一状态机，非交互只是"无 UI 消费者"的事件流消费者差异。

## 7. 事件协议（`agent/events.py`）

dataclass 事件族（`agent/events.py#L26-128+`）：`StreamText` / `ThinkingText` / `RetryEvent` / `ToolUseEvent` / `ToolResultEvent` / `TurnComplete` / `LoopComplete(total_turns)` / `UsageEvent` / `ErrorEvent` / `CompactNotification` / `CompactStarted` / `HookEvent` / `PermissionRequest`（含 `PermissionResponse`） / `AskUserRequest`（携带 `asyncio.Future`）。

- **边界行为**：
  - `AskUserRequest` 的 future 有 **300 秒超时**，超时产出错误结果 "User did not respond within 5 minutes"（`core.py#L813-818`）——防前端失联挂死整个循环；
  - 生命周期 Hook 事件（session_start/turn_start/pre_send/post_receive/turn_end/session_end）与普通事件同流产出（`#L312`、`#L355`、`#L417`、`#L485`、`#L699`）。
- **坑**：B-04（提问 future 超时上限）。

### Questor 采纳决定
沿用"一套事件流多端消费"；Questor 事件族按 protocol.md 裁剪命名；审批/提问 future 一律带超时（归 `habena`）。

## 8. 后台任务纪律

- **行为**：fire-and-forget 统一走 `_spawn_bg`：持强引用集合 + done callback 记日志（`agent/core.py#L703-721`）。
- **边界行为**：裸 `ensure_future` 的任务可能被 GC 中途回收、异常静默丢失（该函数 docstring 明言）。
- **坑**：B-01。

### Questor 采纳决定
沿用强引用 + done-callback 纪律（`engine` 内部工具函数）。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-01 | engine | fire-and-forget 任务必须持强引用并观察异常，否则被 GC 中途回收且异常静默 | `agent/core.py#L703-721` |
| B-02 | engine | 预算收敛轮撤光全部工具 schema 后，模型仍幻觉调用会零产出强杀——收敛轮应保留只读工具 | `agent/core.py#L553-561` |
| B-03 | engine | 并行批不得清零 unknown 计数，防"每轮夹一个幻觉调用"逃逸 ≥3 熔断 | `agent/core.py#L619-623` |
| B-04 | habena | 审批/提问 future 必须带超时（FlowCoder 300s），防前端失联挂死循环 | `agent/core.py#L813-818` |
| B-05 | engine | 循环阈值常量必须集中一张表（FlowCoder 散布 50/3/300s/5 于各处） | `agent/core.py#L137,L316,L813,L124` |
| B-06 | engine | 循环必须拆显式状态机，不允许 1076 行单文件巨型函数 | `agent/core.py`（全文） |
| B-07 | engine | 子代理路径必须复用交互路径的同一状态机——FlowCoder 双实现已漂移（子代理无预算闸/无熔断/无输出恢复） | `agent/core.py#L289 vs L911` |
| B-08 | engine | max_tokens 触顶恢复的状态每 run 重置，恢复轮次需有上限（FlowCoder 提上限+续写提示） | `agent/output_recovery.py`、`core.py#L317,L502-513` |
| B-09 | engine | 记忆观察/提取走后台任务，主循环不阻塞；重提取按轮次间隔节流 | `agent/core.py#L124-125,L523-530` |
| B-10 | limen | 权限门不得内嵌模式特例（FlowCoder 把 plan 文件路径塞进 checker 字段）——Plan 提醒是循环层职责 | `agent/core.py#L437-447` |
| B-11 | engine | 压缩成功后必须重注入环境/指令/记忆，否则压缩丢工作集 | `agent/core.py#L389-397` |
