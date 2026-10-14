# Questor app-server 协议（protocol）——跨进程契约真相源

版本: v2.0（词表取齐 wuu app-server，ADR-0042）| 更新: 2026-10-14 | 状态: 待用户评审
关联: `ADR-0042`（词表同源）、`ADR-0045`（无 review/turn_diff）、`ADR-0028`（加性演进）、`docs/research/phase0-wuu-protocol-table.md`（全量事实源）、`AGENTS.md` §三

> 本文件是「协议」契约三件之一，**改方法/通知/字段先改本文件并递增版本，代码跟随**。
> **单一来源纪律**：本表首列 ↔ `src/questor/schemas/app_server/` ↔ `serve` handler 注册表 ↔ `phase0-wuu-protocol-table.md` 四处同源；护栏 `test_serve_names_are_contracted` 解析 §3/§4 表首列 + §7 错误方言，断言「实现面 ⊆ 契约面」（B-119/B-121）。
> 词表**取齐 wuu 实测**（snake_case）；旧自研命名（`thread/create`、`run/stop`、`review/turn_diff`）作废。§3/§4 列 **A 阶段目标词表**；`serve` 尚未按此重写时，护栏红 = 契约先于实现的**正确信号**，Phase 1/2 移植 serve 后转绿（ADR-0044）。

## 1. 传输与信封（照 wuu）

- **单一传输**：stdio NDJSON；**无服务端监听 WebSocket**（`websocket` 只属 provider 流式与不做的 remote）。桌面 stdio；web 宿主后期按「同 renderer 换传输」评估。
- **协议版本**：`questor-app-server/v0.1`（对齐 wuu 串值），`initialize` 严格相等、不降级（B-60）。
- **单帧上限**：`64 * 1024 * 1024`（两端同值，base64 附件内嵌）。
- **信封**：请求 `{id,method,params}`；响应 `{id,result}` / `{id,error:{code,message}}`；通知 `{method,params}`（无 id）；反向（server→client）id 带 `srv-` 前缀。
- 命名 snake_case；路径字段按 Windows 原生生成。

## 2. initialize 握手

`InitializeParams{protocol_version, client{name,version}, capabilities{reverse_rpc.methods[], deferred_notification_content}}` → `InitializeResult{status, issues, protocol_version, core, provider, model, effort, variant, max_parallel, runtime_host, workspace_root, permissions, model_profile, tool_surface, model_roles, model_aliases, providers, advanced_settings, general_settings, features{browser, safe_mode, project_agent}}`。插件/二开面字段裁剪或退化（port-ledger 记）。

## 3. 方法表

| 方法 | 域 | 说明 |
| --- | --- | --- |
| `initialize` `shutdown` | 握手 | 生命周期 |
| `thread/start` | 会话 | 建会话（旧 `thread/create` 作废） |
| `thread/resume` | 会话 | 恢复（旧 `thread/show`） |
| `thread/fork` `thread/archive` `thread/delete` | 会话 | 分叉/归档/删除（删除需 idle） |
| `thread/list` `thread/listAll` `thread/listArchived` `thread/search` | 会话 | 列表与跨会话搜索 |
| `thread/pin` `thread/rename` `thread/preview` `thread/regenerate-title` `thread/edit-message` | 会话 | 元数据 |
| `thread/compact/start` `thread/context-composition` | 会话 | 显式压缩 / 上下文构成（可见） |
| `turn/start` `turn/interrupt` | 执行 | 起一轮 / 中断 |
| `turn/steer` `turn/unsteer` `turn/queue` `turn/dequeue` `turn/requeue` `turn/update-queued` | 执行 | **可干预柱本体**（steer=改道、queue=排队；`client_id` 幂等） |
| `run/start` `run/interrupt` | 执行 | run 控制/观测边界 |
| `process/list` `process/read` `process/write` `process/resize` `process/stop` | 终端 | 后端 worker 进程面（Windows ConPTY 或让位前端 node-pty） |
| `activity/list` `activity/takeover` `activity/release` `activity/stop` | 接管 | 控制权仲裁（租约+takeoverVersion） |
| `user-question/hold` `user-question/respond` `user-question/list` `user-question/cancel` | HITL | agent 反向提问 |
| `config/read` `config/model/update` `config/advanced/update` `config/general/update` `config/provider/remove` `config/model-catalog/refresh` `config/model-catalog/providers` | 配置 | 分层配置（permission_mode 不可由项目层设定） |
| `usage/overview` `settings/usage` | 用量 | 最小读数（insight 大盘不做） |
| `git/commit-message` `text/polish` | 杂项 | 轻量 |
| `workspace/list` `workspace/state/cleanup` | 工作区 | 注册与清理 |
| `sessionFolder/create` `sessionFolder/update` `sessionFolder/reorder` `sessionFolder/delete` | 会话 | 文件夹 |
| `browser/cdp` `browser/screenshot` `browser/open_tab` `browser/close_tab` `browser/set_visibility` `browser/list_tabs` `browser/turn_ended` `browser/finalize` | 反向 | core→client server-initiated，不注册进 handleLine；`tab_id` core 侧 mint |

