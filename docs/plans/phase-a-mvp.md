# Questor A 阶段纵向切片计划（phase-a-mvp）

版本: v1.0 | 更新: 2026-10-14 | 状态: 待用户评审
**取代** `development-plan.md` 的 M 系列骨架（M0–M8 + Phase U 作废为历史）；关联总计划 `docs/plans/`（Qoder 计划文件）+ `docs/research/port-ledger.md` + `docs/architecture/{overview,structure,protocol,data-model}.md`（已重写为母本对齐口径）。

> 本文是 **Phase 1–4（A 阶段=可安装 exe）** 的可开工计划。每波开工前按 `port-ledger` + 计划 §1.5 先扫 wuu、以帧序列等价性为出口。规则冲突：**可用 > 扩展 > 性能**。

## 0. 开工前必读（每窗口，§12-C 交接协议）
① 本文对应 Phase；② `docs/research/phase0-wuu-*.md` + `scan-wuu-*.md`；③ `port-ledger.md`（含 TL-1 契约先于实现的 2 红、TL-3 版本串待定）；④ `AGENTS.md` §〇§二§三；⑤ 母本 `wuu-main` 对应源码（**不读将废弃的旧 `src/questor/*`**，禁复用旧码）。

## Phase 1 — 接缝安全带（契约层，纯新增不碰旧码）
- **目标**：把"前端吃 wuu 协议 + Python 后端"这道唯一跨语言接缝用契约钉死。
- **wuu 锚点**：`packages/protocol/src/index.ts` + `internal/appserver/{protocol.go,stdio.go,config_handlers.go}` 的实际 JSON（以 Go 结构体 tag 为准）。
- **交付**：`schemas/message.py`（ChatMessage/Part/FinishReason 归一，第一前置件）；`schemas/app_server/`（词表照 protocol.md）；`serve/{envelope,stdio}.py`（64MiB 帧、`srv-` 反向 id、initialize）；`tests/contract/`（wuu 测试 golden/手写期望帧回放）；`packages/protocol` 由 schemas 生成 TS。
- **规避缺陷**：wuu 无代码生成 → 我们生成 TS + 回放钉死；`questor-app-server/v0.1` vs `wuu-...` 版本串按 TL-3 定。
- **出口**：initialize + thread/turn/run/item 四族 fixture 回放绿；`test_serve_names_are_contracted` 随 serve 迁移转绿；`just check`（本 Phase 起 serve 仍旧码，红项须清零或按 ADR-0044 受控作废）。

## Phase 2 — 可跑竖切（拆 2a/2b，一窗一个）
- **2a headless 内核**：`engine`（手写 loop，硬语义：`max_consecutive_continuations=8`、FinishReason 归一、悬空 tool-call 位置修复、overflow 只重试一次、`ToolExecutionGate` 读写分波、取消仍结算 `asyncio.shield`、删 `isBarrierTool` 死枝）；`tools`（read/list/glob/grep/write/edit/bash + `boundary` 三档 + Windows `ResolvePath` 强化 + 脱敏独立逃生阀 + result_budget）；`limen`（checkPermission 五步序 fail-closed）；`gesta`（SQLite 权威 + inbox 幂等 + held_work 事务 + storelock Windows + ACL/DPAPI）；`providers`（anthropic+openai，默认 0 重试分档）；`serve`（stdio sidecar 对齐 Phase1 契约 + 通知最小集）。**CLI/脚本驱动端到端跑通一轮 read→edit→bash→权限门→中断不丢账**；契约回放绿。
- **2b 前端 + 打包**：`desktop/src/renderer` 会话列表/对话流/Review(壳侧 GitService 跑 git)/内嵌终端(node-pty)；`desktop/src/main` spawn 冻结 Python sidecar + initialize + IPC 透传；`electron-builder` NSIS 出 **exe 门槛 1**（装→冷启动→跑通竖切→卸载干净）。Windows：沿用 Git Bash 修补、Job Object 兜进程树、放开 `keyring.go:54` macOS-only。
- **规避缺陷**：god-object 方法表单一来源；SIGTERM Windows 静默失败→Job Object/CTRL；`securefs` 0600 假安全→ACL；`credentialstore` macOS-only→wincred/DPAPI。
- **出口**：2a headless e2e 绿；2b exe 装机冒烟绿；§1.5 五件齐（含 port-ledger 差异全登、不做项登记）。

## Phase 3 — 补齐（工具面 + 可干预 + 压缩）
- **wuu 锚点**：`tools/{tool_git,tool_process_tool,tool_web,tool_history,tool_notes,tool_browser,tool_discovery}`、`activity`、`appserver/{turn,run,activity,browser,user_question}_handlers`、`worktree`、`compact`+`adaptive_compact`+`compaction_registry/note`。
- **交付**：git/process/web/history/notes/new_context/present_artifact；**tool_search 三态**（Direct/Deferred/Hidden + 历史恢复已加载态，禁默认全量暴露破 prompt cache）；可干预全套（steer/queue/held、user-question HITL、**activity 接管仲裁**租约+takeoverVersion、browser 反向 8 + CDP 同页）；compact 三件套 + fresh-context；worktree 分叉可见。
- **出口**：插话/接管/分叉各从 UI 走通一次；并发分区 + 接管竞态负向护栏；exe 门槛 2。

## Phase 4 — 可验证 + Windows 硬化
- **wuu 锚点**：`execution/{exitcodes,store}`、`toolledger`、`providers/{retry,recovery,stream}`、`session/{storage_governance,history_checkpoint,inference_journal}`；AppContainer 官方文档。
- **交付**：evidence（声称↔录制并排、`recorded_output_ref`、结构化输出校验）；退出码语义映射；**AppContainer 写隔离**（seam 可插拔，passthrough/sandboxed 回报）；崩溃恢复 checkpoint/journal；韧性 retry_profiles；脱敏 JWT JOSE 二次校验。
- **出口**：e2e 整链（跑命令→声称→核对→打回）；AppContainer 正/负向；消除 0600 假安全；**exe 门槛 3 = A 阶段 done**（可用产品完成）。

## 后置
- **Phase 5** 优化（prompt cache/offload/deferred/web 宿主/清理，读 `docs/proposals/`）。**Phase 6** 长任务/编排/验收（EvoFlow 规格、围自研 run、不引 LangGraph，ADR-0043）。
- **不做（登记非遗漏）**：remote/relay、插件宿主、MCP、subagent/多-agent、skills、排班值班、多用户 SaaS（§1.7 保缝，不焊死，尤其多租户留边界字段）。

## 门禁
每 Phase：先扫描→实现→`just check`（ruff/format/pyright/pytest）+ 阶段出口判据 + 文档同步（port-ledger/behavior/modules/CHANGELOG/新坑）；Windows 真机跑；破坏性清理（旧码移出工作树）在 Phase 2 入口做，先 commit 存档。
