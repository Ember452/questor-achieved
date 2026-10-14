# behavior-protocol-wuu —— wuu app-server 协议行为规格（Questor `serve`/`protocol.md` 蓝本）

来源：wuu `internal/appserver/protocol.go` + `server.go` + `internal/session/inbox.go` +
`internal/appserver/turn_handlers.go`。扫描日期 2026-10-11。Questor 模块归属：`serve`。

---

## 1. 协议版本与信封

- **版本**：`ProtocolVersion = "wuu-app-server/v0.1"`（`protocol.go#L26`），initialize 校验
  **严格相等，不做降级兼容**。
- **能力声明 opt-in**：`ReverseRPC.ReverseRPCCapabilities`（`protocol.go#L279-285`）与
  `DeferredNotificationContent`（`#L282`）都是客户端显式声明的可选能力。
- **坑**：B-60（版本严格相等不降级）、B-61（deferred/reverse 都走 opt-in 能力协商）。

## 2. 反向请求与慢发现（`internal/appserver/server.go`）

- **反向请求路由**：core→desktop 的请求（审批、浏览器宿主）由 pendingCalls 表 +
  clientCallSeq 守卫（`server.go#L205` 注释："guards both the map and clientCallSeq; see
  callClient"）；**无 method 带 id 的行先路由给等待者，再进 method switch**——否则响应被
  "unknown method" 吞掉（wuu 556 行协议文档的血泪）。
- **慢发现不阻塞**：`startBackground`（`server.go#L659`）承载 engine/list、目录刷新、
  存储维护（`#L436,L685,L955`）——串行 stdio 分发永不被慢操作卡住。
- **坑**：B-59（反向请求路由顺序）、B-62（慢发现一律后台化）。

### Questor 采纳决定
`serve` 的 qst-app-server 层沿用：pending 调用表先路由 + startBackground 等价物
（asyncio.create_task + 强引用，见 B-01）。

## 3. 插话/排队幂等（`internal/session/inbox.go`）

- **幂等键**：`INSERT OR IGNORE ... client_id`（`inbox.go#L59`）；**client_id 出现在
  session_messages 即视为已送达**（`#L93` 的 EXISTS 子查询）——重复提交天然去重。
- **送达确认**：`SettleInbox` 用 `ON CONFLICT(client_id) DO UPDATE SET delivered_at`
  （`#L66-79`）；`InboxHas` 供启动检查（`#L148-158`）。
- **steer 校验**：`ExpectedTurnID` 空 = 允许（旧客户端兼容），非空不匹配当前 turn =
  拒绝（`turn_handlers.go#L731,L880-887` `validateSteerTargetLocked`）。
- **坑**：B-63（client_id 幂等 + 历史 EXISTS 判重）、B-64（ExpectedTurnID 空=兼容、
  非空=严格校验）。

### Questor 采纳决定
habena 的 inbox 表照此设计：client_id 主键幂等 + 送达即 settle + ExpectedTurnID 校验。

## 4. held_user_work（`internal/session/held_user_work.go`）

- **双 origin**：`HeldUserWorkOriginQueue = "queue"` / `"steer"`（`#L11-12`）——排队与
  插话可互转，origin 记录来源。
- **落盘**：`ReplaceHeldUserWork` 整表 delete + insert 事务（`#L24-46`）——core 重启后
  重建未决工作。
- **坑**：B-65（held work 双 origin + 整表替换事务）。

---

## 5. 逐符号线格式对照表（Phase 1 深扫产物·Go 结构体 tag 为准）

> 来源：逐字段读 `internal/appserver/protocol.go`（2770 行）+ `stdio.go` + `config_handlers.go` +
> `internal/providers/types.go` + `internal/execution`。扫描日期 2026-10-14（Phase 1）。
> **线格式真相 = Go `json` tag**，TS `packages/protocol/src/index.ts`（3310 行）是并行镜像、会漂移，不作基准。
> Questor 侧一律 snake_case；下表的 Go 字段名即线上键名（除标注 `omitempty` = 可缺省）。

### 5.1 信封（`protocol.go#L223-337`）

