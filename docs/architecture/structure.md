# Questor 项目结构（structure）

版本: v1.0（母本对齐重写：wuu 单锚、ADR-0037/0038/0040/0041/0042/0043/0044/0045）| 更新: 2026-10-14 | 状态: 待用户评审
关联: `overview.md`（语义/分层/R1–R5/职责登记）、`AGENTS.md` §〇§二§三、`docs/adr/0037~0045`、`docs/research/phase0-wuu-*.md`（目标态事实源）、`docs/research/port-ledger.md`（逐文件源映射）

## 本文的定位（先读这段，避免被过度约束）

- **只定边界，不焊死内部**：本文冻结「顶层目录 / 模块清单 / import 方向 / 契约真相源 / 物化波次」；**每个模块内部怎么切文件、私有结构长什么样，移植时由执行者按 wuu 蓝本自定**（AGENTS §一「偏离许可」）。
- **可扩展优先**：新增工具 / provider / 模块走「R5 登记 + 注册表接入」，**不改动既有 import 行、不碰核心**。§1.7 的 6 条接缝是"必须保住的可扩展点"，本文对其落点做索引。
- **这是目标态，不是现状**：带波次标记的目录随该波首个任务物化，**不预先建空目录**。当前实际状态见 §10。
- 参照系 = **wuu（母本）**，结构惯例参照 **EvoFlow** 的治理外围与 src 单包布局；语义层参照标准 Python `src layout` + 大型开源项目惯例。

---

## 1. 顶层结构（目标态）

```
questor/
├── src/questor/                 # 唯一 Python 包（标准 src layout + py.typed）
│   ├── engine/                  #   手写循环 + agentengine 薄契约 + 事件流（来源 wuu agentengine/loop/）
│   ├── tools/                   #   工具注册/schema/执行/结果封装/boundary 门（wuu internal/tools）
│   ├── limen/                   #   唯一权威权限门（wuu boundary/sensitive_paths）
│   ├── context/                 #   上下文预算 + 摘要/换窗压缩（wuu compact/contextbudget）
│   ├── review/                  #   工作区修订号 + tool-time diff（壳侧另有 GitService，见 ADR-0045）
│   ├── gesta/                   #   会话权威库（SQLite，ADR-0041）+ append-only + 验收导出（wuu session）
│   ├── habena/                  #   插话/排队/接管暂停/取消传播（wuu held_user_work + activity）
│   ├── providers/             #   模型客户端/流式/韧性（wuu internal/providers；MVP 收敛 1–2 家）
│   ├── serve/                  #   app-server 协议层：stdio JSONL 分发 + initialize（词表照 wuu，ADR-0042）
│   ├── cli/                    #   命令行入口 questor/qst（含 app-server 子命令）
│   ├── schemas/                #   协议与数据契约 schema（真相源，纯 JSON Schema，§5）
│   ├── state/ secrets/ config/ #   路径单点/原子写/锁 + 凭据(wincred/DPAPI) + 类型化配置
│   ├── workspaces/ worktree/   #   工作区注册 + Git worktree 分叉可见
│   ├── sessiontrace/ capability/ version/ prompts/  # 最小 trace / feature flag / 版本单点 / 提示词资产
│   ├── orchestration/ vigilia/ evidence/  # 【Phase 6 后置】长任务/编排/验收，A 阶段不建（ADR-0043）
│   ├── testenv/                #   测试基建（fake home/provider/git），不进生产
│   └── py.typed
│   # 【远期·留缝不建】skills/ mcp/ hooks/ extensions/：§1.7 保 seam，命中第二使用者再立
├── desktop/                    # Electron 壳（照 wuu 形态，ADR-0040）
│   ├── src/main/               #   主进程：spawn 冻结 Python sidecar(stdio)、反向 RPC 路由、GitService(壳侧 diff)、node-pty 终端、browser CDP、childShutdown
│   ├── src/preload/            #   contextBridge
│   ├── src/renderer/           #   React 19 渲染层（照 wuu renderer 重搭：会话/对话流/Review/终端/浏览器/worktree）
│   ├── src/shared/            #   协议类型 re-export（引 packages/protocol 生成物）
│   └── electron.vite.config.ts  electron-builder 配置（NSIS 打包 exe）
├── packages/protocol/          # 由 Python schemas 生成的 TS 契约（弥补 wuu 无代码生成，ADR-0040）
├── clients/core/               # 传输无关的共享 app-server 客户端；web 宿主后期复用 renderer（wuu mobile-web 模式）
├── tests/                      # §7：unit/contract/integration/architecture/adversarial/e2e/fixtures
├── evals/                      # tasks/ runner/ results/ result.schema.json（照 wuu；基线见 §8）
├── scripts/                    # ci/ gen/ docs/ release/ windows（只工具，不放业务逻辑）
├── docs/                       # architecture/ adr/ specs/ plans/ research/ proposals/
├── assets/ third_party/        # 图标源；THIRD-PARTY-NOTICES（wuu MIT 署名，ADR-0037）
├── .github/                    # workflows(ci/contracts/desktop/evals/docs/security/release) + 模板 + dependabot(pip/npm/github-actions)
├── pyproject.toml uv.lock justfile VERSION .python-version .editorconfig .pre-commit-config.yaml
├── .gitattributes .gitignore .env.example config.example.toml
└── README CHANGELOG CONTRIBUTING SECURITY CODE_OF_CONDUCT LICENSE NOTICE  # LICENSE=MIT；NOTICE 列 wuu 上游 + 第三方
```

