# Questor 项目结构（structure）

版本: v0.4 | 更新: 2026-10-11 | 状态: 待用户评审（v0.4：M1 增补 `ui/` 骨架，裁定记录见 `docs/plans/development-plan.md` M1）
关联: `overview.md`（语义、分层、R1–R5、职责登记、契约的唯一来源）、`AGENTS.md` §二 §四、
`docs/adr/0001`（命名）、`docs/adr/0007`（Windows 沙箱）

本文回答**目标态布局**：仓库最终该有哪些目录、包与工程外围文件，以及每个部分的职责边界。
颗粒度到**目录/包**为止；文件级布局随各模块首个任务确定（§10 文档视距）。

**权责划分**：`overview.md` 管语义与约束；本文管物理布局与物化节奏。任一方越界描述对方内容，
评审打回并修正越界方。

**关于"目标态 vs 现状"**：本文描述完整目标；带 `[Mx]` 标记的目录/文件表示随该里程碑物化，
**现在不建空目录**（§10）。当前实际存在的只有 §9 那张表里的 10 项。

---

## 1. 参照与实测依据

| 参照 | 实测到的结构事实 | 本项目取用 |
| --- | --- | --- |
| **wuu** | 顶层 20 项；`internal/` **76 个包**（含 `testenv` `statepath` `shellpath` `securefs` `storelock` `storagecodec` `stringutil` `version` `capability` `context` `contextbudget` `compact` `instructions` `workingnotes` `sessiontrace` `toolctx` `toolerrors` `toolledger` `toolresult` 等基建包）；`cmd/` **11 个入口**（主 CLI、server、8 个插件二进制、1 个 codegen）；`packages/{protocol,plugin-sdk,plugin-go}` 对外契约与 SDK；`plugins/` 8 个内置插件**各带单测与集成测试**；`examples/plugins/` 7 个扩展示例；`evals/{cases,results,result.schema.json,README}`；`prompts/`（**独立 `LICENSE-Codex` 与 `NOTICE`**）；`config/`（生成的主题/表面矩阵契约 JSON）；`containers/execution/Dockerfile`；`deploy/remote/`（compose、Caddyfile、Dockerfile、verify 脚本、API.md）；`.github/`（**9 个 workflow** + ISSUE_TEMPLATE×2 + PR 模板）；`third_party/licenses/`；`docs/` + `docs-site/`(Astro) + `landing/`；根：`Makefile` `VERSION` `SECURITY.md` `CODE_OF_CONDUCT.md` `CONTRIBUTING.md` `CHANGELOG.md` `README_zh.md` `.node-version` `.dockerignore`；`desktop/`（`electron.vite.config.ts` `vitest.config.ts` `tsconfig.json` `index.html` 双 lock） | 薄入口厚内核的切法；基建包单列；契约与 SDK 独立发布物；`evals` 三件套；提示词资产带独立 notice；CI 按能力拆分；`VERSION` 单点 |
| **EvoFlow** | 根含 `AUTHORS.md` `CLA.md` `MAINTAINERS.md` `NOTICE` `SUPPORT.md` `SECURITY.md` `CODE_OF_CONDUCT.md` `CONTRIBUTING.md` `CHANGELOG.md` `mkdocs.yml` `requirements-docs.txt` `.env.example` `.gitattributes` `config.example.yaml` `extensions_config.example.json` `uv.toml`；`docker/{nginx,provisioner}`；`scripts/{ci,docs,git-hooks,maintainer,release,windows}`；`skills/public/`（82 个技能）；`licenses/`；内核与桌面壳物理分离（`backend/` 与 `evopanel/`） | 治理文件全集；`scripts/` 子目录分类；示例配置文件；沙箱 provisioner 独立目录 |
| **FlowCoder** | `.pre-commit-config.yaml`、`PROMPTS.md`、`pyproject.toml` 单点、`src/flowcoder/` 单包 27 模块、`tests/` 分层、`web/` 独立前端、`eval-data/` 与 `chaos-results/` | Python 侧单包；pre-commit 门禁前移；评测与混沌产物独立目录 |
| 大型开源 Python 惯例 | src layout、`py.typed`、`conftest.py`、`noxfile`/`justfile`、`dependabot`、`CODEOWNERS`、Keep a Changelog、`THIRD-PARTY-NOTICES` 由工具生成、`docs/` + 站点、`examples/`、`.editorconfig` | 全套 |

