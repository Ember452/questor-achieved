# Changelog

本项目所有值得注意的改动都记在此。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [CalVer `YYYY.M.D`](https://calver.org/)（与 `VERSION` 单点一致，见 ADR-0001）。

**纪律**：每次里程碑收口时把 `Unreleased` 段落到具体的日期版本；条目按 `Added` / `Changed` /
`Removed` / `Fixed` 分门；每条附对应的 commit 或 ADR/B-NN 引用——**不写"优化 / 提升 /
改进"这种无锚表述**（AGENTS §五 与 development-plan 的"每阶段收尾四件事"同源）。

## [未发布]

### Added
- **Phase 1 跨语言接缝契约层**（计划 Phase 1；protocol.md §8、behavior-protocol-wuu §5）：
  - `schemas/message.py` — ChatMessage/Role/Part 判别联合 + FinishReason 归一枚举与映射
    （照 `providers/types.go#L116-146`）；frozen + `extra=forbid` 机械拒凭据（P1-4）；Origin≠Role（P1-5）。
  - `schemas/app_server/`（新包）— `names`（A 阶段方法/通知/错误单一来源注册表 + `questor-app-server/v0.1`）、
    `envelope`（Request/Response/Notification/ReverseResponse，id 容数字或字符串 P1-2）、`initialize`
    （全字段 result，未实测的 config 面 summary 以 dict 透传并登记后置）、`entities`（Thread/Turn/
    ThreadItem/Run + 状态枚举；`Turn.items` nil→`[]` 硬语义 P1-3）、`families`（thread/turn/run/item 四族）。
  - `tests/contract/` — wuu 帧回放（真实 golden 取自 `client_calls_test.go:60/:89` + 手写期望帧），
    initialize+四族逐字段一致 + 硬语义 + 负向（camelCase/凭据注入即红）。
  - `schemas/app_server/control_plane.py` + `tests/contract/test_replay_control_plane.py` — 控制/配置/HITL
    面（config/read·activity(lease_token)·process(offset 语义)·workspace·user-question）类型化 + 回放，
    补全 A 阶段“做”方法覆盖（pluginhost/activity/config 内部面透传、登记后置）。
  - `tests/architecture/test_protocol_single_source.py` — `protocol.md` §3/§4/§7 ↔ `names.py` 双向同源
    护栏（B-119/B-121，契约侧即绿）。
- **Phase 1 审计收口**（用户核码发现 4 项，已逐项修）：① 双真相源——旧 `app_server/v0-1.json` 仍 44KB
  在包内且 `test_schemas_method_families` 绿，措辞由“取代”改“并行过渡·Phase 2a 同批推倒”（schemas/__init__
  口径同步收窄）；② C19 据 `internal/approvefor/review.go` 实测关定（收紧型 approve_for_me、五态、fail-closed）
  回写 protocol §5 + overview §11；③ 补齐对话面遗漏的通知模型 + replace/64MiB/数字 id 回放测（见上）；
  ④ 回写 `phase-a-mvp.md` Phase 1 交付/出口为实际改判（serve→2a、TS 生成→2b）。
- **Phase 0 欠账闭合**：回填曾为 0 字节的三份前置扫描表——`research/phase0-wuu-protocol-table.md`
  （方法/通知全枚举 + A 阶段处置）、`phase0-wuu-renderer-assembly.md`（实测 wuu 648 文件渲染层
  装配/AppState.ts 事件 reducer/189 个 `wuu:` IPC 通道）、`phase0-wuu-sqlite-schema.md`（实测
  session.go 全建表/PRAGMA·WAL/inbox 幂等/held_user_work 整表替换事务）；Phase 0 “三表可复核”出口判据真正达成。
- **Phase 0 收口（知识抢救 + 契约重立基，计划 §12-B/§12-E）**：新渲染层设
  计篇 `docs/architecture/modules/{review,habena}.md`；壳侧知识归档
  `docs/research/archive-desktop-restart-policy.md`（原 notes 锚定的 `desktop/src/main/*` 已移出）；
  `port-ledger.md` 写 ADR-0044 逐目录处置地图与 Phase 0 收口基线；
  `behavior-review-fidelity-wuu.md` 补登“母本双源分工”并勘误 `@pierre/diffs` 选型声称。
- **M3 工作台数据面**（overview §12 M3 行；详见 `docs/plans/development-plan.md` Phase M3）：
  - `src/questor/review/` — 工作区修订号单点、写工具算 diff、turn↔revision 聚合（ADR-0005、B-66/B-93）；
  - `src/questor/habena/` — 插话收件箱、接管栅栏（CAS + revision）、`habena.held_work` 记录 kind 落正文（B-63/64/65/67）；
  - `src/questor/sessiontrace/` — 会话轨迹投影回放，不重跑工具不联系模型（overview §6）；
  - `src/questor/worktree/` — Git worktree 生命周期（`thread/fork mode=worktree`）；
  - `serve` — `files/*` / `review/turn_diff` / `content/read` / `workspace/*` / `sessiontrace/get` /
    `thread/{rename,archive,delete,show,fork}` / `turn/{steer,queue,dequeue}` / `session/control` 方法族；
  - `serve/fanout.py` — 多宿主通知扇出（B-96，每订阅者一个 `asyncio.Queue`）；
  - `serve/ws.py` + `serve/http.py` — WS 传输与本地 http 宿主（ADR-0022/0023，硬 assert 127.0.0.1）；
  - `cli serve http` — 起本地 http + WS 宿主；`--host 0.0.0.0` 启动即拒；
  - `ui/src/rpc/` — `Transport` 抽象 + `WebSocketTransport` + 强类型 `client.ts`（R4：类型全部从
    `rpc/generated/` 引，无手写 DTO）；
  - `ui/src/panels/` — 视图注册表骨架（`PANELS` + `resolvePanel` + `PanelHost` 单分发点，ADR-0020）
    与 `Review` / `Files` 两块真接面板；`MessageStream` 从 Notification union 分派渲染；Composer 解禁。
- `src/questor/schemas/app_server/v0-1.json` — 扩到方法族形状（15 方法 + 6 通知族 + 内嵌
  `ThreadDTO` / `WorkspaceDTO` / `FileDiff` / `DiffHunk`）；`scripts/gen/types.mjs`（新，从 `ui/scripts/`
  搬来，兑现 ADR-0019 归属）打开 `declareExternallyReferenced` 让 `$defs` 全部 export。
- `docs/adr/0022-serve-ws-starlette-uvicorn.md` / `0023-m3-transport-ws-only.md` /
  `0024-desktop-shell-deferred-to-m4.md` — M3 期新增决策；`0005-workspace-revision.md` 从 planned
  归档 accepted。
- 坑目录 `docs/specs/pitfalls.md` 追加 B-89..B-93（M2.2 复审遗留修复与 M3 期新坑）；
  B-60/63/64/65/66/67 从 open 转 covered（回填具体测试名）。
- **Phase U 收口后架构审计的四份决策记录**：`docs/adr/0033`（引擎契约提取列为 M6
  准入条件）、`0034`（长跑驱动的宿主归属，待裁）、`0035`（Review 的 diff 权威源，待裁）、
  `0036`（AppServer 拆分时机）；`docs/adr/README.md` 索引同步，`development-plan.md`
  的 Phase U 新增"收口后审计与待裁项"、M6 新增"准入条件"。
- 护栏测试两件：`tests/architecture/test_serve_names_are_contracted.py` 加
  `test_method_table_has_single_source` / `test_initialize_publishes_the_same_method_table`（B-119）；
  新建 `tests/architecture/test_tool_kind_single_source.py`（B-120，AST 扫定义点）。
  两条均已附负向验证输出。坑目录追加 B-119..B-121（B-121 为已登记的护栏盲区，open）。

### Changed
- **母计划（总计划）自编辑器缓存区入库 + 修必读表指向作废文档**（port-ledger TL-4；可追溯纪律见
  ADR-0008）：新增 `docs/plans/2026-10-13-wuu-alignment-master-plan.md`，逐字归档 Qoder 计划缓存区那份
  `Questor_对齐_wuu_重构计划_99f1c707.md`（与原文 `Compare-Object` 比对＝3 行新增、0 行改写），顶部加
  “计划态快照、不含执行进度”横幅——此前仓库内 10+ 处按「计划 §1.5 机制 N / §12-A~E / §13 C0–C21 / §14」
  编号引用它、而仓库内查无出处（`docs/specs/README.md`、`tests/contract/README.md`、
  `schemas/app_server/initialize.py`、`behavior-protocol-wuu.md`、`modules/habena.md`、port-ledger 本身）；
  `phase-a-mvp.md` §0 必读第①条与 `docs/README.md` 文档地图同批改指。
- **同批修两处“文档声称与文档态两张皮”**（铁律 1）：`AGENTS.md` §七 必读表原指向已标作废的
  `development-plan.md`（port-ledger TL-2 曾记“已 redirect”，实际未改），现改指 `phase-a-mvp.md` 并
  显式标旧档不得作实现依据；文首状态行“承重 ADR 待随 Phase 0 补齐”按 0037–0045 全落库改写；
  TL-3 版本串状态按 P1-1 实况（`questor-app-server/v0.1`）收敛；TL-2 那句“必读已 redirect”就地标为长期不实。
  坑目录追加 **B-123**（open）：文档类收口项必须用 grep 断言旧指向已消失——`check_docs.py` 只校链接存在性、
  不校反引号路径与作废标记（本次两处均为其盲区）；B-123 归属模块记为 `docs`，**系 `structure.md` §2 清单外首例**，
  待用户裁是否把文档类加进清单。**未动代码/契约/schema**（
  `just check` 全绿：611 passed / 5 skipped / 3 xfailed；`check_docs` 52→57 条链接均可解析）。
- **`ToolKind` 定义点唯一化**：曾由 `tools/base.py` 与 `limen/gate.py` 各写一份
  `Literal["file","shell","process","meta"]`，现下沉到 `schemas/model.py` 作唯一定义点，
  两侧向下 import（B-120）。选 schemas 而非让 tools 引 limen，因为 tools→limen 被
  `test_permission_gate_single_entry` 禁着。**行为不变**（`Literal` 是纯类型构造）。
- **`serve/app_server.py` 方法表收成单一来源**：原 `_methods()` 手写字面量元组（44 项）
  与 `_handler()` 字典（同样 44 项）合成唯一一份 `_handler_registry()`，`_methods()` 改为
  其键序派生视图，`build_dispatcher` 直接遍历注册表（B-119）。`initialize.methods`
  的数组序逐字不变→对外线形无变更（`just gen-check` 绿）。
- **桌面壳选型改判 Electron；界面/桌面壳主线提前为 Phase U**（ADR-0030，取代 ADR-0006
  壳选型与浏览器面板边界、改判 ADR-0024 排期）：`overview.md` v0.2 §4/§12/§14/§15、
  `structure.md` v0.5 §2/§4/§7/§9/§11、`development-plan.md` v0.4（新 Phase U，E1 并轨）同步；
  Browser 面板从 "CDP 镜像、不得称同一页" 升为 Chromium 内嵌真·同页接管。**内核/协议/
  schema/sidecar 未动**（stdio 传输与壳无关，`desktop/` 原为 0 文件）。
- `Workspace.revision` 由 write / edit 工具通过 `bump_revision` 单点递增（B-92）；
  `ToolContext.workspace_id` 新增字段；`serve/assembly.build_engine` 缺省时经
  `ensure_workspace_for_root` 归一化 workspace id（B-91）。
- `serve/dispatch.py`：加 `ProtocolError`（业务错自持 code）与 `request_client` 反向请求路由；
  pending 表优先于 method switch（B-59）；`_run` 里 ProtocolError 分支在 ValueError 之前。
- `Engine._loop`：iteration 起点前调 `_consume_inbox_iteration`（B-67/94），
  `Engine.__init__` 加 `inbox: InboxPort | None = None` 参数与 `attach_inbox()` setter。

### Fixed
- `tools/executor.py::_as_outcome`：`asyncio.CancelledError` 不再被降级为 error 结果，
  改重传（AGENTS §五 异步纪律；B-89；M2.2 复审遗留 M3 修）。
- `tools/impl/{read,write,edit,search,list}.py`：async execute 里的同步文件 IO 全部沉入
  同步 helper + `asyncio.to_thread`（B-90；M2.2 复审遗留 M3 修）。
- `cli/__init__.py`：不再自己算 `sha256` 当 workspace_id；改走 `serve.assembly.ensure_workspace_for_root`
  （B-91）。
- `engine/loop.py` 与 `tests/unit/test_engine_shape.py` 里的"单函数 ≤60 行"文案与
  `MAX_FUNCTION_LINES = 80` 常量对齐。
- `limen/gate.py` docstring：判定顺序补"参数提权"（B-55 门内侧）与"缺路径"（B-31）两层。

### Removed
- **Phase 0：旧 `ui/` 与 `desktop/` 从工作树物理移出**（ADR-0040/0044、计划 §12-B；快照在
  `reference-only-archive` 分支 d558494），新代码结构上 import 不到旧实现；连带把
  justfile `gen`/`gen-check`/`types-check`/`desktop-test`/`desktop-build` 配方、pre-commit gen-check
  钩子、contracts.yml `gen-check` job、security.yml npm audit leg、`desktop.yml` 整体、
  dependabot `/ui` npm ecosystem 同批暂停（Phase 2b 新渲染层重建时逐项恢复）；
  `tests/architecture/test_no_hardcoded_panel_case.py` 按 ADR-0044 ② 作废（绑旧 `ui/src/app-shell`；
  替代契约用例 Phase 2b 重建）。旧内核簇（`serve`/`tools`/`limen` 等）按延迟清理策略
  **过渡期保留**（仍为保留侧依赖闭包），新实现替换落地时同批移出——逐目录定性与时机见
  `docs/research/port-ledger.md` 处置地图。
- `ui/scripts/gen-types.mjs`（搬到 `scripts/gen/types.mjs`，避免两处定义，ADR-0019 归属兑现）；
  `ui/package.json` 里 `gen` / `gen:check` 脚本移除。

## [M3 骨架] - 2026-10-12（本 CHANGELOG 起始条目，对应 `91bbd78` 之后的 M3 提交序列）

见上方 `[未发布]`。M3 出口判据 1–4 全部经测试钉住；判据 5（evals N=12 首跑）
诚实标注"未跑"（本机无凭据），见 `evals/README.md` §M3d。

## [M4] - 2026-10-12（长跑与编排；ADR-0025/0026/0027/0028；含收口审查修复）

### Added
- `src/questor/vigilia/` — 值守长跑：声明式触发器（`once`/`interval`/`cron`）+ tick
  （per-task 锁 + 守卫锁，拿锁后复判，B-49/B-94）+ 分批游标清扫（B-40）+ once 幂等（B-42）
  + 同分钟去重（B-41）+ 启动/周期双 reconcile（B-44）+ 唤醒检查点；`process` 工具补"改唤醒周期"。
- `src/questor/orchestration/` — 编排域：`transitions.py` 单点任务状态机（data-model §3.3）、
  独立 append-only store（`~/.questor/orchestration/tasks.jsonl` + 可重建索引，ADR-0025）、
  编排门（结构化错误载荷 B-43）、Plan/Goal/Task/board、`OrchestrationService`（端口实现）。
- `src/questor/evidence/` — 验收证据最小版：声称 vs 录得核对器、`export` 接口形状、
  按 subject 投影（ADR-0027；不做复跑）。
- `src/questor/schemas/orchestration.py` + `schemas/orchestration/v1.json`（编排实体契约，
  data-model v1.3）；`schemas/vigilia.py`（调度形状）。
- `tools/ports.py` `OrchestrationPort` + `ToolContext.orchestration`/`thread_id`（R1 端口注入）；
  模型侧 `plan`/`task` 工具经该端口生效（tools 不 import orchestration）；收口扩
  `sync_subtasks`：按已定稿计划逐步派生子任务（未定稿机械拒绝，崩溃重跑不重复）。
- 提示词资产 `plan_protocol.toml` / `task_protocol.toml` / `goal_loop.toml`（禁止内联提示词）。
- `serve` 方法族 `task/*` `goal/*` `schedule/*` `evidence/get`（21 项，含收口审查补登的
  `task/review` 与 `schedule/create`）+ 通知族
  `task/status` `plan/updated` `goal/status` `evidence/reported` `notice/schedule`；
  `initialize.notification_families` 改为从注册表取（单一真相）。
- `serve/longrun.py` `LongRunDriver`（收口：计划 M4e.2 启动 hook）——挂 http 宿主生命周期：
  tick 循环到点 `turn/start`、启动+周期双 reconcile（B-44，活体不误杀、僵尸必收）、
  Goal 轮自驱（`goal/start` 即时唤醒 + 重启拾取）；stdio 宿主不挂，`goal/start` 在那只登记状态（诚实标注）。
- `cli` 薄命令 `questor task {list,show,create}` / `questor goal {list,create}`（能力全经 serve）。
- `ui/src/panels/board.tsx` + 注册表登记：任务分栏看板 + 任务总结卡确认/打回（DAG 图推 E1，D7）。
- `tests/e2e/` — M4 出口主钉：转后台 → 任务总结 → 打回 → 重做 → diff 可回看。
- `.github/workflows/docs.yml` + `scripts/ci/check_docs.py`（文档相对链接存在性）。
- 坑目录新增 B-94/B-95/B-96；B-40/41/42/43/44/49 由 open 转 covered；B-38/B-39 裁定 moot。
  收口审查再新增 B-97（检查点双写回退竞态）/B-98（白名单迁移缺产品入口）/
  B-99（域内记账绕白名单）/B-100（新 store fold 异常类型化回归），均 covered + 测试先红后绿。

### Changed
- 收口审查修复（TDD 先红后绿）：vigilia 检查点改持锁字段级读-改-写（`record_tick`/
  `set_sweep_cursor`，防游标回退）；`record_round` 仅 RUNNING 可记、完成/失败经 `_move`；
  编排 store `_apply_invalidation` 脏记录统一报存储错；e2e/集成链“进入待审”改经
  `task/review`，看板补“提交待审”按钮。
- `docs/architecture/data-model.md` → v1.3（编排实体 + `Run.task_id`/`goal_id`）；
  `protocol.md` → v1.1（编排方法族/通知族 + 协议加性演进规则 ADR-0028）；
  `overview.md` §7/§12/§14、`structure.md` §5/§6/§11、`development-plan.md` M4 同步。
- `structure.md` §5 依赖矩阵给 `orchestration` 增 `state`（独立 store 需原子写/锁/路径单点）。

### Removed
- 无。

## [M5] - 2026-10-12（验收闭环：可验证柱生产化；ADR-0029）

### Added
- `src/questor/orchestration/acceptance.py` — 验收状态机单点入口（§3.2 白名单
  `proposed → accepted_by_user → executing → reported → verified | regressed`），形态同 `transitions.py`。
- `src/questor/evidence/source.py` — 只读“录得源”核对入口 `collect_recorded(thread_id)` /
  `verify_claims(...)`（只读消费 gesta 落盘 tool_result，不复跑；将来接复跑只换实现源）。
- `evidence` 生产写入点：`OrchestrationService.report_task` 落 `Evidence`（经唯一入口
  `store.add_evidence`）+ 驱动验收态 + `executing → reviewed`；`evidence/reported` 通知自此真实 publish。
- 模型侧 `task` 工具新增 `report` 动作（`ClaimedCheck` 声称 + 绑定 `tool_use_id`）；
  `tools/ports.py` `OrchestrationPort` 扩 `report_task`（`serve/longrun.py` 接宿主事件循环发布器）。
- `schedule/create` 支持 task 目标（到点派发任务执行）；`serve/longrun.py::_fire` 按
  `task_id`/`thread_id` 分派。
- `ui/src/panels/board.tsx` — 验收证据卡：逐条 verdict 色 + `recorded_output_ref` 点击经
  `sessiontrace/get` 回链到具体记录条目（注册表驱动，外壳不改）。
- `evals/runner/grading.py` — 把 `replay_audit`/`recorded_output` 两类 grading 接到真实
  `evidence`/编排 store 只读函数；`evals/tasks/tasks.json` 三柱扩充 12→17。
- 护栏：`tests/unit/test_orchestration_acceptance.py`、`tests/integration/test_evidence_report.py`、
  `tests/integration/test_evals_grading.py`、schedule task 目标与 driver 派发。
- **桌面壳 Python 侧地基**（ADR-0006/0024，M5-desktop 前置）：`serve/stdio.py::serve_stdio`
  完整 sidecar 宿主（入站走 dispatcher、run 通知经 Fanout 泵到同一 stdout、与 WS 同一方法表）+
  `questor serve stdio` 启动器（管道连 stdin/stdout、日志走 stderr）；原生壳待续（ADR-0030 改判 Electron，随 Phase U 交付）。

### Changed
- `docs/architecture/data-model.md` → v1.4（验收态枚举强制 + evidence 生产写入点 + claim→Evidence 可追溯）；
  `structure.md` §5 依赖矩阵 `orchestration` 增 `evidence`（有向无环）；`protocol.md` schedule/evidence 行回写。
- `schemas/orchestration` `TaskAcceptance.status` 由裸 `str` 收敛为 `AcceptanceStatus` 枚举（schema 同步重生成）；
  `store.update_task` 新增拒改嵌套 `acceptance.status`（旁路守卫）。

### Fixed
- 需求改版作废驱动接真：`plan.revise_plan` 递增 `requirement_revision` 时调 `invalidate_acceptances`
  （此前该函数无真实调用方）。B-101/B-102 covered + 负向验证。

### Removed
- 无。
