# port-ledger —— 移植对账台账（wuu 符号 ↔ questor 符号 ↔ 差异/理由）

> 复刻完成度的对账清单（计划 §1.5 机制 3）。每个移植文件/模块与 wuu 不一致处在此记一行理由；"不做/后置"也登记为决定，不留遗漏。随各 Phase 追加。

## Phase 0 · 契约重立基

### 差异登记（契约先于实现）
| # | 项 | 状态 | 说明 / 何时收口 |
| --- | --- | --- | --- |
| TL-1 | `protocol.md` 词表取齐 wuu（`thread/start`/`run/updated` 等），但 `serve/app_server.py` 仍注册旧名（`thread/create`/`run/stop`/`delta`） | **transition-red** | 护栏 `test_serve_methods_are_documented`、`test_serve_notification_families_are_documented` 现红 2 条 = 契约先行、实现待迁移的**正确信号**；**Phase 1/2 重写 serve 后转绿**。不作废护栏、不改测试迁就。 |
| TL-2 | `overview.md`/`structure.md`/`protocol.md`/`data-model.md` 已改母本对齐口径；`modules/*.md`、`development-plan.md`、`phase-u-*` 仍是旧 M 系列/FlowCoder 口径 | 待收口 | 各 `modules/X.md` 在对应 Phase 移植前重写；`development-plan.md`/`phase-u-*` 加历史横幅（见下"文档处置"）。窗口在重写前以本台账 + 转向 ADR 为准（AGENTS §七 必读已 redirect）。 |
| TL-3 | 协议版本串 `questor-app-server/v0.1` vs wuu `wuu-app-server/v0.1` | 待 Phase 1 定 | 复用 wuu 前端需两端版本串一致：要么保留 `wuu-app-server/v0.1`，要么 patch 前端 `packages/protocol`。Phase 1 接缝实测时定，记此不静默。 |

### 文档处置（回答"删什么/会不会影响开发"）
> 判据：会不会被开窗口当"现状/实现依据"读错。多数是**标历史/改写中**，不是删；仅无保留价值者删。

| 文档 | 处置 | 会误导开发? |
| --- | --- | --- |
| `docs/plans/development-plan.md`（M 系列 + "已完成"勾销） | 加"已被 `phase-a-mvp.md` 取代、M 系列作废"横幅；`phase-a-mvp` 未写前不得据此开工 | 🔴 会（必读）→ 必须标 |
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
| `state` | 按 wuu 蓝本重写（→ SQLite 权威 C3） | 过渡期保留（config/gesta/secrets/workspaces/worktree 依赖 atomic/paths/locks） | 新存储层落地同批（Phase 3/4） |
| `orchestration` `vigilia` `evidence` | 后置 Phase 6 | 保留不动 | Phase 6 重建时 |
| `gesta` `schemas` `config` `secrets` `version` `workspaces` `worktree` `capability` `prompts` `habena` `testenv` | 保留（知识/外围/接缝） | 保留 | — |

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
- **后置含登记（非遗漏）**：C11/C16（id 正则/大小写）、C19（approval/request 收紧 vs per-command）——均待 Phase 1 逐字段实测 wuu `protocol.go`/`stdio.go` 定夺（本台账上行 + overview §13 未决项 #5）。

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

- 旧 `serve/{envelope,stdio,app_server,dispatch}.py` + 旧名测试：不拷行重写；旧 `serve/` 仍按 Phase 0 处置地图「过渡期保留」到 Phase 2a 新内核同批推倒（因 Phase 1 不写 handler，旧 app_server.py 与其绿测本阶段不动，新契约层并行立住、由 tests/contract 驱动）。
- `tests/contract/`（原仅 README 空壳）：本阶段核心交付，建 wuu golden fixtures + 信封/模型层回放（不经 handler）。
- `schemas/message.py` 新增；`schemas/app_server/` 新建 pydantic 模型包（取代旧 `app_server/v0-1.json`+生成链路线；该路线原服务已废弃的 ui/，Phase 1 改 pydantic 单一来源）。旧 `schemas/llm.py` 与新 `message.py` 的重合在 Phase 2a 收敛，本阶段记此不静默。
