# ADR-0028 — 协议演进规则：加性方法/通知不升版本，破坏性改动才升

状态: accepted
日期: 2026-10-12 | 关联: `docs/architecture/protocol.md` §1 §2 §5、`docs/architecture/overview.md` §8 §14、
`src/questor/serve/app_server.py` 的 `initialize`

## 结论

`qst-app-server` 的版本号只标记**破坏性变化**，规则如下：

- **加性变化不升版本**：新增方法族、新增通知族、给请求/响应/通知**追加可选字段**——
  一律追加进当前版本（`qst-app-server/v0.1`）。客户端通过 `initialize` 回显的
  `methods` 与 `notification_families` 发现能力；客户端义务本就是"容忍未知通知"（`protocol.md` §2）。
- **破坏性变化才升版本**：删除/改名方法、改变既有字段语义或类型、改变必需字段集合、
  改变信封形状——升 `v0.x`，并继续遵守"版本严格相等、不降级兼容"（`protocol.md` §1）。

M4 的全部新增（`task/*` `goal/*` `schedule/*` `evidence/get` 方法族与
`task/status` `plan/updated` `goal/status` `evidence/reported` `notice/schedule` 通知族）
按本规则**不升版本**，直接追加进 `v0.1`。

## 理由与取舍

- **`initialize` 的字段就是为此存在**：它已经回显 `methods` 与 `notification_families`，
  若每次加方法都升版本，这些字段就成了摆设，且 M3 已落成的 stdio/WS/http/前端生成物要全部连带改版。
- **对"计划外大量扩展"是负资产**：M6 外部引擎、M7 插件、M8 渠道未来都会持续加方法；
  一个只标记破坏点的版本号，让扩展的代价停留在"加数据"，而不是"全网改契约版本"。
- **严格相等不等于拒绝加性**：严格相等守的是"客户端与服务端**能互相读懂**"，加性变化不破坏可读性；
  真正需要拒绝的是破坏性差异，而那时版本号会变。

## 被否决的选项

- **每次加方法就升 `v0.x`**：见上——连带改版成本高、且让 `initialize.methods` 失去意义。
- **改为语义化版本 + 兼容协商（capability negotiation 扩到方法级）**：本期只有本机单用户、
  无外部客户端，属"无消费者的形状"（ADR-0020）；留到真出现多端版本错配时再评，须新 ADR。
- **取消版本号、只靠字段探测**：破坏性变化需要显式拒绝点；没有版本号就无法 fail closed。

## 适用条件与失效条件

- **前提**：单会话层、两种传输同源（`protocol.md` §1）；客户端按 `id` 关联并持续读通知。
- **失效信号**：① 出现需要并行维护多个**破坏性**协议版本的真实客户端 → 引入方法级能力协商，须新 ADR；
  ② 加性变化累积到 `initialize` 的 `methods` 列表不可读 → 改为分组/命名空间，须新 ADR。