**结论**：`cmd/`+`packages/`+`plugins/`+`examples/`+`evals/`+`config/`+`containers/`+`deploy/`+`third_party/`
+ 治理文件 + 多 workflow CI，这些"外围"才是让一个内核成为**可维护开源项目**的部分。
本项目全部纳入目标态，按里程碑物化。

---

## 2. 总体结构（目标态）

```
questor/
├── src/questor/                # 唯一 Python 包（§4 模块清单，§5 import 矩阵管方向）
│   ├── cli/                    #   命令行入口 questor（别名 qst）
│   ├── serve/                  #   网关：REST + SSE/WS + qst-app-server 会话层
│   ├── engine/                 #   引擎契约、注册表、内置循环、外部适配器
│   ├── tools/                  #   工具登记、schema、执行、结果封装
│   ├── limen/                  #   唯一权威权限门（三档 / 可达性 / 敏感守卫 / 收紧审批）
│   ├── context/                #   上下文预算、自适应压缩、大结果落盘与回读
│   ├── review/                 #   工作区修订号、真实 diff、turn↔revision 绑定
│   ├── gesta/                  #   会话记录（append-only）与验收导出
│   ├── habena/                 #   插话、排队、接管与暂停、取消传播
│   ├── vigilia/                #   值守长跑、调度、唤醒检查点、僵尸清扫
│   ├── evidence/               #   声称的检查 vs 当时真实输出
│   ├── orchestration/          #   Plan / Goal / 看板 / 验收与打回
│   ├── providers/              #   模型客户端、用量、能力声明
│   ├── prompts/                #   运行时提示词与指令资产（随包发布）
│   ├── schemas/                #   协议与数据契约 schema（真相源，§6）
│   ├── skills/  mcp/  hooks/   #   M7 能力扩展（与第三方插件同契约）
│   ├── extensions/             #   M7 插件宿主（生命周期、safe mode、诊断）
│   ├── workspaces/ worktree/   #   工作区注册与 Git worktree 隔离
│   ├── config/                 #   类型化配置加载（用户/机器/会话作用域与错误通知）
│   ├── state/                  #   路径单点解析 + 原子写 + 跨进程文件锁 + 编码
│   ├── secrets/                #   凭据存储（OS keyring 优先，回退文件+守卫）
│   ├── capability/             #   feature flag 与能力开关（L4 渐进启用的机制）
│   ├── sessiontrace/           #   会话轨迹回放（不重跑工具、不联系模型）
│   ├── version/                #   版本单点与构建标识
│   ├── testenv/                #   测试基建：fake home、fake provider、fake git（不进生产路径）
│   └── py.typed                #   类型标记
├── plugins/                    # M7：内置插件（各带单测与集成测试），与第三方同公开 API
├── examples/                   # M7：扩展示例（最小插件、技能、MCP 接入）
├── packages/                   # M7+：对外发布物（协议 TS 包 / 插件 SDK），一旦有第二使用者才建
├── schemas/                    # ✗ 不建顶层目录：契约在 src/questor/schemas/（§6 说明）
├── ui/                         # M3：**唯一前端代码源**（React/TS），一套代码两个宿主：桌面与网页
│   ├── src/                    #   panels / conversation / state / rpc / design / i18n
│   ├── index.html  vite.config.ts  vitest.config.ts  tsconfig.json  eslint.config.mjs
│   └── package-lock.json        # 单一 lockfile（见 §7 lockfile 纪律）
├── desktop/                    # M3：Tauri 桌面壳（**只包壳**，不持有前端代码）
│   └── src-tauri/              #   Rust：窗口、sidecar 生命周期、capabilities、图标、tauri.conf.json
├── containers/                 # M8：执行环境镜像（worker 镜像 Dockerfile）
├── deploy/                     # M8：`web/`（compose + Caddyfile）自托管 Web 宿主；远程/遥控另计（需单独 ADR）
├── clients/                    # 远期：**只放原生/RN 等真异质客户端**；网页不建端，走 `ui/` 响应式
├── evals/                      # M1 起：tasks/ runner/ results/ result.schema.json README.md
├── tests/                      # §8：unit / contract / integration / architecture / adversarial / e2e / fixtures
├── scripts/                    # §9：ci / docs / gen / release / windows（**不放业务逻辑**）
├── docs/                       # architecture / adr / specs / plans（阶段级开发计划）
├── assets/                     # M3：应用图标与截图源（含再生成命令说明）
├── third_party/                # M2：licenses/ + 由脚本生成的 THIRD-PARTY-NOTICES
├── .github/
│   ├── workflows/              # §10：ci / contracts / desktop / evals / docs / security / release
│   ├── ISSUE_TEMPLATE/         # bug_report.md、feature_request.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── dependabot.yml          # pip + npm + cargo + github-actions
├── pyproject.toml  uv.lock  justfile  VERSION
├── README.md  CHANGELOG.md  CONTRIBUTING.md  SECURITY.md  CODE_OF_CONDUCT.md
├── LICENSE  NOTICE             # NOTICE 列上游致谢（参照项目设计参考 + 第三方）
├── .editorconfig  .pre-commit-config.yaml  .gitattributes  .gitignore
├── .env.example  config.example.toml  # 配置样例（EvoFlow 用 config.example.yaml）
└── .python-version  .dockerignore  SUPPORT.md(可选)  AUTHORS.md(可选)
```

