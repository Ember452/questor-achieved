# EvoFlow-main 扫描报告 V2（深挖机制层版，为 Questor 后期补编排/验收打底）

> 扫描对象：`d:\DEVELOP\My-project\EvoFlow-main`（只读）。
> V2 变更：应"不许片面"的要求，V1 的 docstring 转译层全部下钻到实现——点名中间件逐个读源码、审批状态机读到 DB 行态、supervisor 派发读到 claim/租约、reconcile 读到三级判定、耦合面改为全仓 import 普查定量。V2 附"仍未读"清单（§8），不再把推测写成结论。
> V2.1 变更：新增 §R（读者上手：四实体/端到端时间线/术语表），并修正两处被加载器源码证伪的旧 docstring 说法（task 存储与 thread collab 状态均已在 SQLite）。
> 分类：🟦 可作规格借鉴 / 🟥 因 LangGraph 耦合需重写 / ⬛ 属不做范围直接排除。
> 红线不变：**EvoFlow 主体 PolyForm Noncommercial 许可证，只可搬设计，不可搬代码**（§7）。

---

## R. 读者上手：实体、时间线、术语（没看过 EvoFlow 先读这节）

### R.1 四个核心实体与 ID（编排层的理解前提）

| 实体 | ID 形态 | 存在哪 | 是什么 |
|---|---|---|---|
| **会话 Chat session** | `session_key` | `evoflow_chat_sessions`（transcript 在 `evoflow_chat_messages`） | 用户视角的一个聊天窗口：`run_status`、token 合计、审批 policy 挂在这里。**UI 的事实源**。 |
| **线程 thread** | LangGraph thread id；派生形态 `Thread_YYYYMMDDHHMMSS_XXXXXX`；worker 线程 = `{lead}__sub__{tool_call_id}` | LangGraph checkpoint（🟥）+ `evoflow_thread_collab` | 一个 agent 执行上下文。lead thread 跑主循环；每个被派发的子任务起一个 `__sub__` worker 线程，transcript 按该 scope 独立持久化。**执行的事实源**。 |
| **主任务 task** | 短 ID `YYMMDDHHMM_xxxx`（UTC 时间前缀，可在聊天文本中被正则识别；legacy `Task_…` 仍有效） | `evoflow_collab_tasks`（bundle 结构 project→tasks[] 由 `ProjectStorage` 读写；类注释与 `storage_dir` 参数均标 legacy——**文件 JSON 时代已结束**） | 业务台账：状态机、plan 绑定、授权位、handlers 都挂在 task 行。 |
| **子任务 subtask** | `Subtask_YYYYMMDDHHMMSS_XXXXXX` | `evoflow_collab_subtasks`（嵌在 bundle 的 task.subtasks[]） | 派发给 worker 的工作单元：`work_checklist`、`progress`、`lease_until_ts`、outcome 全在这一行。 |

绑定关系（互相之间怎么找到对方）：
- `session_key ↔ thread_id`：`find_session_key_by_thread_id()`（审批持久化、终态写入都要先翻这层）。
- `thread ↔ task`：`ThreadCollabState.bound_task_id`（线程侧）+ task 行记录的 lead thread（任务侧），双向。
- `task → worker 线程`：派发时合成 `{lead}__sub__{tool_call_id}`；子任务行还携带 `background_task_id` 指向执行器。
- 待办 `inbox` 与 task 是两种东西：前者 `evoflow_todos`，升级为正式任务才进状态机。
- ⚠️ 给后来者的警示（本次实锤两例）：`ThreadCollabState` 模型 docstring 写着 "persisted under threads/{id}/task_state.json"、`ProjectStorage` 写着 "task bundles"，**两处都已是过时描述**（实际分别在 `evoflow_thread_collab` 表和 SQLite，`TASK_STATE_FILENAME` 常量自己都标注 "legacy name; data lives in SQLite"）。读这个仓库必须以加载器/仓储层为准，docstring 会撒谎。

### R.2 端到端时间线：一个长任务从创建到验收闭环

