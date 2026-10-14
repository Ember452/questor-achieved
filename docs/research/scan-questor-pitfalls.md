# Questor 重构前知识提取（只读扫描产出）

## 第零部分 · 零基础导读（没接触项目的人先读这一段）

### 0.1 这份文档是什么、给谁用
Questor 已写完一版（内核 M2–M5 跑通、~560 测试全绿），但作者决定**彻底重构：现有代码一行不留，
全部参照 WUU 从 Python 侧重写**。本文 = 把"旧代码里踩出来的、扔掉可惜的经验"抽成**知识**，
喂给①新计划②未来的测试。三类东西要分清：**代码扔掉、经验留下、决策当约束用**。

### 0.2 Questor 是个什么东西（一句话 + 三柱）
**跑在自己电脑上的"可审计 AI Agent 工作站"**：Agent 在本地项目上长活，过程全部摊开、随时能插手、跑完能验收。
一切功能必须服务以下三柱之一，优先级固定、冲突按序让位（本贯穿全篇的"铁律 1 诚实呈现"即来自第三柱）:

| 柱 | 承诺 | "可审计"具体指 |
| --- | --- | --- |
| **可见 Visible** | 读了哪些文件/跑了哪些命令/改了哪几行全在眼前 | 磁盘**真实 diff**、命令**真实输出**、Agent 正在用的终端与页面 |
| **可干预 Intervenable** | 运行中能改方向/接管/中止/分叉 | 插话何时被消费、接管后任务是否真停、分叉从哪一版起 |
| **可验证 Verifiable** | "它说做完了"必须能指回证据 | 声称通过的验证命令与当时**录得的真实输出**并排核对，不轻信 |

**核心纪律（读坑之前必懂）**："透明度恒为最大，分级的是写域"——权限三档只限制"能碰什么"，
**绝不用于少显示**；任何"为界面简洁而隐藏过程"直接打回。大量坑（B-88/B-101/B-110 等）都是这条的具象化。

### 0.3 三个参照项目（"学费"从哪来）与"对齐 WUU"的含义
| 代号 | 语言 | 角色（借什么 / 不借什么） |
| --- | --- | --- |
| **WUU**（`wuu-main/`） | **Go** | 桌面端形态与权限三档语义的**最高标准**；借协议形状/权限档/工具输出/会话操作**规格**；**不借任何代码**（Go→Python 只有重实现、无迁移）。本次重构"全面对齐 WUU"即以此为准 |
| **EvoFlow**（`EvoFlow-main/`） | Python | 借编排/验收**行为规格**、边界层已知失败模式、桌面壳工程骨架；**不借**代码及其 LangGraph 底座依赖 |
| **FlowCoder**（另一路径） | Python | 借 agent 循环/工具/权限/沙箱/压缩**行为规格** + 当**对照评测基线**；**不借**代码（引擎必须归本项目所有） |

总策略：**不照搬任何代码、全部重新实现**；参照项目的价值是"已付过的学费"，拆成坑目录+行为规格+护栏，而不是搬进来。

### 0.4 模块地图（拉丁名怎么读、各管什么）
项目用拉丁词给内部模块命名（不对外发布、不受包名占用约束）。新实现沿用同一职责划分：

| 模块 | 拉丁义 | 承担语义 |
| --- | --- | --- |
| `engine` | — | 自研 agent 循环、事件流、turn 生命周期 |
| `tools` | — | 工具登记与执行（run/read/write/edit/search…） |
| `limen` | 门槛 | **唯一权威权限门**与写域边界（三档判定） |
| `habena` | 缰绳 | 运行中插话、接管、暂停 |
| `vigilia` | 夜间班次 | 无人值守长跑与调度、僵尸清扫 |
| `gesta` | 行事簿 | 会话记录（append-only JSONL）与验收导出 |
| `review` | — | 真实 diff、工作区修订号、turn↔revision 绑定 |
| `evidence` | — | 验收证据：声称 vs 当时录得真实输出并排核对 |
| `orchestration` | — | Plan→执行→验收/打回（Task/Goal 状态机） |
| `serve`/`cli` | — | 协议服务（stdio/WS）与命令行入口 |
| `context`/`state`/`schemas`/`providers`/`prompts`/`config`/`secrets`/`workspaces` | — | 上下文压缩 / 路径·原子写·锁 / 数据契约 / 模型接入 / 提示词 / 配置 / 凭据 / 工作区 |

### 0.5 术语与内部代码速查（本文与 questor 文档里反复出现）
| 记号 | 含义 |
| --- | --- |
| `B-NN` | **坑目录编号**，唯一真相源在 `docs/specs/pitfalls.md`；每条必有一个"对应测试" |
| `ADR-NNNN` | **架构决策记录**（`docs/adr/`）；状态 `accepted`/`proposed`(待裁)/`superseded by`/`moot` |
| `covered` / `open` / `待落` | 坑的测试已回填 / 未回填 / 允许暂标未来落 |
| `AGENTS.md §一~§七` | 仓库工程纪律文档：§一铁律（1 诚实呈现/3 不隐藏过程）、§二扫描三资产与复用三分法、§三"同一事实禁止两套真相"、§四门禁与护栏准入、§五异步纪律与出口判据、§六分支保护、§七文档改动顺序 |
| 复用三分法 `(a)/(b)/(c)` | (a) 边界层="只重实现不重发明策略"、(b) 语义与契约="必须新写"、(c) UI 与工程="搬设计搬状态表、代码新写" |
| `R1`/`R4` | 结构不变量：R1 依赖矩阵可执行形式、R4 前端类型由 schema 生成（非手写 DTO） |
| `F-NN` / `R-NN` | 代码审查发现编号 / phase-u 计划风险编号（本文引用如"审查 F5"、"R-13"） |
| `fc` / `ef` / `wuu`（behavior 文件名后缀） | 该行为规格的来源项目：FlowCoder / EvoFlow / WUU |
| `per-turn 级` vs `工作区级` | Questor 的 Review 审计"一轮 agent 循环的产出"，WUU 审计"整个工作区未提交改动"——借 WUU 视觉不借其语义 |
| `Go→Python` | WUU 是 Go、本项目是 Python；不存在"移植代码"，只有"照规格重写" |

### 0.6 已知文档债（新人会撞上，先说明）
`README.md` 仍写"**Pre-alpha、src 空、仓库只有命名与复用决策**"，但 `overview.md` 已是 v0.2、
M2–M5 内核已建成、~560 测试通过。**两处自相矛盾**——以 overview 与实际源码树为准，README 是未回写的陈旧件。

### 0.7 怎么读全文
第一部分是**最高价值资产**（坑台账，逐条对应必写测试）→ 第二部分是**架构约束**（哪些决策接着用、哪些作废）
→ 第三部分是**行为规格与教训**（参照实现的输入→输出→边界）→ 第四部分是**带走/扔掉清单**
→ 第五部分是**散落在注释里、台账没编号的怪癖**（写代码时最容易漏）。

---

> 目的：Questor（`d:\DEVELOP\My-project\questor`）将**彻底重构、代码基本废弃**，本文把过去手写的
> **踩坑经验、行为规格、架构裁决**提取为可迁移"知识"，喂给新计划与未来测试。
> 依据：项目记忆「彻底重构与零代码复用原则」「代码重构与知识留存原则」——现有代码一行不留，
> 只保留坑台账、ADR 纪律与思路，新实现参照 WUU 源码从零移植。
> 扫描范围：`docs/specs/pitfalls.md`、`docs/specs/behavior-*.md`（14 份）、`docs/adr/`（全部 + README）、
> `docs/notes/`（全部 + README）、以及 `src`/`ui`/`desktop`/`scripts`/`evals`/`tests/architecture` 注释中的 B-NN 引用。
> 编号纪律提醒：`B-NN` 以 `pitfalls.md` 为**唯一真相源**；各 behavior-*.md 底部小表存在历史偏移
> （如 behavior-limen 曾把 B-50～B-58 全标成 B-50、behavior-permissions 曾把 B-30～B-34 混标），
> 已在 2026-10-11 对齐；`src` 注释里的个别编号（如 AppShell.tsx 写 B-97、review/diff.py 写 B-93）
> 与 pitfalls.md 台账存在漂移，**以台账为准**。

---

## 第一部分 · 坑台账（B-01 ～ B-122 全量）

格式：**坑描述 / 触发条件** → **当时怎么解** → **新实现必须对应的测试**（`covered` 表示已有测试、`open` 待落、`moot` 不再适用）。
归属模块列在括号内。

