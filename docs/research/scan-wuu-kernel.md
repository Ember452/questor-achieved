# wuu 内核功能 + 架构清单（供 Questor 实施计划文档使用）

> 只读扫描 `d:\DEVELOP\My-project\wuu-main`（Go 内核）。忽略 `clients/`、`packages/`（前端 TS）、`desktop/`、`*_test.go`；`packages/protocol` 因涉及 RPC 契约仅在子系统 7 纳入。
> 目标：为「把 wuu 的 Go 逻辑翻成 Python 跑在 Windows、agent 循环按 wuu 语义手写（不引 LangGraph）」建立功能+架构底账，非逐行读码。
> Questor 三柱优先级固定：**可见 → 可干预 → 可验证**。明确不做：多用户 SaaS、组织排班/岗位值班、给别人二开的 agent 框架、LLM tracing 大盘。
> 规模信号（非测试 .go 文件数）：appserver 87 / tools 60 / providers 54 / session 34 / remote 29 / runtime 24 / agent 24 / agentcontrol 19 / pluginhost 17。

> 怎么读本文：**没看过 wuu 先读 §0 导读**（含四层对象图与一条消息的端到端流向）；要定移植范围查下面的归属速查表与 §8/§9；要开工某子系统再看对应 §1–§7；**§11 是本文的可信边界**（哪些结论已读到代码本体、哪些仍是形状级）。

## 目录 → 归属速查

| 归属 | 包 |
|---|---|
| 核心移植（做） | agentengine, agent(除 plugin 专用 seam), tools(除下列不做工具), toolresult, toolctx, toolerrors, toolledger, session, storagecodec, storelock, statepath, securefs, compact, contextbudget, providers(+anthropic/openai/codex/grokbuild/xaisub), providerfactory, provideroptions, modelcatalog, modelroles, modelvariant, modelprofile, modelbudget, process, execution, processsandbox, worktree, workspaces, shellpath, runtime(仅 engine_wuu/host/session/thread_derivation/artifact_publisher 等 ~7 文件), appserver(部分), packages/protocol(契约形状), instructions, capability, structuredoutput, imageproc, authstorage, credentialstore, prompt, context, config, runtimeconfig, workingnotes, sessiontrace, **activity(接管仲裁,本轮从"不做"移入)**, cmd/wuu(入口形态参照) |
| 待用户拍板（本轮新增） | `plugins/goal`·`todo`·`memory`·`ask-user`·`peers`·`automation`·`dream` 对应的**能力**是否内建；`agentprofile`(list/create_agent_profile 工具)；`exec`(CLI 驱动面)；`executionworker`(本地 socket worker)；见 §9 |
| 明确不做 | remote(全部), plugin, pluginhost, runtime(plugin_* 胶层 ~14 文件), **loopdriver(实为插件接管循环的口子)**, extensions, hooks, skills, subagent, agentcontrol, agentthread, participant, sidethread, mcp, codemode, externalengine, codexengine, claudeengine, enginecatalog, schedule, **insight(用量分析大盘)**, evalharness, harness, executionenv(云/codemode 耦合), cmd/wuu-server(实为 relay 服务)、cmd/plugin_dev*、cmd/remote*, grokbuildspec(视 provider 取舍) |

---

## 0) 导读：给没看过 wuu 的人（先建立心象，再读清单）

**一句话**：wuu 是一个本地跑的"AI Agent 工作台"内核——一个 Go 进程持有 agent 循环，跑模型、跑工具、把过程写进本地 SQLite，并通过 **stdio 上的 JSON-RPC** 向界面（桌面 Electron 壳）推流。它不是服务，不监听端口，不作为多用户后台。

**四层对象（最重要的心智模型，弄混就会把循环写错）**：

```
Thread  一个会话（绑定一个引擎与一个工作区，永不静默换引擎）
 └ Run   一次 agent 调用的"控制与观测边界"（引用而非复制下面的 Turn）
    └ Turn  一次用户输入引发的一轮对话（开始时就定死 model/provider）
       └ Step   一轮 model 往返（循环内部概念，**不对外暴露**）
          └ Item  一个可见产物单元（文字/推理/工具调用，带 delta/replace 流式增量）
```

**一条用户消息的完整流向**（把本清单各节串起来）：

1. 界面发 `turn/start`（stdio JSONL）→ appserver 找到该 thread 绑定的 `agentengine.Session`（内建实现是 `runtime/engine_wuu.go` 的 `WuuEngine`）→ `RunTurn(ctx, TurnInput{History}, EventSink)`。[§1、§7]
2. 循环 `agent/loop.go::RunToolLoop` 进每一轮：先 `BeforeStep`/`BeforeModelStep` **注入插话**（来自 `session/held_user_work.go` 的 queue/steer），再修悬空 tool-call（`repairLiveToolCallHistory`），按需 proactive compact 或换 fresh context。[§1、§3、§4]
3. 拼 `providers.ChatRequest`（经 cache hint / 工具面过滤 / provider 选项）→ `Step` 执行一次往返（Runner 走 `Client.Chat`，StreamRunner 消费 `StreamClient.StreamChat` 的 SSE/WS）→ 产出 `StreamEvent`，经 EventSink 变成 `item/*/delta` 推回界面。[§1、§5、§7]
4. 模型要调工具 → `TurnToolRuntime` 按 `ToolMetadata.ConcurrencySafe` 上 `ToolExecutionGate`（只读并发、写排他），过 `checkPermission` 链（**hook→boundary→特例→Reviewer→Authorizer**）与 `ResolvePath` 路径约束 → 工具真做（文件写内嵌 `DiffResult`，命令走 process/沙箱）→ 结果经预算/投影/脱敏 → **即使被取消也要 `ledger.Settle`** → 作为 tool 消息回给模型。[§1、§2、§6]
5. 收尾：`LoopResult` 带 `HistoryRewritten`（决定持久化是替换还是 append）与累计 usage 回到 appserver，发 `turn/completed`；全程状态写 `sessions.sqlite3`，崩溃可凭 `driver_checkpoint`/`inference_journal` 恢复。[§1、§3]

**三柱在代码里的对应位置**（Questor 的优先级序）：

| 柱 | wuu 靠什么做到 | 本清单 |
|---|---|---|
| 可见 | `item/*` 的 `delta` / `replace` 流式事件；write/edit 内嵌结构化 diff；`Thread.Dirty` / `ChangedFiles`；`process/*` 终端面；`browser/cdp`；`thread/context-composition` | §2 §7 |
| 可干预 | `turn/steer`、`turn/queue`、`turn/requeue` + `held_user_work`（运行中插话改道）；`user-question/*`（agent 反向提问）；`activity/takeover`、`activity/release` + Lease（控制权交接）；`run/interrupt` + 取消仍落账；boundary 三档 | §1 §2 §3 §7 |
| 可验证 | append-only 历史 + inbox 幂等投递；toolledger；结构化输出校验；脱敏常开；敏感路径守卫；`run` 退出码与改动文件 | §2 §3 |

---

## 1) agent 循环与生命周期

引擎生命周期契约的**唯一真实来源**是 `internal/agentengine/agentengine.go`（313 行）；`internal/enginecatalog` 只是外部引擎探测目录，**不是**生命周期契约。循环本体在 `internal/agent/loop.go`（1735 行，函数 `RunToolLoop`）；`internal/loopdriver` 标注为 "experimental"，本轮实测发现它是**插件接管循环的口子**（服务端 `driver.model-loop`/`driver.checkpoint` 长在 pluginhost 上，见 §1 末尾与 §9），Questor 不做插件则整体不移植。

### 能力清单（带目录路径指针）

- **引擎边界契约** `internal/agentengine/agentengine.go`：一个 Engine = 自持 loop/model/auth/tools/native session/resume 的系统；wuu 只统一上层产品语义（thread/turn/run/events/status/stop/resume/桌面呈现），绝不伸进外部引擎内部。
  - `EngineID`（thread 建绑定时绑定、永不静默切换；本 build 只有 `EngineWuu="wuu"`）；`NormalizeEngineID/IsKnownEngine/KnownEngineIDs/CheckEngine`（空→wuu 兼容遗留 thread）。
  - `Descriptor{ID,Version,Capabilities}`；`OpenRequest{ThreadID,SessionID,RootDir}`；`ResumeRequest{OpenRequest,AdapterVersion,ProtocolVersion,ExternalSessionRef}`（wuu 引擎从 canonical history 恢复，不带 adapter state）。
  - `TurnInput{History []providers.ChatMessage}`；`EventSink = func(providers.StreamEvent)`（原生 StreamEvent 转统一事件形状）。
  - 审批面：`ApprovalKind`(command_execution/file_change/permissions)、`ApprovalDecision`(accept/accept_for_session/decline/cancel)、`ApprovalRequest{Kind,EngineID,ThreadID,TurnID,ItemID,Command,CWD,FilePath,Reason,Permissions}`、`ApprovalHandler = func(ctx,ApprovalRequest)(ApprovalDecision,error)`（阻塞直到决策/过期/取消/turn ctx 结束；**缺 handler 必须 fail closed**）。注意：这套审批是给**外部引擎**用的宿主交互桥，内建 wuu 引擎的权限走 §2 的 boundary。
  - `TurnResult{Result agent.LoopResult}`；`Session interface{RunTurn/Interrupt/Close}`；`Factory interface{Descriptor/Open/Resume}`；`Registry`（EngineID→Factory，Register/Lookup/Unregister/Descriptors）；`ThreadBinding{...PermissionMode,Instructions,MCPServers,ExternalRef,PersistRef,RequestApproval}`；`ThreadBoundFactory.SessionForThread`；`FailedSession(err)`（引擎起不来时让本轮带具体错误终止，而非泛化 unavailable）。
- **内建循环** `internal/agent/loop.go`：`RunToolLoop(ctx, history, cfg LoopConfig, step Step)`——transport 无关，caller 提供单轮 model 往返的 `Step`（Runner=Chat，StreamRunner=SSE 消费）。
  - 止损/续跑语义（关键硬编码）：`const maxConsecutiveContinuations = 8`——**即使 MaxSteps 无限也封顶**，"坏掉的兼容端点不得造成无限计费循环"。续跑触发条件：`len(ToolCalls)==0 && finishReason==FinishReasonContinue && !Truncated`→计数+1，否则清零；超 8 直接 `return ..., error("provider continuation limit exceeded")`。
  - `MaxSteps`（0=无限，正值=runaway 安全网）；overflow 时 `cfg.Compact` **调一次**再重发；若那次没缩小则 force-trim 老 turn 到合法 tool-call 边界，仅当替换更小才再试一次；失败/no-op 恢复**绝不重试同一 overflow payload**。
  - `EmptyAnswerError{StopReason}`/`IsEmptyAnswer`（模型本轮无文本无工具；StopReason="" 通常意味着 proxy/兼容问题而非模型自愿）。输出截断=带 `FinishReason=length` 的正常完成（不再自动续请求）。`ToolSurfaceFreezer`（MCP 类异步变动的工具面在一轮内冻结保持 req.Tools 字节稳定）。
  - **fresh context** 旁路（本轮读到执行细节 L455-557）：触发条件 `newContextRequested || hardContextRollover`（后者=`freshContextEnabled && threshold>0 && usage.EstimateCurrent()>=threshold`）；一旦 attempt：**先 `cfg.ArchiveHistory` 归档并把 `archive.Seqs` 回填到 messages/providerMessages**（`applyArchivedHistorySeqs`，清空 `durableNewMessages`，推 `historyArchiveHeadSeq`），再要么 `forceTrimOverflowHistory`（overflow 强制截，不小则 `ErrFreshContextNotSmaller`）要么 `cfg.FreshContext(...)`；成功且确实变小才 `resetTranscript(replacement)` 并**拍下 rollback 闭包 `freshRollbackHistory`**（还原 messages/providerMessages/historyRewritten/retained/sentRequestContext + `usage.Reset()`+`UsageAdjustmentRequestShapeReset`）；随后给模型插一痕 request-only 提醒："The host has installed a fresh active window. Read your persistent notes and recover missing facts from durable history before continuing. **No summary was generated.**"（所以上下文里没有压缩摘要，要模型自己读 notes/查 history）。失败时除了 `CompactAttemptFailed` 事件，仅在 `hookErr!=nil || cfg.CompactOnly || forceOverflowTrim` 时直接返回错误。
    - **另一道独立防线**：每轮开头先跑 `repairLiveToolCallHistory(messages)`——**修补历史里的悬空 tool-call**（上一版未提）；失败直接带当前快照返回。它在 proactive compact 之后、拼请求之前，是 overflow/中断后恢复可发请求的关键。