| Go 结构 | 字段（线上键名:类型 omitempty） | Questor 归属 |
| --- | --- | --- |
| `Request` | `id:json.RawMessage,omitempty`（**数字或字符串**）、`method:string`、`params:RawMessage,omitempty` | `serve/envelope.py::Request` |
| `Response` | `id:RawMessage,omitempty`、`result:any,omitempty`、`error:*ResponseError,omitempty` | `serve/envelope.py` |
| `ResponseError` | `code:string`、`message:string`（**字符串码，非 JSON-RPC 数值**） | `envelope.ProtocolError` |
| `Notification` | `method:string`、`params:any,omitempty` | `envelope::Notification` |
| `clientResponse`（反向响应，`#L333-337`） | `id:RawMessage,omitempty`、`result:RawMessage,omitempty`、`error:*ResponseError,omitempty` | `envelope.try_parse_reverse_response` |

> **漂移点**：Go `id` 是 `json.RawMessage`（允许数字 id），旧 questor `envelope.py` 强制字符串 id。
> Phase 1 重写须容纳数字/字符串两种 id 原样回显（响应 id 与请求 id 逐字节一致），记 port-ledger。

### 5.2 initialize（`protocol.go#L264-325` + 装配 `config_handlers.go#L45-97`）

`InitializeParams`：`protocol_version:string,omitempty`、`client:ClientInfo,omitempty{name,version}`、
`capabilities:ClientCapabilities,omitempty{reverse_rpc:{methods:[]string}, deferred_notification_content:bool}}`。
校验：`protocol_version` 非空且 ≠ 服务端串 → 报 `unsupported protocol version`（严格相等，不降级，B-60）。

`InitializeResult`（全字段，装配 config_handlers.go#L65-97）：
`status`(ready|needs_setup)、`issues[]RuntimeIssue`(非空即 needs_setup)、`protocol_version`、
`core{version,commit,date,dirty}`、`provider`、`model`、`effort?`、`variant?`、`max_parallel`、
`runtime_host{kind,instance_id?}`、`workspace_root`、`permissions`、`extension_trust`、
`extension_inventory?`、`model_profile?`、`tool_surface?`、`model_roles?`、`model_aliases?`、
`project_models?`、`providers[]ProviderSummary?`、`advanced_settings`、`general_settings`、
`features{project_agent,browser,safe_mode?}`。

> **Provider 配置身份字段不上线**：`InitializeResult.provider/model` 是**当前活动选择**（模型标识串），
> **非**凭据/API key/身份配置。`providers[]ProviderSummary` 亦只含可展示的模型面，凭据类字段（api_key 等）
> **永不上线**（B-57 分层 strip 同源）。Phase 1 模型必须 `extra="forbid"` 拒未知键，防凭据误入。

### 5.3 thread / turn / run / item 四族（Phase 1 fixture 回放目标）

**实体**：
- `Thread`（`#L2367-2415`）：`id`、`preview`、`status:ThreadStatus`、`model_provider`、`model`、
  `model_variant`、`model_effort`、`permission_mode`、`approve_for_me`、`cwd`、`workspace_id?`、
  `workspace_kind?`(project|scratch)、`engine_id?`、`parent_id?`、`pinned?`、`archived?`、`turns[]Turn`、
  `history_cursor?`、`worktree?*WorktreeInfo`、`created_at`/`updated_at`(RFC3339)。**扩展性缝**：`owner`类字段无、但 `parent_id`/`project_id`/`folder_id` 保留（§1.7 缝 6）。
- `Turn`（`#L2425-2464`）：`id`、`kind?`(user|internal|compact)、`model_provider?`、`model?`、`items[]ThreadItem`、
  `items_view`(full)、`status`(in_progress|completed|failed|interrupted)、`error?*TurnError`、`finish_reason?`、
  `stop_reason?`、`truncated?`、`started_at?`/`answer_ready_at?`/`completed_at?`、`duration_ms?`、
  `input_tokens?`/`output_tokens?`/`context_tokens?`/`cache_creation_tokens?`/`cache_read_tokens?`。
  **硬语义**：`MarshalJSON` 令 `items` 为 nil 时输出 `[]`（**非 null**）——契约层必须复刻（否则前端 `for` 崩），记 port-ledger + 测试。