| B-NN（归属） | 坑描述 / 触发条件 | 当时怎么解 | 新实现必须对应的测试 |
| --- | --- | --- | --- |
| B-01 (engine) | fire-and-forget 的 `ensure_future` 任务被 GC 中途回收，异常静默丢失 | 统一走 `_spawn_bg`：持强引用集合 + done callback 记日志 | 待落（后台任务收口散见于 serve/loop 测试） |
| B-02 (engine) | 预算收敛轮撤光全部工具 schema 后模型仍幻觉调用 → 零产出强杀 | 收敛轮**保留只读工具**（对 FlowCoder 缺陷的修正） | `test_engine_loop.py::test_budget_converge_keeps_readonly_tools`、`::test_converging_round_still_requesting_tools_fails` |
| B-03 (engine) | 并行批清零 unknown 计数 → "每轮夹一个幻觉调用"逃逸 ≥3 熔断 | 并行批**不清零**熔断计数，只有串行成功路径才清零 | `test_engine_loop.py::test_unknown_tool_breaker_fails_run`、`test_tools_executor.py::test_partition_consecutive_safe_merge` |
| B-04 (habena) | 审批/提问 future 无超时 → 前端失联挂死整个循环 | future 带超时（FlowCoder 300s） | 待落（habena M3） |
| B-05 (engine) | 循环阈值常量散布各处（50/3/300s/5） | 集中一张预算常量表 `engine/constants.py` | `test_engine_shape.py::test_thresholds_live_in_constants_table` |
| B-06 (engine) | 1076 行单文件巨型函数 | 拆显式状态机，方法各司一职 | `test_engine_shape.py::test_no_giant_functions_in_loop` |
| B-07 (engine) | 子代理与交互路径双实现漂移（子代理无预算闸/熔断/恢复） | 拒绝双实现，共用同一状态机 | 待落（M2.2 单一状态机即满足，子代理物化时回填） |
| B-08 (engine) | max_tokens 触顶恢复状态每 run 重置、恢复无上限 | 先提输出上限再注入续写提示，恢复轮次设上限 | `test_engine_loop.py::test_output_recovery_escalates_once_then_retries`、`::test_output_recovery_gives_up_after_budget` |
| B-09 (engine) | 记忆观察/提取阻塞主循环 | 走后台任务，重提取按轮次间隔节流 | 待落（memory M4+） |
| B-10 (limen) | 权限门内嵌模式特例（把 plan 文件路径塞进 checker 字段） | 模式提醒归循环层，门不做特例 | `test_limen_matrix.py::test_boundary_table_matches_overview_s9`（边界表无 Plan 特例档） |
| B-11 (engine) | 压缩成功后不重注入环境/指令/记忆 → 丢工作集 | 压缩后复用同一装配重注入 | `test_context_compact.py::test_rebuilt_history_carries_transcript_escape_hatch`（covered） |
| B-12 (tools) | 退出码语义映射判错段 | 按**管道最后一段**判定，覆盖 `VAR=` 前缀与 basename 提取；grep/diff/find 类阈值是 2 | `test_tools_run_process.py::test_grep_pipe_last_segment_exit1_is_no_match` 等 3 条 |
| B-13 (tools) | 命令超时不回收子进程 → 僵尸进程 | 超时 kill+wait 回收（Job Object/进程组） | `test_tools_run_process.py::test_job_object_kills_whole_tree`、`::test_run_timeout_moves_to_background` |
| B-14 (tools) | 二进制输出炸 decode | 解码 `errors="replace"` | `test_tools_run_process.py::test_format_output_decodes_invalid_utf8` |
| B-15 (tools) | 并行批单工具异常拖垮整批 | `gather(return_exceptions=True)` 降级为错误结果 | `test_tools_executor.py::test_parallel_batch_survives_single_failure` |
| B-16 (tools) | 分区重排破坏模型发出顺序语义 | "连续安全工具合并"，非安全工具打断并行段 | `test_tools_executor.py::test_partition_consecutive_safe_merge` |
| B-17 (tools) | 禁用工具与未知工具混同，都计入熔断 | 只有**未知**计入熔断，禁用走错误结果 | `test_tools_executor.py::test_unknown_tool_flagged_not_disabled`、`::test_disabled_tool_is_not_unknown` |
| B-18 (tools) | 沙箱模式切换失败静默降级 | 保持原模式并返回明确错误 | `test_tools_run_process.py::test_run_success_exit_code_and_sections`（模式切换语义随 M8 补全） |
| B-19 (tools) | 输出双空产生空串歧义 | stdout/stderr 分段标注，双空显式 `(no output)` | `test_tools_run_process.py::test_format_output_sections_and_no_output` |
| B-20 (context) | 压缩丢细节无逃生门 | 重建消息带 transcript 路径逃生门 | `test_context_compact.py::...transcript_escape_hatch`、`test_compact_and_resume.py::test_compaction_then_resume_rebuilds_from_disk`（covered） |
| B-21 (context) | 保留窗口留悬空 tool_result | keep_start 回退到配对 assistant，宁多留一对 | `test_context_compact.py::test_keep_window_never_splits_a_tool_pair`（covered） |
| B-22 (context) | "压了个寂寞"（回收空间极小仍压缩） | 摘要前缀回收低于阈值退化为不压缩 | `test_context_compact.py::test_small_prefix_degrades_to_noop`（covered） |
| B-23 (context) | 压缩反复失败无兜底 | 连续失败 3 次熔断 open，自动压缩拒绝并提示手动 | `test_context_compact.py::test_breaker_opens_after_consecutive_failures_and_blocks`、`::test_success_resets_the_breaker`（covered） |
| B-24 (context) | 大结果落盘重复写/覆盖 | `os.O_EXCL` 幂等写：同 tool_use_id 只写一次，重复静默跳过 | `test_context_tool_results.py::test_second_pass_is_idempotent...`、`test_state_atomic.py::test_write_excl_first_true_second_false`（covered） |
| B-25 (context) | 替换决策 mutate 原始对话且不跨轮 | seen/replacements 跨轮持久；绝不 mutate（frozen 类型兼管） | `test_context_tool_results.py::test_original_history_objects_are_untouched` 等（covered） |
| B-26 (context) | 聚合超限替换顺序随意 | 按单条大小**降序**逐条落盘替换直到达标 | `test_context_tool_results.py::test_aggregate_overflow_spills_largest_first`（covered） |
| B-27 (context) | 陈旧裁剪无状态跑法自认 drift | 若实现必须把裁剪边界记进状态 | `test_context_tool_results.py::test_stale_boundary_is_recorded_in_state`（covered） |
| B-28 (context) | 压缩阈值不信 API 用量 | 优先真实 API 用量，冷启动退化字符估算；缓存命中量也占窗口 | `test_context_compact.py::test_compaction_actually_shrinks_the_estimate`、`test_llm_usage.py::test_total_input_counts_cache`（covered） |
| B-29 (context) | 摘要改写用户消息 | 摘要协议含"用户消息原文不可改写"约束 + 结构化 9 段 | 资产 `prompts/assets/summary_protocol.toml`；`test_context_compact.py::test_summary_extraction_is_lossless_on_missing_tags`（covered） |
| B-30 (limen) | 不存在路径拼回尾部重新引入 `..` 穿越沙箱 | resolve 祖先后对完整结果再 `resolve(strict=False)` 重查 | `test_limen_reachability.py::test_b30_double_resolve_rejects_dotdot_tail`、`::test_b30_dotdot_tail_into_sibling` |
| B-31 (limen) | 触路径工具缺路径参数被跳过 | 缺路径视为 **deny** 而非跳过，unconfined 同样适用 | `test_limen_reachability.py::test_check_path_missing_param_denied`、`test_limen_matrix.py::test_missing_path_denied_not_skipped` |
| B-32 (limen) | 危险命令散落 if/else | 结构化正则清单（可追加） | `test_limen_guards.py::test_dangerous_commands_detected`、`::test_benign_commands_pass` |
| B-33 (limen) | 档位语义分支散布 | 显式表驱动（模式 × 工具类矩阵） | `test_limen_matrix.py::test_boundary_table_matches_overview_s9` |
| B-34 (limen) | 判定层合并回溯 | 短路先决、命中即返回，层间不合并 | `test_limen_matrix.py::test_sensitive_write_denied_every_mode` |
| B-35 (serve/M8) | 命令超时单层有逃逸窗口 | 双层：容器内 TERM→KILL + 宿主 grace 兜底 | 待落（M8） |
| B-36 (serve/M8) | 容器复用串状态 | 归还即销毁重建；池统一打 label 供 reaper 清遗留 | 待落（M8） |
| B-37 (evals) | 评测不可复现 / 超时回喂垃圾信息 | 默认温度 0；超时失败不回喂 | 待落 |
| B-38 (orchestration) | 状态迁移 Hook 异常只 print 吞掉 | （M4 裁定：Questor 未引入 hook 注册表，无适用对象） | moot；将来若引入 hook 必须走 logging 上浮观测面 |
| B-39 (orchestration) | 重载领域词命名（plans 撞名） | （M4 裁定：Questor 无模型套餐目录，无撞名对象） | moot；命名纪律由评审保证 |
| B-40 (vigilia) | 无 offset 重查同一 top-N 紧密空转 | 清扫分批游标，一批一间隔 | `test_vigilia_sweep.py::test_next_batch_advances_cursor_without_revisiting` 等（covered） |
| B-41 (vigilia) | cron 依赖本地时钟（休眠/漂移敏感） | 同分钟去重为唯一防重放闸 | `test_vigilia_scheduler.py::test_cron_dedupes_same_minute`、`::test_cron_matches_and_minute_slot`（covered） |
| B-42 (vigilia) | once 任务重放 | 触发成功立即幂等标记 once_fired，标记失败记 warning 不阻塞 | `test_vigilia_scheduler.py::test_once_fires_once_and_is_idempotent`（covered） |
| B-43 (orchestration) | 编排门抛异常导致静默失败/整 run 失败 | 返回结构化错误载荷（error_code/message/hint），模型可读可重试 | `test_orchestration_gate.py::test_create_task_without_plan_needs_plan_first` 等（covered） |
| B-44 (vigilia) | 状态真值在运行时侧 → 重启必有 stale running | 启动 + 周期双 reconcile（本进程在跑的绝不碰） | `test_vigilia_sweep.py::test_startup_reconcile_collects_all_and_resets_cursor` 等（covered） |
| B-45 (gesta) | gate/审批消息与用户跟进行定序错乱 | 先持久化定序，用户跟进行排其后 | `test_gesta_store.py::test_turn_seq_single_point_allocation`（covered） |
| B-46 (gesta) | 会话正文做百表 SQLite 单体（EvoFlow 2191 行/123 表） | append-only JSONL 真相源 + SQLite 仅可重建索引 | `test_gesta_append_only.py`、`test_gesta_store.py::test_index_matches_rebuild_and_self_heals`（covered） |
| B-47 (gesta) | 断线无恢复位 | 事件流独立镜像/持久化，seq 作续传锚点 | `test_gesta_roundtrip.py::test_full_lifecycle_replay`（covered） |
| B-48 (M7 mcp/记忆) | FTS5 unicode61 把中文连成整串 | CJK bigram + OR 引号技巧 | 待落（M7） |
| B-49 (vigilia) | tick 重入同一任务 | per-task asyncio.Lock 字典 + 守卫锁 | `test_vigilia_scheduler.py::test_per_task_lock_prevents_concurrent_fire`（covered） |
| B-50 (limen) | read_only 浏览器粒度错 | 拦 navigate/click/type、放 observe/screenshot（ReadOnly 短路在 mutates 之前） | `test_tools_impl.py::test_todo_granularity_in_read_only_mode` |
| B-51 (limen) | Guard 阻塞等输入或返回 ask | 硬判与审批严格分层，门无 ask | `test_limen_matrix.py::test_gate_has_no_ask_effect`（AST 扫无 'ask' 字面量） |
| B-52 (limen) | 拒绝只说不行 | 拒绝必带 model_next_action（error_kind+reason+model_next_action） | `test_limen_matrix.py::test_file_read_outside_root_denied_when_enforced` |
| B-53 (limen) | 子串误伤 credentials.go / symlink 绕过 | 敏感路径按段匹配 + 源码扩展名豁免 | `test_limen_guards.py::test_credential_directory_is_sensitive` 等 3 条 |
| B-54 (limen) | 档位解除守卫 | 敏感写包括 unconfined 一律拒；unconfined 读降级脱敏 | `test_limen_guards.py::test_write_blocked_all_modes` 等（covered 侧见矩阵测试） |
| B-55 (habena) | 审批被提权绕过 | 硬拒三件：凭据调用、参数试图 permission_mode 提权、敏感路径写；判定用目标非内容 | 待落 |
| B-56 (habena) | unsure/failed 当总括授权 | 审批五态 allow/deny/unsure/failed/cancelled；unsure/failed 不是安全判定 | 待落 |
| B-57 (config) | 仓库配置提权 | 分层合并 strip 用户专属安全字段（provider/凭据/permission_mode） | `test_config_loader.py::test_user_only_fields_stripped_from_project_layers`（covered） |
| B-58 (limen) | 沙箱 partial enforcement | 契约必须 full enforcement，partial 拒绝；不支持平台 fail closed | `test_config_loader.py::test_user_only_fields_stripped_from_project_layers`（M2.1 已落） |
| B-59 (serve) | 反向请求响应被 unknown method 吞 | 先路由给 pending 调用表等待者，再进 method switch | 待落 |
| B-60 (serve) | 协议版本降级兼容 | 严格相等，不降级 | `test_serve_app_server.py::test_initialize_rejects_version_mismatch`（covered） |
| B-61 (serve) | deferred/reverse 默认开启 | 都是客户端 opt-in 能力声明 | 待落 |
| B-62 (serve) | 慢发现卡住串行分发 | 后台化（startBackground 等价物） | 待落 |
| B-63 (habena) | 插话重复入队 | client_id 幂等：内存 seen + held_work 落盘，同 client_id 只入队一次 | `test_habena_steer_adversarial.py::test_second_submit_same_client_id_is_idempotent` 等（covered） |
| B-64 (habena) | steer 落到错误 turn | ExpectedTurnID：空=旧客户端兼容放行，非空不匹配当前 turn=拒绝 | `test_habena_steer_adversarial.py::test_steer_with_wrong_expected_turn_is_rejected`（covered） |
| B-65 (habena) | held work 重启丢失 | 双 origin（queue/steer）落盘，整表替换事务，重启重建 | `schemas/habena.py`+`gesta/store.py`；`test_habena_steer.py::test_steer_consumed_at_iteration_boundary`（covered） |
| B-66 (review) | 前端吃事后重扫的二手 diff | diff 在写工具执行时刻计算并随结果持久化 | `tools/impl/{write,edit}.py` 调 compute_diff；`test_review_turn_diff.py::test_review_turn_diff_aggregates_write`（covered） |
| B-67 (habena) | 插话任意时刻注入 | 消费只在步前边界（BeforeStep）；live 分叉允许未结算最终答案作分叉点 | `engine/loop.py`；`test_habena_steer.py::test_steer_consumed_at_iteration_boundary`（covered） |
| B-68 (schemas) | 生成物跨平台字节不可复现 | banner 路径一律用正斜杠（`path.relative()` 会让 Linux runner 重生成漂移） | ci.yml/contracts.yml 跑 `node scripts/gen/types.mjs --check`（covered） |
| B-69 (ci) | 只存在于 CI 的 flag 本地永远验不到 | 写进 CI 的命令必须先原样本地跑过（曾给 pytest 加不存在的 `--full-path`） | `test_ci_parity.py::test_ci_invents_no_gate_commands_of_its_own`（covered） |
| B-70 (ci) | `language: system` 钩子依赖未装先跑 | `pre-commit run --all-files` 必须排在 `npm ci --prefix ui` 之后 | 待落（workflow 步骤顺序，靠本地原样跑顶） |
| B-71 (state) | 删锁文件后并发锁到不同 inode | 锁文件释放后禁止删除 | `test_state_locks.py::test_lock_file_survives_release`、`test_state_lock_contention.py`（covered） |
| B-72 (state) | 跨目录 rename 不原子留半写 | 原子写临时文件必须与目标同目录 | `test_state_atomic_failure.py::test_temp_file_lives_in_target_directory` 等（covered） |
| B-73 (state) | env 覆盖 import 时求值 → 陈旧 home | 每次调用时求值 env | `test_state_paths.py::test_home_env_read_at_call_time`（covered） |
| B-74 (gesta) | 崩溃半行阻断回放与追加 | JSONL 读取容忍残尾（空行与坏行跳过） | `test_gesta_tail_tolerance.py`（三用例，covered） |
| B-75 (config) | 大小写变体绑定同一字段 | strip 大小写不敏感全拼写删除 | `test_config_loader.py::test_user_only_fields_stripped_from_project_layers`（covered） |
| B-76 (testenv) | Windows TMP 8.3 短名（RUNNER~1）raw-vs-resolved 断言本机绿 runner 红 | fake_home 先 resolve 再喂 env 与 yield | `test_state_paths.py::test_standard_dirs_live_under_home`（covered） |
| B-77 (tools) | PyHANDLE 被 GC 关闭底层句柄，int 拷贝 Assign 报"句柄无效" | Job Object 句柄把 PyHANDLE 本体持活在 ManagedProcess 上 | `test_tools_run_process.py::test_run_background_then_read_and_stop`（covered） |
| B-78 (tools) | 增量读子进程管道用 read(n) 阻塞到缓冲满 | 用 `read1` | `test_tools_run_process.py::test_run_background_then_read_and_stop`（covered） |
| B-79 (ci/平台) | 平台标记代码单平台自测盲区（盘符路径 POSIX 落回工作区、Windows-only 属性 pyright Linux 视角报错） | 改平台中立路径（/outside）；pyright 一次性 `--pythonplatform=Linux` 复核 | `test_tools_impl.py::test_search_path_outside_root_denied`（covered） |
| B-80 (ci) | 浅克隆使 check_notes 日期语义失效（每锚点 git log -1 返回 tip） | lint job `fetch-depth: 0`，脚本自检浅库直接拒跑 | 待落（workflow 配置，靠本地原样跑顶） |
| B-81 (prompts) | 易变内容排在稳定前缀之前 → prompt 缓存前缀永不命中 | 按类型化块装配并断言缓存边界 | `test_prompts.py::test_assemble_rejects_volatile_before_stable` 等（covered） |
| B-82 (providers) | 按厂商标识符硬编码窗口/输出上限 | 三档可辨来源（显式配置>端点声明>保守默认） | `test_providers_spec.py::test_model_name_alone_never_changes_the_window` 等（covered） |
| B-83 (providers) | HTTP 客户端生命周期漏收口/越权关 | 自持必关、注入不越权关，且幂等（`_owns_client` 分支） | `test_providers_resilience.py::test_lifecycle_and_capabilities_are_delegated`（covered） |
| B-84 (providers) | 流已交付后整体重试/重放；吞掉 CancelledError | 只有零交付失败可重放；`CancelledError` 不被重试吞 | `test_providers_resilience.py::test_never_replays_after_delivery` 等（covered） |
| B-85 (context/gesta) | 新 record kind 未同批登记 fold/投影 → 静默丢记录全测仍绿 | kind 与 fold 分支、ThreadView 投影同批登记 | `test_fold_kinds_are_projected.py` 三条（负向验证已做，covered） |
| B-86 (engine/gesta) | 工具结果未落盘只存定长 preview → 审计找不到模型实际看过字节 | 未落盘时正文存全文 | `test_compact_and_resume.py::test_unspilled_tool_output_is_stored_in_full`（covered） |
| B-87 (cli) | 日志/进度混进 stdout → `--json` 消费方解析炸 | stdout 只住机读帧，日志一律 stderr | `test_cli.py::test_exec_json_emits_only_protocol_frames` 等（covered） |
| B-88 (engine) | assistant 那轮（含 tool_use）不入历史 → 下一轮 tool_result 无配对真实端点 400 | 落盘同时 `conversation.add_assistant` | `test_single_turn_kernel.py::test_single_turn_full_chain`（covered） |
| B-89 (tools) | `gather(return_exceptions=True)` 把子任务 CancelledError 当普通异常收集，外层收不到取消 | `_as_outcome` 顶部特判重传 CancelledError | `test_tools_executor.py::test_parallel_batch_cancellation_propagates` 等（covered） |
| B-90 (tools) | file 类工具 async execute 直接同步文件 IO 阻塞事件循环 | 走 `asyncio.to_thread`（同步 helper 收口） | `test_tools_impl_no_blocking_io.py`（AST 守卫，covered） |
| B-91 (cli) | CLI 独立算 sha256[:16] 当 workspace_id 绕过单点 | 改走 `serve.assembly.ensure_workspace_for_root`，不 import hashlib | `test_cli.py::test_cli_does_not_recompute_workspace_id`（covered） |
| B-92 (schemas) | json-schema-to-typescript 默认丢弃 `$defs` 未引用类型 → 前端类型退化手写 DTO | 选项 `declareExternallyReferenced:true`+`unreachableDefinitions:true` | `test_schemas_method_families.py`；重生后 d.ts 展开（人工确认不写行数断言，covered） |
| B-93 (ui) | 外壳硬编码面板名字面 case 互相踩 | 新面板只在 `panels/registry.ts` 登记，单分发点 | `test_no_hardcoded_panel_case.py`（负向验证已做，covered） |
| B-94 (vigilia) | per-task 锁只串行化不去重，拿锁后不复判仍重复触发 | 拿锁后 `_reload_trigger` + `is_due` 复判 | `test_vigilia_scheduler.py::test_per_task_lock_prevents_concurrent_fire`（covered） |
| B-95 (architecture) | fold-kinds 护栏只覆盖 gesta，新 store 静默逃检 | 每个 append-only store 有自己副本的镜像护栏 | `test_orchestration_fold_kinds_are_projected.py` 两条（covered） |
| B-96 (orchestration) | 整对象覆盖入口可绕过白名单改 status | `update_task` 显式拒绝改状态字段，状态只经 `transition_task` | `test_orchestration_store.py::test_update_task_cannot_change_status`、`test_orchestration_transition_single_entry.py`（covered） |
| B-97 (vigilia) | 共享检查点两写方"tick 读、结尾整写回"覆盖游标（游标回退重开 B-40） | 持锁字段级读-改-写，各写方只动自己字段 | `test_vigilia_scheduler.py::test_tick_does_not_rewind_sweep_cursor_advanced_during_fire`（covered） |
| B-98 (orchestration) | 白名单某状态只能测试直调 store 到达 → 下游 UI 永远为空的假闭环 | 每条迁移必须有产品入口（task_review 经 serve） | `test_orchestration_methods.py::test_task_review_enters_reviewed_and_publishes`、`test_longrun_board_chain.py`（covered） |
| B-99 (orchestration) | 域内记账函数写状态字段绕开白名单（已停 Goal 被翻 completed） | record_round 仅 RUNNING 可记、完成经 `_move` | `test_orchestration_store.py::test_record_round_rejected_when_goal_not_running`（covered） |
| B-100 (architecture) | fold 移植漏异常类型化，裸 KeyError/TypeError 让脏记录口径在新旧 store 不一致 | 脏记录字段一律包成存储错基类 | `test_orchestration_store.py::test_invalidation_record_*_raises_store_error` 两条（covered） |
| B-101 (evidence) | 声称绑到不存在/陈旧 tool_use_id 时默认通过 | 落 `unverified`，recorded_output_ref 空即不可信 | `test_evidence_report.py::test_report_regressed_on_mismatch_and_missing_record`（covered） |
| B-102 (orchestration) | `update_task` 只挡任务 status，嵌套 acceptance.status 可旁路改 | `update_task` 另挡 `acceptance.status`，迁移只经 `transition_acceptance` | `test_orchestration_acceptance.py::test_update_task_cannot_change_acceptance_status`（covered） |
| B-103 (ui) | @pierre/diffs 长行 wrap 截断 diff 头行 `@@`/尾行 | 显式开 wrap，合成 git header 喂 processFile，fixture 断言含 hunk header | `review.fidelity.test.tsx > B-103` 两条（covered） |
| B-104 (ui) | CI/headless 缺 `prefers-reduced-motion` 使动效断言非确定 | base.css 加 `@media` 块，护栏测正则断言存在 | `review.fidelity.test.tsx > B-104`（covered） |
| B-105 (ui) | fingerprint 短哈希与 `#` 前缀字重不同视觉漂移 | 同一 `<span>` 保一致 | `review.panel.test.tsx > 卡片头显示 fingerprint 前 7 位（B-105）`（covered） |
| B-106 (ui) | 主题切换 diff 色对不反相（暗底亮绿/红刺眼） | 暗色用低饱和 rgba 变体 | `review.fidelity.test.tsx > B-106`、`design.tokens.test.ts`（covered） |
| B-107 (ui) | 空态与 diff 卡片同时渲染（误认卡片空但仍有 diff） | `diffs.length===0` 时 empty 分支 return 早于 map | `review.panel.test.tsx > 无 threadId/diffs 空显示占位（B-107）`（covered） |
| B-108 (desktop) | crash 残尾使 generation 不可读、同代 pid 被误认新代 | 主 parse 失败回退写前 rename 的 `.bak` | `generation.test.ts > state 文件损坏回退 .bak`（负向验证已做，covered） |
| B-109 (desktop) | 两个壳同开争同一会话存储 | sidecar 拉起经 lifecycle_lock 串行化（O_EXCL `wx`），5s 超时 fail-open 不开第二个 | `generation.test.ts > lifecycle_lock 防并发拉起`（covered） |
| B-110 (desktop) | sidecar 持续秒退 → respawn 风暴 | fail-open 重启有上限（backoff 表 + maxRetries）；per-handle closure 归零拦不住 crash loop，需模块级 spawnAttempts 守门 | `restart.test.ts > armRestartPolicy` 三条 + 真机 checklist（covered） |
| B-111 (desktop) | 挂死 sidecar 阻主进程退出 | 三层定时关停 SIGTERM→SIGKILL→reject，timer 全 unref | `restart.test.ts > killTree 三层定时`（POSIX stub 验证，covered） |
| B-112 (desktop) | `~/.questor/` 多处各自 homedir() | 单点 `resolveQuestorHome`（QUESTOR_HOME env → homedir fallback） | `generation.test.ts` 间接覆盖 + index 单点（covered） |
| B-113 (desktop) | 只听 pipe close 误认已停（后代仍持继承 stdio） | 等子进程 exit 事件、不等 pipe close | `restart.test.ts > killTree 三层定时（B-111/B-113）`（covered） |
| B-114 (desktop) | 从 workspace/PATH 找陈旧/异平台 sidecar binary | env → USE_UV_RUN+sourceRoot → packaged → throw，绝不 inspect appPath/bin | `questor-command.test.ts > B-114 有假 bin 也不能 resolve → throw`（covered） |
| B-115 (desktop) | writeFile+rename 无 fsync 非 crash-safe | O_EXCL temp 上 fsyncSync 后 rename（mkdir-p→temp→fchmod→write→fsync→close→rename） | `atomic-file.test.ts > atomic write` 四条（covered） |
| B-116 (desktop) | preload channel 与 main 侧不对偶，renderer 默默挂或报错 | ipc-parity 护栏扫两边源码行级对偶（集合双向包含） | `ipc-parity.test.ts > IPC channel parity` 五条（covered） |
| B-117 (desktop) | 每 token 一帧 IPC 卡 renderer；snapshot 前不 flush 致 delta 双份 | 50ms 同 identity 合批 + 控制事件先 flush + raw delta 不转发 + resolveSnapshot 前 flush | `renderer-batcher.test.ts > Batcher` 五条（covered） |
| B-118 (desktop) | 外泄内核真实 server-request id → 跳 respawn 写回陈旧会话 | 桥接成 public id `server-request-${N}`，反查写回 | `bridge.test.ts > server-initiated request public id 桥接`（covered） |
| B-119 (serve) | 方法表两份名单静默漂移（registry 多一行而 methods 没跟上 → handler 成死代码） | 唯一 `_handler_registry()`，`_methods()` 为键序派生视图 | `test_serve_names_are_contracted.py > test_method_table_has_single_source` 等（负向验证已做，covered） |
| B-120 (schemas) | `typing` 缓存 Literal 特化，两份手抄取值运行时同一对象 `is` 比也绿 | ToolKind 唯一定义点，下游 import；护栏扫 AST 赋值定义点 | `test_tool_kind_single_source.py > test_tool_kind_is_defined_in_exactly_one_module`（covered） |
| B-121 (serve) | 契约文档只做单向子集断言（实现⊆文档），文档声明未实现的 `thread/search` 永远绿 | 补法二选一：实现或改双向断言并显式登记未实现项 | 待落（open） |
| B-122 (desktop) | run/status 通知无 run/thread 身份，归属表滞留历史 threadId | 保守立场 detach 时全清、宁缺勿滥；正修需加身份字段=协议改动另开 ADR | `bridge.test.ts > detach 后归属表清空（B-122）`（covered） |