1. **创建**：UI `POST /api/tasks`（或聊天内 supervisor 建单）→ 状态机入 `pending`；lead thread 的 collab state `bound_task_id` 绑定。
2. **规划**：`start` → phase=`planning`，plan_guard 限制工具面；plan 场景走独立 supervisor 路径。产出 committed plan → phase=`plan_ready/awaiting_exec`；可选用户确认 `user_execution_confirm`。
3. **授权**：用户 `authorize-execution`（或审批门逐次批准）→ 置 `execution_authorized` 位并**立即派发第一波**；此后可 `revoke`。
4. **执行**：Lead 调 `supervisor(start_execution)` → dependency 模块算出 eligible 波次 → `claim` 子任务（防双派）→ 生命周期事件广播 → 上游 outcome 拼成下游交接上下文 → 每个子任务起后台 SubagentExecutor 于 `{lead}__sub__{tcid}` 线程（子 agent 链 ≈15 个中间件，含 turn 上限）。worker 侧自维护 `work_checklist`（自动折 progress%）→ `subtask_progress_report`（阶段边界）→ `subtask_outcome_report`（终态+task_report+evidence_paths，**没报过 outcome 不算 DAG 依赖满足**）。
5. **监控**：Lead 用 `monitor_execution_step` 轮询（该动作在 loop_detection 豁免清单里）；后端自治 lease 看门狗回收超期子任务；卡住要人拍板时发 `task:decision_required` 事件；主任务 progress 由子任务 rollup 自动汇总、**封顶 99%**。
6. **验收**：全部子任务 completed 且验收通过 → Lead 写 `completed`+100%（唯一能破 99% 帽的动作）；打回=`reviewed→executing` 边 + 在原编排单再派；`upstream_receipt` 在子任务终态时软唤醒上级编排线程（禁止新建回执单、只允许在原单操作）；`task_state_service` 为每次迁移留 from/to/changed_by 历史行。
7. **回收**（贯穿）：run 级 zombie sweeper（§3.3）、subtask 级 lease（§2.5）、board 级 reclaim（stale awaiting_close）三层并行；用户 Stop 走 `sweep_langgraph_runs_until_idle` 的"只杀 sweep 开始时已存在 run"协议。

### R.3 术语表

`lead_agent`=主循环 agent（create_agent 装配）· `subagent`/`worker`=另起图执行子任务的 agent 实例 · `gate`=模型调用前的触发判定（折叠/审批闸）· `wire tokens`=真实发给 provider 的 payload token 数（含 system+schema）· `replay`=审批通过后脱离模型循环直接执行工具 · `signature grant`=按(工具名+归一化参数)哈希的会话级授权 · `wave/eligible`=DAG 中依赖已满足、可派发的子任务集合 · `lease`=子任务心跳租约 · `rollup`=子任务进度向主任务汇总 · `footer`=每轮模型调用追加到消息尾部的 ephemeral 注入块（不进 system，保前缀缓存）· `claim`=派发前原子认领 · `hydrate`=checkpoint 消息缺失时从 transcript 表回填 · `interrupt`=LangGraph 同 run 挂起原语（🟥，Questor 需自研等价物）· `awaiting_close`=本岗已交付、整单待验收的中间态。

---

## 0. 耦合面定量普查（先给硬数据）

全 backend 共 **1285 个 .py**（不含 tests/.venv），其中 **190 个文件 import langgraph/langchain**。按子包：

| evoflow 子包 | 引用 LC/LG 的文件数 | 其中引用 langgraph\* 的 | 判读 |
|---|---|---|---|
| `agents/` | 92 | 61 | 耦合震中：中间件钩子面 + interrupt/Command + runtime/config |
| `tools/` | 62 | 30 | 工具全部定义为 LangChain `BaseTool`/`@tool`（`langchain.tools` 69 处）|
| `community/` | 10 | 3 | 第三方搜索/媒体 provider |
| `models/` | 7 | 0 | chat model 工厂（LangChain 消息协议） |
| `collab/` | **1** | **1** | **编排台账几乎框架无关**（仅 1 处引用） |
| `persistence/` | **0** | 0 | 纯 SQLite，零框架耦合 |
| `execution_security/` | **0** | 0 | 纯 subprocess/profile JSON |
| 其余（context/mcp/knowledge/observability/subagents…） | 各 ≤3 | 多数 0 | 外围 |

热点模块（文件数）：`langchain_core.messages` 84、`langchain.agents.middleware` 76、`langchain.agents` 72、`langchain.tools` 69、`langgraph.runtime` 44、`langgraph.typing` 32、`langchain.agents.middleware.types` 32、`langgraph.types`(interrupt/Command) 22、`langgraph.config`(get_config/get_stream_writer) 14、`langgraph.prebuilt.tool_node`(ToolCallRequest) 13。

**结论（这决定了"搬设计"的可行边界）**：
- Questor 自建循环的重写面 = `agents/`（92 文件对应物）+ `tools/`（62 个工具定义换皮）+ 网关层代理/session_execution（约 3 文件）——**不是全仓**。
- `collab/`、`persistence/`、`execution_security/` 三域接近零耦合，其算法与表结构是**可整段按规格重写**的自包含资产，验证了"EvoFlow 作编排/验收规格来源"这一定位。
- `langchain_core.messages`（84 文件）说明：消息模型（HumanMessage/AIMessage/ToolMessage/tool_calls/invalid_tool_calls/usage_metadata）已成为全仓通用语言。Questor 必须先定**自己的消息/Part 规范**，否则一切重写无从挂靠——建议列为 M 系列第一个前置件。