---

## 3. 模块清单与 wuu 对应物

新增模块必须先在 `overview.md` §6 登记职责（R5），再建目录。**两表的模块名必须逐项对齐**
（一行一个模块，不得合并行列），以便用脚本做奇偶校验。

| questor 模块 | 职责 | wuu / EvoFlow 对应包（证据） | 物化 |
| --- | --- | --- | --- |
| `engine` | 循环、turn 生命周期、事件流、引擎契约与注册表、外部适配器 | `internal/agent`、`loopdriver`、`agentengine`、`enginecatalog`、`externalengine`、`claudeengine`、`codexengine` | M2 |
| `tools` | 工具登记、schema、执行、结果封装与截断 | `internal/tools`(122 文件)、`toolctx`、`toolerrors`、`toolledger`、`toolresult` | M2 |
| `limen` | 唯一权威权限门；三档、可达性推导、敏感路径守卫、只能收紧的审批 | `internal/tools/boundary.go`、`authorization.go`、`approvefor`、`capability` | M2 |
| `context` | 上下文预算、自适应压缩、压缩边界记录、超预算结果落盘与回读 | `internal/context`、`contextbudget`、`compact`、`agent/adaptive_compact.go` | M2（最小）→M4（自适应） |
| `review` | 工作区修订号、真实 diff、turn↔revision 绑定、Git 归属 | `internal/gitattribution`、`worktree`、`desktop` Review 语义 | M3 |
| `gesta` | 会话记录 append-only、可重建索引、验收导出 | `internal/session`(57 文件)、`sessiontrace`、`statepath` | M2 |
| `habena` | 插话收件箱、排队、接管与暂停、取消传播 | `session/inbox.go`、`held_user_work.go`、`sidethread`、`participant` | M3 |
| `vigilia` | 值守长跑、cron 与一次性、唤醒检查点、僵尸运行清扫 | `internal/schedule`、`activity`、`agentcontrol`、EvoFlow `proactive`/`scheduler` | M4 |
| `evidence` | 声称的检查与当时真实输出并排核对、验收证据出口 | `toolledger`、`evalharness`；本轮不复跑（overview §2） | M5 |
| `orchestration` | Plan / Goal / 看板 / 验收与打回 | EvoFlow `collab`、`plans`、`stage`、`session_execution` | M4 |
| `providers` | 模型客户端、用量、能力与选项声明 | `internal/providers`(62 文件)、`providerfactory`、`provideroptions`、`modelcatalog`、`modelprofile`、`modelroles`、`modelvariant`、`modelbudget` | M2 |
| `prompts` | 运行时提示词与指令资产，分用途分块，随包发布 | wuu `prompts/`（**含 `LICENSE-Codex` 与 `NOTICE`**）、`internal/prompt`、`instructions`、`workingnotes` | M2 |
| `schemas` | 协议方法与数据契约 schema（纯 JSON Schema） | `packages/protocol` + wuu `config/*.json` 生成契约 | M1 |
| `skills` / `mcp` / `hooks` | 技能装载、MCP 客户端与传输、生命周期钩子 | `internal/skills`、`mcp`(20 文件)、`hooks`(22 文件) | M7 |
| `extensions` | 插件宿主：安装/批准/启停/运行时世代/safe mode/诊断 | `internal/extensions`、`plugin`、`pluginhost`(29 文件)、`pluginsettings` | M7 |
| `workspaces` | 工作区注册、路径可见性与默认工作区 | `internal/workspaces`、EvoFlow 工作空间面板 | M2 |
| `worktree` | Git worktree 生命周期与隔离（分叉到 worktree、长跑隔离） | `internal/worktree`、wuu 会话 Worktree 开关 | M3 |
| `config` | 类型化配置加载与作用域合并、热改错误通知 | `internal/config`(16 文件)、`runtimeconfig` | M2 |
| `state` | 路径单点解析、原子写、跨进程文件锁、存储编码 | `internal/statepath`、`securefs`、`storelock`、`storagecodec`、`shellpath` | M2 |
| `secrets` | 凭据存储（OS keyring 优先）与守卫 | `internal/credentialstore`、`authstorage`、`securefs` | M2 |
| `capability` | feature flag 与能力开关 | `internal/capability`、`harness` | M2 |
| `sessiontrace` | 轨迹回放，不重跑工具不联系模型 | `internal/sessiontrace`、`evals/README` 的复现要求 | M3 |
| `version` | 版本单点与构建标识（`VERSION` 文件为唯一来源） | `internal/version`、wuu `VERSION` + `make version-sync` | M2 |
| `testenv` | 测试基建：fake home / fake provider / fake git / 时钟 | `internal/testenv` | M1 |
| `cli` / `serve` | 命令行入口 / 网关与协议服务 | `cmd/wuu`、`cmd/wuu-server`、`internal/appserver`(192 文件)、`remote` | M2 / M3 |