**台账统计**：122 条，其中 `covered` 约 78 条、`open`（含待落）约 42 条、`moot` 2 条（B-38/B-39）。
**必须优先重落的新实现测试**（当前 `open`/`待落` 且尚无宿主）：B-04 审批超时、B-35/B-36 容器双层超时与池销毁、
B-37 评测温度、B-48 FTS5 中文、B-55/B-56 审批硬拒与五态、B-59/B-61/B-62 传输路由与后台化、B-70/B-80 workflow 顺序与浅克隆、B-121 契约双向断言。

---

## 第二部分 · ADR 裁决：仍有效 vs 因对齐 WUU 而作废/需重评

> 判据口径：本次重构"后端逻辑按 WUU 蓝本移植为 Python、UI/桌面壳全废弃重写、对齐范围限于三柱能力"。
> 因此**语义/契约/状态机类决策**（多为"参照 WUU 已定死"）基本**仍成立**；
> **选型/排期/实现类决策**里，与 WUU 形态冲突或已被项目内后续 ADR 改判的，**作废或需重评**。

### 2.1 已被项目内后续 ADR 改判（历史既成事实）

| ADR | 结局 | 说明 |
| --- | --- | --- |
| 0006（壳=Tauri、浏览器=CDP 镜像） | 结论 1/3 **已被 0030 作废** | 结论 2/4/5（一套前端两宿主、传输双形态契约唯一、默认只绑 127.0.0.1）仍适用；复刻 WUU 桌面体验形态的诉求触发改判 |
| 0024（桌面壳推 M4/M5） | **排期被 0030 翻转作废** | 桌面壳不再后推，提前立为 Phase U；"壳与后端并行=两条学习曲线"的顾虑在内核已建成当下不再成立 |

