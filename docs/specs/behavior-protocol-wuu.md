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