**明确不单列的 wuu 包**（合并或不做，避免无使用者的碎片包）：
`stringutil`（无共性就留在调用点）、`codemode`（程序化工具调用属 M6+ 再评）、
`imageproc`（并入 `tools` 结果处理）、`insight`/`activity`（并入 `vigilia`/`serve`）、
`grokbuildspec`/`sdk`/`plugin-go`（Go 专有）、`landing`/`docs-site`（M8 之后再议）。

---

## 4. 入口与可执行物

| 入口 | 命令 | 对应 wuu |
| --- | --- | --- |
| 主 CLI | `questor` / `qst`：`exec`、`resume`、`fork`、`session`、`review`、`plugin`、`skills`、`init`、`version` | `cmd/wuu` |
| 协议服务 | `questor app-server`（NDJSON over stdio） | `cmd/wuu` 子命令 |
| 自托管服务 | M8+ 才考虑 `questor relay` | `cmd/wuu-server`、`internal/remote` |
| codegen | `scripts/gen/`：schema → TS 类型、THIRD-PARTY-NOTICES | `cmd/wuu-modelcatalog-gen`、`scripts/generate-*.ts` |
| 桌面壳 | `desktop/`（Tauri sidecar 起 Python core） | `desktop/`（Electron spawn Go core） |

内置插件与示例各带自己的测试（`plugins/*/..._test.py`），不接受只验包不验行为。

---

## 5. 依赖方向如何被机械强制（R1 的可执行版本）

R1 在**同一个 Python 包内**不由包边界保证，必须由检查器保证。

- 工具：**`import-linter`**（声明式 contract，CI 给出违规清单）；受阻则自写 AST 遍历，落 `tests/architecture/`。
- **0 违规起步**：新仓库无历史债，不设 baseline 文件（对照 EvoFlow 的 60 条豁免债）。
- **禁环**：矩阵不得出现双向允许（A 允许依赖 B 且 B 允许依赖 A）——双向即环，
  由 `tests/architecture/` 断言（M1 复审发现 `serve`↔`cli` 曾双向允许，已收敛为 `cli`→`serve` 单向）。