### 2.2 因"全面对齐 WUU + 全量重写"需重评（决策仍是有价值的经验，但落地前提变了）

| ADR | 需重评的点 |
| --- | --- |
| 0007（Windows 沙箱：诚实降级 + Job Object，不做受限令牌/deny-ACL） | 与"以 WUU 源码为实施最高标准"有张力——WUU 在 Windows 是 **fail-closed**（受限模式命令工具直接失败）。本 ADR 选的是"路径门+Job Object+敏感守卫+显式标注确认"的降级路线。移植时须重新对齐 WUU 语义：诚实降级这层经验带走，具体档位内容按 WUU 蓝本重裁 |
| 0015（pywin32 Job Object 平台标记依赖） | 决策"不为 ctypes 重造编组、用维护中绑定"是有效经验；但引入时点/依赖面随新实现重走 ADR（记忆：新增依赖需先写 ADR） |
| 0016（providers 自建 wire 层 over httpx，不接厂商 SDK） | 语义经验（断流不重放、状态码优先分类、取消收口）仍成立；WUU 是 Go 无对应 SDK 取舍，Python 侧自建 wire 的选型须重裁 |
| 0022/0023（serve 引 starlette+uvicorn、M3 只落 WS 推 SSE） | "契约唯一、不为浏览器开私有端点、只绑 127.0.0.1"原则仍成立；具体 ASGI 栈选型随 serve 重写重评（WUU 用自家 app-server） |
| 0030/0031/0032（Electron 壳 + @pierre/diffs/vitest/happy-dom + electron-vite/builder + 两份 lockfile） | 壳选 Electron 与"纯壳职责、renderer 复用 ui 不复制、@pierre/diffs 显式 rollupOptions.input"等仍是有效约束；但桌面/前端代码**全废弃重写**，具体工具链版本与偏离须在新实现里重新确认 |

