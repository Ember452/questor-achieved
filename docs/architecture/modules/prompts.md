# prompts —— 模块设计篇（M2.2）

状态: 随开工落盘 | 2026-10-11 | 参照: wuu `prompts/`（形态）；依赖: 无

## 职责与边界

运行时提示词资产：`assets/*.toml`（description + body），`importlib.resources`
加载，`string.Template` 渲染（`$placeholder`——正文大括号不被误当占位符）。
M2.2 只落 engine 当期消费的四件：system_core / converge_message /
max_tokens_escalation / max_tokens_recovery。**文档视距**：plan 提醒随 M4
orchestration、摘要协议随 M2.3 context——不预置未消费的资产。

M2.3 分块装配（ADR-0018）：`system_core` 拆为 `agent_identity` + `questor_rules`，与
`tool_policy` 一起构成**稳定前缀**；`assemble`/`system_assembly` 产出 `PromptAssembly`
（类型住 `schemas/llm.py`，本模块只做资产与装配），`cache_boundary` 之前的块全为稳定块，
违反即抛 `PromptAssemblyError`（B-81）。护栏只断言**边界索引与块归属**，不断言字节。

## 方法与决策

- **缺资产/缺占位符显式爆炸**（PromptNotFoundError/KeyError），不静默渲染空串
  ——提示词缺失是行为缺陷，必须可见。
- **结构护栏**：assets/ 下每个 .toml 必须有非空 description 与 body（防半成品
  混进发布包）；wheel 经 `uv build` + zipfile 检查确认资产随包。
- **护栏反馈闭环的实例**：B-05 形状护栏落地时当场咬住 output_recovery 里
  重复的提示词常量——迁往本模块资产（max_tokens_escalation/recovery），
  单一真相恢复。