**明确不进目标态**（wuu/Evo 有、Questor「不做」，§1.7 已登记为决定，非遗漏）：`remote/`、`plugin`/`pluginhost`、`examples/plugins`、`containers`（Docker 默认执行）、`deploy/remote`、多用户 auth。

---

## 2. 模块清单 ↔ wuu/EvoFlow 源 ↔ 波次（port-ledger 骨架）

> 只到模块级；逐文件映射在 `docs/research/port-ledger.md`。新增模块先 `overview §6` 登记职责（R5）再建目录。

| questor 模块 | 职责 | 母本源（wuu 为主） | 波次 |
| --- | --- | --- | --- |
| `engine` | 手写循环/turn 生命周期/事件流/引擎薄契约 | `agentengine`、`agent/loop.go`、`step.go`、`tool_runtime.go`（**不搬 `loopdriver`/多引擎宿主**） | P2 |
| `tools` | 工具注册/schema/执行/boundary | `internal/tools`(18 工具子集)、`toolresult`、`toolledger` | P2/P3 |
| `limen` | 唯一权限门（三档/可达性/敏感/收紧审批） | `boundary.go`、`authorization.go`、`sensitive_paths.go` | P2 |
| `context` | 预算 + 摘要 + 换窗压缩 | `compact`、`contextbudget`、`adaptive_compact`、`fresh_context` | P2/P3 |
| `review` | 工作区修订号 + tool-time diff | `tools/diff.go`（盘态真相在 `desktop` GitService，ADR-0045） | P2/P3 |
| `gesta` | 会话 SQLite 权威库 + append-only | `internal/session`（表清单见 phase0-wuu-sqlite-schema.md） | P1/P2 |
| `habena` | 插话/接管/取消传播 | `inbox.go`、`held_user_work.go`、`activity` | P2/P3 |
| `providers` | 模型客户端/流式/韧性 | `internal/providers`（MVP anthropic+openai） | P1/P2 |
| `serve` | app-server stdio 分发 | `internal/appserver`（词表照 wuu，单一方法表） | P1/P2 |
| `cli` | 入口 | `cmd/wuu` | P1/P2 |
| `schemas` | 契约真相源（纯 JSON Schema） | `packages/protocol` 形状 | P1 |
| `state` `secrets` `config` `workspaces` `worktree` `sessiontrace` `capability` `version` `prompts` | 基建 | `statepath`/`securefs`/`storelock`、`credentialstore`/`authstorage`、`config`、`worktree`、`instructions` 等 | P1–P4 |
| `orchestration` `vigilia` `evidence` | 长任务/编排/验收 | EvoFlow `collab`/`tool_approval`/`reconcile`（读设计、围自研 run 重写） | **P6** |

---

## 3. 依赖方向（import 矩阵）——只定方向，不定内部

用 **import-linter**（或 `tests/architecture/` AST 遍历）机械强制，**0 违规起步、不设 baseline**（对照 EvoFlow 60 条债）。矩阵**只约束「谁能 import 谁」**；模块内部文件结构自由。

顶层规则（R1/R5）：
- `schemas`/`version` = 叶，无业务依赖；`providers` 只取 `schemas`（不 import 业务）。
- `limen` = 只依赖标准库 + `schemas`（权限判定唯一入口，不可被绕过，AGENTS 铁律）。
- `serve` 是最上层组装点，可 import 除 `cli` 外全部；`cli`→`serve` 单向（不得反向成环）。
- **横切不变量**（护栏必附负向验证）：append-only 不可改写、状态迁移唯一写入入口、权限无绕过路径、协议方法表单一来源（B-119/B-121）。
- **禁复用旧码边**（ADR-0044/§12-E）：新 `src/questor/*` 不得 import 任何 reference-only 归档模块；由矩阵 + AST 护栏挡。
- **6 条可扩展接缝**（§1.7）的落点：`engine`(agentengine 契约)、`tools`(注册表+Surface+ToolExposure)、`serve`(传输无关协议)、`schemas`(加性演进 ADR-0028)、`limen`(ToolKind 枚举)、`gesta`(run/turn/item 数据形状)。新增能力接进这些点，不改动其它行。