---

## 1. 循环框架耦合面：lead_agent + middlewares（机制层）

### 1.1 装配与顺序语义（🟥 机制、🟦 语义）

- `lead_agent/agent.py`：`make_lead_agent(config, runtime)` → `create_agent(model, tools, middleware=_build_middlewares(...), system_prompt=apply_prompt_template(...), context_schema=LeadAgentRuntimeContext, state_schema=ThreadState)`；同一 `_build_middlewares` 被 bootstrap 图与正式图复用；subagents 用同一 `create_agent` 起独立图（`subagents/executor.py`）。
- 顺序即语义（LangChain 规则，注释明文依赖）：**列表首=最外层**；`before_*` 正序执行、`after_*`/`wrap_*` 逆序执行。因此出现三种固定手法：①"要最后跑就插最前"（CheckpointTranscriptSlim `insert(0)`，让别的 after_agent 先看全量）；②"要最先 patch 就压后"（ProactiveTool 必须在 DynamicSystemPrompt 之前 patch tools 列表）；③折叠器压到链尾（ContextCompaction 在 deferred 过滤/footer 注入**之后**才 gate，折叠口径=真实上线 payload）。Questor 无论用什么 hook 机制，**必须把包裹顺序写进契约文档**，这些手法才会自然涌现。
- 链上关键排序决定（agent.py L684–906 实况）：Hydration→Uploads→ContextFiles 在 compaction 前；PlanGuard/Proactive/DeferredFilter→ToolSurfaceLock→DynamicSystemPrompt→SkillsInjection/KbInjection→各 live footer→审批四件套→LoopDetection→Budget→RunLatencyWrap→ToolApproval→ModelFallback→footer 簇→**Compaction 倒数第二段**→ThinkingGuard→**Clarification 恒最后**（捕获所有下游澄清请求）。
- 每中间件再套 `middleware_timing`（before_model/abefore_model 墙钟），链级可观测。

### 1.2 点名中间件机制深挖（V1 只有 docstring，V2 给算法）

**LoopDetectionMiddleware（821 行，after_model + wrap_tool_call 双点位）** 🟦机制/🟥接线
- 指纹：对整批 tool_calls 做 name+args 规范化排序后 md5[:12]（**顺序无关**）；窗口 20 条、120s 单调时间衰减、按 thread LRU 追踪（上限 100 线程）。
- 分级：同指纹窗口内 ≥3 次→注入警告 HumanMessage（"[LOOP DETECTED] 换策略"）；≥5 次→**不杀整个批次**，把该批 tool_call_id 记入 blockset，wrap_tool_call 命中时返回合成 error ToolMessage（"[重复调用·已拦截]"），run 继续、模型换路。**"拦重复个体而不是截断到 END"是刻意设计**（docstring 明说不要 strip-to-END）。
- 豁免面：supervisor 的 monitor/start/get_status/list/update_progress 轮询视为有意重试直接豁免；安全 terminal（只读 git 子命令白名单、curl.exe）豁免。
- 探索类指纹体系（read 路径+offset//50 分桶、rg pattern、list_dir depth、terminal 复合命令取最后非 cd 段再取"动词/脚本名"）与"连续只读 streak 警告"当前**在本 build 被禁用**（`_check_explore_loops`/`_check_explore_streak` 直接 return None，注释"read/rg/search may run freely"）——是演进遗留：**规格上保留双层设计（批哈希 + 目标指纹），阈值可关**。
- 给 Questor 的启示：这套"warn→block duplicates→keep run alive + 豁免清单"三态比硬停环好，直接照抄语义。

**DanglingToolCallMiddleware（115 行，wrap_model_call）** 🟦
- 悬空=AIMessage.tool_calls 的 id 在全史 ToolMessage 里无应答。修复：**用 wrap_model_call 而不是 before_model**，因为 before_model+add_messages reducer 只会把补丁 append 到列表尾部，破坏消息次序；wrap 里 override(request.messages=patched) 把合成 ToolMessage（"[Tool call was interrupted...]", status=error）**插在对应 AIMessage 正后方**。这是一条对任何消息型循环都成立的教训：修复类中间件要区分"改写请求"与"改状态"。
- 只修当轮请求不落库——checkpoint 里仍悬空，下次再修（幂等）。配合 §3.1 hydration 才有终态一致。