- **循环配置扩展面** `internal/agent/step.go`（`LoopConfig` L203-415 / `StepResult` / `LoopResult` L418）：`LoopConfig` 是巨型 harness seam，含 Model/ProviderName/ProviderObservationKey/ModelVariant、MaxContextTokens/MaxInputTokens/OutputReserveTokens、CompactThresholdTokens/Pct/KeepRecentTokens、Compact/FreshContext/ArchiveHistory/CompactionRegistry/CompactionNoteStore/ForkCompactionNote、BeforeStep/BeforeModelStep/BeforeRequestContext/BeforeRequest/RequestTransforms(插件链)、OnUsage/OnTokenUsage/OnMessage/OnToolResult/OnToolResultDetail/OnCompact*/OnToolBatchRejected、Effort(low/medium/high/max)、ForceToolFirstStep(agent_report 机械收尾)、RetainedRequestContext(prompt-cache 连续性)、UsageTracker。`LoopResult{Content,NewMessages,DurableNewMessages,HistoryRewritten,HistoryArchiveHeadSeq,RetainedRequestContext,...}`——**HistoryRewritten=true 时持久化要替换而非 append**。
- **两个 Runner** `internal/agent/runner.go`(`type Runner` L109, 非流 Chat)、`internal/agent/stream_runner.go`(`type StreamRunner` L31, SSE 流式)——确认 wuu **确有 StreamRunner 符号**。
- **并发门** `internal/agent/tool_gate.go`：`ToolExecutionGate`——读写信号量，leaf 执行共享读、unsafe 写排他（waitingWriters 防写者饿死）；编排器**不获取**该门（持叶子槽等子会死锁）。
- **每调用执行体（本轮新读，上一版完全缺失）`internal/agent/tool_runtime.go`（895 行）的 `TurnToolRuntime`**：这才是"一个 tool call 如何跑起来"的真体。
  - **元数据驱动并发**：`runner.go` L45 `ToolMetadata{Orchestrator, ReadOnly, ConcurrencySafe, Destructive, Risk, Reason}`；`ToolMetadataProvider` 注释原文："The agent loop uses this to partition tool calls: **read-only tools run concurrently, write tools run serially**"；`Orchestrator` 注释："coordinate child calls but perform no leaf operations themselves. **Their children, not the parent, consume execution slots**"。分流落点：`toolIsOrchestrator` 为真→`toolctx.WithNestedExecutor(&nestedToolScope{...})`；否则→`WithNestedExecutor(nil)` + **`r.gate.acquire(runCtx, concurrencySafe)`**（true=共享，false=排他）。
  - **调度时刻定死并发性**：L304-306 注释——"Final-call registration can refresh metadata while this streamed run is already starting. **Use the scheduling decision made under the runtime lock**"；即 `concurrencySafe` 在锁内一次定死，防流式已起后元数据被刷新导致的不一致。
  - **取消也不能丢账**：结算走 **`r.ledger.Settle(context.WithoutCancel(runCtx), invocationID, result)`**——即使本轮被取消/中断，工具结果仍写入 toolledger；移植到 Python 时必须用不受取消影响的结算通道（`asyncio.shield`/独立 task），否则中断会丢工具结果。**错误不向上抛而是当结果回给模型**：`executionErr != nil` → `toolresult.FromErrorText(errorJSON(err))`。
  - **流式期间就起工具**：`toolCanStartDuringStreaming` + 测试 `DoesNotStreamStartAcrossWriteBarrier`——模型还在输出时叶子工具已可开跑（推测式并行）；另可选接口 `ToolCallContextProvider.TakeAdditionalContext(call)`→`postToolAdditionalContextSegment`（**工具跑完可注入 request-only 上下文**）与 `ToolResultFinalizer.FinalizeToolResult`。
  - **barrier tool 机制存在但当前空置**：`rejectBarrierToolBatch(calls,...)` 在批量>1 且含 barrier 时 `r.Cancel()` 并给每个 call 生成拒因结果（barrier 自身："must be called alone; re-issue it as the only tool call after reviewing sibling results"；兄弟：“not executed because a barrier tool was called in the same assistant message”），并通过 `OnToolBatchRejected(ToolBatchRejectionInfo{StepIndex,BarrierTool,SiblingTools,ToolCallCount})` 上报——**但 `isBarrierTool(name)` 现为 `return false`**（无工具被分类为 barrier）。移植时要么接上自己的 barrier 集（如 new_context/agent_report 类"必须单独调"），要么明确删掉该枝，不要留一个永不命中的死枝。
  - `registerFinalCalls`/`TakeRequestContextSegments`/`currentStepIndex` 与 `StepIndex` 经 `toolctx.WithStepIndex` 下传；nested 调用走 ledger 而不做 provider 投影（测试 `NestedCallsUseLedgerWithoutProviderProjection`）。
- **可选实验循环边界（实为插件扩展面，订正）** `internal/loopdriver/contract.go`：`ContractVersion=1`、`Descriptor/ExecutionContext/PersistedInput/LoopPolicy{ModelRoundLimit,DisableTools,DisableCompaction}/ModelLoopReceipt/TerminalStatus(succeeded|failed|canceled)/Checkpoint{contract_version,driver_id,state}/TerminalOutcome`、`KernelGateway{ExecuteModelLoop,WriteCheckpoint}`、`Driver{Descriptor,Create,Resume}`、`Instance{Run,Checkpoint,Cancel,Shutdown}`、`CheckpointStore`。其余：`default.go`(内建驱动)、`gateway_wire.go`、`helpers.go`、`remote.go`。
  - **关键发现（上一版未识）**：`runtime/driver_gateway.go` 说明这个"实验性边界"的服务端就长在插件宿主上——"tracks the live kernel gateways of in-flight **remote driver** runs... The kernel's **`driver.model-loop` and `driver.checkpoint` services** route through it"，且该文件 **import `internal/pluginhost`**。即：把循环控制权交给外部 driver，是 wuu 给**插件接管循环**预留的口子。Questor 不做插件→**`loopdriver` 整体不移植**（而不是上一版说的"留作后续可插拔"），但其中两个概念要保留在内建实现里：`Checkpoint{driver_id,state}` 的续跑语义（§3 `driver_checkpoint.go`）与 `TerminalStatus` 三态终因。

### 移植成 Python 的要点/风险

- **取舍**：Questor 手写循环应对齐 `RunToolLoop`+`Step` 抽象（transport 无关），**直接实现 StreamRunner 语义**；`loopdriver` 经本轮实测确认是**插件接管循环的口子**（服务端长在 pluginhost），Questor 不做插件则**整体不移植**，只保留其 `Checkpoint` 续跑与 `TerminalStatus` 三态终因两个概念。`agentengine` 的多引擎 seam 在单引擎（仅 wuu）下可**退化为薄契约**——但建议保留 EngineID/TurnInput/EventSink/Session/TurnResult 命名，作为「引擎契约缺位」ADR-0033 的 M6 准入落地载体。
- **止损边界必须硬编码同值**：`max_consecutive_continuations = 8` 是与"坏端点无限计费"搏斗的关键，Python 循环必须复刻，不能只靠 max iterations。`FinishReason.continue` 语义（无工具也要再来一轮）需在 provider 归一化层显式建模。
- **两条上下文路径不可混为一种**：reactive/proactive `Compact`（摘要、要模型调用）与 `FreshContext`/`new_context`（无模型、先归档再释放）。`LoopResult.HistoryRewritten` 决定持久化是替换还是 append——移植到 append-only store 时是核心正确性点。
- 与上互补：Go 的 `context` 取消/超时链要用 `anyio`/task cancel 对齐；`ApprovalHandler` 的 **fail-closed**（缺 handler 即拒）在 Python 侧要用"没有审批通道就拒"而不是默认放行。
- **工具并发模型必须按元数据分波，不能图省事全串行或全并行**（本轮新读 `TurnToolRuntime`）：Python 侧等价做法——给每个工具声明 `ToolMetadata(concurrency_safe=...)`，用 **`asyncio.Semaphore` + 一个写互斥锁**建模 `ToolExecutionGate`（共享读/排他写 + 等待写者时不再放新读者），并在**调度那一刻**确定 `concurrency_safe`（锁内一次定死）而非执行时再查；编排类工具标 `orchestrator=True` 且**不占槽**（否则子任务永久死锁）。最易错的一条：**工具结算要用不受取消影响的通道（`context.WithoutCancel` → Python `asyncio.shield` 或独立 task）**，否则用户中断会丢工具结果、账本与历史不一致；错误也不向上抛而是 `FromErrorText(errorJSON(err))` 当结果回给模型。
- 另一条待决：`isBarrierTool` 现在恒返 false（barrier 机制写好但无工具注册）。Questor 若要用（例如要 `new_context` 必须单独调）就同时接上判定与 `OnToolBatchRejected`→`turn/*` 事件；若不用则删枝，不要带一个永不命中的分支进计划文档。
- **`LoopConfig` 字段裁剪**：近 60 字段大半服务于插件/子代理/MCP（`RequestTransforms`/`MCPServers`/`BeforeStep` 注水 send_message/`ForceToolFirstStep` 服务于 agent_report），Questor 不做这些→**砍字段但要留最小扩展点**，避免退化成不可测的巨石 config。已证实**不属插件面、建议保留**的钩子：`BeforeStep`/`BeforeModelStep`（插话注入←→§3 held user work）、`OnToolResultDetail`（无损结果，比 `OnToolResult` 字符串投影更可审计）、`OnCompactStart`/`OnCompactAttempt`（压缩进度与失败的真实来源，UI 要用）、`BeforeCompact`/`AfterCompact`（可否决某次压缩或拒收替换转录）、`UsageTracker`（让新一轮首请求前就能做与轮中一致的 compact 决策）。

### 关键文件

