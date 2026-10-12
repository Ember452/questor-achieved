# ADR-0016 — providers 传输层：自建 wire 层 over httpx，不接厂商 SDK

状态: accepted
日期: 2026-10-12 | 关联: M2.3 / `overview.md` §6（providers 职责）、`structure.md` §5（providers
只可 import `schemas` `state`）、ADR-0013（依赖引入纪律）、B-82 B-83 B-84、
`docs/specs/behavior-engine-fc.md`

## 结论

M2.3 的模型接入按以下方式落地：

1. **唯一新增运行时依赖 `httpx>=0.27`**（异步流式 HTTP 客户端）；不引入 `openai`、`anthropic`
   等厂商 SDK，也不引入 `aiohttp`。
2. 协议实现落 `src/questor/providers/protocols/`，**一协议一文件**；本期只做两个：
   `anthropic_messages`（`/v1/messages`，SSE）与 `openai_chat_completions`
   （`/chat/completions`，SSE）。`openai_responses` 按同一形状后置，加入时不改 ModelPort。
3. SSE 解析、请求体装配、流事件聚合、错误映射、重试/退避全部由本项目自持
   （`providers/sse.py`、`providers/resilience.py`、`providers/errors.py`）。
4. 模型能力与预算以**声明**承载：`providers/spec.py` 的 `ModelSpec`（协议、model id、base_url、
   凭据、`context_window`、`max_output_default`、`supports_thinking`、`supports_prompt_cache`、
   `tool_choice`）。窗口/上限来源三档：显式配置 > 端点声明 > 保守默认（标注 `conservative`），
   **禁止按厂商标识符硬编码**（B-82）。
5. `providers` 不 import `config`：`ModelSpec` 由上层装配点（cli/serve）从配置构造后注入，
   与 ADR-0012 对 `capability` 的裁决同构。

## 理由与取舍

- **API 形状所有权**：Questor 的 `ModelPort` 要吐统一的 `StreamEvent`（正文增量 / thinking /
  完整工具调用 / 终局+用量），SDK 返回的是厂商对象图，仍需在本侧再翻译一层——翻译层省不掉，
  SDK 只省下 HTTP 往返。FlowCoder 正是反证：它在 SDK 外面又包了一层 `ResilientClient`
  （`client/factory.py#L21-41`），重试/超时/取消语义与 SDK 内建的相互遮蔽。
- **取消与断流语义**：本项目要求"断流不重放"（B-84，data-model §5 与 overview §10），
  重试决策必须自己持有；SDK 的自动重试默认在流中途重放，与三柱里的"可验证"冲突。
- **M6/M3 的传输异质性**：外部引擎（ACP/Claude/Codex）与桌面壳走 stdio JSON-RPC/NDJSON，
  SDK 帮不上；届时 providers 与 adapters 共用自己的流式基础设施更省一次重写。
- **依赖树与审计**：`openai` 与 `anthropic` 各自自带 httpx/pydantic 版本约束，两个 SDK 会让
  `uv.lock` 与 `pip-audit` 的面扩大一倍；本项目刻意极简（ADR-0013 只引三件）。
- **代价（如实承认）**：请求体装配与流解析要自己写、自己测（wire 层测试量 > SDK 方案）；
  各家字段怪癖（reasoning 字段名不一、usage chunk 缺失、`response.failed` 被丢弃）需要逐条
  踩坑并落 `B-NN`。换来的是：模型接入面完全由契约文档控制，升级/加协议不需要等上游发版。

## 被否决的选项

- **`openai` + `anthropic` SDK（照 FlowCoder 现状）**：把 API 形状、重试与取消语义的所有权交给
  厂商；依赖树翻倍；M6 引擎适配器与 M3 stdio 传输复用不上；本项目仍要写翻译层，净收益为负。
- **纯标准库（`urllib` / `asyncio` 自写 HTTP）**：需要自己实现 TLS、连接池、chunked/SSE 解码、
  超时与代理——属 AGENTS §二 (a) 类明令禁止的"重新发明边界层"。
- **`aiohttp`**：能力与 httpx 重叠，但 httpx 的超时模型（读写分别计时）与已声明的 HTTP/2 路径
  更贴合，且 pydantic/starlette 生态同源；多引一个客户端库没有收益。
- **`httpx[http2]`（引 hyper-h2）**：SSE 走 HTTP/1.1 即可，多一层依赖换不到本期的真实收益。
- **把窗口/上限写成 config 项而不做声明**：会让"保守默认"退化成"魔法数散布"（B-05 同族），
  且无法在 `initialize` 里如实回显能力。

## 适用条件与失效条件

**适用**：providers 的全部协议实现；M2.3–M8 期间的模型接入。
**失效信号**：① 出现第三个协议且其 SSE 帧格式与两家的差异大到需要共享抽象（此时按 ADR 抽
`protocols/_common.py`）；② 某厂商只提供 SDK 可达的能力（如双向流式 tool-use），届时单独评审
是否允许该协议目录下引 SDK；③ `httpx` 停止维护或出现无法绕过的安全缺陷。
