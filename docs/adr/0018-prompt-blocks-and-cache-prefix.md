# ADR-0018 — 提示词分块与缓存前缀：稳定前缀排在动态尾部之前

状态: accepted
日期: 2026-10-12 | 关联: M2.3 / B-81、`prompts/__init__.py`、`prompts/assets/system_core.toml`、
`engine/loop.py#L264`（`render("system_core")` 单串消费点）、ADR-0016、ADR-0017、
`docs/specs/behavior-context-fc.md`（压缩侧重注入的消费点）

## 结论

`prompts` 从"返回一个字符串"升级为"返回带缓存边界的类型化块序列"：

```python
PromptBlockKind = "agent_identity" | "questor_rules" | "project_rules" | "tool_policy" |
                  "environment" | "task_state" | "active_files" | "memory" | "skill_index"
PromptBlock(kind: PromptBlockKind, text: str, stable: bool)
PromptAssembly(blocks: tuple[PromptBlock, ...], cache_boundary: int)
```

1. **块归属固定**：稳定（进缓存前缀）= `agent_identity` / `questor_rules`（能力边界、上下文管理
   纪律、风格、安全与透明度、工具使用约定）/ `project_rules`（AGENTS.md 等项目指令文件，会话
   内不变）/ `environment`（CWD 与日期——一次会话内视为稳定，易变的仓库状态不进）；
   易变（动态尾部）= `task_state` / `active_files` / `memory` / `skill_index` / `tool_policy` 中
   随档位变化的部分。
2. `cache_boundary` = **最后一个 `stable=True` 块的下标 + 1**，即动态尾部的起点。装配函数保证
   `blocks[:cache_boundary]` 全为 stable、`blocks[cache_boundary:]` 全为 volatile，顺序违反即抛错
   （"稳定在前"是被断言的不变量，不是约定）。
3. provider 侧按能力消费：`anthropic_messages` 对 `blocks[:cache_boundary]` 的末块打
   `cache_control: {"type": "ephemeral"}`；`openai_chat_completions` 拼成单条 system 消息并如实
   声明 `supports_prompt_cache=False`（诚实降级，不假装等价保护）。
4. `context` 压缩后的**重注入**（B-11）复用同一装配，不允许循环里就地拼字符串。
5. 易变内容的生效路径**不挤进 system 前缀**：`task_state` / `active_files` 一类运行态按 wuu 的
   分层——"稳定会话上下文进 system prompt，瞬时运行态作为 request-only 块且不成为持久会话历史"
   （`wuu internal/context/context.go#L1-L8`）；Questor 本期先落 system 的 stable/volatile 分界，
   request-only 投影随 M3 habena 的注入通道一并落地（不做无消费者的半套）。

## 理由与取舍

- **为什么必须在 M2.3 定死**：这是"接口面"而非"功能面"（overview §14 判据三问第 1 条）。
  `ModelPort.stream`、`prompts` 装配、`context` 重组、M6 外部引擎适配器**四方共用**这个形状；
  若本期继续传单串 `system`，将来加缓存要同时改 port、循环、压缩与适配器——是重写而不是搬运。
- **实测依据**：FlowCoder 的 system 是全量单串拼装
  （`agent/core.py#L1009-1017`：`SYSTEM_PROMPT` + 项目指令文件 + 技能 + 记忆 + scratchpad），
  其中会变的与不变的混在一起，Anthropic 侧没有任何缓存断点，等于每次请求整个 system 前缀重新计费。
  对照 wuu：`internal/context/context.go#L56-L58` 明确 CWD 与日期算稳定会话输入、git 字段易变故
  默认不采集；`#L66-L80` 用 `BlockKind` 给块分类——本 ADR 的类型化块即取自这一形状（重写实现）。
- **代价**：块边界是新的不变量，需要护栏测试（断言**边界索引与块 kind 归属**，不断言字节——
  内容会改、边界含义不变，避免把测试写成文案复述，AGENTS §四 护栏准入判据）。

## 被否决的选项

- **继续单串 `system`**：provider 无法标缓存断点；压缩重组时只能整串重发；实测缓存不命中（B-81）。
- **per-call 全量重建 system**：把项目指令文件读取与规则拼装塞进每次模型调用（FlowCoder 的
  `_build_system_prompt` 在会话内重建一次已属勉强），既慢又让"提示词是什么"不可审计。
- **把缓存做成 config 开关（`prompt_cache: true/false`）**：能力是端点属性不是用户偏好；
  开关会变成"用户可关掉的诚实性"，且 providers 已用 `supports_prompt_cache` 声明表达同一事实。
- **让 provider 自己决定哪段可缓存**：把语义（哪些内容稳定）交给传输层，等于两处真相；
  稳定性判定必须在 `prompts` 侧做出。

## 适用条件与失效条件

**适用**：M2.3 起所有 system 提示词的装配与消费；`context` 的压缩重组；M6 引擎适配器的
instructions 透传（不得静默丢弃）。
**触发重新评审**：① 端点提供比"单断点"更强的缓存控制（多断点/TTL 可调）→ 扩 `PromptAssembly`
字段而非改块语义；② 出现第二类稳定内容（如按工具集派生的规则块）→ 重评边界计算规则。