`internal/agentengine/agentengine.go` · `internal/agent/loop.go` · `internal/agent/step.go` · `internal/agent/runner.go` · `internal/agent/stream_runner.go` · `internal/agent/tool_gate.go` · `internal/agent/tool_runtime.go` · `internal/agent/adaptive_compact.go` · `internal/loopdriver/contract.go`

---

## 2) 工具层 `internal/tools`（60 文件）

### 能力清单（带目录路径指针）

- **工具集（真实工具名，从 `Name()` / 工具名常量逐文件解析，非按文件名推断）**：共 18 个属于要移植的面——
  `bash`(tool_bash.go；**`tool_shell.go` 不单独注册工具，只是 shell 辅助**，上一版把它当成第二个工具误列)、`read_file`、`write_file`、`edit_file`、`list_files`(均在 tool_files.go)、`grep`、`glob`(tool_search.go，+游标分页/回退)、`git`(tool_git.go)、`process`(tool_process_tool.go)、`web_search`、`web_fetch`(tool_web.go)、`present_artifact`、`tool_search`(tool_discovery.go——**工具也需被发现**,按需加载)、`notes`(tool_notes.go，常量 `toolNotes="notes"`)、`new_context`(常量 `="new_context"`)、`history_read`、`history_search`(tool_history.go)、**`wuu_browser`**(tool_browser.go，常量 `browserToolName="wuu_browser"`)。→ 没有独立的 `search`/`diff`/`review`/`terminal` 工具：diff 在 write/edit 结果里(§2 diff.go)，终端在 app-server `process/*` RPC 面(§7)，而不是工具。
  不做/取舍：`run_code`(tool_code_mode.go→codemode)、`load_skill`(skills)、`plugin_manager`(plugin)、`session`(tool_project_session.go,常量 `="session"`,协调器)、thread_get(子代理)、`list_agent_profiles`/`create_agent_profile`(tool_profiles.go→agentprofile,**若 Questor 保留"岗位/角色画像"则需重评**否则不做)、`set_session_workspace`(tool_session_workspace.go,工作区切换,可取)。
- **权限门（单一权威）** `boundary.go`：`WorkspaceBoundary{Enforce,AllowMutations,Guards}`——**"derived from reachability, never from trust. 无 approval、无 human-in-the-loop、无 per-tool 信任策略"**，每次调用只答"允许吗"，denied 带 model 可读理由。三档 profile：`StandardBoundary()`(Enforce+Allow 默认)、`ReadOnlyBoundary()`(Enforce 禁所有 mutation)、`UnconfinedBoundary()`(lift path 限制，稀有逃生阀)。**路径约束由 `Env.ResolvePath` 落地，不在 Check 内**；`Check` 只跑 read-only 门 + Guard 链。`Guard.Check(info,call) error`——"绝不为等待用户输入而阻塞，绝不返回 approval/ask"。`mutates(info)` 按 `ToolKind`(File/Shell/Test/Git/Agent/Process/Schedule/MCP/Browser/Plugin) 判定；Browser 除非该 call 分类为 read-only 否则算 mutating。`boundaryError` 携带 `Reason`+`ModelNextAction`。
- **可选收紧缝** `authorization.go`：`Authorizer{Authorize(ctx,AuthorizationRequest{SessionID,ActorID,CWD,PermissionMode,Tool,Arguments})(AuthorizationDecision)}`——"workspace boundary 仍权威、**不可被 authorizer 提权**"，只能进一步限制。
- **HITL 复核（独立于 boundary）** `review.go`+`approvefor/review.go`：`Reviewer{Review(ctx,approvefor.Request)(approvefor.Decision)}`；`Toolkit.reviewToolCall` 仅当 `t.approveForMe` 为真时触发——boundary 已放行后对高风险原生调用二次把关；`reviewDenied/reviewBlocked` 的 model_next_action 明确要求"勿绕过/勿重试等价操作，等用户显式批准后重提"。
- **权限链真实顺序（本轮读 `toolkit.go::checkPermission` L112-146 证实；上一版写的"boundary→Authorizer→Reviewer"顺序是错的）**：
  1. **幂等护盾**：`ctx.Value(permissionCheckedContextKey{})` 为 true 则直接放行——**同一 ctx 内只过一次门**（nested/子调用不重复触发审批）；`markPermissionChecked(ctx)` 给已检过的下游用。
  2. `permissionRequestHook`（可选，在所有判定**之前**）。
  3. **`t.boundary.Check(info, call)`**——单一权威。
  4. **硬编码特例**（L126-128）：`plugin_manager` 且非 ReadOnly 且 Enforce 且（未开 approveForMe 或无 reviewer 或 mode≠standard）→ `reviewBlocked("plugin_trust_required")`；注释原文："Host plugin code is not confined by the workspace process sandbox. **Optional review must not silently turn into implicit execution trust.**"——即**可选复核不得默认变成隐式执行信任**（插件不做，但这条设计原则要沿用）。
  5. `t.reviewToolCall(...)`——Reviewer/approveForMe（HITL）。
  6. **最后才是 `t.authorizer.Authorize(...)`**：`t.authorizer == nil` 则放行；**报错即 `authorizationDenied("authorization provider unavailable")`（fail closed）**，且 `decision.Outcome` 必须字面等于 `"allow"`。
  另有 `RefreshAuthorityFrom(parent)`（休眠 worker 恢复前重贴父策略，含当前 turn 绑定的 reviewer）与 `AuthorizeTool(...)`（动态/插件工具走同一 `checkPermission`，但 Kind 强置 `ToolKindPlugin`）。