- 三条硬断言同处：append-only 不可改写、状态迁移唯一写入入口、权限判定无绕过路径。

| 模块 | 允许 import |
| --- | --- |
| `limen` | 标准库、`schemas`（类型）——其余全部禁止 |
| `state` `version` `capability` `config` `secrets` | 标准库、`schemas`、彼此单向（`config`→`state`，不得反向） |
| `tools` | `limen` `state` `config` `schemas` `prompts` `review` `workspaces`（M3a-2：写工具需 `review.compute_diff` 与 `workspaces.bump_revision`；M4：编排工具经 `OrchestrationPort` 注入——port 定义在 tools、实现在 orchestration、装配在 serve，**tools 不 import orchestration**，ADR-0025 D4） |
| `context` | `schemas` `gesta` `providers`（仅用量结构） |
| `gesta` | `schemas` `state` `config` |
| `engine` | `tools` `limen` `context` `gesta` `providers` `schemas` `prompts` `state` |
| `review` | `limen` `state` `schemas` `gesta`（M3a-2：turn_bindings 读 ThreadView 取 run/item 投影，TYPE_CHECKING 引用运行时不引） |
| `worktree` `workspaces` | `limen` `state` `schemas` |
| `habena` | `engine` `gesta` `schemas` |
| `vigilia` | `engine` `gesta` `schemas` `state` |
| `evidence` | `review` `tools` `gesta` `schemas` |
| `sessiontrace` | `gesta` `schemas`（只读投影，不写盘不联系模型） |
| `orchestration` | `engine` `vigilia` `gesta` `context` `schemas` `prompts` `state`（M4：编排实体住独立 append-only store，需 `state` 的原子写/锁/路径单点，ADR-0025） |
| `providers` | `schemas` `state`（**不得 import 任何业务模块**；wire 词汇表取 `schemas.llm`，ADR-0016） |
| `prompts` `schemas` | `schemas` 无依赖；`prompts` 只取 `schemas` 的类型（资产与装配，不取业务） |
| `skills` `mcp` `hooks` `extensions` | `schemas` + 已注册的公开扩展接口；**内核不得反向 import 它们** |
| `serve` | 除 `cli` 外全部（最上层组装点；**不得 import `cli`**，否则与下行构成环） |
| `cli` | `serve` `engine` `providers` `config` `schemas` `version`（`version` 是叶模块，只读取版本单点） |
| `testenv` | 任何模块（只被测试 import，生产代码禁止） |

---

## 6. 契约真相源与生成物

- 位置：**`src/questor/schemas/`**（随包发布、与代码同版本、运行时可直接校验）。
  顶层 `schemas/` 被否决：要么靠 hatchling `force-include` 塞进 wheel（脆弱配置），
  要么与代码不同版本（校验用的 schema 和运行代码不是同一份）。
- `schemas/app_server/`：qst-app-server 方法与事件；`schemas/model/`：Workspace / Thread / Turn / Run / Item / Event；
  `schemas/orchestration/`：编排域 Task / Plan / Goal / Evidence（M4，ADR-0025）。
- schema 必须是**纯 JSON Schema**（TS 与其他语言可直接消费），Python 专有表达式不得写进去，pydantic 只做绑定。
- 生成物：`ui/src/rpc/generated/`；**`just gen` 后 `git diff --exit-code` 必须为空**，CI 跑同一断言（R4 的可检查形式）。
- 对外发布物（`packages/protocol`、插件 SDK）**等有第二个真实使用者时再建**（AGENTS §二：无第二使用者不做抽象）。

---

## 7. 前端与宿主（`ui/` + 桌面壳 + 网页）

**形状定为"单套前端 + 两个宿主"**，依据两个参照：wuu 用 `clients/core` 共享前端资产喂多个宿主
（desktop / mobile-web / native），EvoFlow 的 `evopanel/` 同一份 TS 代码**既能装 Tauri 桌面包又能装 Docker 跑网页**
（`evopanel/Dockerfile`、`docker-compose.yml`、`docker/nginx`，后端侧 `webui` 包管 JWT/OIDC 与静态伺服）。
写两份 UI 会立刻分叉，所以定：**`ui/` 是唯一前端代码源**，`desktop/` 只包壳，网页由 Gateway 伺服同一构建产物。

