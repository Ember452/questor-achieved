# serve —— 模块设计篇（M2.3 雏形，未完）

状态: 雏形已落（2026-10-12）；`turn/start` 通知链的缺陷已定位并修正（原因见下）
关联: `protocol.md`（方法表与事件族的真相源）、ADR-0020（`HandlerCtx` 与 `principal`）、
ADR-0021（出口判据）、B-01 B-60 B-61 B-62 B-85、`overview.md` §8 §14

## 职责与边界

网关与协议服务：矩阵上是最上层组装点，**不得 import `cli`**（否则与 `cli → serve` 构成环，
`tests/architecture/test_dependency_matrix.py::test_matrix_has_no_bidirectional_edges` 守着）。
GUI 能力必须经这里可达——不存在"只有桌面壳能调"的私有端点（overview §14），M3 的 WS/SSE
宿主与桌面 sidecar 共用同一张方法表。

## 分层与文件

| 文件 | 承担 | 为什么这么切 |
| --- | --- | --- |
| `envelope.py` | 字节 ↔ 结构（NDJSON 行、64 MiB 上限、字符串错误码） | 只做转换不碰语义，否则信封规则会在每个 handler 里各抄一份 |
| `dispatch.py` | 方法表 + 每请求一任务 + 行级出口 `push` | B-62（分发不被慢操作串行阻塞）与 B-01（后台任务持强引用并观察异常）只在此处实现一次 |
| `notifications.py` | 内核事件 → 协议通知的唯一映射 | 事件名散在 handler 里就会漂出契约；`PROTOCOL_NOTIFICATIONS` 是给护栏测试的清单 |
| `app_server.py` | 会话层方法（`initialize`/`thread/*`/`turn/start`/`run/stop`） | 生命周期与 IO 都在这里，传输层保持零业务知识 |
| `stdio.py` | NDJSON over stdio 传输 + **stdout 洁净** | 与 M3 的 WS/SSE 平级，换传输不改方法表 |

## 方法与决策

- **`HandlerCtx` 统一 handler 第二参**（ADR-0020）：`principal` 从第一天就在结构里，
  默认取 `platform.node()`（不是用户名——它只是标识，不是凭据）。本期**不写任何鉴权判定**；
  护栏 `test_handler_signature_takes_context_object` 断言的是**签名形状**，将来加判定不用改测试。
- **协议版本严格相等，不降级**（B-60）：不匹配时 `initialize` 直接失败，不做"尽力兼容"。
- **`needs_setup` 不是断线**：配置有问题时连接仍可用，问题列在 `issues`（本期 `issues`
  由装配点传入；config 快照的 `layers_applied`/`stripped` 接入随 cli 的装配点一起做）。
- **通知与响应同一条道**：`Dispatcher.push` 是唯一出口；本轮就是在这里发现并修掉了
  "响应只进内部缓冲、传输层永远收不到"的缺陷（否则 sidecar 会看到"有通知无响应"的半截协议）。
- **不发契约外的事件族**：`Thinking` / `LoopCompleted` / `LoopFailed` / `Converging` 一律
  不入协议（`protocol.md` §4 没有它们的名字；族名要连呈现与持久化形状一起在 M3 定）。
- **方法名合法性对着 `protocol.md` 判**，不对着 JSON 判：schema 的 `method` 字段今天仍是
  自由字符串（扩枚举要重跑生成链，属 M3）。`test_serve_names_are_contracted.py` 直接解析
  契约文档的表格首列——断言的是"实现与真相源不漂移"。

## 已知未完（不当已交付）

1. **已修正的一个**：`turn/start` 一度观测不到任何通知。原因不是"推送链断了"，而是
   `_pump` 是**不被任何一方跟踪的 fire-and-forget 任务**（B-01）：`dispatcher.drain()` 只等
   handler 任务，而 handler 立即返回 —— 测试在 run 还没跑出事件时就去读列表。修正：
   `_runs` 持强引用 + `add_done_callback` 观察异常 + `wait_idle()` 供宿主/测试等待。
2. `run/stop` 只做到"取消任务"；"响应先回、终态后到"的跨传输时序至今没有断言。
3. 反向请求通道（`approval/request`）与 pending 路由表（B-59）随 M3 habena 一起做——
   本期无消费者，不做无消费者的形状。
4. WS/SSE 传输、`thread/rename|archive|delete|show`、`files/*`、`review/*` 属 M3；
   `thread/show` 入表时要同步 `protocol.md` §3（否则契约名护栏会红）。