- **敏感路径守卫** `sensitive_paths.go`：`sensitivePathReason` 逐段判定 `.git/.hg/.svn`(版本控制元数据)、`.env`/`.env.*`、`.netrc`、`.npmrc/.pypirc/.pgpass`(凭据配置)、含 credential/secret 的路径、SSH 私钥(id_rsa/id_ed25519/id_ecdsa)。`sourceCredentialExtensions` 白名单让 `credentials.go` 等**源码**不误判为凭据存储（凭据后缀 .json/.yaml/.pem/.env 仍算敏感）。
- **结果预算/投影/脱敏**：`result_budget.go` `finalizeGenericToolResult` 是结算边界——只约束 model 可见文本、结构化 metadata 保持私有完整、保留原生 media；超 `defaultProjectionTokenBudget` 则 `persistResult` 落 sessionDir 并 `buildBoundedResultReference` 生成预览引用；**artifact 写失败则 fail-open 原样返回**；`maxRecoveryPageBytes=128KB`。`result_projection.go`/`result_projectors.go`(per-tool 投影)、`providers/tool_result_projection.go`。`redaction.go`：`toolOutputRedactors` 正则脱敏 bearer/api_key/access_token/refresh_token/id_token/token/authorization/password/secret、`sk-` 密钥、PEM 私钥块；JWT 用 JOSE header 校验区分真凭据 vs 点分模块名。
- **diff / review 能力**：`diff.go` `computeDiff(old,new,contextLines)` 基于 `sergi/go-diff`(diffmatchpatch) 产 `DiffResult{Hunks[]{OldStart,NewStart,Lines[]{Op(equal|insert|delete),Content}},NewFile,Lines,OldLines,NewLines,Truncated,Summary}`——**write/edit 工具把结构化 diff 塞进 tool result**，是 Review 面板数据源。`git_attribution.go`+`gitattribution/`(author/committer 归因)、`review.go`。
- **路径约束的真体（本轮补读）** `env.go::ResolvePath(input)` L413-455：trim→空则`"."`；绝对则 `Clean`，相对则 `Join(e.RootDir, candidate)`；再 `filepath.Abs`；**`BypassToolHardProtections()`(=`e.Unconfined`) 为真则直接返回不做约束**（这就是 `UnconfinedBoundary` 的落地）；若 `len(e.FileScopeRoots) > 0` 则逐 root 走 `pathWithinRoot`，不命中就拒，**拒绝文案是中英双语且面用户**：`"...outside the allowed file scope (agent home directory, Wuu home, registered workspaces, and the system temp directory): 该路径不在工作区内，请用户在侧栏添加该目录为工作区后重试"`；否则用 `filepath.EvalSymlinks` **同时对 root 与 resolved 解软链**后再 `relInsideRoot` 判逐出（软链逐出防御）。`relInsideRoot` L462：**`runtime.GOOS == "windows"` 时把 root 与 path 都 `ToLower` 再比**——即 wuu **已处理 Windows 大小写不敏感**（上一版把这个列为未处理风险，现修正）；仍未见处理的只剩 **8.3 短名、`\\?\` 前缀、UNC 路径**这三类，移植时需补规范化。`pathWithinRoot` L560 同样走 EvalSymlinks。
- **不变量（对移植重要）** `env.go` L404-409 注释原文：`RedactToolOutput` **"stays on in every permission mode, including unconfined: lifting the path boundary does not lift secret redaction"**——即**脱敏与路径约束解耦，逃生阀不能关掉脱敏**；Python 移植必须保持这条单向依赖。`Env` 其他关键字段：`FileScopeRoots []string`、`ActiveSurface capability.Surface`、`OnFileChanged func(absPath)`（写后触发 FileChanged hook，**tools 包不依赖 hooks 包的解耦手法**：回调注入）、`OnSessionWorkspaceChanged`(持久化+广播工作区变更)。
- **工具注册表本体（本轮新读）** `toolkit.go::rebuildRegistry` L354-413：这是"到底有哪些工具"的**唯一权威清单**，默认注册 21 个：`read_file`/`write_file`/`list_files`/`edit_file`、`grep`/`glob`、**`bash`+`process`**、`git`、`web_search`/`web_fetch`、`load_skill`、`thread_get`、`set_session_workspace`、`new_context`、`notes`、`history_read`/`history_search`、`list_agent_profiles`/`create_agent_profile`、`wuu_browser`、`tool_search`；**条件注册 4 个**：`plugin_manager`(有 PluginManager)、`present_artifact`(有 ArtifactPublisher)、`session`(有 ProjectSessions)、`run_code`(有 codeMode/PTC)。注释两处关键：**"bash runs bounded foreground commands and local verification; process owns the background-process lifecycle. **Both are emitted by the model profile compiler.**"**（前台有界 vs 后台生命周期分工，且由 model profile 编译器决定暴露）；浏览器默认启用、可 `SetBrowserEnabled(false)`/`WUU_ENABLE_BROWSER=0` 隐去。
- **执行链（`ExecuteResult` L1251-1280 实读）**：nested 且 `DirectOnly` 工具 → 拒("must be called directly")；`CodeModeOnly`(PTC) 且非白名单且非 nested → 拒("requires calling tools inside run_code")；`IsToolDisabled` → 拒；`ensureToolAvailableForExecution`——**工具面(surface)不允许则拒；`ToolExposureDeferred` 且未加载则拒："tool %q is deferred; call tool_search first to load it"**，但会从历史里 `DiscoveredToolNamesFromMessages` **恢复已加载态**（重建运行时不丢 discovery 结果）；`registry.Lookup` 不命中→ 回退查 MCP 快照；**`wuu_browser` 走专用枝：绑定一个 `KindBrowser` activity lease**（注释原文："binds its tab-addressed actions to a KindBrowser activity lease, **the same discipline MCP CUA tools get**, via the shared spine"）→ 最后 `executeKnownToolResult`。这条注释直接证实 §8 把 `activity` 归为"接管仲裁"而非 tracing。
- **工具接口/注册** `tool.go`(`Tool interface{Name...}`、`Registry{tools []Tool}`)·`toolkit.go`(`type Toolkit{env *Env,...}`,1880 行)·`tool_info.go`(`ToolKind` L18 / **`ToolInfo{Name,Kind,ReadOnly,Destructive,Risk,Reason,Exposure,ConcurrencySafe}`** L51——上一版漏了 `Exposure`(Direct/Deferred/Hidden) 与 `ConcurrencySafe`，而后者正是 §1 并发门的共享/排他依据)·`tool_policy.go`/`tool_profiles.go`·`tool_result_envelope.go`。
- **结果规范形状** `toolresult/result.go`(349 行)：`Result`+content types(text/image/audio/file/resource/resource_link)、`ArtifactPlacement`(inline/turn_end)、上限 MaxContentParts=128/MaxInlineDataBytes=2MB/MaxStructuredJSONSize=1MB/MaxResultBytes=3MB、SHA256 完整性；`toolresult/envelope.go`/`structured_index.go`；`toolledger/ledger.go`(工具账本,ledger-backed stream 恢复)。辅助：`toolctx/`(nested/ctx)、`toolerrors/error.go`、`structuredoutput/validator.go`(结构化输出校验)。`file_mutation_queue.go`(串行化文件写)、`env.go`(`Env{SessionID,RootDir,PermissionMode}`,含 `ResolvePath`)、`test_guard.go`/`tool_test_runner.go`(测试运行工具)、`surface_text.go`、`tool_surface_validation.go`、`tool_telemetry.go`。

### 移植成 Python 的要点/风险

- **权限模型要原样照搬，且照搬顺序**：单一权威 boundary + 从可达性推导 + 无 per-tool 信任 + 三档 profile，然后按 **hook → boundary → （硬编码特例）→ Reviewer/approveForMe → Authorizer（最后，报错即拒）** 的顺序实现（`checkPermission` 实读）。三条必须同时移植的设计意图：① **同一 ctx 只过一次门**（`permissionCheckedContextKey`）——否则嵌套/多通道会重复弹审批或重复计数；② **Authorizer 错误 fail-closed 且只认字面 `"allow"`**；③ **可选复核不得默认变成隐式执行信任**。这是 wuu「可干预」的骨架，别引 LangGraph 式 middleware 把它打散。路径约束与 boundary 分离（ResolvePath）这一设计也要保留。
- **工具面是编译出来的，不是写死的**：实际暴露由 `modelprofile` 编译器产出 `capability.Surface` → `Definitions()` 过滤 → `ToolExposure{Direct,Deferred,Hidden}` 三态决定；**Deferred 工具未加载前执行会被拒**（"call tool_search first to load it"），但重建运行时会从历史 `DiscoveredToolNamesFromMessages` 恢复已加载态。→ Questor 若不做 `tool_search`，就只能选：全量暴露（每请求带全 schema，影响 prompt cache 前缀稳定性）或另设发现机制；这个选择必须写进计划，不能默认“少个工具而已”。
- **diff 数据源是净新增能力**：wuu 用 write/edit 内嵌 `DiffResult`；Questor 当前 `review/diff.py` 只采集 write/edit、run 工具与外部改动零记录（见 ADR-0035 待裁）。移植时明确 diff 权威源＝盘/git 还是 tool-payload，避免 Item.payload 出现两套 diff 真相。Python 侧可 `difflib`/`unidiff` 或调 `git diff`。
- 结果预算 fail-open（写不出 artifact 就原样返回）+ 128KB 分页 + 结构化 metadata 不外泄的取舍要照做，防大结果撑爆上下文。
- 脱敏正则要移植（含 JWT 的 JOSE 头二次校验防误伤），放 Python 会涉及 `re` 的 `(?s)` 等价与性能。
- 风险：`boundary.go` 依赖 `Env.ResolvePath` 做路径约束——Python 无 Go `filepath` 语义，Windows 路径规范化（盘符/短名/符号链接/`\\?\`）是越权/误拒高发区，须重点测试。`securefs` POSIX 0600/0700 模式在 Windows 无等价（需 ACL/`icacls` 或换策略）。

### 关键文件

`internal/tools/boundary.go` · `internal/tools/authorization.go` · `internal/tools/review.go` · `internal/tools/sensitive_paths.go` · `internal/tools/result_budget.go` · `internal/tools/redaction.go` · `internal/tools/diff.go` · `internal/toolresult/result.go`

---

## 3) 会话与持久化 `internal/session`（34 文件）

> 说明：用户提到的「gesta 类」在 wuu **不是独立包**——`gesta` 只是 `agentthread`/`agentcontrol` 里 `EdgeStatus` 的巧合子串。append-only 会话/线程真相集中在 `internal/session`(+`storagecodec`/`storelock`/`statepath`)；线程图 nodes/edges 状态在 `internal/agentthread`（属多 agent 编排，见 §8）。

### 能力清单（带目录路径指针）

- **存储底座**：`session/session.go`(2549 行) SQLite——`dbFileName="sessions.sqlite3"`，驱动 `modernc.org/sqlite`（**纯 Go 无 CGO**，关键移植利好）。`storeWriteMu` 全局写锁 + `db.Begin()` 事务。错误码 `ErrSessionNotFound/NotArchived/HistoryUnavailable`。`storagecodec/`(编解码)、`statepath/`(状态目录布局)、`storelock/`(跨进程锁)。
- **inbox（host→session 待投递）** `inbox.go`：`InboxMessage{ClientID,SessionID,RelatedSessionID,Cause,Content,Wake,Controls,WorkID/Revision/Version}`——"delivered 判据=ClientID 已出现在目标持久历史"，故**重启后可重试投递而不重复注入**；`EnqueueInbox` 幂等（重复 ClientID no-op）。`Wake` 在目标 idle 时起轮，否则等下一轮。
- **held user work（运行中插话）** `held_user_work.go`：`HeldUserWork{SessionID,Position,ID,Origin,MessageJSON,RuntimeJSON}`，`Origin ∈ {queue, steer}`——**steer 即"运行中插话/改道"**，queue 排队；`ReplaceHeldUserWork` 事务化整批替换。
- **append-only 历史与恢复** `history_checkpoint.go`/`history_recovery.go`(418 行)：注册 SQLite 确定性函数 `wuu_history_content`（role/content/toolResult 复用同一 hydration，防 model_text 与多部分投影漂移）；`HistoryRecord`。`inference_journal.go`/`model_input_receipt.go`/`request_context.go`/`token_usage.go`(用量)。`driver_checkpoint.go`——把 §1 loopdriver 的 `Checkpoint` 落库（崩溃续跑）。
- **恢复/存在性** `context_seed.go`、`inference_process_alive_{unix,windows}.go`(进程存活判定)、`session.go` 的 archive 语义。
- **租约/锁（跨进程长驻安全）**：`thread_execution_lease.go`/`thread_lifecycle_lease.go`/`appserver_presence_lease.go`/`plugin_generation_lease.go`，各配 `_lock_unix.go`+`_lock_windows.go`（**OS 级跨进程文件锁**）；`worker_execution_lease`/`worker_terminal_*`(agentcontrol)。`inference_process_alive`/`appserver_presence_lock_windows` 说明 Windows 有专门实现分支。
- **组织/治理**：`session_organization.go`、`storage_governance.go`(保留/GC)、`project_work.go`/`subscription_activity.go`、`participant_store.go`(子代理身份,不做)。`compaction_note.go`(§4 压缩笔记持久化)、`plugin_*`(不做)。
- 相关小包装（已读导出面）：`storelock/store_lock.go`——**"serializes durable file-store transactions across processes"**，`Lock` + `Acquire(dir) (*Lock, error)`（就是记忆里说的 OS 级跳进程锁）；`storagecodec/storagecodec.go`——**"small, versioned encoding for large local [artifacts]"**，`Encode/Decode/Encoded/CompressFile(path)`(返回 changed/bytesBefore/bytesAfter)；`workingnotes/store.go`——**"persists session working memory independently of extensions"**，`Store{Home}`+`Checkpoint`，其测试透露两个语义：`LegacyNotesSurviveMigrationAndRestart`、**`ConcurrentNotesWritersRejectLostUpdates`（拒绝丢更新，即乐观并发）**——Python 移植 notes 时要保留这个冲突拒绝。`sessiontrace/trace.go`(会话 trace,≠tracing 大盘)、`authstorage/`+`credentialstore/`(凭据存储,做)、`instructions/instructions.go`(**做**——AGENTS.md/instruction 发现)、`statepath/statepath.go`(状态目录布局：其测试列出 `Home`/`WUU_HOME` 覆盖、legacy 路径忽略覆盖、`UserInstructionDirs` 先 canonical 后 legacy、**`WorkspaceDir` 稳定且在工作区之外**、`WorkspaceDirByID` 路径无关、`ProfileDir` 在 profiles 下、`AgentHomeDir` 在 WUU_HOME 下——这套目录布局是 Python 移植时定应用数据目录的直接参照)。

### 移植成 Python 的要点/风险

- **利好**：wuu 用纯 Go SQLite，语义就是标准 SQL + 文件库；Python `sqlite3`/`aiosqlite` 可 1:1 移植 schema、事务、WAL、自定义函数（`create_function` 替代 `wuu_history_content`）。append-only 的 seq/head（`HistoryArchiveHeadSeq`）与 `HistoryRewritten` 的"替换 vs 追加"要落到同一套 schema 约束。
- **必须移植的三件「可干预」硬骨头**：① inbox 幂等投递（以 ClientID 落入历史为 delivered）② held user work 的 queue/steer 插话语义 ③ loopdriver checkpoint 落库续跑。这三者共同构成"运行中可插话 + 崩溃可恢复 + 重启不重复注入"，是 Questor 可见/可干预的核心。
- **Windows 适配重点**：`storelock`/各 `*_lease` 的 `_lock_windows.go` 与 `inference_process_alive_windows.go` 表明跨进程锁与存活判定在 Windows 有独立实现。移植到 Python Windows 要用 `msvcrt.locking`/`Portalocker`/命名事件，**注意 Sidecar 崩溃防护与资源释放规范**（记忆项）。`storage_governance`/`worktree_storage_maintenance` 的 GC 要与 Windows 文件占用/句柄释放协作。

### 关键文件

`internal/session/session.go` · `internal/session/inbox.go` · `internal/session/held_user_work.go` · `internal/session/history_recovery.go` · `internal/session/driver_checkpoint.go` · `internal/session/thread_execution_lease.go` · `internal/statepath/statepath.go` · `internal/instructions/instructions.go`

---

## 4) 上下文压缩 `internal/compact` + `agent/adaptive_compact`

### 能力清单（带目录路径指针）

- **摘要压缩核心** `compact/compact.go` 导出 API（实证）：`Compact(ctx, messages, client providers.Client, model) ([]ChatMessage, error)`、`CompactWithContextWindow(..., maxContextTokens)`、`ShouldCompact(messages, maxContextTokens) bool`、`EstimateTokens(text) int`、`EstimateMessagesTokens(messages) int`、`IsSummaryOutputLimit(err) bool`、`type Budget`；`legacy_context.go: IsInternalContextMessage(msg)`。→ 注意摘要走的是 **`Client.Chat`（非流）**，Python 移植时不要复用主流式通道。`defaultCompactTimeout=20min`（overflow 唯一恢复路径，大历史可能要多次摘要请求）。预算常量：`SummaryInputMaxTokens=80_000`（摘要请求自身输入上限，独立于模型窗口）、`compactSummaryFallbackMaxTokens=4096`、`compactSummaryInputMinTokens=4000`、`fraction=0.5`；**分部件字节上限**——普通对话 `compactPromptMessageMaxBytes=80_000`（保留更多用户需求/工程理由），工具结果 `8_000`，工具入参 `4_000`，structured-only `500`（用 `stringutil`/toolresult 的 bounded semantic index 而非复制 raw body，防大/私密 payload）。`media_index.go`(媒体索引)、`legacy_context.go`(旧窗口兼容)。
- **预算推导** `contextbudget/budget.go`：窗口/输入/输出预留→触发阈值的统一推导（被 compact 与 loop 共用，保证 trace/UI 报的阈值与实际触发一致）。
- **自适应/反应式** `agent/adaptive_compact.go`：`compactBudgetHint{Reason(LastSuccessfulTokens/FailedRequestTokens/TargetTotalTokens)}` 经 ctx 传递；`observedCompactSafetyDivisor=5`、`observedCompactMinMargin=4000`——按"上次成功请求实测大小"反应式定目标，而非死算窗口；`BuildProviderObservationKey`(端点/协议隔离,防跨 provider 复用观测)。
- **压缩注册表/回退/笔记 seam** `agent/compaction_registry.go`(最高优先级 provider 胜出，`ErrCompactionUnavailable` 回退 legacy `cfg.Compact`)、`compaction_fallback.go`、`compaction_note.go`+`compaction_note_output.go`(fork-capable 压缩：隐藏 Markdown checkpoint，`ForkCompactionNote` 保主请求的 model+tool surface)、`context_note_metrics.go`、`retained_context.go`、`fresh_context.go`(**new_context 换窗旁路**：无模型调用，`ArchiveHistory` 先归档原始 turn 再释放,不摘要)、`default_context_window.go`、`usage.go`(`UsageTracker` 让新一轮首请求前就能做与轮中一致的 compact 决策)。`session/compaction_note.go` 落盘。
- **两条路径回顾**：① `Compact`（摘要,要模型；proactive 填充率触发 + reactive overflow 恢复）② `FreshContext`/`new_context`（无模型,归档后换窗）。见 §1。

### 移植成 Python 的要点/风险

- 移植成本可控：核心是"给分部件设不同字节预算、拼摘要 prompt、限 20min、按观测大小反应定目标"——Python 纯字符串/token 估算即可，但要**对齐阈值一致性**（contextbudget 单点推导，别在 loop 与 trace 各算各的，呼应记忆「枚举/阈值单一来源」）。
- token 估算：Go 侧混合 provider 报的 usage + 本地估算（`UsageTracker`/`estimate*`），Python 需选定 tokenizer（tiktoken/估算函数）并保证 `EstimateCurrent`/`estimateFreshContextMessages` 语义等价，否则 proactive 触发点漂移。
- fork-compaction note（隐藏 checkpoint + 主请求复用）与 fresh-context 换窗是两种不同产品语义，**不要合并实现**；Questor 若只做「可见」可先取摘要路径，把 new_context/note 作为进阶。
- 风险：20min 超时 + 多次摘要请求 + overflow 只重试一次的正确性（失败/no-op 不重试同一 payload）在 Python async 超时/取消下要显式建模，防死循环计费（与 §1 的 8 连继是两道不同防线）。

### 关键文件

`internal/compact/compact.go` · `internal/contextbudget/budget.go` · `internal/agent/adaptive_compact.go` · `internal/agent/fresh_context.go` · `internal/agent/compaction_registry.go` · `internal/agent/compaction_note.go` · `internal/agent/usage.go`

---

## 5) providers `internal/providers`（54 文件）

### 能力清单（带目录路径指针）

- **provider 无关契约** `providers/types.go`(825 行)：**接口名是 `Client` 不是 `Provider`**（上一版写错）——`Client interface{ Chat(ctx, ChatRequest) (ChatResponse, error) }`(L511)；`StreamClient interface{ Client; StreamChat(ctx, ChatRequest) (<-chan StreamEvent, error) }`(L796)。另含 `ChatMessage{Role,Name,ClientID,Content,DisplayContent,Origin,...}`(L312，**`Origin` 是产品来源,与 provider Role 独立**——插件生成的 query 仍投为 role=user 但在持久历史/UI 保留可审计的非用户作者)、`ChatRequest{Provider,Model,Messages,Tools,Temperature,...}`(L424，`Provider` 字段是配置身份、**永不上线**，防各家原生状态跨端泄漏)、`StreamEvent{Type,Content,Phase,Message,ToolCall,ReasoningBlock,ProviderItemID,Image,...}`(L757)、`TokenUsage{InputTokens,OutputTokens,CacheCreationTokens(仅 Anthropic),CacheReadTokens}`(L652)。
- **可选能力接口（类型断言式扩展，非必选）**：`NativeCompactor{NativeCompactionAvailable,NativeCompact}`(L814，配 `ErrNativeCompactionUnavailable`——**provider 自带压缩能力**,与 §4 摘要压缩是两回事)、`SessionPrewarmer{PrewarmSession}`(冷认证/传输预热)、`QuotaReader{ReadQuota}`(quota.go，注释明确"upstream snapshot，不是价格估算或本地 token 台账")、`MediaInputResolver{ResolveMediaInput}`、`InferenceRequestPreparer{PrepareInferenceRequest}`、`InferenceRecoveryApplier{ApplyInferenceRecovery}`、`InferenceJournal{PrepareOperation/PrepareAttempt/UpsertSubmission/MarkAttemptFirstEvent/CompleteAttempt/PrepareRecoveryAttempt}`+`InferenceProgressJournal`、`CatwalkClient{GetProviders(etag)}`(远程模型目录同步,ETag 缓存)。→ **移植启示**：Go 用"断言接口"而非构造注册做能力探测，Python 等价用 `isinstance`/`hasattr`；MVP 只需 `Client`+`StreamClient`，其余能力接口按需逐个加。
- **provider 无关契约·其余**：`ToolDefinition{Name,Description,InputSchema,Freeform,DirectOnly,DeferLoading,CacheStable}`、`LoadableToolDefinition`(发现流)、`ToolCallDisplay`(带 locale 翻译)、`FinishReason`(L101-114)：`stop / continue("无客户端工具也要再来一轮,不是 retry/truncation/完成证明") / length / tool_calls / content_filter / error / unknown` + `NormalizeFinishReason(stopReason,truncated,hasToolCalls)` 归一各家停止信号。
- **实注册的 5 家 provider（`providerfactory/factory.go` L210-274 逐个 `New`）**：`grokbuild.New`、`codex.New`、`xaisub.New`、`openai.New`、`anthropic.New`。`profile.go` 给出的配置别名字符串：`"openai"|"openai-compatible"|"codex"`、`"anthropic"|"claude"|"anthropic-official"`、`"openai-codex"|"codex-subscription"|"chatgpt-codex"`、`"xai-subscription"|"xai-oauth"|"grok-subscription"|"supergrok"`、`"grok-build"|"xai-grok-build"|"grok-cli"`，另兼容 `@ai-sdk/anthropic`、`@ai-sdk/openai`、`@ai-sdk/openai-compatible`、`@openrouter/ai-sdk-provider`、`@ai-sdk/xai`（即**可接 OpenRouter/兼容端点**）。子目录：`anthropic/`(client+quota)、`openai/`(client + `responses*` Responses API + `responses_websocket*` WS 流 + `dynamic_tools.go` + `turn_routing.go` + quota)、`codex/`(client+oauth+quota,内部复用 `openai.ResponsesWebSocketCache`)、`grokbuild/`、`xaisub/`(login/oauth)。
- **流式/SSE** `sse.go`、`stream_adapter.go`、`stream_emitter.go`、**`stream_transport.go`(`StreamTransportMode ∈ {auto, sse, websocket, websocket-cached}`，`config` 校验该值 L804**、`stream_limits.go`、`stream_recovery_error.go`、`reliable_stream.go`、`unavailable.go`。
- **韧性重试** `retry.go`(559 行)：`RetryConfig{MaxRetries,InitialDelay,MaxDelay}`；`NormalizeRetryConfig`/`DefaultRetryConfig`——**默认 0 retries（一次除非显式开）**,Initial 1s/Max 60s，指数退避+jitter(`math/rand`)；`HTTPError{ProviderFamily,ProviderCode,StatusCode}` 结构化错误分类驱动重试决策。`retry_profiles.go`(按 operation kind 配档)、`attempt_executor.go`(执行/重试生命周期)、`recovery.go`。
- **推理 operation 血缘/账本（去重+恢复）** `inference_operation.go`(`BeginInferenceOperationLineage`/`EnsureInferenceWorkflow`)、`inference_execution.go`、`inference_journal.go`、`inference_request_hash.go`(请求哈希,幂等/复用观测)。
- **配额/预算/路由/发现** `quota.go`、`workflow_budget.go`、`provider_coordinator.go`、`turn_routing.go`、`contextwindow.go`(窗口尺寸)、`media_policy.go`(`MediaInputPolicy` 自动探测)/`video_input.go`、`tool_call_history.go`、`tool_result_projection.go`、`tool_schema.go`、`tool_surface_validation.go`、`message_request.go`、`request_assembler`(agent 侧)、`catwalk_index.go`/`catwalk_sync.go`(模型目录同步)、`debug.go`。
- 相邻小包：`providerfactory/`(装配 provider)、`provideroptions/`、`modelcatalog/`(模型目录)、`modelroles/`、`modelvariant/`(模型选项 bundle)、`modelprofile/`、`modelbudget/`(压缩阈值来源 `CompactThresholdTokens`)、`credentialstore/`+`authstorage/`(凭据/OAuth 存储)。

### 移植成 Python 的要点/风险

- **契约层照搬**：`FinishReason.continue` 的精确语义 + `NormalizeFinishReason` 的各家映射，是 §1 止损循环能工作的前提——Python 适配层必须产出同一归一枚举，否则 8 连继计数逻辑失效。Python 可用 `httpx`+`sse`/手工 SSE；OpenAI Responses-over-WebSocket 是较重的独门流,视需求取舍。
- **默认不重试**是 wuu 的克制（`DefaultRetryConfig` MaxRetries=0）；Questor 移植别默认激进重试,配合 `attempt_executor`+`retry_profiles` 按 operation 分档。`HTTPError` 结构化分类要在 Python 用异常层次复刻以驱动相同决策。
- **operation 血缘/请求哈希**用于跨 provider 观测复用与幂等——移植是"锦上添花"的韧性层,MVP 可先做最小 retry+timeout,`BeginInferenceOperationLineage` 留待可验证阶段。
- 风险：provider 面很宽（5 家 + quota + OAuth + media/video）。Questor 个人工作台可先收敛到 1–2 家（如 anthropic + openai），codex/grokbuild/xaisub 的 OAuth/login 属凭据流程,与 authstorage 一起取舍。凭据文件写入走 securefs 的 POSIX 模式假设在 Windows 需重设。

### 关键文件

`internal/providers/types.go` · `internal/providers/retry.go` · `internal/providers/retry_profiles.go` · `internal/providers/attempt_executor.go` · `internal/providers/sse.go` · `internal/providers/inference_operation.go` · `internal/providers/openai/client.go` · `internal/providers/anthropic/client.go`

---

## 6) 进程与执行 `process/exec/execution/processsandbox/executionenv`

### 能力清单（带目录路径指针）

- **受管进程** `internal/process/`(9)：`command.go`——`ProcessTree`(Unix=进程组 id；Windows=root pid 供 `taskkill /T`)、`PrepareCommand`(隔离 cmd 使**整棵后代可被信号终止而不影响 wuu 自身**)、`DefaultStopGracePeriod=2s`。`manager.go`+`manager_unix.go`+`manager_windows.go`（Windows `ptySupported()=false`→**tty 降级为 pipe**）、`process_identity_{darwin,linux,windows}.go`(定位/杀进程树)、`storage_maintenance.go`、`remote.go`(不做)。→ 对应记忆「wuuCommand 绝不从 PATH 兜底解析被管进程 / childShutdown 等 exit 不等 pipe close」。
- **`wuu exec` 的 app-server 客户端/控制器** `internal/exec/`(8)：`types.go` import `internal/appserver`+`internal/execution`，配 `appserver_controller.go`、`protocol_client.go`、`runner.go`、`input/output.go`、`attachments.go`、`structured_output.go`——即命令行 `wuu exec`（入口在 `cmd/wuu/exec_lifecycle.go`）以协议客户端身份驱动 app-server 的一轮执行，**不是**"跑一条子命令的一次性执行器"（上一版本此处描述有误，已按 import 关系与 cmd 入口订正）。子命令生命周期属 CLI 面，内核移植只需其"如何组一次 turn 请求"的语义。
- **执行记录** `internal/execution/`(3)：`exitcodes.go`、`store.go`、`types.go`（run 结果/退出码持久化——Review 需知道 run 改动了什么,呼应 ADR-0035）。
- **OS 沙箱** `internal/processsandbox/`(4)：`sandbox.go`——`Mode ∈ {read-only, workspace-write}`，把子进程 FS 效应**约束到与 in-process 工具同一预工作区边界**；`ErrUnavailable`+`denialSignatures`(识别 "operation not permitted"/"permission denied")。`sandbox_darwin.go`(Seatbelt)、`sandbox_linux.go`、`sandbox_other.go`——**Windows 走 other：`platformSupported()=false`、`applyPlatform` 直接返回 ErrUnavailable**（确认：Windows 无 OS 沙箱，仅靠 §2 逻辑 boundary）。
- **worker/云执行环境（大多不做）**：`executionworker/`(artifacts/process/server/socket_unix/socket_windows——本地 worker over socket) 视需求取舍；`executionenv/`(client/**cloud.go**/config/environment/manager/protocol——云/远程执行环境,且 `environment.go` import `codemode`+`storelock`) → **属不做（远程/云执行）**。
- **工作区/worktree/shell/安全文件**：`workspaces/`(1,工作区根) · `worktree/`(open_or_create/worktree——`detached HEAD` under `worktrees/{session-id}/{worker-id}/`,worker 完成后**保留供用户 git diff/cherry-pick**,清理显式；wuu 中主用于 subagent 隔离,Questor 可取其"分叉可见"形态) · `shellpath/`(gitbash/normalize/resolve_unix/resolve_windows——shell 路径解析) · `securefs/`(全仓凭据/敏感文件统一 0600/0700,`O_EXCL`+`fsync`+`rename` 原子写,参照 Codex；无向后兼容)。

### 移植成 Python 的要点/风险

- **Windows 是本子系统最大落差**：Questor 跑 Windows，而 wuu 在 Windows 上 ① 无 PTY（pipe-only）② 无 OS 沙箱（`sandbox_other`→ErrUnavailable，只靠逻辑 boundary）。移植必须接受"Windows 无内核级沙箱"这一现实，靠 `Env.ResolvePath` 路径约束 + 命令白名单/deny 兜底；若要真沙箱需另引 Windows 机制（Job Object/AppContainer）。
  - **细化（已核）**：`ResolvePath`/`relInsideRoot` 已在 Windows 下 **lowercase 两边路径再比较**，并对 root 与目标都做 `EvalSymlinks`——所以大小写与软链逐出已防；**仍需 Questor 额外覆盖的是 8.3 短名（`PROGRA~1`）、`\\?\` 前缀、UNC 路径**，这三类能绕过前缀比较，建议 Python 侧统一用 `os.path.normpath`+`Path.resolve()`+casefold，并对 `\\?\`/UNC 显式拒绝或扩展后比较。
- **进程树终止**要用 Windows 语义（`taskkill /T` 或 Job Object）保证整棵后代被清、不误伤宿主；对齐「Sidecar 崩溃防护与资源释放规范」记忆——等 exit 不等 pipe close、优雅期 2s、kill 升级。
- `securefs` 的 POSIX 0600/0700 与原子 rename 在 Windows 需替换为 ACL/`os.replace`+fsync 等价（`MoveFileEx`/`ReplaceFile`）——移植时列"不采纳/需替代"防 scope 漂移。
- worktree 的"分叉可见"（保留 worker worktree 供 diff/cherry-pick）契合「可见」柱，可移植为**用户并行探索**，但要剥离其 subagent 绑定；调用 `git worktree` 需 shell 路径解析（`shellpath`）。
- 不做：`executionenv`(云/codemode 耦合)、`process/remote.go`、大部分 `executionworker`。

### 关键文件

`internal/process/command.go` · `internal/process/manager_windows.go` · `internal/process/process_identity_windows.go` · `internal/processsandbox/sandbox.go` · `internal/processsandbox/sandbox_other.go` · `internal/securefs/securefs.go` · `internal/worktree/worktree.go` · `internal/execution/store.go`

---

## 7) app-server 协议面 `internal/appserver` + `packages/protocol`

> 契约集中在 `internal/appserver/protocol.go`(2770 行)：`ProtocolVersion="wuu-app-server/v0.1"`，方法/通知是 `Method<域>/<动作>` 与 `<域>/<事件>` 字符串常量。
>
> **传输（实测订正）**：app-server ↔ 客户端只有 **stdio JSONL/NDJSON** 一条路——`stdio.go` 的 `runStdioScanner` 用 `bufio.Scanner` 逐行 `handleLine`，`appServerMaxStdioRequestBytes = 64 * 1024 * 1024`（注释：桌面附件按 base64 塞进单条 JSONL 请求，20MB PDF 编码后约 27MB，故本地传输上限要远大于它，provider 侧限制到请求到达后再判）。**上一版写的"远程走 WebSocket"是错的**：代码里的 `websocket` 属两处别的东西——① `providers/stream_transport.go` 的 **provider 侧流式传输模式** `StreamTransportMode ∈ {auto, sse, websocket, websocket-cached}`（OpenAI Responses API，见 §5）；② `remote/host.go` 的**远程桥接**"宿主保持一条出向 websocket 连 relay"（见 §8,不做）。
>
> `packages/protocol` 无 Go 文件，是 TS 契约 `src/index.ts`(**3310 行**)：`APP_SERVER_PROTOCOL_VERSION = "wuu-app-server/v0.1"`（与 Go 侧同值）、信封 `AppServerRequest/AppServerResponse/AppServerError/AppServerNotification`、`InitializeParams/InitializeResult`、`FeatureFlags`、`UserQuestion*` 全套、`BrowserCDPParams/Result`、以及 **`BROWSER_REVERSE_RPC_METHODS`**（服务端反向调用客户端的 RPC 方法集，浏览器/交互走这条反向面）。

### 能力清单：方法面全量（逐条从 `protocol.go` 抽出，非按名推断）

- **会话/回合/运行（做）**：`initialize`、`shutdown`；`thread/{start,resume,fork,archive,delete,list,listAll,listArchived,search,pin,rename,preview,regenerate-title,edit-message,compact/start,context-composition,organization/update}`(17)；`turn/{start,interrupt,steer,unsteer,queue,dequeue,requeue,update-queued}`(8)；`run/{start,interrupt}`(2)。
  - 插话/排队面是完整的一组：`turn/steer`+`turn/unsteer` 对应 §3 `HeldUserWork{Origin: steer}`，`turn/queue|dequeue|requeue|update-queued` 对应 `Origin: queue`——即「运行中可干预」的 RPC 本体，Questor 必须整套移植而非只做 steer。
  - `thread/fork`＝worktree 分叉可见面（§6）；`thread/compact/start`＝显式压缩控制面；`thread/context-composition`＝上下文构成查询（可见）。
- **配置/用量/杂项（做）**：`config/{read,model/update,advanced/update,general/update,provider/remove,model-catalog/providers,model-catalog/refresh,codex/credentials,codex/models}`(9)、`settings/usage`、`usage/overview`、`sessionFolder/{create,delete,reorder,update}`(4)、`workspace/{list,state/cleanup}`(2)、`git/commit-message`、`text/polish`。
- **终端/浏览器面（做，「过程可见」的承载）**：`process/{list,read,write,resize,stop}`(5)——内嵌终端；`browser/{cdp,open_tab,list_tabs,screenshot,close_tab,set_visibility,finalize,turn_ended}`(8)——CDP 驱动，契合 Electron「真·同页接管」。
- **HITL（做）**：`user-question/{hold,respond,list,cancel}`(4)——agent 反向提问（与 §2 Reviewer/approveForMe 两条不同的干预通道）。
- **引擎/凭据（单引擎下退化）**：`engine/{list,update,authenticate,auth/methods,auth/cancel}`(5)；`auth/xai/login/{start,poll,cancel}`(3)——**登录面当前只有 xai 一家有**（其余靠 config 注凭据）。
- **明确不做**：`plugin`(14)、`mcp`(8)、`sideThread`(5)、`extension`(2)、`device`(2,push)、`skill`(1)、`sessionOrganization`(1)、`project`(2,协调器 inbox)——对应二开框架/MCP/子代理/远程设备/tracing。
- **订正：`activity`(4) 不属"不做"**：`activity/{list, takeover, release, stop}` + `activity/{started,updated,control_changed,stopped}` 是**接管/释放控制权的仲裁面**（详见 §8 订正条），是浏览器面板「接管即暂停」的后端支撑，**应列入做**。上一版把它与 `insight` 一同归为 tracing 大盘，是错的。

### 能力清单：通知/事件面

- **thread**：`thread/started`、`thread/resumed`、`thread/updated`
- **turn**：`turn/started`、`turn/queued`、`turn/dequeued`、**`turn/steered`**、`turn/unsteered`、`turn/held`、`turn/event`、`turn/error`、`turn/completed`、`turn/usage`（steered/held 即"运行中插话/改道"的协议投影，对应 §3）
- **item（流式增量,可见柱核心）**：`item/started`、`item/completed`、`item/removed`、`item/agentMessage/delta`+`/replace`、`item/reasoning/delta`+`/replace`、`item/toolCall/delta`+`/outputDelta`
- **run**：`run/started`、`run/updated`
- **browser**：`browser/turn_started`、`browser/request_cancelled`（面板接管）
- **交互/其它**：`user-question/requested`、`user-question/resolved`（agent 反向提问→HITL）、`config/changed`、`config/error`
- **不做面的事件**：`sideThread/event`、`activity/started`/`updated`/`control_changed`/`stopped`、`agent/updated`、`agent/mailbox`、`mcp/status/updated`、`plugin/inventory/changed`

### 关键 handler 文件（appserver 87 文件分组）

`protocol.go`(方法/通知常量表) · `server.go`/`stdio.go`(NDJSON 传输+分发) · `session_creation.go`/`session_input.go`/`session_control.go`/`session_inspect.go`(会话) · `thread_handlers.go`/`turn_handlers.go`/`run_handlers.go`/`turn_execution_lease.go`/`thread_lifecycle_lease.go`(回合/租约) · `held_user_work.go`(插话) · `history.go`/`thread_history_page.go`(历史分页) · `approve_for_me.go`/`engine_approvals.go`/`user_question_handlers.go`(HITL) · `workspace_*`/`browser_handlers.go`/`process_handlers.go`/`process_notifications.go`(工具面) · `fork.go`/`handoff_brief.go`(worktree 分叉) · `model*.go`/`config_handlers.go`(配置) · 不做：`plugin_*.go`(12+)、`mcp_*.go`、`side_thread_handlers.go`、`project_*.go`、`activity_handlers.go`、`device_push.go`、`participant_*`、`agent_threads.go`。

### 移植成 Python 的要点/风险

- **方法表单一来源**（记忆：Questor 已把 AppServer 收成唯一 `_handler_registry()`、`_methods()` 派生,附负向护栏 B-119；B-121 声明面⊆实现需双向断言）：wuu 用 protocol.go 常量表 + 分发,移植时坚持"协议面一处定义、文档/实现/handler 同源",防 1189 行上帝对象回归。
- **传输单一**：app-server 侧实测只有 **stdio JSONL**（带 64MB 单请求上限，为 base64 附件留余量），**没有服务端监听式 WebSocket 入口**；`websocket` 存在于两处与 app-server 无关的地方（provider 流式模式 `StreamTransportMode`、以及 §8 不做的 remote 中继）。因此 Questor 的 stdio sidecar 形态与 wuu 一致，`initialize`/`shutdown` 握手机制与 `ProtocolVersion` 要显式建模；§11 中提到的 ADR-0034（stdio 宿主长跑驱动）仍属 Questor 自有待裁项，不是 wuu 缺口。
- 事件面里 `turn/steered|held` + `item/*/delta|replace` + `user-question/requested` 是「可见+可干预」的最小协议集,优先移植；`activity/*`、`agent/mailbox`、`plugin/*`、`mcp/*`、`sideThread/*` 可整体不实现。
- **概念四层（本轮已从 `protocol.go` 类型定义核实，上一版对 run 的解释是错的）**：`Thread`(L2367)＝会话容器，携 `ModelOptions/Speed/SessionControl/Source/ProjectID/ProjectRole`（后两个是协调器字段，不做）；**`Turn`(L2425) 携 `Kind TurnKind`，且注释明确 `ModelProvider` 与 `Model` 在 turn 开始时捕获并保持稳定**；**`Run`(L2002) 的注释原文："Run is the public control and observation boundary for one agent invocation. Its Turns refer to canonical Thread/Turn records rather than copying them."且 `type Run = execution.Run`**——即 **Run 是包裹多个 canonical Turn 的外层控制/观测边界，不是一次 model 往返**（`RunStartParams{ThreadID, Prompt}`）；`item/*` 才是可见产物单元。→ 移植时：一轮 model 往返的"step"属于 §1 循环内部，**不对外暴露为 Run**；thread/turn/run/item 与持久化 seq、LoopResult 对齐时不要把 turn 与 run 混为一层。
- **顺带发现（直接服务于「可见」）**：`protocol.go` L2421 附近有 `Dirty bool \`json:"dirty,omitempty"\`` 与 `ChangedFiles []string \`json:"changed_files,omitempty"\``——**协议层已自带"脏标记 + 改动文件列表"字段**，这是 Review 面板 thread 级信号的形状，Questor 移植 diff/review 时应直接参照而非另设一套（与 §2/ADR-0035 的"diff 权威源"问题要一并裁：wuu 是把 changed_files 记在协议对象上，而不是只靠 tool payload）。

---

## 8) 明确不做（不移植）范围

对齐用户四禁（多用户 SaaS / 组织排班·岗位值班 / 给别人二开的 agent 框架 / LLM tracing 大盘）。逐包：一句话职责 + 不移植理由。

| 包（文件数） | 干什么（实测依据） | 为什么不移植 |
|---|---|---|
| `remote/*`(29) | wuu 远程控制全栈：`account`(自托管身份/设备成员/可选对话文本副本)、`secure`(设备身份/QR 配对/每连接加密)、`relay`(跨 NAT 盲交换机让手机连宿主)、`phone`(移动端控制器)、`host`(桌面端持远程身份+出向 websocket)、`wire`(两套消息词汇)、`conversations`(纯文本账户历史副本)。内核唯一出现 **PostgreSQL**(`pgtest`) 处 | 多用户 SaaS + 设备远程桥接；记忆已列"远程桥接=不采纳"。Questor 是本地个人工作台,不需要 relay/NAT/配对 |
| `plugin`/`pluginhost`(13/17) | `pluginhost`: "typed bidirectional extension protocol between host and external plugin processes"(CapabilityRPC)；插件安装/生成/诊断/桌面模块/图标 | 别人二开的 agent 框架面；Questor 不做插件宿主 |
| `extensions`/`hooks`/`skills`(4/12/7) | `extensions`:extension 目录/包指纹(ExecutableSpec)；`hooks`:生命周期钩子；`skills`:Agent Skills 打包/可用性 | 均属二开/分发/能力扩展框架；`ToolKindPlugin/Schedule`、`tool_skill.go`/`mcp_activity.go` 一并剥离 |
| `subagent`/`agentcontrol`/`agentthread`/`participant`/`sidethread`(4/19/5/2/3) | `subagent`:"isolated sub-agents the coordinator spawns"(各自 chat)；`agentcontrol`:编排工具 spawn_agent/send_message/close_agent↔subagent+worktree；`agentthread`:线程图 nodes/edges(EdgeClosed 等)；`participant`:"persisted identities carried by subagent runs"；`sidethread`:"/side 打开的只读伴随会话" | 多 agent 编排/"给别人二开"框架；Questor 主线是单 agent 过程可见。注意：worktree 的**分叉可见**形态可单独取用(见 §6),但不带 subagent 绑定 |
| `mcp`(11) | "lightweight Model Context Protocol client"(stdio + streamable HTTP,spec 2025-03-26+) | MCP 工具接入 = 二开面；`agentengine.MCPServers` 本就是外部引擎桥,内建引擎忽略 |
| `codemode`(4) | "connects Wuu to an isolated JavaScript execution host"(不在 Go/extension 进程跑模型生成码) | 独立 JS 执行宿主属重型扩展；Questor 不做（也是 `executionenv` 云耦合点） |
| `externalengine`/`codexengine`/`claudeengine`/`enginecatalog`(10/7/6/8) | `externalengine`:"hosts external coding agents through published protocols,各自保 auth/tools/native history"；`codexengine`:Codex CLI app-server 作外部引擎；`claudeengine`:Claude Code CLI(headless stream-json)；`enginecatalog`:"process launch metadata,不加载引擎" | 宿主第三方 agent CLI = 二开/接入框架；Questor 自研循环,EngineID 只保留 wuu 一家(见 §1) |
| `schedule`(1)+ `project_inbox_scheduler`/`ToolKindSchedule` | 定时/排班触发与值班 inbox 调度 | 组织排班/岗位值班,明确不做 |
| **`activity`(2)— 从"不做"改为“必须做”** | 实证：`Kind ∈ {browser, cua}`、`Controller ∈ {agent, user, none}`、`State ∈ {starting, active, background_controlled, foreground_controlled, **user_controlled**, waiting_confirmation, stopped, error}`；`Registry{Start/Acquire→(Session,**Lease**), List(threadID), ListByKind, Update, **UpdateWithLease**, Subscribe}` + `takeoverVersion uint64`；注释原文"**UpdateWithLease prevents a completed action from overwriting a concurrent takeover**"、"A user takeover and a stopped tombstone are hard..."；错误含 `ErrThreadMismatch`/`ErrControlRevoked`/`ErrTargetBusy`("activity target is controlled by another thread")。**这是"同一目标在 agent 与用户之间交接控制权"的仲裁机制**，与 tracing 无关 | 上一版把它归"tracing 大盘不做"是错的（用户指令里也与 insight 并列）。它正是 Questor Electron 「面板内同一 tab 即 agent 页面、**接管即暂停**」所需的内核仲裁层：租约+版本防竞态、跨 thread 占用互斥、revoked 可中断。**建议列入做**，待用户确认（见下方备注） |
| `insight`(3) | "aggregates session-level token usage and model breakdowns for the desktop settings page(handleSettingsUsage)" | LLM 用量分析大盘，**明确不做**；Questor 至多保留 `usage/overview`+`settings/usage` 两个方法的最小读数(§5 OnTokenUsage) |
| `evalharness`/`harness`/`grokbuildspec`(3/2/1) | `evalharness`:评测跑批；`harness`:引擎 harness 装配；`grokbuildspec`:Grok Build 客户端默认值 | 评测框架非产品功能；`grokbuildspec` 仅随是否保留 xAI Grok provider 取舍,可暂缓 |
| `testenv`(1)/`version`(1)/`stringutil`(1) | 测试脚手架/版本常量/字符串工具 | 非能力面；Python 用 pytest/`__version__`/内置即可,不逐包移植 |

> 保留但易被误判为"不做"的：`instructions`(系统提示的 project/user instruction 发现,**做**——可见/可验证)、**`activity`(接管/控制权仲裁,本轮实证从不做移入做)**、`capability`(被 `appserver/protocol.go` import 的能力词汇,做)、`authstorage`/`credentialstore`(凭据/OAuth 存储,做)、`workingnotes`/`sessiontrace`(note 后端与最小 trace,做)、`modelcatalog`/`modelroles`/`modelvariant`/`modelbudget`(模型选择,做)。
>
> **两个需用户拍板的归类冲突（本轮新发现）**：① `activity` 在任务描述中与 `insight` 并列列为"不做（LLM tracing 大盘）"，但实测 `activity` 与 tracing 无关而是接管仲裁——若按原指令不移，Questor 的浏览器「同页接管」将无内核可参照；② `plugins/{goal,todo,memory,...}` 揭示的"机制不做、能力待定"问题（见 §9）。两者均已在 §11 列为待确认。

---

## 9) 组装根与入口层 `runtime/` + `cmd/` + `plugins/`（上一版遗漏，本轮补）

> 这一层决定"哪些是内核、哪些是可选件"，是移植范围的真正边界。上一版只扫 `internal/` 就下结论，导致高估了内核厚度。

### 能力清单

- **组装根** `internal/runtime/`(24)：拆两类。
  - **内核必需（~7）**：`engine_wuu.go`——**`WuuEngine` 就是 §1 `agentengine.Factory` 的唯一内建实现**，`Descriptor()` 返 `{ID:EngineWuu, Version:"1", Capabilities:["native-tool-loop","native-session-resume"]}`；注释原文"It implements agentengine.Factory so the app-server talks to it through the same seam it will use for external engines"，且该文件 import claudeengine/codexengine/externalengine/enginecatalog（即多引擎在此注册）。另有 `host.go`、`session.go`、`thread_derivation.go`、`artifact_publisher.go`、`execution_environments.go`、`tool_loading_notice.go`。
  - **插件/扩展胶（~14，不做）**：`plugin_host.go`/`plugin_host_services.go`/`plugin_tool_executor.go`/`plugin_nested_tools.go`/`plugin_session_router.go`/`plugin_generation*.go`/`plugin_history_service.go`/`plugin_data_service.go`/`plugin_artifact_service.go`/`plugin_availability.go`/`plugin_management.go`/`plugin_revocation.go`/`security_extensions.go`/`side_thread.go`/`driver_gateway.go`/`driver_resolution.go`。
  - **移植启示**：Questor 的 `runtime` 等价物只需"把 Engine/Tools/Provider/Session/AppServer 接起来"，可直接去掉一半以上的 import 面。
- **入口** `cmd/`：`cmd/wuu/main.go`(**主 CLI，也承载桌面 app-server**)、`login.go`、`exec_lifecycle.go`(配 §6 `internal/exec`)、`eval.go`；**不做**：`plugin.go`/`plugin_dev*.go`(插件开发与热重载)、`remote*.go`(远程账号/GitHub 登录)。`cmd/wuu-ask-user-plugin`、`-automation-plugin`、`-dream-plugin`、`-goal-plugin`、`-memory-plugin`、`-peers-plugin`、`-subagent-plugin`、`-todo-plugin`(各为独立可执行入口，仅 `pluginapi.Serve(context, xxx.Handler())`)、`-modelcatalog-gen`(生模型目录)、`cmd/wuu-server/main.go`——**它不是桌面 app-server，而是自托管 relay/账号服务**(`internal/remote/server.RunStandalone`，默认 `--state ./data/relay.json`)。
- **`plugins/`(8 个一等公民插件包)**：`goal`、`todo`、`memory`、`ask-user`、`peers`、`automation`、`dream`、`subagent`。`cmd/wuu-goal-plugin/main.go` import `github.com/blueberrycongee/wuu/plugins/goal` 并 `pluginapi.Serve(goal.Handler())`。

### 对移植决策的冲击（必须写进计划文档）

- **重大发现：Goal / Todo / Memory / Peers(多 agent 协作) / AskUser / Automation / Dream 在 wuu 里不是内核功能，而是跑在插件宿主上的外部进程**。上一版 §8 把 `plugin*` 整族归"不做"时未区分**机制 vs 能力**，会误导排期：
  - 不做的是 **机制**：插件宿主、CapabilityRPC、热重载/签名/诊断/图标/桌面模块注入。
  - 但 **Goal/Todo/Memory 这些能力本身**正是 Questor 从 EvoFlow 侧带来的"长任务托管与验收看板(Plan/Goal/打回)"需求——wuu 用插件实现它们，Questor 不做插件，因此**这些能力只能选“内核内建”或“明确不做”两选一**，不能默认"跳过 plugin 包就丢了也没关系"。→ 这是需要用户拍板的**新开口**，已列入下方未尽事项。
  - `ask-user` 插件与 §7 `user-question/*` 方法面的关系需再确认（后者看起来已是内核原生，可能 ask-user 插件只是其中一个供给方）。
- **`enginecatalog`(8) 与 §8 判定一致**（仅外部引擎启动元数据），但注意 `capability`(2) 被 `appserver/protocol.go` import，属协议可见面，不宜按"harness 内部词汇"直接丢弃。

---

## 10) 与 Questor 现状的接缝（供计划文档标注"借鉴/不采纳"）

- **契合三柱可直接照搬**：boundary 可达性单一权威 + 三档(§2)、inbox 幂等投递 + held user work 的 queue/steer 插话(§3)、turn/steered + item/*/delta + user-question 协议面(§7)、loop 的 `maxConsecutive_continuations=8` 硬止损(§1)、compact 与 fresh-context 双路(§4)、纯 Go SQLite→Python `sqlite3`(§3)、diffmatchpatch 结构化 diff 进 tool result(§2)。
- **Windows 现实缺口(必须列"不采纳/需替代")**：无 OS 沙箱(`sandbox_other`→ErrUnavailable)、无 PTY(pipe-only)、securefs POSIX 0600/0700 无等价、跨进程锁/存活判定需 Windows 专门分支(§6)。
- **既有待裁项对映**：diff 权威源(§2/ADR-0035)、Engine 契约最小保留(§1/ADR-0033)、AppServer 方法表单一来源(§7/B-119/B-121)、stdio 宿主长跑驱动(§1/§7/ADR-0034)——移植时按 wuu 实测语义复核,勿凭印象。

