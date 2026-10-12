# context —— 模块设计篇（M2.3，进行中）

状态: Layer1 已落盘（2026-10-12）| provenance: `# Reimplements FlowCoder context/{manager,tool_results,replacement,recovery}.py 的语义 — pitfalls: B-24 B-25 B-26 B-27 B-85`
蓝本: `docs/specs/behavior-context-fc.md`（常量与边界行为逐条摘录）| 契约: `data-model.md` v1.2 §5、ADR-0017

## 职责与边界

上下文预算、超预算结果落盘与回读、自适应压缩、压缩边界记录。矩阵上只可 import
`schemas` `gesta` `providers`（structure §5）：**不碰 engine、不读 config**——预算的
输入（用量锚点、能力声明）由调用方给。

本期已落 Layer1（`budget.py` / `replacements.py` / `tool_results.py`）、Layer2 压缩
（`compact.py`）与跨 turn 恢复（`rehydrate.py`）。`memory`/`skills` 的重注入段随各自模块加入。

## 方法与决策

- **投影不落回历史**（B-25 的正解）：`Conversation.history` 永远是原文，发给模型的
  是 `apply_tool_result_budget(...).messages`——一次纯函数投影。因此"模型这一轮到底
  看到什么"可以重算，而"它实际做了什么"在正文里不被改写。`Message`/`ToolResultBlock`
  已改成 frozen dataclass，这条纪律由类型兼管而非靠自觉。
- **决策一旦下达就不回改**：`ReplacementState.representations` 命中即沿用；二次处理
  幂等（同一 id 不再落盘、不再二次加工预览）。没有这条，模型会看到同一条结果的
  两套表示——比超长更糟（B-24/B-25 的实测面）。
- **聚合降序**（B-26）：只对本轮 fresh 动手，已钉住的表示不回溯修改。附带事实：
  单条落在 10K~50K 时先被内联截断，因此聚合 pass 只对"多条小结果"有意义。
- **陈旧裁剪带边界**（B-27）：`stale_boundary_turn` 进状态并进记录。FlowCoder 的
  无状态重算会在恢复后给出不一致的会话视图（它 docstring 自认的 trade-off）。
- **决策落正文而非 sidecar**（ADR-0017）：`context.replacements` 记录经
  `ThreadWriter.add_context_replacements` 写入——写入口单点，`context` 不自己开文件；
  新 kind 与 fold 分支、`ThreadView` 字段的对齐由 B-85 守卫断言（已做负向验证）。
- **同步 IO 的边界**：本包写盘是同步的（复用 gesta 的 O_EXCL 原语），`engine` 在事件
  循环里用 `asyncio.to_thread` 包裹（AGENTS §五"事件循环内禁止阻塞调用"）。
- **与 engine 阈值的分工**：`engine/constants.py` 的 `TOOL_RESULT_SPILL_CHARS` 管**审计面**
  （Item 落盘），本包 `SINGLE_RESULT_CHAR_LIMIT` 管**模型面**（会话内表示）。两个旋钮
  各管一件事，合并它们会让"审计留全量"与"喂模型留摘要"互相妥协（见 `budget.py` docstring）。
- **阈值只住一张表**：`tests/unit/test_context_tool_results.py::test_budget_thresholds_live_in_one_table`
  用 AST 扫本包非 `budget.py` 文件里的 ≥1000 整数字面量（落地当场咬住了 KB 换算的 `1024`）。
- **压缩不自己叫模型**（`compact.py` 的注入形状）：`auto_compact` 只收
  `summarize: Callable[[Sequence[Message]], Awaitable[str]]`。理由除了矩阵（context 不得
  import engine，也不得 import prompts），更实的是：摘要 pass 的提示词属 `prompts`，
  调用它属 `engine`，本包只回答"该不该压、怎么重建"。
- **四种返回都是正常路径**：`noop` / `compacted` / `breaker_open` / `failed`。熔断与失败
  **不把 run 弄挂**——自动压缩停手是可继续的状态，要用 `notice/compact` 说给用户听，
  而不是静默少一次压缩（B-23）。
- **压缩后必须清锚点**：`Conversation.replace_history` 把 `baseline_tokens`/`anchor_count`
  归零，否则拿旧消息数算新历史的尾部（B-28，`tests/unit/test_llm_usage.py` 钉住）。
- **不做清理会话目录**：FlowCoder 压完 `rmtree` 工具结果目录；本项目删不了——那些全文是
  可审计证据与 B-20 逃生门的落点（删了等于自毁）。
- **恢复的重建顺序**（`rehydrate.py`）：Items → 套替换决策 → 按时间应用 boundary；
  `kept_item_ids` 用 Item id 不用字节偏移（偏移会随任何追加失效）。映射不上的
  （合成的工具结果聚合消息）不造假 id，宁少一条重建线索。

## 对应测试

`tests/unit/test_context_tool_results.py`（三档处理、幂等、不改原文、聚合降序、
边界入状态且可重建、阈值表护栏）、`tests/unit/test_context_compact.py`（阈值公式、
前缀退化、配对对齐、熔断与重置、逃生门、提取不丢内容）、`tests/unit/test_llm_usage.py`
（缓存占窗口、锚点语义、换视图清零）、
`tests/integration/test_context_records_replay.py`（决策落盘→重启折回、追加与 seq 稠密、
跨线程写入被拒）、`tests/integration/test_compact_and_resume.py`（**M2.3 出口：压缩后
resume 可恢复**；兼 B-86 全文入正文）、
`tests/architecture/test_fold_kinds_are_projected.py`（B-85 三条对齐 + 负向验证）。