### 2.3 仍成立（可直接作为新计划的设计约束/契约）

- **命名与占用（0001）**：Questor/questor 命名、拉丁词源一句话说明、模块名表（limen 门槛/habena 缰绳/vigilia 夜班/gesta 行事簿等）、"拉丁短词无冲突是错觉，候选必跑 PyPI+npm+GitHub 三步"——方法论与命名资产带走。
- **工作区修订号（0005）**：单点 `bump_revision`、写时算 diff、turn↔revision 绑定、`expected_revision` CAS 拒 stale、"事后重扫违反可验证柱"——契约层裁决仍成立（与 B-66 同族）。
- **CI 门禁（0008/0009/0011）**：门禁范围=全部 Python 产出（src tests evals scripts）、CI 与本地逐字同源、`just` 唯一入口且装不上时按 justfile 逐条手跑不另写包装、分支保护 required checks 但不强制 PR、**required 名单逐字照抄不加 OS 后缀**（填错永不 report 的名字会让所有 PR 永久卡 Expected）——全部是可直接复用的工程纪律。
- **笔记治理（0010）**：锚点化 + 过期即删 + `check_notes`（浅克隆拒跑、docs 锚点只查存在、日期 vs 复核于拆开）——知识留存机制本身要带走。
- **依赖方向（0012）**：gesta 不 import engine、capability 不 import config（装配点注入），"让叙述性文档服从可执行 AST 矩阵断言"——架构约束仍成立。
- **地基依赖（0013）**：pydantic v2（跨边界数据禁裸 dict、frozen 机械保证）/ keyring（OS 凭据优先，文件回落非平等后端）/ import-linter 与 AST 矩阵双层并存——选型经验带走。
- **运行状态机（0014）**：补 `queued → cancelled`（未起跑可取消，不伪造 running 起点="对状态机撒谎"）——语义仍成立。
- **上下文事实入正文（0017）**：`context.boundary`/`context.replacements` 作 append-only 新 record kind（不扩 ItemKind、不写 sidecar、不把摘要伪装成 user message）——单一真相源裁决仍成立。
- **提示词分块缓存（0018）**：类型化块 + 稳定在前/易变在后是**被断言的不变量**（cache_boundary），provider 按能力消费、不假装等价——接口面裁决仍成立。
- **生成链（0019）**：定义点归位 `scripts/gen/`、notices 生成、"两边一致只有被断言时才算存在"；0030 后"桌面 Rust schema 绑定"子句不再适用，主体仍成立。
- **接口面提前（0020）**：UI 视图注册表骨架 + handler 一律收 `HandlerCtx`（含 principal 只做传递回显、不含鉴权）——接口优先原则仍成立。
- **编排域独立（0025）**：Task/Plan/Goal 独立有界上下文 + 自持 append-only store（不进线程正文）、状态机声明式白名单单点入口、编排门返回结构化载荷——架构裁决仍成立。
- **vigilia 语义（0026）**：声明式触发器数据、tick+per-task 锁+复判、once 幂等标记、错过不重放、一批一间隔带游标、启动+周期双 reconcile、唤醒检查点落盘——调度语义仍成立。
- **evidence 最小版（0027）**：声称 vs 录得并排核对、可追溯 recorded_output_ref、export 形状先定死为接口、不做复跑——第三柱最小可执行形态仍成立。
- **协议加性演进（0028）**：加性方法/通知/可选字段不升版本，破坏性才升，版本严格相等不降级——演进规则仍成立（B-121 暴露单向断言盲区需补）。
- **验收闭环（0029）**：AcceptanceStatus 枚举 + 单点迁移入口、evidence 生产写入点接线、声称显式绑定 tool_use_id、`orchestration→evidence` 有向边——仍成立。
- **M2 出口拆分（0021）**：接口优先切分、evals 对照基线口径（`not_in_baseline`/`not_comparable` 不悄悄消失、档位映射不透传）——判据可执行性经验带走。

### 2.4 proposed（待裁，本次重构须一并裁决）

- **0033 引擎契约定为 M6 准入门禁**：M1 曾把"建了目录"记成"落了套件"（`tests/contract/` 0 用例）。核心判据"先写契约测试再写第二个引擎，否则契约退化成内建引擎私有行为复述"仍成立——对齐 WUU 时外部引擎适配是天然第二实现者，值得优先落。
- **0034 长跑驱动宿主归属**：现状"降级路径只写在注释里、撞上已上线界面"（桌面 stdio 点启动→看板翻 running 而无轮在驱）。推荐 A（stdio 挂驱动 + http opt-in +  initialize 机器可读声明）；真实双触发窗口=判到点与起轮都在锁外。此坑在 WUU 单宿主形态下需重判。
- **0035 Review diff 权威源**：`review/diff.py` 明写"不看盘不看 git"，`run` 工具与外部改动零记录。推荐 A（真 git diff 为权威 + C 非 git 目录内容快照退化）；未裁先写会造 `Item.payload` 两套 diff 真相。
- **0036 AppServer 拆分时机**：1189 行上帝对象挂 ~55 方法横跨 12 域，编排 `*_transition`/`_gate_or_deny` 住在传输层。本轮已收单一来源 `_handler_registry()`（B-119）；整文件按域拆分待排期，触发点=Audit-0035 定案后与 review 重写合并做。

---

## 第三部分 · 经验教训（notes + behavior 提炼为可复用结论）

### 3.1 一次性踩坑 → 可复用教训（docs/notes/）

1. **门禁一致性（gate-parity）**：任何"两边必须一致"的约束，**只有被机器断言时才算存在**。
   本仓库为此付过三次学费（overview↔structure 模块表、生成物跨平台复现 B-68、justfile↔CI B-69）。
   可复用结论：**写进 CI/钩子/脚本的命令必须先原样本地跑一次**；把 CI 当第一次执行环境=一次全红+一次误诊。
   任何只存在于 CI 的参数永远不会被本地验证（`--full-path` 事件）。Windows 上 pytest `__pycache__`/vitest transform cache
   有 mtime 精度丢失，负向验证须先清缓存或跨过秒精度边界，否则"测仍绿"被误读成"护栏没咬人"。
