# phase0-wuu-protocol-table —— wuu app-server 方法/通知全枚举 + Questor A 阶段处置

> 来源：逐条读 wuu `internal/appserver/protocol.go#L28-199`（`Method*` / `Notification*` 常量块）。
> 本表原为 Phase 0 前置扫描产物（曾 0 字节空文件，2026-10-14 Phase 1 深扫时回填）。
> **线格式真相 = Go `json` tag**；TS `packages/protocol/src/index.ts`（3310 行）是并行镜像、会漂移。
> 处置三态：**做**（A 阶段契约+实现）/ **后置**（登记，A 后某 Phase 做）/ **不做**（§0 不做清单，留缝）。

- `ProtocolVersion = "wuu-app-server/v0.1"`（protocol.go:26）。**Questor 决定用 `questor-app-server/v0.1`**（用户拍板 TL-3）；Phase 2b 重建前端时其版本常量同步对齐，记 port-ledger 为登记过的 wuu 偏离。
- 帧上限 64 MiB（stdio.go:16）；NDJSON（stdio.go:18-32）；反向 id 前缀 `srv-`（client_calls.go:50）。
- snake_case 为主；`Provider` 配置身份/凭据字段永不上线；`Origin` 与 provider `Role` 分离。

## 一、方法（client→core，约 105）

| 族 | 方法 | A 阶段处置 |
| --- | --- | --- |
| 握手 | `initialize` | **做**（Phase 1 契约核心） |
| 生命周期 | `shutdown` | **做** |
| thread | `thread/start` `thread/resume` `thread/list` `thread/listAll` `thread/listArchived` `thread/search` `thread/preview` `thread/fork` `thread/rename` `thread/archive` `thread/delete` `thread/pin` `thread/compact/start` `thread/edit-message` `thread/context-composition` `thread/regenerate-title` | **做**（核心会话面；Phase 1 定 thread/start·resume 形状，其余 handler Phase 2a） |
| thread 组织 | `thread/organization/update` `sessionOrganization/list` `sessionFolder/{create,update,reorder,delete}` | **后置**（多用户/组织缝 §1.7-保留 `owner/parent_id`，不现在搭） |
| turn | `turn/start` `turn/steer` `turn/unsteer` `turn/requeue` `turn/queue` `turn/update-queued` `turn/dequeue` `turn/interrupt` | **做**（干预柱；Phase 1 定四态 steer/queue 形状） |
| run | `run/start` `run/interrupt` | **做**（长任务在 A 内是单轮 run；`Run` 形状待 execution 移植补） |
| item | 见通知（无 request 方法） | — |
| workspace | `workspace/list` `workspace/state/cleanup` | **做** |
| activity（接管） | `activity/list` `activity/takeover` `activity/release` `activity/stop` | **做**（可干预柱，租约+takeoverVersion） |
| user-question（HITL） | `user-question/list` `respond` `cancel` `hold` | **做** |
| process（终端） | `process/{list,read,write,resize,stop}` | **做**（Phase 2 bash/内嵌终端） |
| config | `config/read` | **做**（只读快照） |
| config 写面 | `config/{model,advanced,general}/update` `config/{provider/remove,model-catalog/refresh,model-catalog/providers}` | **后置**（B 配置面） |
| engine | `engine/list` `engine/update` | **做**（单内建引擎，留 `EngineID/Registry` 缝 1） |
| engine 外部认证 | `engine/auth/methods` `engine/authenticate` `engine/auth/cancel` | **不做**（外部引擎宿主后加，缝 1） |
| usage | `usage/overview` `settings/usage` | **后置** |
| 文本工具 | `text/polish` `git/commit-message` | **后置** |
| project | `project/work` `project/session` | **不做**（多-agent 编排，Phase 6/后加，缝 6） |
| sideThread | `sideThread/{open,getHistory,sendMessage,interrupt,reset}` | **不做**（subagent/多-agent） |
| mcp | `mcp/{list,connect,disconnect,refresh}` `mcp/auth/{start,status,finish,remove}` | **不做**（缝 2：ToolExposure 三态附加式接入） |
| plugin | `plugin/*`（package/install、setting、storage、diagnostics、registry、executions、client/request 等 15 项） | **不做**（插件宿主） |
| extension | `extension/catalog/refresh` `extension/package/update` | **不做** |
| skill | `skill/list` | **不做** |
| auth | `auth/xai/login/{start,poll,cancel}` `config/codex/{credentials,models}` | **不做**（厂商订阅/OAuth 后评） |
| device | `device/push_register` `device/push_unregister` | **不做**（remote/relay） |
| browser（反向 core→desktop） | `browser/{cdp,screenshot,open_tab,close_tab,set_visibility,list_tabs,turn_ended,finalize}` | **后置**（U2/Phase 3 浏览器接管；不进 handleLine switch，走反向通道） |

## 二、通知（core→client，约 40）

| 族 | 通知 | A 阶段处置 |
| --- | --- | --- |
| thread | `thread/started` `thread/resumed` `thread/updated` | **做** |
| turn | `turn/started` `turn/queued` `turn/dequeued` `turn/steered` `turn/unsteered` `turn/held` `turn/event` `turn/error` `turn/completed` `turn/usage` | **做**（`turn/usage` 节流） |
| run | `run/started` `run/updated` | **做**（`run/updated` 节流） |
| item | `item/started` `item/completed` `item/removed` `item/agentMessage/{delta,replace}` `item/reasoning/{delta,replace}` `item/toolCall/{delta,outputDelta}` | **做**（delta/replace 两态硬语义） |
| activity | `activity/started` `activity/updated` `activity/control_changed` `activity/stopped` | **做** |
| user-question | `user-question/requested` `user-question/resolved` | **做** |
| browser 反向 | `browser/request_cancelled` `browser/turn_started` | **后置**（U2） |
| config | `config/changed` `config/error` | **后置** |
| agent | `agent/updated` `agent/mailbox` | **不做**（多-agent） |
| sideThread | `sideThread/event` | **不做** |
| mcp/plugin | `mcp/status/updated` `plugin/inventory/changed` | **不做** |

## 三、契约单一来源护栏（Phase 1 落地）

- `protocol.md` ↔ `schemas/app_server/` ↔ `serve` handler 三者同源（B-119 方法表派生 / B-121 声明面 ⊆ 实现且双向）。
- Phase 1 只钉「做」项的**契约形状**（models + fixtures 回放）；「做」项的 handler 在 Phase 2a 物化时同批转绿。
- 「不做/后置」项在 `port-ledger.md` 显式登记，不静默遗漏（§1.5 机制 5）。
