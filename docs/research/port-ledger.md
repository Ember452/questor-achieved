# port-ledger —— 移植对账台账（wuu 符号 ↔ questor 符号 ↔ 差异/理由）

> 复刻完成度的对账清单（计划 §1.5 机制 3）。每个移植文件/模块与 wuu 不一致处在此记一行理由；"不做/后置"也登记为决定，不留遗漏。随各 Phase 追加。

## Phase 0 · 契约重立基

### 差异登记（契约先于实现）
| # | 项 | 状态 | 说明 / 何时收口 |
| --- | --- | --- | --- |
| TL-1 | `protocol.md` 词表取齐 wuu（`thread/start`/`run/updated` 等），但 `serve/app_server.py` 仍注册旧名（`thread/create`/`run/stop`/`delta`） | **transition-red** | 护栏 `test_serve_methods_are_documented`、`test_serve_notification_families_are_documented` 现红 2 条 = 契约先行、实现待迁移的**正确信号**；**Phase 1/2 重写 serve 后转绿**。不作废护栏、不改测试迁就。 |
| TL-2 | `overview.md`/`structure.md`/`protocol.md`/`data-model.md` 已改母本对齐口径；`modules/*.md`、`development-plan.md`、`phase-u-*` 仍是旧 M 系列/FlowCoder 口径 | 待收口 | 各 `modules/X.md` 在对应 Phase 移植前重写；`development-plan.md`/`phase-u-*` 加历史横幅（见下"文档处置"）。窗口在重写前以本台账 + 转向 ADR 为准（AGENTS §七 必读已 redirect）。**末句长期不实**：§七 必读表实测仍指 `development-plan.md`，2026-10-14 才真改到位（见下行 TL-4 与 B-123）。 |
| TL-3 | 协议版本串 `questor-app-server/v0.1` vs wuu `wuu-app-server/v0.1` | **已定（见 P1-1）** | 用户拍板取 `questor-app-server/v0.1`；initialize 仍严格相等不降级（B-60），Phase 2b 重建前端时其常量对齐。复用 wuu 前端需两端版本串一致：要么保留 `wuu-app-server/v0.1`，要么 patch 前端 `packages/protocol`。Phase 1 接缝实测时定，记此不静默。 |
| TL-4 | 母计划（总计划）只存于 Qoder 计划缓存区 `cache/plans/Questor_对齐_wuu_重构计划_99f1c707.md`，未进版本库；而仓库内 10+ 处按「计划 §1.5 机制 N / §12-A~E / §13 C0–C21 / §14」编号引用它（`docs/specs/README.md`、`tests/contract/README.md`、`schemas/app_server/initialize.py`、`behavior-protocol-wuu.md`、`modules/habena.md`、本台账等） | **已收口** | 2026-10-14 原文**逐字**入库为 `docs/plans/2026-10-13-wuu-alignment-master-plan.md`，顶部加“计划态快照、进度以 phase-a-mvp + 本台账为准”横幅；母计划 §13（仍写“ADR 待写”）与 §12-B（`ui/`、旧 `desktop/` 已移出）的滞后**不改写原文**，现状由本台账“冲突消解收口”与“处置地图”承载。同批修 `AGENTS.md` §七 必读表（原指向已作废的 `development-plan.md`）。本坑已登记 `pitfalls.md` **B-123**（现转 covered：`check_docs.py` 已加两条机械断言 + `tests/unit/test_check_docs_guards.py` 六条用例含负向注入）。 |
| TL-5 | 上游标识写不了 commit SHA：本机 `wuu-main` 是源码快照、**非 git 工作副本**（实测 `git -C wuu-main rev-parse HEAD` 报 `not a git repository`），而 AGENTS §二 与母计划 §1.5 机制 3 都要求 provenance 写 `wuu@<commit>` | **已收口（Phase 2 开工前置）** | provenance 统一改用上游 `VERSION` 串：`# Ported from wuu@2026.10.6 internal/<pkg>/<file>.go`（实测 `wuu-main/VERSION` = `2026.10.6`；`LICENSE` 为 `Copyright (c) 2026 Andy wu`）。AGENTS §二、`NOTICE`、`third_party/THIRD-PARTY-NOTICES` 同批改；记此行以防日后把它误读成一个不存在的 commit。若将来拿到带历史的 wuu git 仓库，需回到 commit SHA 口径并在此登基线。 |
| TL-6 | MIT 署名件缺失：ADR-0037 要求 `NOTICE` + `third_party/THIRD-PARTY-NOTICES`，但 Phase 0/1 未曾真移植代码，两件均不存在（实查 `Test-Path` 皆 False） | **已落地（Phase 2 开工前置）** | 新建 `NOTICE`（逐上游登记 + provenance 口径）与 `third_party/THIRD-PARTY-NOTICES`（wuu MIT **逐字收录**，与 `wuu-main/LICENSE` 按行比对 21/21 EXACT MATCH；比对命令与结果记入本批 commit 正文）。范围如实界定：随 exe 分发的第三方依赖许可证清单留由 ADR-0019 生成器在打包阶段产出，手写必与真实依赖漂移。 |