2. **workflow 是仓库内容不是服务器配置（pr-branch-carries-its-own-workflow）**：Actions 执行"事件所在 ref"里的 workflow 副本；
   修 main 不影响已开出的 PR。可复用结论：看 PR 红先 `git show <pr-ref>:.github/workflows/<file>` 确证跑的是哪一份，
   修法只有 Update branch 同步默认分支，别手改 Dependabot 分支。注意"新配置何时生效"不能一概而论：
   checks 用分支旧副本，而"要不要开 PR"用默认分支新配置。
3. **providers 真实探针（m23-wire-probe）**：把"配置存在"当成"端点可用"是错的——账户欠费伪装成 4xx 业务错误。
   可复用结论：错误分类次序=**先 HTTP 状态码，再 body 的 type/code，最后 message 关键字**（402 的 body type 与真实原因无关）；
   `retry-after`/`x-ratelimit-*` 必须按"可能不存在"实现（本地退避兜底）；判断端点讲不讲某协议，**状态码比 body 更可信**（404 空 body=路径不存在 vs 402 JSON=路径存在没钱）；
   **缓存命中的 token 仍占窗口**（`LLMUsage.total_input()`=input+cache_read+cache_creation）；
   `response.model` 与请求型号名不必一致，能力解析不得拿响应型号名做键；失败响应是最好的 fixture 来源（用 httpx.MockTransport 按真实形状写用例，不依赖真实端点）。
4. **桌面壳重启/关停策略（desktop-restart-policy）**："等 exit、不等 pipe；三层定时；fail-open 到运维"。
   可复用结论：Windows 上 SIGTERM/SIGKILL 都走 TerminateProcess 等价，故 win32 分支**不发第二枪 SIGKILL**（避免误导 reviewer），测里 stub `process.platform` 覆盖两分支；
   per-handle retries closure 每 respawn 归零拦不住 crash loop，真上限需模块级 spawnAttempts 守门；孤儿 lifecycle 锁（硬崩没跑 finally unlink）→ 5s 超时抛 busy→运维手清；`shuttingDown` flag 挡关窗与重启链竞态。
5. **Review diff 链路走查（review-fidelity-walk）**：`@pierre/diffs` 顶层不导出 `<DiffView>`，React 入口在 `@pierre/diffs/react`，组件是 `<FileDiff fileDiff options>`。
   可复用结论：`turn_diff` 返回的是**写时算好的纯 hunk 片段（无 git header）**→选 `processFile`（非 `parseDiffFromFile`），用 path 合成最小 git header 再喂，
   **不重算、尊重写时真相**；happy-dom 会把结构渲染进 shadowRoot 而 testing-library 不穿透→**不断言渲染后像素/字样，改在封装契约层断言 buildFileDiff 元数据完整**；
   测里靠 `disableWorkerPool={IS_TEST}` 走主线程高亮、断言只到 `color-scheme` 这种同步落的 :host style，不等 shiki 异步。

### 3.2 参照实现的输入→输出→边界（behavior-*.md 要点）

- **engine（FlowCoder 蓝本）**：`run()` 返事件异步生成器；一轮 turn 八阶段（迭代上限→预算闸→turn_start→注入外部通知→Layer2 压缩→pre_send 重建 system→Layer1 api_conv 生成+流式调用→分派）；
  **止损四路**（轮次硬上限 50 / 四维预算收敛 / 未知工具连续≥3 熔断 / max_tokens 触顶恢复）；子代理路径拒绝双实现（B-07）；AskUser future 300s 超时。边界：压缩成功后重注入、返回 None 发跳过通知、返回 str 视为错误、ExitPlanMode 即收敛。
- **context（FlowCoder 蓝本）**：常量集中表（13 个阈值）；Layer2 auto-compact（触发 `current>=window-20000-13000`，保留窗口 token 10000 或 5 条先到先停、硬上限 40000 但绝不拒最后一条，keep_start 回退配对，前缀<2000 token 退化 noop，9 段摘要用户消息原文不改，连续 3 失败熔断，manual 绕过）；
  Layer1 工具结果三档（>50K 落盘 preview 2K / >10K 内联截断 / 否则原样）、O_EXCL 幂等、跨轮决策持久不 mutate、聚合>200K 降序替换、陈旧裁剪边界入状态。
- **limen（WUU 权威蓝本）**：`WorkspaceBoundary{Enforce,AllowMutations,Guards}` 唯一权威门 + 三构造器（Standard/ReadOnly/Unconfined）；
  Check=只读闸（`!AllowMutations && mutates`）先于 Guard 链；Guard 不阻塞不 ask；错误方言 `error_kind+reason+model_next_action`；
  mutates 按 ToolKind（browser read-only 短路放 observe/screenshot）；敏感路径按段匹配+源码扩展名豁免+symlink 防绕；unconfined 写恒拒读降级脱敏。
  permissions 对照（FlowCoder 六层短路）：安全命令放行+危险黑名单、路径沙箱二段 resolve 防穿越、缺路径=deny、表驱动模式矩阵。
- **tools（FlowCoder 蓝本）**：Tool ABC 声明 `permission_path_field`（不声明则路径沙箱跳过它）；Bash 超时 kill+wait、退出码按管道最后一段（阈值 2 类）、errors=replace、双空 (no output)；分区"连续安全合并"；执行三早退（未知/禁用/正常）、异常转错误结果不抛给循环、`gather(return_exceptions=True)`、结果顺序=提交顺序。
- **state（WUU 蓝本）**：home env 每次调用读；工作区 slug-hash16 目录名（realpath+sha256、sanitizeSlug 折叠）；原子写 temp 同目录+chmod+fsync+rename 复核 mode（Windows MoveFileEx REPLACE_EXISTING）；StoreLock 锁文件释放不删、25ms 重试 60s 超时、无心跳（进程死内核自动释放）、纯读者两锁都不拿。
- **gesta（WUU 蓝本）**：事件日志只 append 打开（`O_CREATE|O_WRONLY|O_APPEND` 从不截断）；loadEvents 残尾跳过、文件不存在返空；索引 temp+rename 轻量路径（不 fsync）可全量重建；RMW 全程持双锁、纯读免锁、状态是事件流 fold（绝不改旧行）、幂等靠先扫日志查重。
- **protocol（WUU 蓝本）**：版本严格相等不降级；反向请求 pending 表先路由再 method switch；慢发现 startBackground；插话 client_id 幂等（INSERT OR IGNORE + history EXISTS 判已送达）；ExpectedTurnID 空=兼容非空不匹配=拒；held_user_work 双 origin 整表替换事务重启重建。
- **review（WUU 蓝本）**：真实 diff 写时刻计算随结果持久化、前端不事后重读；fork 三级回退（raw persisted→display→live）、live 分叉允许未结算最终答案作分叉点；BeforeStep 是插话消费与后台 completion 唯一汇聚边界。
- **orchestration（EvoFlow 对照）**：任务状态机白名单全表（INBOX/PENDING/PLANNING/PLANNED/EXECUTING/PAUSED/REVIEWED/COMPLETED/FAILED/CANCELLED，含 REVIEWED→EXECUTING 打回）；未知状态 can_transition 返回空集 fail-closed；编排门返回结构化载荷 `{success:false,action,error_code,message,hint}` 不用中间件；人工门≠取消，gate 消息先持久化定序。
- **queue/vigilia（EvoFlow 蓝本）**：tick 60s、per-task Lock 字典+守卫锁；once 触发即标 once_fired（标记失败 warning 不阻塞）、同分钟去重、错过不重放；清扫一批一间隔带游标（旧版无 offset 每 0.5s 空转）、启动+周期双 reconcile、可用 env 整体关闭。
- **sandbox/eval（FlowCoder 蓝本）**：容器硬化默认值（non-root 65534、read_only 根、tmpfs 1777、默认断网、mem 256/cpu 1/pids 128）、双层超时（容器内 TERM→KILL + 宿主 grace）；池归还即销毁重建+label reaper+排队超 max_queue 快速失败；评测温度默认 0、超时不回喂、k-sample 首胜取消其余、失败四分类。
- **review-fidelity（WUU 视觉/动效蓝本）**：Questor 是 per-turn 级不是 WUU 工作区级（借视觉不借语义）；文件卡片含 path/状态徽标/byte_size/hunks 数/fingerprint 前 7 位，>100 hunks 默认折叠；已阅 dot 4px、reduced-motion 关过渡；所有色/阴影/时长走 token、禁 hex 字面量（护栏正则扫）。
- **persistence（EvoFlow 反面教材）**：反面=百表 SQLite 单体（2191 行/123 表）；Questor 用 JSONL 真相源+可重建索引；FTS5 中文 CJK bigram+OR 引号；验收态存储以 gesta 记录为准、看板是索引投影。

---

## 第四部分 · 废弃清单（带走知识 / 扔掉代码）

> 原则（记忆「彻底重构与零代码复用」）：现有代码**一行不留**，全部参照 WUU 源码从 Python 侧重写；
> 只带走**坑台账、行为规格、ADR 纪律、机制笔记、契约文档、护栏"该测什么"的思路**。

### 4.1 直接扔掉（代码全废，不迁移任何行）