| 分块 | 职责 |
| --- | --- |
| `ui/src/panels/` | Review（逐文件真实 diff）、Files（预览与"只改这一段"）、Terminal；Browser 面板延后（决定见 overview §4，完整理由待补 `ADR-0006`） |
| `ui/src/conversation/` | 会话流、插话与排队、分叉、侧聊、选中引用与批注 |
| `ui/src/workbench/` | 工作区与面板布局、展开/窄窗适配（三柱里的"可见"全在这层的约束里） |
| `ui/src/state/` | 会话列表、工作区与面板状态 |
| `ui/src/rpc/` | 协议客户端（WS/SSE）+ §6 生成的类型；**禁止手写 DTO** |
| `ui/src/design/` | 设计 token 与风格基座（参照 evopanel 组件与样式体系） |
| `ui/src/i18n/` | 文案分层（参照 EvoFlow `prompt_blocks_en/zh` 的拆分思路，但只存用户可见文案） |
| `desktop/src-tauri/` | Rust：窗口、`questor` sidecar 进程生命周期与崩溃重启、capabilities、图标 |

**宿主差异与约定**

| 宿主 | 传输 | 绑定与信任 | 建立 |
| --- | --- | --- | --- |
| 桌面（Tauri） | 本机 **stdio NDJSON**（sidecar） | 无网络监听；本机用户即权限主体 | M3 |
| 网页（本地） | Gateway **WS/SSE** | **默认只绑 `127.0.0.1`**；无鉴权（同机同用户） | M3（与桌面同一构建产物） |
| 网页（自托管/局域网） | Gateway WS/SSE + `deploy/web/` 反代 | **必须鉴权**（登录与会话归属），属 L4 能力且需单独 ADR | M8 |
| 手机浏览器 | 同上（响应式） | 同上；不单独建 `clients/` | M8 |
| 原生客户端 | app-server 协议 | 未定 | 远期 `clients/` |

两条硬约定：

1. **一套会话层协议、两种传输**（桌面 stdio、网页 WS/SSE）；Web 宿主绝不得拥有第二套契约或私有端点
   （overview §8 §14）。违反的后果就是 wuu 那种 556 行协议文档也撕不平的双真相。
2. **lockfile 只允许一个**（`ui/package-lock.json`，配 npm）。wuu 的 `desktop/` 同时存在 `bun.lock` 与
   `package-lock.json`，是典型的双锁源漂移，不予复制。前端包若入 CI，dependabot 需同时覆盖 npm 与 cargo。

**技术栈与现成件**（evopanel 实测在用，可直接沿用其选型，省掉 M3 重新选型）：
React 19 + TS + Vite 6 + Tailwind 4 + **zustand** + SWR；
`@xterm/xterm`（+ `node-pty` 侧支持）→ Terminal 面板；`@pierre/diffs` → Review diff 渲染；
`@xyflow/react` → DAG 看板；`@tauri-apps/plugin-shell` → sidecar 生命周期；
`streamdown` / `shiki` / `pdfjs-dist` / `lexical` → 流式 Markdown、代码高亮、PDF、编辑器。

**版本纪律**：evopanel 用的是 **zustand v4**（`^4.5.7`）。本项目**显式选 v5** 并只用官方 hook 用法，
因为参照它的代码是 v4 写法——不写清就会两边混用出隐性 bug。同理 `zod` 用于前端体验校验，
但**跨进程契约的唯一校验权威在 Python 侧**（pydantic v2）。

**前端地图**：目录职责、命令、mock 与生成物边界、状态归属约束见 `ui/README.md`；
本文只定归属与物化节奏，不复述实现细节。

---

## 8. `tests/` 与 `evals/`

