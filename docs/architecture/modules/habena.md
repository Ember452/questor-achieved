# habena —— 模块设计篇（目标态，Phase 2/3 移植）

状态: 设计先行，实现待 wuu 蓝本移植 | 2026-10-14 | provenance 锚: `wuu-main internal/agent/loop.go`（BeforeStep 步界）+ `wuu-main internal/appserver`（`turn/steer|queue|requeue`、`activity/*`）；行为规格 `docs/specs/behavior-review-habena-wuu.md` §2-§3、`behavior-limen-wuu.md`（审批方言）；pitfalls: B-04 B-55 B-56 B-63 B-64 B-65 B-67

> 旧 `src/questor/habena/` 为待替换实现，只读参考；本篇描述 wuu 单锚对齐后的目标态。

## 职责与边界

运行中干预的**缰绳**：插话（steer）、排队（queue/requeue）、审批请求与应答、
activity 接管租约。它决定"用户的话何时进入模型上下文"，但**不做**权限判定——
该不该放行归 limen，怎么说进去归 habena。

## 核心语义（不可丢失的硬件）

| 语义 | 母本锚 | 坑号 |
| --- | --- | --- |
| 插话消费只在**步前边界**（BeforeStep 等价物）：任何时刻提交，只在下一个模型步之前统一注入，不在任意时刻插入在飞的 prompt | `internal/agent/loop.go#L400-401` | B-67 |
| inbox 以 `client_id` 幂等：重复提交只入队一次；内存 seen + 持久双保险 | `session/inbox.go` `INSERT OR IGNORE(client_id)` | B-63 |
| `ExpectedTurnID` 定靶：空=旧客户端兼容放行；非空不匹配当前 turn=拒绝（防 steer 落错轮） | appserver `turn/steer` | B-64 |
| held user work 重启不丢：双 origin（queue/steer）落盘（C3：SQLite `session_inbox`/`held_user_work` 表）、整表替换事务、重启重建 | `held_user_work.go` | B-65 |
| 审批五态 allow/deny/unsure/failed/cancelled；unsure/failed **不是**安全判定、不得当总括授权 | `behavior-limen-wuu` 方言 | B-56 |
| 审批/提问 future 必带超时，前端失联不许挂死循环 | 裁决保留（FlowCoder 300s 经验） | B-04 |
| activity 租约 + `takeoverVersion` 防接管竞态 | wuu `activity/*` 族 | §1.5 机制 4 硬语义 |

## 词表（ADR-0042 取齐 wuu）

方法：`turn/steer`、`turn/queue`、`turn/requeue`、`activity/acquire|release|takeover`、
`user-question/request|respond`；通知：`user-question/requested|resolved`、`run/updated`
（activity 态）。旧自研词表（`turn/interrupt` 等）随 serve 重写作废。

## 取舍与被否决项

- **否决"任意时刻注入"**：看起来响应快，实际会撕裂消息形状（tool_call 与 tool_result
  配对被插话切断=协议违规）；wuu 的步界汇聚是母本答案。
- 审批弹闸的判定逻辑住 limen（B-51 Guard 契约不得返回 ask），habena 只负责**送达与
  回音**——把"ask"实现在 habena = 双实现漂移起点（B-07 同族）。

## 对应测试（移植时物化）

`test_habena_steer` 族（步界消费/幂等/ExpectedTurnID/held_work 重启重建，契约层用例
按 ADR-0044 相容规则只增不减）、`test_habena_steer_adversarial`（同 client_id 重放、
错轮 steer 注入——负向验证配对）。