| 位置 | 处置 | 理由 |
| --- | --- | --- |
| `ui/**`（app-shell/conversation/design/panels/rpc/state/testing） | **扔** | 用户判定现有前端界面已乱，改用 WUU 形态重搭；@pierre/diffs 封装/review 面板/token 层全部重写，**但 B-103~B-107 还原度坑与封装契约层断言策略带走** |
| `desktop/**`（src/main 全部 sidecar/bridge/batcher/atomic-file/child-shutdown 等） | **扔** | Electron 壳代码全废；**B-108~B-122 与 desktop-restart-policy 笔记的全部经验带走**，新壳从零按 WUU desktop TS 写法实现 |
| `src/questor/engine`（loop/conversation/constants/events/model/output_recovery） | **扔** | 按 WUU 蓝本重写；**B-01~B-11、B-86~B-91、B-88 经验带走**，状态机/止损四路/预算表作设计约束 |
| `src/questor/tools`（executor/base/processmgr/impl） | **扔** | 重写；**B-12~B-19、B-77~B-90（Job Object PyHANDLE 持活、read1、退出码映射、to_thread、CancelledError 重传）经验带走**，ADR-0007/0015 语义需重裁 |
| `src/questor/limen`（gate/matrix/reachability/sensitive/commands） | **扔** | 重写；**B-10/B-30~B-34/B-50~B-58 + behavior-limen-wuu 三构造器/表驱动/二段 resolve/敏感段匹配** 作蓝本 |
| `src/questor/serve`（app_server/dispatch/fanout/stdio/ws/http/longrun/assembly） | **扔** | 重写为对齐 WUU app-server；**B-59~B-62/B-87/B-96/B-119/B-121 + ADR-0022/0023/0036 原则**带走（契约唯一、127.0.0.1、单一来源、后台化） |
| `src/questor/context`（compact/rehydrate/replacements/tool_results/budget） | **扔** | 重写；**B-20~B-29/B-86 + Layer1/Layer2 全部阈值与边界策略**作蓝本 |
| `src/questor/gesta`/`state`/`workspaces`/`worktree`/`sessiontrace` | **扔** | 重写；**append-only 真相源、残尾容忍、锁文件不删、原子写同目录、env 每调用、workspace slug-hash 单点**（B-24/B-46/B-47/B-71~B-76/B-85/B-95）作蓝本 |
| `src/questor/orchestration`/`vigilia`/`evidence`/`review`/`habena` | **扔** | 重写；**状态机白名单单点入口、双 reconcile+游标、声称绑 tool_use_id、写时 diff、步前边界消费插话**（B-38~B-44/B-94~B-102/B-63~B-67）作蓝本 |
| `src/questor/providers`/`prompts`/`schemas`/`config`/`secrets`/`capability`/`cli`/`version`/`testenv` | **扔** | 重写；**自建 wire 语义、类型化块缓存前缀、pydantic v2、strip 安全字段、keyring 优先、stdout 洁净、fake_home resolve**（B-57/B-75/B-81~B-84/B-87/B-92/B-120）作蓝本 |
| `evals/**` | **扔** | 脚手架重写；**对照基线口径 not_in_baseline/not_comparable、温度 0、档位映射不透传**（ADR-0021、behavior-sandbox-eval §3）作经验 |
| `scripts/gen`/`scripts/ci`/`.github/workflows`/`.pre-commit-config`/`justfile` | **扔实现，留纪律** | 脚本重写；**CI↔本地逐字同源、required 名单不加 OS 后缀、浅克隆 fetch-depth:0、gen 跨平台正斜杠、check_notes 锚点新鲜度**（B-68~B-80、ADR-0008~0011/0019）作为门禁设计约束 |

### 4.2 必须带走的"知识"（喂给新计划 + 未来测试）

1. **坑台账 B-01~B-122**（本文第一部分）——最高价值资产；新实现每模块开工时按 `每条 B-NN 至少一个对抗用例` 回填测试。
2. **14 份 behavior-*.md**（本文 3.2 要点）——参照实现的输入→输出→边界，作为行为规格蓝本；**不搬代码不搬断言原文，只搬"在什么条件下发生什么"**。
3. **仍成立的 ADR 裁决**（本文 2.3）+ **待裁的 0033~0036**（2.4）——直接作为新计划的架构约束与准入门禁。
4. **notes 机制解释**（本文 3.1）——门禁一致性、workflow 版本化、providers 探针、桌面生命周期、diff 链路五条可复用教训。
5. **契约文档**（`docs/architecture/data-model.md`、`protocol.md`、`overview.md`、`structure.md`）——三柱语义、状态机图、依赖矩阵、路径单点，作为规格输入（内容留、随新实现更新版本）。
6. **护栏"该测什么"的清单**（从 `src`/`ui`/`desktop`/`tests/architecture` 注释里的 B-NN 映射反推）：
   单一来源护栏必须扫 AST 赋值定义点（B-120 Literal 缓存陷阱）、fold-kinds 每个 append store 各自镜像（B-85/B-95）、
   IPC channel 两侧行级对偶（B-116）、方法表单一来源负向验证（B-119）、CI parity 双向断言（B-69）——这些负向验证经验直接带走。

### 4.3 B-NN → 代码宿主映射（供新实现回填测试定位，注释实测）

`engine/loop.py`：B-01/02/03/05/06/07/08/09/11/15/20/24/25/29/67/82/86/88 ·
`limen/gate.py`：B-30/31/32/34/50/51/52/53/54/55 ·
`tools/executor.py`：B-03/15/16/17/31/54 · `tools/processmgr.py`：B-01/77/78 ·
`context/{compact,budget,replacements,tool_results,rehydrate}.py`：B-11/20/21/22/23/24/25/26/27/86 ·
`gesta/{store,writer}.py`：B-24/45/46/65/74/85 · `state/{atomic,locks,paths}.py`：B-24/71/72/73 ·
`vigilia/{scheduler,store,sweep,constants}.py`：B-40/41/42/44/49/74/94/97 ·
`orchestration/{gate,store}.py`：B-38/39/43/74/76/96/99/100/102 ·
`serve/{app_server,dispatch,fanout,stdio,ws,http,longrun,assembly}.py`：B-01/04/24/43/44/59/60/61/62/64/65/67/92/96/119 ·
`providers/{spec,errors,http,resilience,registry,protocols/*}.py`：B-28/81/82/83/84 ·
`cli/__init__.py`：B-83/87/91 · `config/loader.py`：B-57/75 · `schemas/*`：B-08/20/25/27/28/63/64/65/82 ·
`review/diff.py`：B-66/93 · `workspaces`：B-92 ·
`ui/{panels/review.tsx,review.diff-view.tsx,files.tsx,design/*,app-shell/AppShell.tsx,rpc/*}`：B-63/64/67/92/93/103/104/105/106/107/117 ·
`desktop/src/main/{sidecar-state,sidecar-lock,child-shutdown,atomic-file,questor-home,questor-command,renderer-batcher,app-server-bridge,index,sidecar}.ts`：B-77/87/108/109/110/111/112/113/114/115/116/117/118/122 ·
`scripts/{ci/check_notes.py,ci/check_specs.py,gen/types.mjs}`：B-01/68/80/98 ·
`tests/architecture/{test_fold_kinds_are_projected,test_orchestration_fold_kinds_are_projected,test_no_hardcoded_panel_case,test_schemas_method_families}.py`：B-74/85/92/93/95。

> 注：以上路径均随代码废弃，列出仅为**帮助新实现把每条 B-NN 的对抗测试重新落到对应模块**；
> 个别注释编号与 `pitfalls.md` 台账漂移（如 AppShell.tsx 标 B-97 实为 B-93 语义、review/diff.py 标 B-93），**以台账编号语义为准**。

---

## 第五部分 · 深度补充：代码注释里【未被 B-NN 收录】的散落裁决与外部工具怪癖

> 采集方法（区别于第一版的捷径）：用脚本按信号词（为什么/必须/否则/漂移/静默/两套/真相/诚实/竞态/幂等/原子/
> 惰性/缓存/特化/句柄/短名/浅克隆/残尾/等价/所有权/权威/单点/旁路 + 外部名 wuu/EvoFlow/FlowCoder/httpx/pywin32/
> electron/pierre/shiki/Job Object）扫 `src`/`ui`/`desktop`/`scripts`/`evals`/`tests` 的**全部注释行**，
> **主动剔除已含 `B-\d` 的行**（那些第一部分已映射），得 305 条候选；再逐条回**原文件**精读（UTF-8，
> 避开终端 GBK 乱码）后筛出下列**台账未记**的条目。这一类正是任务第 5 项要的"散落的为什么/外部怪癖"。

### 5.1 外部工具/库怪癖（接入时必踩，非本项目逻辑）