| 目录 | 内容 | 现状 |
| --- | --- | --- |
| `tests/unit/` | 纯逻辑；先枚举失败方式再写实现；`conftest.py` 提供 fake home/provider/git | 1 文件（配置一致性护栏） |
| `tests/contract/` | 所有引擎跑同一套行为契约（参数化：内置 + 各适配器） | 未建（M1） |
| `tests/integration/` | 协议往返、会话恢复、diff 与修订号绑定、审批不能提权 | 仅 README |
| `tests/architecture/` | §5 import 矩阵 + 三条硬断言 | 仅 README |
| `tests/adversarial/` | **只增不减**；坑目录 `B-NN` 每条至少一个用例 | 仅 README |
| `tests/e2e/` | 三柱整链：转后台 → 任务总结 → 打回 → 重做 → diff 可回看 | 未建（M4） |
| `tests/fixtures/` | 字节级固定样本；行尾由 `.gitattributes` 钉死；**禁含真实会话、prompt 全文、真实绝对路径** | 未建（M1） |

`evals/`：`tasks/`（参照任务集，**必须覆盖三柱**，不只测编码）、`runner/`、`results/` + `result.schema.json` + `README.md`（布局照 wuu `evals/`）。
基线只取可运行参照：**FlowCoder 为主**，EvoFlow 按任务类型可选；**wuu 不作基线**（Go 工具链与引擎依赖使评测脚手架成本高于收益；桌面预览仅 macOS——可运行性详述见 overview §2）。

---

## 9. `scripts/` 与 CI

`scripts/` 分类参照 EvoFlow，**只放工具，不放业务逻辑**（禁 `utils/` 兜底目录的延伸）：

```
scripts/
├── ci/          # 门禁辅助：check-evals、check-test-policy、check-docs（对应 just 任务）
├── gen/         # schema→TS 生成、THIRD-PARTY-NOTICES 生成、VERSION 同步
├── docs/        # 文档链接与放置策略检查
├── release/     # 版本号推进、产物校验
└── windows/     # Windows 专属开发脚本（PowerShell，仍按 .gitattributes 用 LF）
```

`.github/workflows/` 按能力拆分（wuu 有 9 个，本项目起步 6 个）：

| workflow | 内容 | 建立时机 |
| --- | --- | --- |
| `ci.yml` | 四条门禁 + import 矩阵 + pre-commit 同源命令 | M1 |
| `contracts.yml` | schema 重新生成后无 diff；契约测试全引擎 | M1 |
| `desktop.yml` | 前端 eslint / tsc --noEmit / vitest / Web 静态构建 / Tauri 构建；并跑一次"网页宿主仅 localhost 伺服"的冒烟 | M3 |
| `evals.yml` | 对照评测跑批并上传结果记录（不阻塞合入，阻塞里程碑出口） | M2 |
| `docs.yml` | 文档策略 + 链接 + 站点构建 | M2 |
| `release.yml` | 版本校验、产物、CHANGELOG 校验、发布 | 首次发布前 |
| `security.yml` | 依赖审计（pip-audit/npm）、secret 扫描 | M1 |

另：`dependabot.yml`（pip、npm、cargo、github-actions 四类）、`ISSUE_TEMPLATE/`×2、
`PULL_REQUEST_TEMPLATE.md`（必须列门禁命令与实际输出——与 `AGENTS.md` 收尾自检同一套）。

---

## 10. 根文件（治理与合规必备）

