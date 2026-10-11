# behavior-context-fc —— FlowCoder 上下文压缩行为规格（Questor `context` 蓝本）

来源：FlowCoder `src/flowcoder/context/manager.py`（421 行）+ `context/tool_results.py`（322 行）。
扫描日期 2026-10-11。Questor 模块归属：`context`。

---

## 常量表（重写时集中为 Questor 的预算常量表，防 B-05）

| 常量 | 值 | 语义 | 证据 |
| --- | --- | --- | --- |
| `SUMMARY_OUTPUT_RESERVE` | 20_000 | 给摘要输出预留的窗口 | `context/manager.py#L68` |
| `AUTO_COMPACT_SAFETY_MARGIN` | 13_000 | 自动压缩触发冗余 | `context/manager.py#L69` |
| `MANUAL_COMPACT_SAFETY_MARGIN` | 3_000 | 手动压缩触发冗余 | `context/manager.py#L70` |
| `KEEP_RECENT_TOKENS` | 10_000 | 尾部原文保留窗口（token） | `context/manager.py#L76` |
| `MIN_KEEP_MESSAGES` | 5 | 尾部保留保底条数 | `context/manager.py#L77` |
| `KEEP_MAX_TOKENS` | 40_000 | 保留窗口硬上限 | `context/manager.py#L78` |
| `MIN_SUMMARIZE_PREFIX_TOKENS` | 2_000 | 前缀低于此不压缩 | `context/manager.py#L82` |
| `SINGLE_RESULT_CHAR_LIMIT` | 50_000 | 单条结果落盘阈值 | `context/tool_results.py#L22` |
| `INLINE_RESULT_CHAR_LIMIT` | 10_000 | 单条结果内联截断阈值 | `context/tool_results.py#L23` |
| `AGGREGATE_CHAR_LIMIT` | 200_000 | 一轮聚合阈值 | `context/tool_results.py#L24` |
| `PREVIEW_CHARS` | 2_000 | 落盘预览长度 | `context/tool_results.py#L25` |
| `KEEP_RECENT_TURNS` | 10 | 陈旧裁剪保留轮数 | `context/tool_results.py#L27` |
| `OLD_RESULT_SNIP_CHARS` | 2_000 | 陈旧结果裁剪长度 | `context/tool_results.py#L28` |

## Layer 2：auto-compact（全对话摘要）

- **触发**：`current_tokens >= window - 20_000 - 13_000`（手动为 -3_000）；阈值锚点优先
  **真实 API 用量**（上次计费基准 + 新增消息字符估算），冷启动退化为全 history 字符估算
  （`context/manager.py#L116-124,L307-310`）。
- **保留窗口**：从尾部回溯累加，保底条件 = token 达 10_000 **或** 条数达 5（先到先停）；
  硬上限 40_000（但**绝不拒绝最后一条消息**，即使它单独超限，`#L219-234`）；
  keep_start 回退对齐 tool_use/tool_result 配对——**绝不保留悬空 tool_result**
  （宁可多留一对，`#L239-255`）。
- **前缀过小退化为不压缩**（keep_start<=0 或摘要回收空间 < 2_000 token）——避免
  "压了个寂寞"（`#L258-262,L326-329`）。
- **摘要协议**：9 段结构化摘要（主要请求/关键概念/文件代码/错误修复/解决过程/
  **所有用户消息原文保留不可改写**/待办/当前工作/下一步），`<analysis>` 段丢弃、
  `<summary>` 段保留，标签缺失时原样返回全文（`#L127-155`）。
- **重建消息**：摘要正文 + "近期消息已原样保留" + **transcript 路径逃生门**
  （"需要压缩前细节请读完整会话记录：<path>"）+ 恢复附件（`#L158-176`）。
- **边界行为**：
  - `CompactBoundary{summary, keep}` 是纯数据，写操作（内联进 compact_boundary 记录）
    解耦给 session 层，使 auto_compact 保持纯粹、resume 可重建（`#L89-97`）；
  - 熔断器：连续 3 次摘要失败 → open，自动压缩拒绝并提示手动处理（`#L270-282,L315-316`）；
  - 手动压缩绕过阈值与熔断（`manual=True`，`#L305-316`）。