**InvalidToolCallMiddleware（214 行，after_model，ToolNode 前）** 🟦
- 处理 `AIMessage.invalid_tool_calls`（参数 JSON 坏/工具名不存在）。先抢救：`plan` 工具做宽松 JSON 解析 + `coerce_plan_tool_call_args` 修复后**升格回 tool_calls 继续执行**（修复计数日志）；不可修的才物化为 error ToolMessage，且 hint 分工具定制（plan 报"depends_on/tools 须 JSON 数组勿传字符串 + 原始参数片段 240 字符"；mind_map 场景注入误调用提示）。
- 语义分层值得抄：**能确定性修复的静默修，不能修的给模型"可操作纠错指令"而非裸异常**。

**LargeContentOffloadMiddleware（237 行，after_model，ToolNode 前）** 🟦
- 问题：write/replace 的超大 content/old_string/new_string 全程走 模型输出→state→SSE→ToolNode，会撞 vendor 输出 token 限/SSE 帧限。方案：≥32KB 字符串写 tempfile，args 替换为哨兵 `__EVOFLOW_LARGE_FILE_REF__::<abspath>`；工具端（write_file_hd/str_replace_hd）识别哨兵读盘再删。对模型完全透明。
- 这是"大载荷旁路化"的最小机制：**引用哨兵 + 接收端解引用**。Questor 的 tool 参数与事件流同样需要（V1 只写了名字，此处补阈值/方向=只 offload 入参方向）。

**ContextCompactionMiddleware（1458 行）+ context_compaction_core（~2200 行）** 🟦核心规格
- **gate 口径 = 真实 wire tokens**：messages 估算（content+reasoning+tool_calls 全序列化+每条 +4 framing；image≈1300tok、audio≈1500tok）+ **contextvar 注入的本次调用真实 system prompt+tool schema tokens**（`set_gate_overhead_tokens`，拒用 legacy 4096 拍脑袋）。这就是为什么它在链尾挂载——deferred 过滤/审批 footer 都改完 payload 后才量。
- 触发参数（SummarizationConfig 默认）：`threshold_ratio=0.90`（对齐 runtime `context_window*9/10`）、`aggressive_ratio=1.0`（一轮折叠后二次硬阈值）、`cooldown=120s`（成功后免再调压缩 LLM，期间用缓存摘要重折叠 refold）、`release_ratio=0.42`（回落线，防抖 hysteresis 可开）、`protect_tail_messages=12`、`protect_tail_tool_rounds=3`、`protect_first_n=0`（system/开场也可进摘要）、`compaction_min_middle_tokens=2000`（中段太小不值得折）。
- 结构：`CompactionPlan`（纯结构切片不用 LLM：working/head_end/compress_end/middle/middle_tokens）→ 中段交压缩模型异步队列化（后台线程池 max 3；**sync 路径硬上限 120s，超时按"不折叠"降级而不是拖死整轮**——注释记录了 600s 冻结事故史）。
- 单一事实源：摘要只存 `evoflow_chat_messages`；hydration 已拼好 `[bridge][summary][tail]` 的转录**永不内存重折**（`should_passthrough_db_hydrated_transcript`）；摘要尺寸上限=head+tail 70/30 按段落对齐（保住尾部 Key Context/Pending Asks/Remaining Work 结构段）。
- 分级工具裁剪：critical 工具（read_file/worker/search_code_index/grep/glob/list_dir）被剪时保留 head+tail；写路径开启 shaping 时尾部截断 cap 与写时 shaper 对齐（同一预算两处一致，防双重截断）。
- 事件：emit_compaction_start/end + emit_context_usage（UI 上下文条）；`mark_skip_compaction_once`（空响应重试轮跳过折叠，防止重试又触发折叠的死循环）。

**ToolApproval 家族（机制见 §2.3，与 V1 合并深化）。**

### 1.3 全量中间件职责清单（保持 V2 §1.2 的 checklist 用途，按组压缩）

`agents/middlewares/` 88 文件 / 84 个 `*Middleware` 类（另有 goal/ 3、guardrails/ 1、sandbox/ 1；lead 链实挂约 50+，subagent 链约 15）。职责一句话版（全部：职责🟦/实现🟥）：