（细化到每模块的允许集在实现时填 `port-ledger`，本文只立上述顶层规则，避免过早焊死。）

---

## 4. 契约真相源与生成链（§1.5 接缝的落点）

- 契约真相源 = `src/questor/schemas/`（随包发布、与代码同版本、运行时可校验）。`schemas/app_server/`（app-server 方法/事件，词表照 wuu ADR-0042）、`schemas/model/`（Run⊃Turn/Item/Event，SQLite 权威 ADR-0041）、`schemas/orchestration/`（Phase 6）。
- schema 必须**纯 JSON Schema**（Python 专有表达式不进）；pydantic v2 只做跨边界数据绑定，禁裸 dict。
- 生成链：`schemas/` → `packages/protocol`（TS）→ `desktop/src/shared`；`just gen` 后 `git diff --exit-code` 必须为空（R4 可检查形式，CI 跑同一断言）。这是**对 wuu「协议无代码生成、两份人工漂移」缺陷的修正**。
- **单一来源纪律**：`protocol.md` ↔ `schemas/` ↔ handler 注册表 ↔ `phase0-wuu-protocol-table.md` 四处同源，护栏解析。

---

## 5. 前端与宿主（照 wuu 形态，ADR-0040）

- **渲染层住 `desktop/src/renderer/`，无独立 `ui/`**；`clients/core` 传输无关共享；契约在 `packages/protocol`（生成）。
- **一套 app-server 协议、两种传输**：桌面 stdio JSONL（A 阶段）；网页后期按 wuu mobile-web「同 renderer 换传输」评估（不预建 web 端）。会话/运行/权限真相**永不镜像进前端**（前端只存 UI-local）。
- 依赖选型回到 **wuu 实测集**（Monaco diff/编辑器、@xterm 终端、react-markdown、@pierre/trees 文件树、lucide 图标）；撤销旧 `ui/` 的 zustand/@pierre/diffs/@xyflow/shiki（ADR-0031/0032 随之重裁）。
- lockfile：`desktop/` 一份、`clients/`（若建）各一份，**同一 package 内不双锁**（wuu 双锁漂移不复制）。
- 界面/动效/主题照 wuu（Tailwind v4 `@theme`、`prefers-reduced-motion`）；保真度沿 P2→3→4 逐波贴近（每波对照 `phase0-wuu-renderer-assembly.md`）。

---

## 6. 入口

| 入口 | 命令 | 母本 | 波次 |
| --- | --- | --- | --- |
| 主 CLI | `questor`/`qst`（`exec`/`resume`/`fork`/`app-server`/`version`） | `cmd/wuu` | P1/P2 |
| 协议服务 | `questor app-server`（NDJSON over stdio，64MiB 帧） | `cmd/wuu app-server` | P1 |
| 桌面壳 | `desktop/`（Electron `child_process` 起 Python sidecar） | `desktop/` | P2（打包 exe §1.6 门槛） |

---

## 7. 测试目录

`tests/{unit,contract,integration,architecture,adversarial,e2e,fixtures}`。`contract/` = wuu 基准帧回放（§1.5，本机无 Go → 取 wuu 测试 golden + 手写期望）。`adversarial/` 只增不减**对跨实现契约类**（ADR-0044 相容规则），绑定旧实现细节者按 port-ledger 受控作废。fixtures 禁真实会话/绝对路径，行尾 `.gitattributes` 钉 LF。

## 8. evals 与基线

`evals/{tasks,runner,results,result.schema.json}`。**基线考官 = wuu**（同任务同模型比帧序列等价性，AGENTS §五），非旧「wuu 不作基线」口径（C18 已被转向推翻）；FlowCoder 退出参照系（ADR-0038）。

## 9. scripts / CI / 治理

`scripts/{ci,gen,docs,release,windows}` 只放工具。CI 与 `justfile` 同源（门禁四件套 + import 矩阵 + gen-check + notes/specs 核查）。dependabot **pip/npm/github-actions**（无 cargo，随 Tauri 撤下）。根治理件齐（LICENSE=MIT、NOTICE 列 wuu 上游 + 第三方、SECURITY、CONTRIBUTING、CHANGELOG=Keep a Changelog）。

---

## 10. 当前实际状态（不美化）

已完成：Phase 0 扫描产物（`docs/research/phase0-wuu-*`）+ 六扫描归档 + 承重 ADR-0037~0045 + AGENTS.md 复用优先改写 + 5 份 spec 坑号修复 + check_specs 三断言。
待做（本文件之外）：契约三件的 `protocol.md`/`data-model.md` 同步重写（依 ADR-0042/0041）；`phase-a-mvp.md`；旧码从工作树物理移除 + reference-only 存档（Phase 2 入口，需 commit 授权）；import 矩阵实现期细化。
**物化节奏**：目录随该波首个任务创建，不预建空目录；测试目录可先带 README 占位。