- **坑**：B-20（transcript 逃生门）、B-21（配对对齐）、B-22（前缀过小）、B-23（熔断）、
  B-28（阈值锚点）、B-29（摘要协议）。

### Questor 采纳决定
全收。`CompactBoundary` 纯数据 + session 层落盘的解耦沿用（正好对接 Questor 的 gesta
append-only 记录）；摘要 prompt 的"用户消息原文不可改写"是铁律级要求。

## Layer 1：工具结果预算（不 mutate 原对话）

- **三档处理**（fresh 结果）：>50K 字符 → 落盘 + `<persisted-output>` 预览（2KB）；
  >10K → 内联截断 + "(output truncated)"；否则原样（`context/tool_results.py#L93-101`）。
- **落盘幂等**：`os.O_EXCL`——同一 tool_use_id 只写一次，重复调用静默跳过不覆盖
  （`#L66-76`）。
- **跨轮决策持久**：`ContentReplacementState.replacements/seen_ids` 让"已替换"在后续轮
  保持替换、已见过的结果不再重复判定；**Design B：不 mutate 原 conversation**，返回新
  ConversationManager，原始 history 完整保留（`#L104-117`）。
- **两遍预算 + 陈旧裁剪**：Pass 1 单条超限落盘；Pass 2 聚合 >200K 时按大小**降序**逐个
  替换直到达标（`#L146-183`）；Pass 3 陈旧消息裁剪（保留最近 10 轮、旧结果剪到 2K）在
  新 history 上**无状态**运行——边界 drift 是 docstring 自认的已知 trade-off
  （`#L112-114`）。
- **清理**：会话目录整体 rmtree 重建（`#L60-63`）。
- **坑**：B-24（O_EXCL 幂等）、B-25（跨轮决策持久 + 不 mutate 原始对话）、B-26（聚合降序
  替换）、B-27（Pass 3 无状态 drift）。

### Questor 采纳决定
全收，一处收紧：Questor 的陈旧裁剪若实现，**必须把裁剪边界记进状态**（不继承 FlowCoder
的无状态 trade-off，见 B-27 的采纳标注）。落盘目录对接 `~/.questor` 会话工作文件带过期
语义（overview §10）。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-20 | context | 压缩重建消息必须带 transcript 路径逃生门——摘要有损，细节必须可达 | `context/manager.py#L158-176` |
| B-21 | context | 保留窗口绝不留悬空 tool_result：keep_start 回退到配对 assistant，宁可多留一对 | `context/manager.py#L239-255` |
| B-22 | context | 摘要前缀回收空间低于阈值时退化为不压缩，防"压了个寂寞" | `context/manager.py#L258-262,L326-329` |
| B-23 | context | 压缩熔断器连续失败 3 次后 open，自动压缩拒绝并提示手动 | `context/manager.py#L270-282,L315-316` |
| B-24 | context | 大结果落盘用 O_EXCL 幂等写：同 tool_use_id 只写一次，重复静默跳过 | `context/tool_results.py#L66-76` |
| B-25 | context | 替换决策跨轮持久（seen/replacements），且绝不 mutate 原始对话——重写实现时同构保证 | `context/tool_results.py#L104-117,L121-134` |
| B-26 | context | 聚合超限按单条大小降序逐个落盘替换直到达标 | `context/tool_results.py#L159-183` |
| B-27 | context | 陈旧裁剪若实现必须把边界记进状态——FlowCoder 无状态跑法自认 drift trade-off | `context/tool_results.py#L112-114` |
| B-28 | context | 压缩阈值锚点优先真实 API 用量，冷启动退化字符估算 | `context/manager.py#L307-310` |
| B-29 | context | 摘要协议必须含"用户消息原文不可改写"约束与结构化分段 | `context/manager.py#L127-146` |