- **修复层**：dangling（位置正确的合成应答）/ invalid（可修的修、不可修的给纠错指令）/ tool_error_handling（异常→error ToolMessage+结果 shaper+空结果占位"[Tool completed — no output]"+proactive 硬截+working_memory 登记，GraphBubbleUp 放行🟥）/ pre_call_guardrail*(孤儿对消毒) / retry / provider_fallback / model_fallback / tool_timeout（每工具时限，被 executor 复用🟦）/ 参数 coerce。
- **体积层**：context_compaction（gate=wire 真值+冷却+回落）/ large_content_offload（哨兵旁路）/ tool_history_ager + tool_shaped_cache（冷区后台老化→回填）/ monitor_tool_prune / checkpoint_transcript_slim / thinking_context_guard / loop_detection / session_budget / automation_run_guard / subagent_limit / subagent_turn_limit。
- **注入层**：transcript / session_transcript_hydration / memory×3 / external_memory_plugin / mission_state×2 / session_intent / turn_context / context_refs_footer / skills_injection / kb_injection / context_files / uploads / view_image / dynamic_system_prompt / plan_doc / title / todo / scenario_* / tool_binding_sync / deferred_tool_filter / **tool_surface_lock（排序+会话锁 tools 保前缀缓存）** / mind_map / 各 live footer（"strip stale + append fresh"统一模式，全部走 ephemeral Human 尾部注入**不进 system**保缓存——全仓最一致的单一原则）。
- **HITL 层**：clarification(+answers) / tool_approval(+answers/+deny-continue/+replay/+executor) / plan_guard / workspace_guard(遗留已禁用)。
- **生命周期/观测层**：session_run_lifecycle（图内终态写 run_status，🟥但语义🟦）/ round_trace / collab_cycle_trace / collab_lifecycle_cn / middleware_timing / run_latency_timing / token_usage+message_usage_helpers（usage_metadata 归一须在持久化**前**——after_model 逆序，故链尾 append）/ stream_accumulator。
- **产品专属⬛**：proactive_tool（值班）、xiaomi_ui_context、scheduler_orchestration（本地调度器概念🟦）。

---

## 2. 编排与验收：collab/（V2：读到行态机与派发协议）

### 2.1 双状态机（`models.py`/`state_transitions.py`，同 V1，补历史细节）

- TaskStatus：`inbox/pending/planning/planned/executing/paused/reviewed(legacy→completed)/completed/failed/cancelled`；CollabPhase：`idle/req_confirm/planning/plan_ready/awaiting_exec/executing/verifying/reflecting/paused/done`；两向映射表在 state_transitions。
- 关键边：`executing→reviewed→(completed|executing 打回)`、`failed→executing`（唯一重试边）、completed/cancelled 终态、`planned→planning`（重规划）。`REVIEWED` 注释标明 **legacy：写入时映射为 completed**——状态机在演进中收缩，审核语义已上移到线程 CollabPhase(VERIFYING/REFLECTING)与 upstream_receipt。
- `TaskStateService`（task_state_service.py）：状态变更走单一服务= 校验(InvalidStateTransitionError)+hooks+**TaskStatusChangeRecord 历史行**（from/to/changed_by/changed_at）持久化。🟦"每次迁移留痕"是审计工作台的刚需规格。
- 生效通道🟥：phase→模型的注入靠 collab_phase/plan_guard 中间件；Questor 需自建"阶段→工具面+提示词"闸（语义见 VERIFYING 限副作用、REFLECTING 只读+编排）。
- phase 持久化在 `evoflow_thread_collab`（SQLite，3s TTL 读缓存——单轮模型调用有 8+ 中间件 27+ 调用点读它；`load_merged_collab_phase` 的合并规则：**盘上非 idle 值压过 runtime.context**，因 context 在整个流式期间可能停留在旧值——注释点名 `supervisor(start_execution)` 后盘上已写 executing 而 context 未刷的场景）。🟦 "两个事实源合流时谁赢"必须写成显式规则，这就是范例。

### 2.2 plan→authorize→execute 门（🟦 全套）

- 三要素门：committed plan + execution_authorized + （用户确认时）`user_execution_confirmed_at`（存 ThreadCollabState）。`supervisor_plan_gate` 在 supervisor 工具入口前置校验，返回错误文本而非中间件异常。
- Gateway `authorize-execution` 置授权后**立即派发第一波**（§5.3 注释原文），`dispatch-execution` 后续波次，`revoke` 撤销。authorize 独立成模块的原因写在 docstring：避免大 storage.py 的 stale bytecode 干扰 LangGraph/uvicorn worker 热载——**部署卫生型规格**。

### 2.3 tool_approval 全机制（V1 七层语义 + V2 数据面）