---

## 11) 扫描覆盖度与未尽事项（诚实声明）

本文档经四轮扫描。第一轮只读到部分文件头部就下了一些结论；第二/三/四轮已把其中**十一处错写/错归类**就地标"订正"：Provider→**`Client`/`StreamClient`** 接口名、app-server 传输误写 "远程走 WebSocket"（实为 stdio JSONL 单一）、`exec/` 误作"一次性执行"（实为 `wuu exec` 的 app-server 客户端）、`cmd/wuu-server` 误作桌面 app-server（实为 relay/账号自托管服务）、`tool_shell` 误列为工具、`loopdriver` 定位含混（实为插件接管循环的口子）、§8 未区分**插件机制 vs 插件能力**、**`run` 误作"一轮 model 往返"（实为包裹多个 canonical Turn 的外层边界）**、**`activity` 误归"tracing 大盘不做"（实为接管/控制权仲裁，属必须做）**、**权限链顺序写错（实为 hook→boundary→plugin特例→Reviewer→Authorizer，且 Authorizer 报错 fail closed）**、**`ToolInfo` 漏列 `Exposure`/`ConcurrencySafe`（后者是并发门的分流依据）**。另修正一个误判的风险：wuu 已在 `relInsideRoot` 里处理 Windows 路径大小写不敏感。