- `Run`（`#L2004` = `execution.Run` 别名）：见 §5.5 执行域；`RunStartedNotification{run}`、`RunUpdatedNotification{run}`。
- `ThreadItem`（`#L2501-2556`）：`id`、`seq?`(session_messages.seq 稳定地址)、`type`(user_message|agent_message|reasoning|tool_call|context_compaction|stream_reconnect|error)、`status?`(in_progress|completed|failed)、`terminal?`、`role?`、`text?`、`content_parts?[]MessageContentPart`、`input_text?`、`images?`、`files?`、`name?`、`origin?`/`origin_id?`（**≠ role**）、`arguments?`、`display?`、`result?`、`result_detail?`、`error?`、`summary?`、`finish_reason?`/`stop_reason?`、`retry_count?`/`max_retries?`/`retry_at_ms?`。

**方法 param/result**：
- `thread/start`：`ThreadStartParams{model_options?, project?...}` → `ThreadStartResult{thread}`（`#L1428,L1556`）。
- `thread/resume`：`ThreadResumeParams{session_id?, response_only?}`（`#L1577`）。
- `turn/start`：`TurnStartParams{client_id?, thread_id, ...}` → `TurnStartResult{turn}`（`#L1967,L1998`）。
- `turn/steer`：`TurnSteerParams{thread_id, prompt, images?, files?, expected_turn_id(必填非 omitempty), client_id?, active_document?, content_parts?}` → `TurnSteerResult{turn_id}`（`#L2095-2108`）。**B-64**：`expected_turn_id` 空=兼容放行、非空不匹配当前 turn=拒。
- `turn/queue`：`TurnQueueParams{hold?, thread_id, prompt, ...client_id?}` → `TurnQueueResult{queued:QueuedTurn}`（`#L2051-2074`）。
- `turn/requeue`/`unsteer`/`dequeue`/`interrupt`：见 `#L2090-2143`，interrupt 返 `OKResult{ok}`。
- `run/start`：`RunStartParams{thread_id, prompt, images?, files?, permission_mode?(*string), request:execution.Request, output_schema?}` → `RunStartResult{run}`（`#L2006-2018`）。
- `run/interrupt`：`RunInterruptParams{run_id, reason?}` → `RunInterruptResult{run}`（`#L2026-2033`）。

**通知 param**（族级，`#L2145-2632`）：
- `thread/started|resumed|updated`：`{thread}` / `ThreadResumed{thread, held_user_messages?, pending_user_messages?}`。
- `turn/started`：`{thread_id, turn, queue_id?}`；`turn/queued`：`{queued, message}`；`turn/dequeued`：`{thread_id, queue_id}`；`turn/steered`：`{message}`；`turn/held`：`{thread_id, messages[], error?}`；`turn/event`：`{thread_id, turn_id, event:StreamEventPayload}`；`turn/error`：`{thread_id, turn_id, error, code?, category?, provider?, status_code?, turn}`；`turn/completed`：`{thread_id, turn, content, input_tokens, output_tokens, ..., finish_reason?, stop_reason?}`；`turn/usage`：`{thread_id, turn_id, model?, input_tokens, output_tokens, ..., context_window_tokens?}`（服务端节流推送）。
- `item/started`：`{thread_id, turn_id, item, started_at_ms}`；`item/completed`：`{thread_id, turn_id, item, completed_at_ms}`；`item/removed`：`{thread_id, turn_id, item_id, removed_at_ms}`。
- `item/agentMessage/delta`：`{thread_id, turn_id, item_id, delta}`；`/replace`：`{...item_id, text}`；`item/reasoning/delta|replace`；`item/toolCall/delta`；`item/toolCall/outputDelta`：`{...delta, tool_result_detail?}`。

> **增量语义硬线（§1.5 机制 4）**：`item/*` 有 `delta`（追加）与 `replace`（整体替换）两态，前端按 `item_id` 定位、`delta` 追加 / `replace` 覆盖；Phase 1 fixture 必须断言两态字段形状。**`run/updated` 与 `turn/usage` 是节流通知**，非逐 token。

### 5.4 FinishReason 归一枚举（`providers/types.go#L101-146`）

枚举集：`stop` / `continue` / `length` / `tool_calls` / `content_filter` / `error` / `unknown`（+ 空串）。
`NormalizeFinishReason(stopReason, truncated, hasToolCalls)` 映射表（Questor `schemas/message.py` 照抄语义，不照抄代码）：