数据面（`tool_approval_service.py` + `tool_approval_repositories.py`，表 `evoflow_tool_approvals/grants/audit`）：
- **行状态机**：`PENDING → APPROVED → EXECUTED`，旁路 `DENIED / CANCELLED`。
- **peek→execute→consume 两段式**：`pop_replay_queue` 只 peek 不消费，执行成功后才 `consume_replay_queue` 标 EXECUTED——docstring 明文这是修过"destructive-consume bug"（执行失败但行已标 EXECUTED、无工具结果）后的契约。🟦 **Questor 审批队列必须同款**。
- `begin_approval_batch`：新一批 interrupt 前，**只取消批外 PENDING，保留 APPROVED**（批内已批未 replay 的仍可执行）；再把跨批孤儿 APPROVED 标 EXECUTED 防 replay 污染。批次一致性规则完整可抄。
- `append_pending` 幂等：行已是 EXECUTED/DENIED/APPROVED 则跳过（防重注册覆盖）。per-thread `RLock` 包住"approve+解析 session_key+pending 探针"单锁域（`apply_user_approval_with_session`）；过期 pending 用**节流 sweep**（默认 60s 间隔）避免 UI 轮询放大 UPDATE。
- 授权粒度策略：会话 policy（effective_policy 可 grant_all）+ **运行时签名**（sha256 前 24 位 of canonical{name,归一化 args}）；`consume_signature_grant` 在执行**前**消费（注释原文：即使 handler 失败也不留签名，防下次自动放行）。单次批准绝不升级为整工具放行（`should_persist_tool_name_grant` 恒 False）。
- deny 面：内存计数 (thread,tool)，≥2 硬拦+提示换方法/问用户；批准即清计数。
- replay 执行器（`tool_approval_executor.py`）：**脱离图直接调工具**——合成 `ToolRuntime(state={}, context, config={thread_id}, stream_writer=noop)`（失败退 `SimpleToolRuntime`），重过一遍 denylist，复用 `_timeout_for_tool`。🟦 这证明"审批后执行"无需模型在场，Questor 自研时同款：执行器只依赖工具注册表+上下文快照。
- 挂起面🟥：`interrupt()` 前先用 `get_stream_writer()` 推 `tool_approval_pending` 帧（因 interrupt 抛出后 wrap_tool_call 永不返回、pending ToolMessage 不会进 messages-tuple——注释把这个坑写明了），同一条 SSE 保持打开、Gateway 推迟 RUN_FINISHED（`thread_has_pending_approvals` 轻探针）。Questor 自研暂停必须保证：**先可见、后挂起**。

### 2.4 human_gate 两类闸门（同 V1，补语义）

clarification=`goto END` 结束本轮（下一条用户消息自然续起）；tool_approval=`interrupt()` 同 run 挂起。两种暂停并存的原因：澄清不需要恢复原执行点、审批需要。**transcript seq 纪律**：门行必须 `persist_transcript_tool_message_now` 先占 seq，保证用户答复行号在门行之后。

### 2.5 supervisor 派发与监控（V2 新读，🟦 核心编排协议）

- **delegate 流**（`supervisor/execution.py::delegate_collab_subtasks_for_start_execution`）：
  1. `_claim_subtasks_for_delegation` **原子认领**（防双派），失败路径 `_revert_claimed_subtasks_to_pending` 回滚；
  2. 逐个 emit `task:started/running` 生命周期事件（unified_stream→SSE/WS），写 "子任务已派发" current_step；
  3. 依赖交接：从 dep_by_id/name_index/ref_index 解析 `depends_on`（id 或 name 混合引用都支持），把**上游 subtask_outcome 快照拼成 dependency context** 注入下游 prompt；
  4. `delegate_via_task_tool` 每子任务起后台 SubagentExecutor，worker 线程 id=`{lead_thread}__sub__{tool_call_id}`（`worker_tool.py`；transcript 按该 scope 独立持久化）；默认**不等待完成**（fire-and-track，完成由 task_tool 轮询路径回写 project 行）。