**已达实证级**（读过定义/导出面而非靠文件名）：`agentengine.go` 全文、`loopdriver/contract.go` 全文、`boundary.go` 全文、`env.go::ResolvePath`/`relInsideRoot`/`pathWithinRoot`/`RedactToolOutput` 本体、`agentengine` 全部生命周期符号、`LoopConfig`/`LoopResult` 字段、`Client`/`StreamClient`/各能力接口、`FinishReason`、`RetryConfig`、5 家 provider 注册点、18+ 工具名、`compact` 导出 API、`storelock`/`storagecodec`/`workingnotes`/`statepath` 导出面、`sessions.sqlite3`+inbox+held_user_work、`activity` 的 Kind/Controller/State/Registry(Lease/takeoverVersion)、app-server **stdio 传输与请求上限**、**方法面逐条清单**、通知/事件全集、`Thread/Turn/Run/Item` 四层定义、`runtime`/`cmd`/`plugins` 边界。

**仍未读、不得当成已穷尽**（按风险排序）：
1. **`agent/loop.go` 1735 行已读~500 行**（入环声明、fresh-context attempt 全枝、`repairLiveToolCallHistory`、续跑/终止判定、compact 触发点）。**仍未逐段读**：L120-396 的 helper 区（`tryProactiveCompact`/`emitCompactAttempt`/`resolveEffectiveCompaction`/usage 初始化）与 L560-1010 的**请求拼装→Step 调用→overflow 恢复→工具批次下发**主链。结论：循环骨架与止损/换窗/悬空 tool-call 修补已证实，但 **Step 如何把事件吐给上层、overflow 后 `lastSuccessfulTokens` 如何参控 compactBudgetHint 尚未逐行确认**，开工前仍需精读这三段。
2. **`appserver` 87 文件中只读了 `protocol.go` 部分 + `stdio.go` 头部**。各 handler 的具体行为、租约与 turn 生命周期、反向 RPC 的实际调用链未验证；`packages/protocol/src/index.ts` 3310 行只扫了导出类型名前 30 个。
3. **`providers/openai`、`anthropic` 两家 adapter 正文未读**（仅确认入口与文件划分）；SSE 解析、错误映射到 `HTTPError`、cache breakpoint 处理均未验证。
4. `agent/` 剩余 ~13 文件（`request_assembler`/`request_shape`/`request_transform`/`system_prompt`/`cache_hint`/`tool_nested`/`retained_context`/`model_input_receipt`/`provider_registry`/`usage`/`compaction_*` 等）只知存在，职责未逐个核（`tool_runtime.go` 本轮已读，上一版列在欠账里）。`runner.go`/`stream_runner.go` 仅拿到类型定义行号与 `ToolMetadata` 定义，正文未展开——而 StreamRunner 是 Questor 要直接对标的对象，优先级仅次于 loop.go。
5. `session/session.go` 2549 行读了前 30 行；schema 列定义、`storage_governance` GC 策略、archive 转移语义未读。
6. `tools/` ：已详读 `boundary.go` 全文、`env.go::ResolvePath`/`relInsideRoot`/`pathWithinRoot`/`BypassToolHardProtections`/`RedactToolOutput` 本体、`toolkit.go` 的 **`checkPermission`(L112-146) + `rebuildRegistry`(L354-413) + `ExecuteResult`/`ensureToolAvailableForExecution`(L1251-1301)** 与函数全表。**仍未展开**：`executeKnownToolResult`/`executeBrowserToolResult`/`executeActivityBoundToolResult` 内部（即 activity lease 如何获取/释放）、`Definitions()`/`exposedSurfaceLocked()` 的 21→对外投影完整推导、`file_mutation_queue.go`、各工具参数 JSON schema 逐个。
7. `hooks`/`skills`/`schedule`/`agentthread` 无包文档注释，只据目录名/RPC 方法/`ToolKind` 判定为不做，**结论方向可信但描述不够深**（已核 `hooks`：`Dispatcher`+`Event`+`HookedExecutor` 做 PreToolUse/PostToolUse 装饰，属二开面，确认不做）。`plugins/*` 与 `internal/exec`/`executionworker` 本轮首次发现，只做到边界级认识。
8. **两处归类需用户拍板**（本轮新发现，见 §8/§9 备注）：`activity` 已从"不做"移入"做"（接管仲裁，与 tracing 无关）；`plugins/{goal,todo,memory,ask-user,peers,automation,dream}` 所代表的**能力**是否内建。
9. 未涉及：`go.mod` 外部依赖版本、构建/发布链、`evals/`、`docs/`、`internal/capability`与`modelcatalog` 正文。

**建议下一轮顺序**：① `agent/loop.go` 剩余三段（L120-396 helper、L560-1010 主链）与 `stream_runner.go` 正文；② `plugins/goal`+`todo`+`memory` 读实现以便拍板"内建 vs 不做"；③ `toolkit.go` 的 `executeKnownToolResult`/`executeBrowserToolResult`/`executeActivityBoundToolResult`（activity lease 生命周期）；④ `appserver` 的 turn/thread 租约与反向 RPC 调用链；⑤ `session` schema 与 `storage_governance`；⑥ `openai`/`anthropic` adapter 正文（SSE 解析与错误映射）。