| 输入条件 | 归一结果 |
| --- | --- |
| `truncated == true`（**最先判**） | `length` |
| `stop`/`end_turn`/`stop_sequence`/`completed` | `hasToolCalls ? tool_calls : stop` |
| `length`/`max_tokens`/`max_output_tokens` | `length` |
| `tool_calls`/`tool_use`/`function_call` | `tool_calls` |
| `content_filter`/`refusal` | `content_filter` |
| `error`/`failed` | `error` |
| `""`（空） | `hasToolCalls ? tool_calls : ""` |
| 其他（default） | `hasToolCalls ? tool_calls : unknown` |

入参先 `ToLower(TrimSpace(stopReason))`。`continue` 是循环语义（再来一轮、无客户端工具调用），不由本函数产出、但属枚举集。各家停止信号（OpenAI `finish_reason`、Anthropic `stop_reason`、Gemini、Kimi…）**归一到本 7 值**，线上 `finish_reason` 只见归一值、原始串留 `stop_reason`（诊断）。

### 5.5 执行域 `execution.Run`/`Request` 的边界

`Run = execution.Run`（别名，`#L2004`），完整形状属 `internal/execution` 包。Phase 1 契约层只固定 **`run` 作为不透明对象随 `run/start`(result) / `run/started|updated`(通知) 上线**、其内部字段随 Phase 2a 移植 `execution` 时逐符号补；本表标注「形状待 execution 移植定」，不凭猜写死（§1.5 机制 1「不得出现『大概/应该』」）。

---

## 6. 硬语义清单（Phase 1 逐条挂 port-ledger + 测试）

| 硬语义 | wuu 锚 | Phase 1 落点 | 测试族 |
| --- | --- | --- | --- |
| 64 MiB 单帧上限 | `stdio.go#L16` | `envelope.MAX_LINE_BYTES` | 超限帧红 |
| NDJSON·TrimSpace 跳空行 | `stdio.go#L18-32` | `stdio.run_stdio` | 空行不产生帧 |
| `srv-<seq>` 反向 id | `client_calls.go#L50` | `dispatch` pending 表 | 反向请求 id 前缀断言 |
| 响应 id 原样回显（可数字） | `protocol.go#L230` RawMessage | `envelope` | 数字 id 回放 |
| 版本严格相等不降级 | `config_handlers.go#L50-51` | `handle_initialize` | 错版本回 error（B-60） |
| Provider 凭据不上线 | `InitializeResult` 无 key 字段 | schemas `extra=forbid` | 注入 api_key 键被拒 |
| Origin ≠ Role | `types.go#L313,L321` | `message.ChatMessage` | 断言两字段独立 |
| FinishReason 归一 | `types.go#L116-146` | `message.normalize_finish_reason` | 逐入参表测 |
| Turn.items nil→[] | `protocol.go#L2457-2464` | `app_server` Turn 模型 serializer | 空 items 序列化为 `[]` |
| item delta/replace 两态 | `#L2591-2617` | `app_server` 通知模型 | 两态形状断言 |

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-59 | serve | 反向请求的响应先路由给 pending 调用表等待者，再进 method switch，否则被 unknown method 吞掉 | wuu `internal/appserver/server.go#L205` |
| B-60 | serve | 协议版本严格相等，不做降级兼容 | wuu `internal/appserver/protocol.go#L26` |
| B-61 | serve | deferred content 与反向 RPC 都是客户端 opt-in 能力声明，不默认开启 | wuu `internal/appserver/protocol.go#L279-285` |
| B-62 | serve | 慢发现/维护一律后台化（startBackground），串行分发不被卡住 | wuu `internal/appserver/server.go#L436,L659,L955` |
| B-63 | habena | 插话 client_id 幂等：INSERT OR IGNORE + "client_id 在 history 中即已送达" | wuu `internal/session/inbox.go#L59,L93` |
| B-64 | habena | steer 的 ExpectedTurnID：空=旧客户端兼容放行，非空不匹配当前 turn=拒绝 | wuu `internal/appserver/turn_handlers.go#L880-887` |
| B-65 | habena | held_user_work 双 origin（queue/steer）落盘，整表替换事务，重启重建 | wuu `internal/session/held_user_work.go#L11-12,L24-46` |