**不做族（登记非遗漏）**：`plugin/*` `extension/*` `mcp/*` `sideThread/*` `participant` `project/*` `sessionOrganization/*` `skill/*` `device/*`。**明确不存在**：`review/*` `diff/*` `task/*` `goal/*` `schedule/*` `evidence/*`（盘态 diff 归壳侧 ADR-0045；编排/验收族 Phase 6）。

## 4. 事件族

| 通知 | 说明 |
| --- | --- |
| `thread/started` `thread/resumed` `thread/updated` | 线程生命周期 |
| `turn/started` `turn/queued` `turn/dequeued` `turn/steered` `turn/unsteered` `turn/held` `turn/event` `turn/error` `turn/completed` | 回合（含可干预旁态） |
| `run/started` `run/updated` | run 状态（旧 `run/status` 作废） |
| `item/started` `item/completed` `item/removed` | Item 生命周期 |
| `item/agentMessage/delta` `item/agentMessage/replace` `item/reasoning/delta` `item/reasoning/replace` `item/toolCall/delta` `item/toolCall/outputDelta` | **流式增量（可见柱核心）** |
| `turn/usage` | 用量（后端按秒节流，前端算 tokens/s） |
| `activity/started` `activity/updated` `activity/control_changed` `activity/stopped` | 接管/控制权 |
| `browser/turn_started` `browser/request_cancelled` | 浏览器面板反向通知 |
| `user-question/requested` `user-question/resolved` | HITL |
| `config/changed` `config/error` | 配置 |

**不做通知**：`sideThread/event`、`agent/updated`、`agent/mailbox`、`mcp/status/updated`、`plugin/inventory/changed`。

## 5. 反向请求与能力协商

反向 browser 8 方法（§3）经 `callClient` 单桥、30s 超时、单 stdin scanner 串行；客户端不回则 `features.browser=false` 降级。审批走 wuu 收紧型 `approve_for_me`（非 per-command 弹窗，C19 待 Phase 1 实测对表）。

## 6. 客户端义务

按 `id` 关联响应；未决期间持续读通知；反向响应先路由给 pending 等待者再进 method switch（B-59）；慢发现后台化不卡分发（B-62）。

## 7. 错误方言

| error_kind / code | 场景 | model_next_action 示例 |
| --- | --- | --- |
| `boundary_denied` | limen 拒绝 | "use read-only tools, or tell the user..." |
| `authorization_denied` | Authorizer fail-closed | 无（终止本轮该动作） |
| `review_blocked` | 可选复核不得默认变隐式信任 | "await explicit user approval" |
| `stale_revision` | 修订号不匹配 | "re-read the file at the new revision" |
| `protocol_version_mismatch` | 握手失败 | 无（终止） |
| `unknown_method` `invalid_params` `internal_error` | 信封/技术层 | — |

- 拒绝带模型读得懂的理由 + 下一步；审批不得解除硬拒（B-56）。字符串错误码不自造，须落本表或 app_server schema `code.enum`。

## 8. 演进与校验

- **加性演进**（ADR-0028）：新增方法/通知族不升版本；破坏性改动才升；族级停用显式登记。
- **契约测试**：`tests/contract/` 用 wuu 测试 golden / 手写期望帧回放驱动 Python，逐帧形状/顺序/终态一致（本机无 Go → 软模式，运行期行为标盲区）——「无代码生成」缺陷的唯一防线。