| 文件 | 用途 | wuu/EvoFlow 依据 | 时机 |
| --- | --- | --- | --- |
| `pyproject.toml` `uv.lock` | 单点配置与锁定依赖 | 三者皆有 | 已有 |
| `justfile` | 门禁单一入口（`just check/test/gen/build`），CI 调同一批命令 | wuu `Makefile`、EvoFlow `Makefile` | M1 |
| `VERSION` | 版本唯一来源（CalVer `YYYY.M.D`；`pyproject` 用 dynamic 读它） | wuu `VERSION` + `make version-sync` | M2 |
| `LICENSE` `NOTICE` | MIT + 上游设计参考与第三方声明 | wuu `LICENSE`；EvoFlow `NOTICE` | 已有 LICENSE |
| `third_party/licenses/` | 生成式第三方声明（`just gen notices`） | wuu `third_party/licenses/`、EvoFlow `licenses/` | M2 |
| `SECURITY.md` | 漏洞披露路径，必须早于第一个 bug report | wuu / EvoFlow / FlowCoder 皆有 | M1 |
| `CODE_OF_CONDUCT.md` `CONTRIBUTING.md` `CHANGELOG.md` | 社区三件套（Keep a Changelog 格式） | wuu 全有 | M2–首次发布 |
| `.editorconfig` `.pre-commit-config.yaml` | 与 CI 同源的风格与钩子 | FlowCoder 有 pre-commit | M1 |
| `.env.example` `config.example.toml` | 配置样例（密钥只在环境，不进仓库） | EvoFlow `.env.example`、`config.example.yaml` | M2 |
| `.gitattributes` `.gitignore` `.python-version` `.dockerignore` | 行尾/忽略/解释器/镜像上下文 | wuu `.dockerignore`；EvoFlow `.gitattributes` | 已有（缺 `.dockerignore`，M8 补） |
| `README.md`（英文） | 对外定位；中文版在稳定后追加（wuu 有 `README_zh.md`） | wuu 双语 | 已有 |
| `SUPPORT.md` `AUTHORS.md` `CLA.md` `MAINTAINERS.md` | 有外部贡献者时再建 | EvoFlow 全有 | 远期 |

---

## 11. 当前实际状态（不美化）

仓库现有：**治理与文档基线**（pyproject/uv.lock/LICENSE/README/AGENTS/SECURITY、
docs/{README,adr×2,architecture×3,specs×13,plans×1}）+ **M1 物化**（justfile、
.editorconfig、.pre-commit-config.yaml、.github/{3 workflows,模板,dependabot}、
src/questor/{schemas,testenv}、tests/{contract?—暂缺,fixtures—暂缺,architecture,
integration,adversarial,unit}、scripts/ci、ui/ 骨架、evals/ 骨架）。
`tests/contract` 与 `tests/fixtures` 随 M2 首批引擎契约测试物化。

**物化节奏与例外**：目录随首个任务创建，结构文档描述目标、文件系统只长真实内容；
**唯一例外是测试套件目录可先带 README 占位**（写明用途与"收集 0 条属预期、不作门禁依据"），
因为套件的存在本身就是规则。

| 里程碑 | 新增 |
| --- | --- |
| M1 | `docs/specs/`（三资产）、`src/questor/schemas/`、`src/questor/testenv/`、`justfile`、`.editorconfig`、`.pre-commit-config.yaml`、`SECURITY.md`、`.github/`（workflows 3 个 + 模板 + dependabot）、`tests/{contract,fixtures}`、`scripts/{ci,gen}`、`evals/` 骨架、`ui/` 骨架（design token + schema 生成类型 + mock 协议服务；面板实体仍 M3） |
| M2 | `cli` `serve(雏形)` `engine` `tools` `limen` `context` `gesta` `providers` `prompts` `config` `state` `secrets` `capability` `workspaces` `version`、`VERSION`、`third_party/`、`tests/e2e` 前置的 `evals/runner` |
| M3 | `review` `worktree` `habena` `sessiontrace`、`ui/` 面板与视图注册表、WS 传输与 `serve http` 子命令（`starlette` + `uvicorn`，ADR-0022）；`contracts.yml` 契约护栏升级到方法族匹配。**`desktop/src-tauri/` + `assets/` + `desktop.yml` 推 M4/M5**（ADR-0024）；SSE 推 M8（ADR-0023） |
| M4 | `vigilia` `orchestration`（含编排 store/状态机/门）`evidence` 最小版、`tests/e2e/`、`docs.yml`、`serve` 编排方法族 + `ui/` 看板面板（ADR-0025/0026/0027/0028）。**看板 DAG 图推 E1；桌面壳推 M5**（ADR-0024 M4 收口） |
| M5 | `evidence` 完整、`evals/` 三柱任务集扩充 |
| M6 | `engine/adapters`（ACP / Claude / Codex） |
| M7 | `skills` `mcp` `hooks` `extensions`、`plugins/`、`examples/`、`packages/`（仅在有第二使用者时） |
| M8 | `containers/`、`deploy/web/`（自托管网页）、`clients/`（仅真异质端）、`release.yml` 首次发布链路；网页对外暴露需先过鉴权 ADR |