| 外部件 | 怪癖 / 硬约束 | 出处 |
| --- | --- | --- |
| **electron-vite 5** | renderer 段 `root` 跳到 `../ui` 后**必须显式给 `rollupOptions.input`**——它在 configResolved 里捕不到自动扫描的 index.html（root 已离开 `desktop/src/renderer`）；`findInput(root)` 从 `process.cwd()` 扫；**不能写 `fileURLToPath(import.meta.url)`**——electron-vite 先 esbuild bundle config，`import.meta.url` 不指向本文件 | `desktop/electron.vite.config.ts:34-46` |
| **electron-vite / vite dev** | `fs.allow` 默认只开 root 与 workspace root；root 指 `../ui` 后 electron-vite 会**往上一层回仓根把 desktop/ 与 ui/ 都圈进来**，需显式 `fs.allow=["..","../ui"]` | 同上 49-53 |
| **electron-vite preload** | preload 编为 **CJS**，产物名 `index.cjs`；main 里拼射 preload 路径需同步用 `.cjs` | `desktop/src/main/index.ts:29` |
| **@pierre/diffs** | 顶层**不导出 `<DiffView>`**，React 入口在子路径 `@pierre/diffs/react`；组件是 `<FileDiff fileDiff options>`，入参是元数据非 unified 串 | `notes/review-fidelity-walk`、`ui/panels/review.diff-view.tsx` |
| **@pierre/diffs 选 API** | `turn_diff` 返回**纯 hunk 片段无 git header** → 选 `processFile`（解析 patch）**而非 `parseDiffFromFile`**（那要两份完整文件现场重算），并用 path 合成最小 git header 再喂，**不重算、尊重写时真相** | 同上 |
| **@pierre/diffs 测试面** | 行文本要 shiki **异步**高亮才落 shadow；happy-dom 把结构渲染进 **shadowRoot**、testing-library 不穿透 → **不断言渲染后像素/字样**，只在封装契约层断言 `buildFileDiff` 元数据完整；靠 `disableWorkerPool={IS_TEST}` 走主线程、断言只到同步落的 `color-scheme` :host style | `ui/tests/review.fidelity.test.tsx:4-7,44,61,81` |
| **httpx** | `httpx.ProtocolError`（远端帧不合规）**与本项目 `ProtocolError` 同名不同类**——合并 `except` 后必须 `isinstance` 单独分流映射，否则被错误归类 | `src/questor/providers/http.py:69-75` |
| **msvcrt.locking（Windows）** | `EACCES`/`EDEADLOCK` 表示"区域已被锁（含**同进程另一句柄**）"，属**竞争而非故障** → 返 False 让上层重试；其他 OSError 原样抛（POSIX 走 fcntl 分支） | `src/questor/state/locks.py:41-51` |
| **pywin32 Job Object** | 停树**持 Popen/句柄对象本身而非记 pid 再查**——对象句柄杀进程天然无 PID 复用窗口，比"记 pid+pgid+start_time 重查"更强（没有重查环节）；前台超时移交（adopt）移的是活对象 | `src/questor/tools/processmgr.py:189` + 头注 |
| **Windows 路径折叠** | 可达性/工作区 id 比较用 `os.path.normcase` **大小写折叠（wuu resolveStartCWD 同款）**，POSIX 恒等；**前缀比较必须带分隔符边界**（`/root-evil` 不算 `/root` 内部）；空盘符病态输入让 `strict` resolve 报错而非猜 | `src/questor/limen/reachability.py:18-57`、`tests/unit/test_workspaces.py:35` |
| **@xterm/wuu 语义** | Windows/Linux 全窗口关即退；**macOS 保留 dock 常驻**（本项目不主用 mac，语义照 wuu） | `desktop/src/main/index.ts:182` |

### 5.2 跨文件/跨层"同一事实单点/同源"裁决（无编号，但是硬约束）

- **异常接住次序**：`dispatch._run` 里 `ProtocolError`（业务错带 code，如 stale_revision/boundary_denied）与 `ValueError`（归 invalid_params）**接住次序不能逆**，否则 ProtocolError 会被后接吞掉、丢掉自带 code。`serve/dispatch.py:204-205`
- **回显字段必须有执行体兑现**：`initialize.max_concurrency` 不是空头字段——`_run_sem`（上限=max_concurrency）在 loop 内 lazy 建，`max_concurrency=1` 时第二个 run 必须排队到第一个终态（护栏钉）。`serve/app_server.py:118` + `tests/unit/test_serve_app_server.py:235`
- **CHARS_PER_TOKEN 必须住共享层**：`engine`（预算）与 `context`（压缩阈值）**必须用同一个数**（=3.5），各写一份会让两侧对"窗口占了多少"得出不同结论（B-28 的落地根因）。`schemas/llm.py:42-45`
- **context 三阈值必须有序**：`SINGLE_RESULT_CHAR_LIMIT > INLINE_RESULT_CHAR_LIMIT > OLD_RESULT_SNIP_CHARS`——乱序则**内联截断会先于落盘吞掉内容、预览回链永远拿不到**。`tests/unit/test_context_tool_results.py:220-223`
- **版本唯一真相源三处同源**：根 `VERSION` 文件 = `hatchling dynamic` 版本 = `uv sync` 安装的元数据，三处必须同值。`src/questor/version/__init__.py`、`tests/unit/test_version.py`
- **Python 下界三处一致**：`pyproject requires-python` == `ruff target-version` == `pyright pythonVersion`——若不一致，3.13-only API 会静默被用、包在 3.12 用户处坏掉；**失败信息须同时列三处值**否则定位不到哪处改了。`tests/unit/test_project_metadata.py:1-42`
- **工作区身份单点**：workspace_id（sha256[:16]）单点在 `workspaces.register`，**CLI 不得自己算 sha256、前端不造 id**；serve http 起服务登记 `--cwd` 为 `default_workspace_id`，客户端不传时回落它，避免造 "ws-local" 幽灵 id。`cli/__init__.py:207-208,273`、`serve/app_server.py:116-118`（B-91 的完整边界）

### 5.3 诚实呈现/状态机的更细行为约束（比台账条目更深一层）

- **回放也过白名单**：gesta 的 `_load_state` fold 时 `run.status` 记录**同样经 `transition()` 白名单裁决**——篡改历史在**回放时**就爆炸，不只是写入时挡；未知状态/缺字段/引用不存在 run 一律显式抛 `ThreadStoreError` 不静默。`gesta/store.py:220-232`
- **载荷用 pydantic 模型把门**：字段不对=写错了一整条记录，**显式炸点不静默跳过**（与 B-100 同族但更强：连脏记录本身都拒）。`gesta/store.py:227` 区
- **归档/重命名有未终态 run 时拒绝**（wuu 语义：归档运行中拒绝）。`gesta/store.py:542`
- **缺终局事件不得无中生有**：Anthropic 流被截但没 `message_stop` → **绝不能默认成 `end_turn`** 让上层以为"答完了"（区别于 B-84 的"断流不重放"，这条是"不伪造完成"）。`tests/unit/test_providers_anthropic.py:239-240`
- **长跑断电恢复**：`driver.start()` 必须扫出 RUNNING 状态的 Goal 并**继续自驱**（B-44 的桌面重启接管侧具体语义）。`tests/integration/test_serve_longrun.py:264`
- **未装配端口 fail closed**：未接好端口的 `ToolContext` 必须显式报"不可用"，e2e 反向对照钉住（门是真拦不是文档）。`tests/e2e/test_longrun_board_chain.py:137`
- **审批只收紧不提权**：编排门 `EXEC_AUTHORIZATION_ACTIONS` 须用户「开始执行」授权——审批只能收紧、不能提权（与 B-55 一致但落在编排侧）。`orchestration/gate.py:24`
- **重建只采纳在线 id**：已随压缩离场的结果**不该继续占状态**，否则长跑无界增长。`tests/unit/test_context_tool_results.py:179`
- **回调抛错标 skipped 不吞成 fired**：vigilia tick 回调失败→本轮记 `skipped` 而非 `fired`（诚实呈现）。`tests/unit/test_vigilia_scheduler.py:189`

### 5.4 UI 双宿主分岔（一套代码两宿主的落地判据）

- **transport 分岔只在默认参数**：`client.ts` 构造里 `isElectronHost()` 真→`IpcTransport`（preload 桥），否则→`WebSocketTransport`；**显式传 transport 的注入位不变**（测试/集成可手动传 fake）。`ui/src/rpc/client.ts:95-96`、`ipc-transport.ts:1-4`
- **diff 颜色不写 hex**：主题只以 light/dark **名义透传**给 @pierre/diffs，色对由内置主题 + `tokens.css` 的 `--color-diff-*` 决定，护栏正则扫组件禁 hex 字面量（B-106 的落地约束）。`ui/panels/review.diff-view.tsx:9`、`ui/tests/design.tokens.test.ts:1-5`
- **verdict 诚实色**：看板 `unverified` 用中性警示、**不当作通过**呈现。`ui/panels/board.tsx:21`

### 5.5 本次深度扫描仍未覆盖的边界（诚实标注，供后续补）

1. **docs/architecture 契约正文**（`overview.md` 404 行的 §9 边界表/§14 留门纪律、`data-model.md` 254 行、`protocol.md`、`structure.md`）——本次只作 ADR/pitfalls 的二手引用，未逐行提取其中"外部怪癖/为什么这样切"的原始论述；这三柱边界表与留门判据是新计划的直接输入，建议单列一次扫描。
2. **AGENTS.md**——铁律（§五异步纪律/§四门禁准入/§三两套真相禁令）被大量 B-NN 与 ADR 引用为判据来源，但其正文未纳入本次提取。
3. **行内尾注与部分 jsdoc `*` 续行**——脚本按注释起始符采集，个别写在代码行尾的 `# ...` 短注与跨行注释的中间续行可能未取全；若要 100% 无遗漏，需按"含信号词的全部行"再扫一遍（不筛注释前缀、不剔 B-NN）。
4. `docs/plans/`（development-plan.md 505 行、phase-u 计划 3327 行）未扫——属排期而非经验，但其中 R-NN 风险项、F-NN 审查发现（如 F1/F5/F6/R-01/R-13）是可复用教训来源。
