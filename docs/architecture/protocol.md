# Questor 跨进程协议（protocol）

版本: v1.0 | 更新: 2026-10-11 | 状态: accepted（M1 定稿）
关联: `overview.md` §8（草案出处）、`data-model.md`（实体契约）、
`src/questor/schemas/app_server/`（本协议的 JSON Schema 物化）、
`docs/specs/behavior-protocol-wuu.md`（协议形状参照）

**本文件是跨进程边界的唯一真相源**（R4）。改动先改本文并递增版本号。

---

## 1. 传输与信封

- 协议名 `qst-app-server/v0.1`；**版本严格相等，不做降级兼容**（B-60）。
- 两种传输、**同一会话层**（Web 宿主不得拥有第二套契约或私有端点）：
  - 桌面（Tauri sidecar）：**stdio 上的 NDJSON**；
  - 网页（本地）：Gateway 的 **WS/SSE**，默认只绑 `127.0.0.1`。
- 单行 JSON 上限 64 MiB；超限的命令输出走全量日志引用（deferred content）。
- 信封：
  - 请求 `{"id":"...","method":"...","params":{...}}`
  - 响应 `{"id":"...","result":{...}}` / `{"id":"...","error":{"code":"...","message":"..."}}`
  - 通知 `{"method":"...","params":{...}}`（无 id）
- **错误码是字符串**，不假装 JSON-RPC 数值码；业务错误载荷可带
  `error_kind` / `reason` / `model_next_action`（limen 方言，`boundary_denied` 等）。
- stdout 必须干净（禁 banner 与调试日志）；行缓冲有上限。

## 2. 客户端义务

- 按 `id` 关联响应，**请求未决期间持续读通知**，不得假设每行都是最近请求的响应
  （反向请求响应先路由给等待者，B-59）；
- 慢发现/维护由服务端后台化，客户端不得假设方法串行完成（B-62）；
- 未决期间收到的通知必须缓冲处理，不得丢弃。

## 3. 方法表（v0.1）

### 会话与线程

| 方法 | 说明 |
| --- | --- |
| `initialize` | 握手（见 §5） |
| `thread/create` / `thread/list` / `thread/rename` / `thread/archive` / `thread/delete` | 会话管理；删除需 idle（运行中、活跃侧聊拒绝）；归档运行中拒绝 |
| `thread/search` | 跨会话搜索，命中带上下文定位到具体消息 |
| `thread/fork` | `{thread_id, turn_seq, mode: local\|worktree}`；三级历史回退 + live 分叉 |

### 执行

| 方法 | 说明 |
| --- | --- |
| `turn/start` | 发起用户输入，返回 `turn_id` + `run_id` |
| `turn/steer` | 运行中插话；`expected_turn_id` 空=兼容放行、非空不匹配=拒绝（B-64）；`client_id` 幂等（B-63） |
| `turn/queue` | 排队下一条（与 steer 可互转，held work 双 origin，B-65） |
| `turn/dequeue` | 撤回未决 |
| `run/stop` | 取消（传播到进程树，终态 `cancelled`） |
| `session/control` | 接管/暂停/释放（CAS + revision 栅栏；stale 进程不能撤销人的接管） |

### 工作区与工作台

| 方法 | 说明 |
| --- | --- |
| `workspace/status` / `workspace/revision` | 修订号查询（data-model §4） |
| `review/turn_diff` | 某一 turn 的逐文件真实 diff（写时刻持久化的结构化 diff） |
| `files/read` / `files/list` | 读取绑定修订号；不匹配拒绝 |
| `content/read` / `attachment/read` | **deferred content**：大内容按引用延迟取 |
| `selection/annotate` | 选中文字→批注/侧聊/只改这段（源定位 = 修订号 + 字节 offset） |

### 能力与配置

| 方法 | 说明 |
| --- | --- |
| `engine/list` | 引擎目录（四态：unsupported/error/empty/ready；探测零副作用） |
| `config/get` / `config/update` | 分层配置；**permission_mode 等用户专属字段不可由项目层设定** |
| `extensions/list` / `extensions/enable` / `extensions/disable` | M7；关插件即停产品行为 |

## 4. 事件族（服务端 → 客户端通知）

| 通知 | 说明 |
| --- | --- |
| `turn/queued` `turn/steered` `turn/held` | turn 生命周期旁态（data-model §3.1） |
| `turn/usage` | 用量（限流推送，前端自行算速率） |
| `item/started` `item/completed` `item/removed` | Item 生命周期（tool_call/tool_result 含写时刻 diff） |
| `delta` / `replace` | 流式文本双通道 |
| `run/status` | 状态机迁移（含旁态与终态） |
| `notice/compact` | 压缩通知（started/success/noop/失败） |

## 5. `initialize`

- 请求：`{client_version, capabilities:{reverse_rpc:{methods[]}, deferred_notification_content}}`
  ——能力 **opt-in**，不声明不启用（B-61）。
- 响应：
  `{protocol_version:"qst-app-server/v0.1", status:"ready"|"needs_setup", issues:[],
    build:{version, commit}, host:{os, arch}, workspaces:[...], permissions:{mode, sandboxed},
    engines:[...], feature_flags:{...}, max_concurrency:N}`
  ——`needs_setup` 时连接仍可用（配置问题列在 `issues`，修复后由变更通知刷新）。

## 6. 服务端反向请求（server-initiated）

| 方法 | 说明 |
| --- | --- |
| `approval/request` | 收紧型审批（habena）：payload 只带用户可读的中立字段；五态结果
 allow/deny/unsure/failed/cancelled（unsure/failed 不是安全判定，B-56/B-57 同族）；**超时或
 取消即动作不执行** |
| `browser/host` | M8 延后（ADR-0006） |

- 客户端能力白名单之外的反向请求直接失败（opt-in 协商）。

## 7. 错误方言

| error_kind | 场景 | model_next_action 示例 |
| --- | --- | --- |
| `boundary_denied` | limen 拒绝 | "use read-only tools, or tell the user..." |
| `need_execution_authorization` | 编排门 | "待用户「开始执行」后重试" |
| `need_plan_first` | 编排门 | "先调用 plan 落库计划" |
| `stale_revision` | 修订号不匹配 | "re-read the file at the new revision" |
| `protocol_version_mismatch` | 握手失败 | 无（终止） |
| `unknown_method` / `invalid_params` | 信封层 | — |

- 拒绝时返回模型读得懂的理由 + 下一步动作；**审批不得解除硬拒**（B-56）。