- **DAG 模块**（`dependency.py`）：depends_on 抽取/ref 解析/**unrunnable pending 自动终结**（上游 failed 则下游不再空等，自动 finalize）/start_execution wave 的 eligible 计算。🟦 "波次=eligible 集"而非全图跑，是断点续跑的前提。
- **租约看门狗**（`monitor.py::_expire_stale_running_subtasks`）：子任务行携带 `lease_until_ts/last_heartbeat_ts`；过期→标 `timed_out`+error；但先查 `is_subtask_background_executor_active` **同机执行器还活着就跳过**（防误杀）；后端自治不依赖 Lead 调 monitor。🟦 run 级 zombie（§3.3）与 **subtask 级 lease 是两层不同回收**，Questor 都需要。
- **decision_required**：monitor 判定需要人决策时写 task memory + 广播 `task:decision_required` 事件——"编排中途升级人工"的通道。🟦
- worker 护栏：`collab/worker_tool_allowlist.py`（子任务可调用工具面按 plan 绑定裁剪）+ `SubagentTurnLimitMiddleware(max_turns)`。

### 2.6 验收闭环（同 V1，证据补强）

work_checklist（worker 自治、自动折 progress%）→ subtask_progress_report（阶段边界上报）→ **subtask_outcome_report（终态+task_report+evidence_paths/outputs；"上报过"才算 DAG 依赖满足 `is_upstream_subtask_dependency_met`）** → 主任务 rollup 封顶 99% → Lead 验收后写 completed+100% → `upstream_receipt` 子任务终态软唤醒上级编排线程（禁止新建回执任务、只允许在原编排单操作；全 sibling 结案才提示提出人闭环）。verification_rounds/steps 独立验收轮次表。打回=`reviewed→executing` 边 + 上级再派。
（`collab/peer/wake.py` 属 **peer 协作**子域——跨线程软唤醒实现体，机制与 receipt 一致；peer 功能整体⬛ 不入 Questor MVP，留名备忘。）

---

## 3. 持久化与网关（V2 补 reconcile 算法与 DB 并发模型）

### 3.1 persistence（V1 结论保持，补两点机制）

- `db.py` 并发模型：单进程级共享连接 + RLock 逐语句 + busy_timeout 10s + 指数重试（max 8）+ `run_db_transaction`；legacy 列缺失触发**一次性** lazy backfill 后不再重试（防未知列 bug 死循环）——桌面单库 SQLite 的完整答案。🟦
- 三库分工（app/observability/checkpoints）；collab 台账也已在 SQLite（`evoflow_collab_tasks/subtasks`、`evoflow_thread_collab`，见 §R.1——文件 JSON 仅存于更早版本）；部分运行时产物仍走文件层（plans markdown、artifacts、uploads/outputs 目录）。87 张表全清单见 §3.1 V1 版。`session_run_state.py` run_status 常量与 normalize（idle→done 只读归一）🟦。
- **transcript 双向**：`TranscriptMiddleware` 实时写 chat 表（SSOT），`SessionTranscriptHydrationMiddleware` 在 checkpoint 空/丢时从表回填运行时 messages，回填产物带 `[bridge][summary][tail]` 结构且 compaction 对其透传不重折。"写实时、读兜底、折叠幂等"三件套是长会话完整的最低配置。🟦

### 3.2 gateway/routers/tasks.py（路由语义清单同 V1；补鉴权与队列）

无人值守队列 `queue/status`、`queue/tick` 暴露"队列由 runner 周期推进、可手动单步调试"的运维面 🟦；`restart=克隆新任务+原单归档`（不原地复活）🟦。

### 3.3 zombie/reconcile（V2 算法级，🟦 全套必抄）

`run_status_reconcile.py`：
- 动因（docstring 原意）：gateway 或 LangGraph 重启后 DB 停 `running` 而无真实 run。启动一次+周期 sweep（120s/批 100）复用同一 `reconcile_stale_session_runs`。
- **单行判定序**（reconcile_session_run_row）：①无 thread_id→直接清终；②stream mirror 停更 ≥120s 且 run 确认 inactive→清 mirror+清终；③探针 `is_thread_run_active`（三态 True/False/**None=LangGraph 不可达→skipped，绝不瞎猜**，结果带 TTL 缓存：active 4s / inactive 12s，上限 256 条）；④run 活着但 DB 非活跃→**反向 heal**（start_session_turn 补回 running，user-stop 终态豁免不 heal）；⑤run 活着且 DB 也活跃→**三级防误杀**：有活跃 stream proxy（客户端在收流）→kept；live-run 心跳快照 `last_event_at_ms` 停更 ≥90s→cancel（快速通道）；无快照则 updatedAt ≥180s→cancel。
- 取消实现：`stop_session_execution(user_initiated=False)` 只 cancel 当前 run（不走多秒 sweep），随后**无条件 force_end_session_turn 写终态**（因非用户停不写 DB）。
- staleness 依据"最后活动"而非"回合开始"（docstring 点名 currentTurnStartedAt 会把 15 分钟子任务误判 stale）。
- 前端每 ~2s PUT live snapshot 作为心跳事实源——**run 健康度=心跳+代理连接+服务端探针三源交叉**，单源必误判。这套判定对 Questor（自研 run、Electron 渲染端心跳）逐条适用。🟦
- subtask 级 lease 见 §2.5；initiative/board 级 reclaim 见 `collab/task_reclaim.py`（executing@100 卡住、stale awaiting_close，每小时限频）。三层回收体系完整。

---

## 4. execution_security/（结论同 V1：整套 🟦；V2 补充）

- 决策面 `decide_shell_approval`：already_granted/never→跳问；untrusted→必问；on-request→标记"应咨询审批 UI"由中间件弹窗——**双轨不打架的实现点在 tool_risk_level 里的桥接段**（terminal/process/bash 依 AskForApproval 覆写 risk）。
- `runner.py`：argv 显式化（禁 shell=True）、PowerShell 子命令拆分防注入、env 清洗、Windows 隐藏窗口 kwarg；`mode: sandboxed|passthrough` 始终回报——面板/审计能区分"真沙箱跑了"与"直跑"。
- helper 发现：平台命名约定（`evoflow-linux-sandbox`/`evoflow-windows-sandbox.exe`/macOS sandbox-exec passthrough），不依赖任何上游 CLI 二进制。Questor Windows 面同款：helper 名、搜索路径、缺失时 passthrough+明示。
- profiles JSON 形状（read-only/workspace/danger-full-access，special path kinds root/project_roots/slash_tmp/tmpdir + access read|write|deny + network restricted）**可整段作 schema 规格**，helper 协议与 Python 无桥接耦合。

---

## 5. evopanel（只记录，同 V1）

Vite+React19+Radix+zustand+Lexical+xyflow；Tauri 2 Rust 壳（多 conf 变体、autostart/dialog/notification/process/shell/updater 插件、签名公钥）；与后端只走 Gateway `/api/langgraph` SSE。⬛ 不移植。留两条交互规格：审批在工具卡片就地点击（拒用 slash 命令为默认路径）；voice-overlay/agent-trace 独立 HTML 入口拆分。

---

## 6. 不做范围（⬛，同 V1）

channels(IM)/authz 多用户/orgs/license 发码/chat_shares/apps 生成托管/proactive 值班排班（其 zombie 复用逻辑除外）/a2a/meetings/person-memory/exploration_graph/xiaomi/eval 平台/collab.peer。

---

## 7. 许可证 / 耦合红线（同 V1，重申）

- **PolyForm Noncommercial 1.0.0 + Required Notice（景银银/EvovexAI）**：禁复制任何 EvoFlow 代码；DeerFlow 段 MIT 但经 EvoFlow 转手即被 NC 污染；LangChain/LangGraph 本体 MIT/Apache（Questor 不引入则无义务）；sandbox crate Apache-2.0（自编 helper 保留 LICENSE）。
- 🟥 需重写清单（V2 定量后修订范围）：①`agents/` 全部 92 处 LC/LG 引用（钩子面/interrupt/Command/get_config/stream_writer）；②`tools/` 62 个工具的 BaseTool 定义→Questor 工具协议；③`models/` chat model 工厂（LangChain ChatModel 协议→自研 provider 层）；④checkpointer+ThreadState reducer channels→自研 run 状态；⑤langgraph.json/Agent Server/langgraph_proxy.py/langgraph_sdk→删除，自研 run manager 顶替；⑥subagent executor 的第二图→自研子 run（父流桥接语义保留）；⑦消息模型（langchain_core.messages 84 文件）→**Questor 消息/Part 规范为第一前置件**。
- 🟦 高价值资产排序（V2 依机制深度重排）：1) tool_approval 全家族（七层决策+行态机+批次一致性+两段消费+循环外 replay）；2) zombie/lease/reclaim 三层回收与三源健康交叉判定；3) context_compaction 参数体系与"gate=真实 wire"原则；4) supervisor 派发协议（claim/波次/依赖交接/租约/decision_required）；5) 双状态机+迁移留痕；6) 修复层三件套（dangling 位置修复/invalid 抢救/offload 哨兵）；7) execution_security profile JSON schema；8) live-footer 注入模式与 tool_surface_lock 缓存纪律。

---

## 8. 诚实的未读清单（本轮仍未逐行、不可不说的边界）

以下文件存在但只读了入口/局部，V2 结论未依赖其未读分支：`collab/storage.py`（**V2.1 已补读关键段**：ProjectStorage 实为 SQLite 存储、per-main-task mutation lock、bundle=project→tasks[]→subtasks[] 的 dict 视图、30s project cache——§R.1 据此写成；仍余 save/load 分支细节未逐行）、`collab/plan_subtasks_sync.py`（38KB，plan→subtasks 同步算法）、`collab/debug_runner.py`、`persistence/chat_message_repositories.py`（91KB，seq/分支/编辑语义——**若 Questor 抄 transcript 模型，此文件需单独深扫**）、`lead_agent/prompt.py`（2141 行，系统提示词全文）、`gateway/routers/chat_sessions.py`（71KB）、`tools/builtins/task_tool.py`（1159+ 行只读了 delegate 入口）、supervisor `execution.py` 的 L780–1521 后半、`context_compaction_core.py` 的压缩 LLM prompt 与分区函数细节。下一轮做 M 系列编排任务时按 §7.3 优先级逐文件补扫即可，本轮打底不含对这些分支的断言。

*方法：两轮扫描——V1 目录枚举+88 中间件 docstring 全量抽取+关键模块直读；V2 应要求对点名件全读源码（loop_detection 821 行、tool_approval_middleware 1446 行、compaction 主链、reconcile 全判定、delegate 流、lease 看门狗、executor），并以脚本对 1285 个 .py 做 import 普查定量（临时脚本已删除）。EvoFlow 仍为只读。*
