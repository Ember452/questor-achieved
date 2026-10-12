# providers —— 模块设计篇（M2.3）

状态: 随开工落盘 | 2026-10-12 | provenance: `# Reimplements FlowCoder client/{core,resilience,errors,error_mapping}.py + providers/*_streaming.py 的语义 — pitfalls: B-82 B-83 B-84`
关联: `ADR-0016`（选型）、`ADR-0018`（缓存前缀）、`structure.md` §5（providers 只可 import `schemas` `state`）、`docs/notes/2026-10-12-m23-wire-probe.md`（实测事实）

## 职责与边界

模型客户端、用量与能力声明。向上只对内核暴露一个装配入口 `create_model(spec)`；
**不 import config**（`ModelSpec` 由 cli/serve 装配点构造后注入，同 ADR-0012 对
capability 的裁决）；**不 import 任何业务模块**（wire 词汇表取 `schemas.llm`）。

## 分层与文件

| 文件 | 承担 | 为什么这么切 |
| --- | --- | --- |
| `spec.py` | `ModelSpec` + 能力三档解析（配置 > 协议声明 > 保守） | 数值来源必须可标注，否则保守兜底会被当成端点事实（B-82） |
| `errors.py` | `LLMError` 家族 + **状态码优先**的分类表 | 实测 402 的 body 写着 `invalid_request_error`；照 body 归类会丢掉"欠费、重试无用"这个真原因 |
| `sse.py` | 帧解析（字段归属与帧边界） | 只做解析，不碰协议语义——两个协议的差异留在各自文件里 |
| `http.py` | 传输管道：状态码分类、间隔超时、帧流 | 错误映射与超时策略若分散到两个协议里必然各修各的（structure §4 的依赖纠缠信号） |
| `protocols/anthropic.py`、`protocols/openai_chat.py` | 请求体装配 + 帧→`StreamEvent` 翻译 | 一协议一文件；`openai_responses` 后置时不改 port |
| `resilience.py` | 零交付重试窗口 | 重试判据只此一处（B-84） |
| `registry.py` | 协议 → 客户端类 + 韧性包裹 | 新增协议 = 加一个文件 + 登记一行 |

## 方法与决策

- **不接厂商 SDK**（ADR-0016）：翻译层省不掉，SDK 只省下 HTTP 往返；重试/取消语义必须
  自持才能守住"断流不重放"。代价如实承认：请求体装配与流解析自己写、自己测。
- **B-84 的窗口只有一格**：`delivered` 标记在第一个事件交付时置位，此后任何失败只上抛。
  `asyncio.CancelledError` 在 `except LLMError` 之前显式放行——取消不是错误。
  退避不掺随机抖动（单机单用户不构成惊群，抖动只会让测试与真实行为分叉）。
- **两个时钟取大**：本地指数退避与端点的 `retry-after` 取 `max`——建议值优先，但
  `retry-after=0` 不能变成空转。实测错误响应里**没有** `retry-after` 与 `x-ratelimit-*`，
  所以"头缺失"是正常路径而非异常。
- **SSE 的两处刻意取舍**（`sse.py`）：EOF 冲刷无空行的残帧（否则丢 `data: [DONE]`
  终局信号）；单行长度上限（否则端点异常时一行无限增长吃光内存）。
- **`[DONE]` 是哨兵不是 JSON**：各家 OpenAI 兼容端点都会发这一帧，必须先拦再解析——
  拿它去 `json.loads` 会把一次正常终局误报成协议错（本轮实测前写的第一版就踩在这里，
  由 `test_content_and_reasoning_and_tools_stream_in_order` 当场咬住）。
- **截断与损坏要分开处理**：工具参数分片不完整时，终局是 `max_tokens`/`length` 就丢弃
  并记 warning（交给内核的续写），否则上抛 `ProtocolError`——丢弃必须发生在有明确
  截断证据时，不能默认"模型没说话"。
- **能力降级要如实**：`openai-chat-completions` 没有缓存断点概念，声明
  `supports_prompt_cache=False` 并把块拼成单条 system（不假装与 Anthropic 等价保护）。

## 实测边界（已验证与未验证分写）

- **已实测（2026-10-12 复测，详见 `docs/notes/2026-10-12-m23-wire-probe.md`）**：真实 200
  往返；`usage` 分两段到达（`message_start` 给输入与缓存分量、`message_delta` 给输出）；
  `cache_read_input_tokens=3072` ；错误形态 400/402/404/422 与"无 `retry-after`"。
- **已修正的设计说法**：该端点自动缓存前缀并在 usage 里如实回报，`cache_control`
  **不是命中的必要条件**——本模块照旧在可缓存前缀末块打断点（各家机制不同，声明在
  内核侧才能一致取用），但不得声称"加了断点才有命中"（B-81 已按此改写措辞）。
- **预算含义**：缓存命中那部分 token 仍占窗口，所以 `LLMUsage.total_input()` 把
  cache_read + cache_creation 一起计入锚点（B-82 实测补充）。
- **未实测**：`thinking` 开关的真实行为（需支持推理的 Anthropic 本体端点）；
  429 的 `retry-after`（无法主动制造）只按"头可能不存在"实现，由假端点用例覆盖。
- **不得拿响应里的型号名做能力键**：同一次充值账号下，anthropic 路径回
  `deepseek-v4-flash`、openai 路径回 `deepseek-flash`（B-82 的新变体）。

## 对应测试

`tests/unit/test_providers_spec.py`（能力三档与型号名不变窗口）、
`test_providers_sse.py`（帧边界/心跳/CRLF/超长行）、`test_providers_errors.py`
（状态码优先表 + 实测 body 回归）、`test_providers_anthropic.py`（装配 + 流翻译 +
截断两路）、`test_providers_openai_chat.py`（转换/端点规范化/usage-only 尾帧）、
`test_providers_resilience.py`（重试窗口/退避/取消/生命周期）、
`tests/adversarial/test_providers_stream_break.py`（断流不重放、首事件超时）。