### 文档处置（回答"删什么/会不会影响开发"）
> 判据：会不会被开窗口当"现状/实现依据"读错。多数是**标历史/改写中**，不是删；仅无保留价值者删。

| 文档 | 处置 | 会误导开发? |
| --- | --- | --- |
| `docs/plans/development-plan.md`（M 系列 + "已完成"勾销） | 加"已被 `phase-a-mvp.md` 取代、M 系列作废"横幅；`phase-a-mvp` 未写前不得据此开工 | 🔴 会（必读）→ 必须标 |
| `docs/plans/2026-10-13-wuu-alignment-master-plan.md`（母计划，2026-10-14 自编辑器缓存区逐字入库） | 加“计划态快照、不含执行进度”横幅 + 在 `docs/README.md`、`phase-a-mvp.md`、`AGENTS.md` §七 三处指向它作 §1.5/§12/§13 的出处；§13/§12-B 旧状态由本台账承载，不就地重写 | 🟡 会（“待写/待做”易被当现状）→ 已标 |
| `docs/plans/2026-10-13-phase-u-*.md`（3327 行已做完 + completion） | 加"历史执行记录，不得再作实现依据"横幅 + 撤销 pending（代码废弃后 pending 全废）；**不删**（B-108~118 唯一出处） | 🔴 会 → 必须标 |
| `docs/architecture/modules/*.md`（tools/providers/context/engine/serve 挂 FlowCoder provenance + 旧内核假设） | 各在其 Phase 移植前重写为"照 wuu X 移植"；重写前窗口**只读 wuu 源码 + 本台账**，不信 modules/*.md 旧结论 | 🟠 局部会 → 该模块开工前重写 |
| `ui/README.md` | 重写/标注：ADR-0040 已废弃 `ui/`，改 `desktop/src/renderer` | 🟠 会 |
| `evals/adapters/mode_map.md`（FlowCoder 六档映射） | **可删**——删前把"实测 `flowcoder --mode read_only` 报错"证据并入 `pitfalls.md` | 否 |
| 根目录 `.scan-*.md`（6 份，已复制进 `docs/research/`） | **可删**（重复）；属临时产物 | 否 |
| 未跟踪 ADR `0033~0036` | 保留文件：0033 仍有效(Phase 2)、0035 superseded by 0045、0036 withdrawn by 0037（README 已标） | 否 |
| `docs/specs/cases-*.md` | 从未存在（C12）；AGENTS §二 已移除该引用；清理 `specs/README`/`overview §3` 的悬空引用 | 🟡 小 |

### 处置地图（ADR-0044 ① 逐目录定性，Phase 0 step1 执行登账）

> 快照分支：`reference-only-archive`（=转向基线 d558494，含旧 src/questor + ui + desktop 全量）。
> 「物理移出」=已从 main 工作树删除；「过渡期保留」=仍在工作树、**替换落地同批移出**
> （延迟清理策略：旧实现仍是后置/保留侧的生产依赖，现在硬拆必产生断 import 红潮，
> 反而诱发"改代码迁就删除"的倒挂）；移出前旧代码只读参考，禁复制实现行。

| 目录 | 定性（ADR-0044） | Phase 0 动作 | 物理移出时机 |
| --- | --- | --- | --- |
| `ui/` | 废弃重写（→`desktop/src/renderer`） | **已物理移出** + toolchain 同步裁剪 | 已完成 |
| `desktop/`（旧 Electron 壳） | 废弃重写（知识存 `archive-desktop-restart-policy.md`） | **已物理移出** + desktop.yml 删 | 已完成 |
| `serve` `tools` `limen` `sessiontrace` `review` `cli` `context` | 按 wuu 蓝本重写 | 过渡期保留（被保留侧依赖闭包） | Phase 2a 新内核替换同批 |
| `engine`（除 `model.py`） `providers` | 按 wuu 蓝本重写（FinishReason 归一等语义重验） | 过渡期保留（testenv/providers 依赖） | Phase 2a/2b 替换同批 |
| `state` | 按 wuu 蓝本重写（→ SQLite 权威 C3） | 过渡期保留（config/gesta/secrets/workspaces/worktree 依赖 atomic/paths/locks） | 新存储层落地同批。**订正（2026-10-14）**：新 gesta SQLite 层在 **Phase 2a** 落地，其已验证 Windows 语义（B-71/B-72/B-73/B-76）由新侧继承后旧 `state` 才能移出；本行“Phase 3/4”仅指旧文件本身的物理移出时机 |
| `orchestration` `vigilia` `evidence` | 后置 Phase 6 | 保留不动 | Phase 6 重建时 |
| `gesta` `schemas` `config` `secrets` `version` `workspaces` `worktree` `capability` `prompts` `habena` `testenv` | 保留（知识/外围/接缝） | 保留 | — |
| `gesta`（**从上行拆出，2026-10-14 改判**） | 按 wuu `internal/session` **重写为 SQLite 权威库**——旧实现是 append-only JSONL 真相源（B-46），与 `data-model.md` v2.0 + ADR-0041（SQLite 权威、JSONL 降为镜像）硬冲突；标“保留”会误导窗口以为无需改动 | Phase 1 已落契约模型知识；存储层重写属 Phase 2a | Phase 2a 新库落地同批（旧 `gesta/{writer,transitions}.py` 与其旧立场测试移出） |

| 尾注 | 登记 |
| --- | --- |
| gen 链（`scripts/gen/types.mjs`、justfile gen/gen-check/types-check/desktop-test、pre-commit 钩子、contracts.yml gen-check job、security npm audit、dependabot /ui ecosystem） | 随 `ui/` 退役整体暂停；真相源 `src/questor/schemas` 保留；Phase 2b 重建时逐项恢复（ADR-0011 required 名单同批） |
| `tests/architecture/test_no_hardcoded_panel_case.py` | 按 ADR-0044 ② 作废：绑死旧 `ui/src/app-shell` 内部细节；替代契约用例（新渲染层外壳不得硬编码面板名）Phase 2b 随 registry 重建，B-93 条目保留 |
| `desktop/README.md`（计划产出 8） | 随壳移出不再单独补写：壳侧知识已在 `archive-desktop-restart-policy.md` + `phase0-wuu-renderer-assembly.md`，新 README 由 Phase 2b 新壳自带 |
| C11/C16（id 正则/大小写） | Phase 0 未实测（phase0 三表无 id 形状证据），**后置 Phase 1**：写 `schemas/app_server/` 时逐字段实测 wuu `protocol.go`/`stdio.go` 定夺，进 port-ledger；属"登记过的后置"非遗漏 |

**当前门禁基线**（Phase 0 收口）：`just check` 全绿（556 passed / 3 xfailed；check_specs、check_notes、check_docs OK）；TL-1 两条 xfail 护栏仍按计划留到 Phase 1/2 转绿。已 commit、已 push。

### 冲突消解收口（计划 §13 C0–C21，Phase 0 逐条落定）

> 仓库侧证据（主计划在编辑器缓存区不可写，此处为可复核的落点记录）：

- **已关（ADR 落定 + 契约文档同步）**：C0→ADR-0045・`behavior-review-fidelity-wuu`§0；C1→ADR-0037・AGENTS §二；C2→ADR-0040・structure・ui/ 已移出；C3→ADR-0041・data-model；C4→ADR-0042・protocol；C5/C6→data-model 重写（Run⊃Turn、状态集、UTF-16）；C7→ADR-0016（自建 wire、与 wuu 同形）；C8→ADR-0042/0030；C9→ADR-0043（后置 P6）；C10→ADR-0039；C12→ADR-0037・specs/README+docs/README 悬空引用已清；C13→structure 重写；C14→AGENTS §六；C15→dependabot 实查无 cargo、`/ui` npm ecosystem 已移；C17→AGENTS §四/ADR-0009；C18→ADR-0037/0038；C20→ADR-0011・justfile/workflow 同步；C21→ADR-0001。
- **Phase 1 实测后新闭**：C11/C16（id 形状：实测为 `json.RawMessage`、数字/字符串皆可、原样回显，见 P1-2）；C19（approval/request：实测 `internal/approvefor/review.go:13-18` **收紧型** `approve_for_me`、五态 allow/deny/unsure/failed/cancelled=B-56、HardDeny 先判、超时/失败 fail-closed，非 per-command 弹窗 → 回写 protocol §5 + overview §11）。
- **C0–C21 至此全部落定**（已关或 Phase 1 实测闭）；无遗留“待 Phase 1”挂账。

## Phase 1 · 跨语言接缝契约重立基

### 硬语义差异登记（wuu ↔ Questor，逐行有理由）

| # | 项 | wuu 事实（锚点） | Questor 差异与理由 | 收口时机 |
| --- | --- | --- | --- | --- |
| P1-1 | 协议版本串 | `wuu-app-server/v0.1`（protocol.go:26） | **改 `questor-app-server/v0.1`**（用户拍板 TL-3）：项目自命名，Phase 2b 重建前端时其常量同步对齐；initialize 仍严格相等不降级（B-60） | 已定 |
| P1-2 | `Request.ID` 类型 | `json.RawMessage`，允许数字或字符串（protocol.go:224/230） | 旧 questor envelope 强制字符串 id；Phase 1 重写容纳两种、响应 id 逐字节回显请求 id | Phase 1 |
| P1-3 | `Turn.items` nil→`[]` | 自定义 `MarshalJSON` 令空 items 输出 `[]` 非 `null`（protocol.go:2457-2464） | Questor 模型必须复刻（前端 `for` 遍历不得收 null）；`model_serializer` 保证 | Phase 1 |
| P1-4 | Provider 凭据 | `InitializeResult.provider/model` 仅活动选择串，无 api_key | Questor 模型 `extra="forbid"` 拒未知键，防凭据误上线（B-57 同源） | Phase 1 |
| P1-5 | `Origin` ≠ `Role` | ChatMessage.Role(provider 角色) 与 .Origin(产品出处) 分离（types.go:313/321） | `schemas/message.py` 保留两独立字段，不得合并 | Phase 1 |
| P1-6 | FinishReason 归一 | `NormalizeFinishReason` 七值表（types.go:116-146） | `message.py` 照语义重写映射（不拷代码），各家停止信号归一 | Phase 1 |
| P1-7 | `run` 内部形状 | `Run = execution.Run` 别名（protocol.go:2004） | Phase 1 只固定 `run` 作为不透明对象上线；内部字段随 Phase 2a 移植 `execution` 逐符号补，不凭猜写死 | Phase 2a |
| P1-8 | item delta/replace | 两态通知（protocol.go:2591-2617） | 契约层分别建模、fixture 断言两态 | Phase 1 |
| P1-9 | 64MiB/`srv-`/NDJSON | stdio.go:16 / client_calls.go:50 / stdio.go:18-32 | 与 wuu 同形，保留 | Phase 1 |

### C11/C16 收口

Phase 1 已实测：id 为 `json.RawMessage`（数字/字符串皆可，原样回显），无固定正则强约束；小写 snake_case 为字段命名主调（逐字段见 protocol.go tag）。C11/C16 从「待实测」转「已实测入表」（P1-2）。

### Phase 1 代码层处置（用户拍「彻底重写不继承」）

- **旧协议世界（过渡期保留，未取代）**：`serve/{envelope,stdio,app_server,dispatch}.py` +
  `schemas/app_server/v0-1.json`（旧词表 `thread/create` 等，**仍在包内 44KB**）+
  `tests/architecture/test_schemas_method_families.py`（按 v0-1.json 与旧 serve 自洽跑**绿**）。
  它们构成一个**自洽的旧世界**；新世界 `schemas/app_server/*.py`(pydantic)+`names.py`+`protocol.md`
  是**目标单一来源**。二者**并行、非同一系统双真相**（§1.5 机制 5 禁的是同一系统两套真相，此处是新旧两世界待合一）；
  旧世界随 **Phase 2a handler 重写同批推倒/合一**（届时 `test_serve_names_are_contracted` TL-1 转绿、
  v0-1.json 与旧 serve 一同移出）。旧 `serve/` 不拷行重写；Phase 1 不写 handler，旧 app_server.py 与其绿测本阶段不动。
- `tests/contract/`（原仅 README 空壳）：本阶段核心交付，建 wuu golden fixtures + 信封/模型层回放（不经 handler）。
- `schemas/message.py` 新增；`schemas/app_server/` 新建 pydantic 模型包，是 A 阶段线契约的**目标**单一来源
  （旧 `app_server/v0-1.json`+`scripts/gen` 生成链原服务已废弃的 ui/，随旧世界 Phase 2a 同批推倒——**非“已取代”**，见上行）。旧 `schemas/llm.py` 与新 `message.py` 的重合在 Phase 2a 收敛，本阶段记此不静默。

### A 阶段方法类型化覆盖率对账（§1.5 机制 5）

| 族 | 模型 | 回放测 | 状态 |
| --- | --- | --- | --- |
| initialize / envelope / error | `envelope` `initialize` | `test_replay_wuu_frames` | 已类型化 + 真实 golden |
| thread/turn/run/item（对话面） | `entities` `families` | `test_replay_wuu_frames` | 已类型化（run 内部透传 P1-7） |
| config/activity/process/workspace/user-question（控制面） | `control_plane` | `test_replay_control_plane` | 已类型化（activity.interaction / user-question.questions·answer / config 大 summary 透传，随 handler 收紧） |
| engine list/update、shutdown、text/polish、usage | — | — | **后置**：属 handler/config/面，Phase 2a/5 物化时补类型化（名字已在 `names.py` 登记） |
| sessionFolder/*、config 写面 | — | — | **后置**（B 配置面，phase0-table 已标） |

> 未类型化项均为“登记过的后置/透传”，非静默遗漏；`names.py` 保证声明面方法/通知全集先行，
> handler+类型模型 Phase 2a 同批。旧 `test_serve_names_are_contracted`（TL-1）待 handler 迁 wuu 名后转绿。

### Phase 1 契约层落地状态（本批）

- 已建（均已测）：`schemas/app_server/{names,envelope,initialize,entities,families}.py` +
  `tests/contract/test_replay_wuu_frames.py`（真实 golden 两份 + 手写四族） +
  `tests/architecture/test_protocol_single_source.py`（protocol.md§3/4/7↔names 双向）。
- 不透明透传（**登记过的后置**，非遗漏）：`run` 内部（P1-7）、`InitializeResult` 各大 summary
  （permissions/providers/model_profile/… 属 config 面）、`images`/`files` base64 形状——均以
  `dict[str, Any]` 占位，随 Phase 2a/2b 逐字段收紧（届时补类型化模型 + 回放断言）。
- **Phase 0 欠账已闭合**：三份 `phase0-wuu-{protocol-table,renderer-assembly,sqlite-schema}.md` 均于 2026-10-14
  Phase 1 期间**回填真实扫描**（之前均为 0 字节空文件、误按“齐”判）。renderer-assembly 实测 wuu 648 文件
  渲染层 + AppState.ts 事件 reducer + 189 个 `wuu:` preload 通道；sqlite-schema 实测 session.go:1214-1470
  全部 CREATE/PRAGMA(WAL/_txlock=immediate/busy_timeout) + inbox 幂等 SQL + held_user_work 整表替换事务。
  Phase 0 “三表逐符号可复核”出口判据至此**真正达成**（不再建在流沙上）。

## Phase 2a · 内核移植（进行中）

### 批次 1：gesta（SQLite 会话权威库，2026-10-14）

蓝本已从旧记的 `internal/agentthread/store.go`（属不做面、且旧行为规格把它当成 gesta 母本）
改指 `internal/session/*`；`docs/specs/behavior-gesta-wuu.md` 已整体重写。

| # | 项 | wuu 事实（结论锁在哪个函数） | Questor 做法与理由 | 收口时机 |
| --- | --- | --- | --- | --- |
| G-1 | 写事务取锁 | DSN 带 `_txlock=immediate`（`session.go#L1225`） | Python `sqlite3` 不认 `_pragma`/`_txlock` 查询串：改用 `isolation_level=None` + `write_txn()` 显式 `BEGIN IMMEDIATE`；PRAGMA 全部连上后逐条执行（照 `configureDB` 取值与顺序） | 已定 |
| G-2 | 进程内写串行 | `storeWriteMu`（全局互斥锁）+ 每次调用 `openStore(dir)` 开关连接 | 每个 store 一个**专用写线程 + 任务队列**：因 `sqlite3` 连接不得在不同线程间使用（实测 `ProgrammingError`），而 engine 会从多个 `to_thread` 工作线程写同一库；读走线程局部连接（WAL 允许读者与写者并存），不进队列 | 已定 |
| G-3 | `session_inbox` 列集 | CREATE 只 8 列，`controls_json/work_id/work_revision/work_version` 由 `addColumnIfMissing` 追加（L2005-2018） | 基线 CREATE 直接含全列（新库无需爬），**同时保留 `ensure_column` 追加路径**与并发竞态容忍（B-125）；实现过程中真以 `KeyError: 'delivered_at'` 撞过一次“拿写入列单去 SELECT”（B-126），已拆 `_WRITE_COLUMNS`/`_READ_COLUMNS` | 已定 |
| G-4 | seq 分配 | `appendHistoryRecordTx` 事务内 `COALESCE(MAX(seq),0)+1` | 一致；额外新增 `SequenceRejected`：调用方自带 seq 直接拒（wuu 无此入口，无对应错误可照搬）——防“两个写者各算各的”（B-45） | 已定 |
| G-5 | append-only 表达 | wuu 靠约定（只有 PK 单调），**无触发器** | 比母本加严：两个触发器——禁 `UPDATE OF content/display_content/seq/role/session_id`；禁“所属会话仍在时删单行”，用 `WHEN EXISTS(SELECT 1 FROM sessions ...)` 区分级联删除（`thread/delete` 是 protocol.md §3 在册方法，不加 WHEN 会把会话删除一起挡死）——`data-model.md` §4 立场 | 已定 |
| G-6 | 送达判据 | `PendingInbox` 的 `UPDATE ... WHERE EXISTS(session_messages.client_id = session_inbox.client_id)`（L92-94） | 逐字对齐（B-127）；负向已实测：改成“入队即写 delivered_at”→ 两条用例当场红 | 已定 |
| G-7 | 控制栅栏 | `validateInboxControls` 同时查 `project_work` 与 `session_controls`（L175-235） | **只移植 `session_controls` 那一半**（manager/revision/state 全等才放行，B-129）；`project_work`/`cause=project` 分支属不做的多-agent 编排面（scan-wuu-kernel §8）——登记为决定非遗漏 | 已定 |
| G-8 | held_work 校验位置 | 事务内逐条校验（失败靠 deferred rollback，L44-55） | 前置到写入之前：可观测结果一致（失败则整表原样），少一次无谓 DELETE；两段取负压缩照搬，**诚实标注**：本机把其换成朴素 `position-1` **测不出红**（SQLite 不保证 UPDATE 扫描序），故 B-128 只记为“母本防御性语义”而非已观测故障 | 已定 |
| G-9 | 不做/后置表 | `participants`/`participant_runs`/`project_work*`/`plugin_turn_lifecycle*`/`inference_journal_runtimes`/`session_folders` | 一律**不建**（`test_migrate_creates_authority_tables` 反向断言它们不在）；`session_driver_checkpoints`/`session_model_input_receipts` 本轮也不建（Phase 6 与审计阶段再评估） | Phase 6 / 审计批次 |
| G-10 | 已建未接写路径 | `session_history_{retractions,checkpoints}`、`session_compaction_notes`（L1390-1425） | 表已建、**尚无写入者**：历史改写（`LoopResult.history_rewritten`）随批次 4 engine、压缩笔记随批次 3b context 接入；登记以免“有表”被误读成“已实现” | 批次 3b/4 |
| G-11 | 旧 JSONL 世界 | 不适用（旧 questor 实现，非母本） | `gesta/{store,writer,transitions}.py` 仍在工作树（被旧 engine/serve 依赖，延迟清理策略）；批次 5 重写 serve 时同批移出，**并把 `pitfalls.md` 的 B-46（JSONL 唯一真相源）改 `moot`**、按 ADR-0044 ② 逐条登记其对抗用例的作废/替代理由 | 批次 5 |
| G-12 | `thread/delete` 的“需 idle” | appserver 侧按 run 状态拒删活跃会话 | 本轮 `delete_session` 只保证“会话存在才删”；`SessionBusy` 错型已定义但**无调用者**（run 状态面属批次 4/5）——不得假装已拦 | 批次 4/5 |
| G-13 | 时间列 | `timeText` UTC 文本 | `schema.now_text()` 单点 UTC ISO8601（创建序/送达判定/updated_at 排序共用一把尺） | 已定 |

### 批次 1–5 的替换节律（防“新旧双真相”）

每批次一个 commit：**新实现 + 新测试 + 旧实现同批移出**；例外只在“旧实现仍是被保留侧的生产依赖”时发生
（gesta 的旧 JSONL 与旧 engine/serve 同命运，故本批并存至批次 5）。并存期间新代码一律只用新门面，
旧门面不再添新功能；各批收口前过一遍清单：`grep` 确认无新代码 import 旧路径。
