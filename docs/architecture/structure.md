# Questor 项目结构（structure）

版本: v0.2 | 更新: 2026-10-11 | 状态: 待用户评审
关联: `overview.md`（分层、职责登记、依赖规则的来源）、`AGENTS.md` §二 §四、
`docs/adr/0001`（命名）、`docs/adr/0007`（Windows 沙箱）

本文回答"代码放在哪、每个部分内部怎么分块、目录如何长出来"，颗粒度到**目录/职责块**。
文件级布局不在此定义——按 `AGENTS.md` §七"文档视距"，随各模块首个任务确定。

**权责划分（避免两份文档互相指）**：
- `overview.md` 管**语义与约束**：三柱、分层、依赖方向规则 R1–R5、模块职责登记（§6）、契约（§7 §8）。
- 本文管**物理布局**：仓库目录树、模块内分块、物化节奏、门禁入口。
- 冲突时按此分工裁决；任一方越界描述了另一方的内容，评审直接打回并修正越界方。

---

## 1. 参照与取舍

| 参照 | 借鉴点 | 不取的部分 |
| --- | --- | --- |
| **wuu**（Go） | `cmd/` 多入口 + `internal/` 按域分包 + `packages/` 公共契约的"薄入口、厚内核"切法；`evals/` 独立于 tests 的三件套布局（cases / results / result.schema.json）；`third_party/licenses` 与 `SECURITY.md` 的归置 | 多语言多顶层（`clients/` `docs-site/` `landing/` `containers/` 等）——本项目 M8 之前不需要 |
| **EvoFlow** | Python 内核与桌面壳**物理分离**（`backend/` 与 `evopanel/` 各为顶层）；壳内 `src/` + `src-tauri/` 分区 | 50 个顶层包的扁平规模；`app/` 与 `packages/harness/` 的双向依赖违规债 |
| **FlowCoder** | **单包 `src/<pkg>` 承载全部 Python 代码**、GUI 独立顶层（它的 `web/`）、`tests` 分层 | GUI 不用 Tauri（本项目要 sidecar 与原生窗口，选 Tauri） |
| 大型开源 Python 惯例 | src layout、pyproject 单点配置、tests 镜像分层、`docs/`（adr + specs + architecture）、`.github/workflows` | — |

由此定型：Python 侧**单包**（依赖方向由 §3 机械强制，不按层嵌套目录）；契约与提示词**随包发布**；
桌面壳独立顶层；对照评测独立于 tests；运行时状态不在仓库内（§8）。

---

## 2. 总体结构（目录级）

```
questor/
├── src/questor/                # 唯一 Python 包：执行核 + 能力服务 + 入口
│   ├── engine/                 # 自研循环、turn 生命周期、事件流、引擎契约与注册表
│   ├── tools/                  # 工具登记、schema、执行与结果封装
│   ├── limen/                  # 唯一权威权限门（三档、可达性推导、敏感路径守卫）
│   ├── review/                 # 工作区修订号、真实 diff、turn↔revision 绑定
│   ├── gesta/                  # 会话记录（append-only JSONL）与验收导出
│   ├── habena/                 # 插话收件箱、排队、接管与暂停、取消传播
│   ├── vigilia/                # 值守长跑、调度、唤醒检查点、僵尸运行清扫
│   ├── evidence/               # 声称的检查 vs 当时真实输出、验收证据出口
│   ├── orchestration/          # Plan / Goal / 看板 / 验收与打回
│   ├── providers/              # 模型客户端、用量、能力声明
│   ├── prompts/                # 运行时提示词与指令资产（随包发布，禁止内联在代码里）
│   ├── schemas/                # 协议与数据契约 schema（真相源，§5）
│   ├── serve/                  # 网关：REST + SSE/WS + qst-app-server 会话层
│   ├── cli/                    # 命令行入口（questor，别名 qst）
│   └── extensions/             # M7：插件宿主；mcp/ skills/ hooks/ code_index/ 为其下的能力包
├── desktop/                    # M3：Tauri 桌面壳（前端 TS + Rust 壳），与 Python 包物理分离
│   ├── src/                    # React/TS：panels / conversation / state / rpc(含生成类型) / design
│   └── src-tauri/              # Rust：窗口、sidecar 生命周期、原生命令
├── evals/                      # 对照评测（独立于 tests）：tasks/ runner/ results/ result.schema.json
├── tests/                      # unit / contract / integration / architecture / adversarial / e2e（§7）
├── docs/                       # architecture / adr / specs
├── scripts/                    # 开发与打包脚本入口；**不放业务逻辑**
├── .github/workflows/          # CI：与本地门禁同一套命令（§2.2）
├── pyproject.toml              # 单点配置
├── justfile                    # 门禁与常用任务的单一入口（§2.2）
├── AGENTS.md  README.md  LICENSE  SECURITY.md
└── .gitattributes  .gitignore  .python-version  uv.lock
```

根目录待建：`SECURITY.md` 在首个公开可用版本前建立（漏洞披露路径必须在有人提交 bug 之前存在）；
`CHANGELOG.md` 随首次发布建立；`CONTRIBUTING.md` 在首个外部贡献者出现前由 `AGENTS.md` 承担其职责。
命名纪律（ADR-0001）：品牌展示体 **Questor**；一切技术标识符小写 **questor**。

### 2.2 门禁的单一入口

四条门禁命令（`AGENTS.md` §四）必须有**一个跨平台入口**，否则本地与 CI 会各跑一套参数：

- 采用 `justfile`（单文件、Windows 有独立二进制、无需 make 兼容层），
  任务为 `just check` / `just test` / `just gen` / `just build`。
- **退路**：若不接受引入 `just` 二进制，改用 `noxfile.py`（Python 内自管 venv，代价是多一个 dev 依赖）。
- **CI 与 `justfile` 必须调用同一批命令**，且 CI 里禁止出现本地没有的步骤；两者不一致视为缺陷。
- 落地时机：M1（与 `docs/specs/`、`schemas/` 同期）。

---

## 3. 依赖方向如何被机械强制（R1 的可执行版本）

R1"内核不得依赖网关与壳"在**同一个 Python 包内**不再由包边界保证，必须由检查器保证。

- 工具：**`import-linter`**（声明式 contract，能在 CI 里给出违规清单）；
  若它与 uv/pyproject 组合受阻，退到自写 AST 遍历，放 `tests/architecture/`。
- 检查粒度：模块级 import 方向；违反即 CI 红，**不接受注释豁免**。
- 与 EvoFlow 的教训对齐：它用"baseline 文件 + 只准变短"来冻结历史违规；
  本项目**新仓库无历史债，直接要求 0 违规**，不留 baseline。

**允许的 import 矩阵**（行＝被检查模块，列＝可 import 的目标；未列出的一律禁止）

| 模块 | 允许 import |
| --- | --- |
| `limen` | 标准库、`schemas`（类型），**其余全部禁止**（它是最底层权威） |
| `tools` | `limen` `schemas` `prompts` |
| `gesta` | `schemas` `providers`（仅类型与用量结构） |
| `engine` | `tools` `limen` `gesta` `providers` `schemas` `prompts` |
| `review` | `limen` `schemas` |
| `habena` | `engine` `gesta` `schemas` |
| `vigilia` | `engine` `gesta` `schemas` |
| `evidence` | `review` `tools` `schemas` |
| `orchestration` | `engine` `vigilia` `gesta` `schemas` `prompts` |
| `providers` | `schemas`（**不得 import 任何业务模块**） |
| `prompts` | 无（纯资产 + 装载器） |
| `serve` | 以上全部（它是最上层组装点） |
| `cli` | `serve` `engine` `providers` `schemas` |
| `extensions` | `schemas` + 已注册的公开扩展接口，不得被内核反向 import |

三条硬断言同时进 `tests/architecture/`：**append-only 不可改写**、**状态迁移唯一写入入口**、
**权限判定唯一入口（无绕过 `limen` 的路径）**。

---

## 4. `src/questor/` 各部分结构

子目录名在模块开工时可调整，**职责不得超出 overview §6 的登记**。下表"内部分块"是职责块，非文件清单。

| 模块 | 内部分块 | 备注 |
| --- | --- | --- |
| `engine/` | `contract/`（引擎 Protocol、注册表、权限映射入口）/ `builtin/`（循环：turn 生命周期、事件流、止损三重）/ `adapters/`（claude / codex / acp，M6） | 适配器只做转发与映射，不做二次裁决（R2/R3）；契约形状参照 `wuu internal/agentengine` |
| `tools/` | `registry/` / `builtin/`（read、edit、write、search、list、run、process、todo）/ `results/`（截断、后台移交、脱敏） | 输出规则（stdout→stderr、只在改变下一步时追加、头尾保留、剥 ANSI）照 overview §5 与行为规格实现 |
| `limen/` | `gates/`（三档、可达性推导）/ `sensitive/`（敏感路径守卫，**三档全开**）/ `approval/`（只能收紧的审批接口） | 唯一入口；Windows 档位内容＝路径门 + Job Object 进程树 + 敏感守卫，**界面不得出现"已沙箱化"**（ADR-0007） |
| `review/` | `revision/` / `diff/`（git CLI 封装、逐文件真实 diff） | 修订号语义见 overview §7 |
| `gesta/` | `writer/`（JSONL 唯一真相源）/ `index/`（可丢弃可重建索引）/ `export/` | 正文永不改写；索引坏了重建 |
| `habena/` | `inbox/` / `takeover/` / `cancel/` | 接管即停的语义要能在 e2e 里断言 |
| `vigilia/` | `scheduler/` / `checkpoints/` / `sweeper/` | 自建状态机清扫，**不依赖任何框架的 runs API**（EvoFlow 的教训） |
| `evidence/` | `reconcile/`（声称 vs 实测并排核对）/ `export/` | 本轮不做沙箱复跑与纵向统计（overview §2 排除说明） |
| `orchestration/` | `plan/` / `goal/` / `board/` / `acceptance/` | 验收状态机见 overview §7 |
| `providers/` | `clients/` / `usage/` / `capabilities/` | 新增供应商依赖须先落 ADR |
| `prompts/` | 按用途分块（系统提示、工具说明、审批评审、压缩指令）；**正文与代码分离** | 目的：可审计、可分语言、可归因"改了哪条提示词导致行为变化" |
| `serve/` | `api/` / `stream/` / `proto/`（qst-app-server，绑定 `schemas/`） | stdout 纪律见 overview §8（禁 banner 与调试日志） |
| `cli/` | 命令解析、`exec`/`resume`/`fork`/`session` 子命令、JSONL 输出 | 入口声明随首个 CLI 任务启用（pyproject 已预留注释） |
| `extensions/` | `host/`（插件生命周期：安装/批准/启停/safe mode）+ `mcp/` `skills/` `hooks/` `code_index/` | **内核不得反向 import `extensions`**；关插件即停产品行为 |

---

## 5. 契约真相源与代码生成

**位置决定**：契约放 **`src/questor/schemas/`**（随包发布、与代码同一版本、运行时可直接用于校验）。
顶层 `schemas/` 被否决——它要么靠 hatchling `force-include` 塞进 wheel（多一层脆弱配置），
要么与代码不同版本（校验时用的 schema 和运行代码不是同一份，正是最难查的 bug）。

- `src/questor/schemas/app_server/`：qst-app-server 协议方法与事件 schema；
- `src/questor/schemas/model/`：核心数据契约（Workspace / Thread / Turn / Run / Item / Event）；
- 生成物输出到 `desktop/src/rpc/generated/`，**禁止手写 DTO**（R4）；
- **生成必须可校验**：`just gen` 重新生成后 `git diff --exit-code` 必须为空，CI 跑同一断言；
  否则"手写 DTO"会静默发生（wuu 用 `make generate-theme-surface-matrix` + 生成物检查处理同一问题）。
- 版本不匹配直接拒绝执行，不做降级兼容（overview §8）。
- schema 必须是**纯 JSON Schema**（可被 TS／其他语言直接消费）：Python 专有表达式不得写进
  schema，pydantic 只做绑定——这是"拆包与多端集成"的逃生门（overview §14）。

---

## 6. `desktop/`

| 分块 | 职责 |
| --- | --- |
| `src/panels/` | Review（逐文件真实 diff）、Files（预览与"只改这一段"）、Terminal；**Browser 面板延后**（决定见 overview §4，完整理由待补 `ADR-0006`） |
| `src/conversation/` | 会话流、插话与排队、分叉、侧聊、选中引用与批注 |
| `src/state/` | 会话列表、工作区与面板状态 |
| `src/rpc/` | 协议客户端 + §5 生成的类型 |
| `src/design/` | 设计 token 与风格基座（参照 evopanel 的组件与样式体系） |
| `src-tauri/` | 窗口、`questor` sidecar 生命周期、原生命令 |

**无私有端点约束**：面板能做的每一件事都必须经 `qst-app-server` 协议可达；
禁止存在"只有桌面壳能调"的隐藏接口（overview §14）——这是将来换壳与做远控的逃生门。

**技术栈与现成件**（evopanel 实测在用，可直接照其选型，省掉 M3 的重新选型）：
React 19 + TS + Vite 6 + Tailwind 4 + **zustand** + SWR；
`@xterm/xterm`（+ `node-pty` 侧支持）→ Terminal 面板；
`@pierre/diffs` → Review diff 渲染；`@xyflow/react` → DAG 看板；
`@tauri-apps/plugin-shell` → sidecar 生命周期；`streamdown` / `shiki` / `pdfjs-dist` / `lexical` → 流式 Markdown、代码高亮、PDF、编辑器。

**版本纪律**：evopanel 用的是 **zustand v4**（`^4.5.7`）。本项目**显式选 v5 并只用官方 hook 用法**，
因为参照它的代码是 v4 写法——不写清就会两边混用出隐性 bug。同理 `zod` 用于前端校验，
但**跨进程契约的唯一校验权威在 Python 侧**（pydantic v2），前端 zod 只做输入体验，不作真相判定。

---

## 7. `tests/` 与 `evals/`

六个目录对应 overview §11 的六类测试：

| 目录 | 内容 | 现状（2026-10-11 如实记录） |
| --- | --- | --- |
| `tests/unit/` | 纯逻辑；**先枚举失败方式再写实现** | 1 个文件（配置一致性护栏） |
| `tests/contract/` | **所有引擎跑同一套行为契约测试**（参数化：内置 + 各适配器） | 未建（M1） |
| `tests/integration/` | 协议往返、会话恢复、diff 与修订号绑定、审批不能提权 | 仅 README |
| `tests/architecture/` | §3 的 import 矩阵 + 三条硬断言 | 仅 README |
| `tests/adversarial/` | **只增不减**；靠改用例变绿视为作弊 | 仅 README |
| `tests/e2e/` | 三柱整链：转后台 → 任务总结 → 打回 → 重做 → diff 可回看 | 未建（M4） |

`tests/fixtures/`：字节级固定样本（JSONL 转录、golden 文件），行尾与编码由 `.gitattributes` 钉死，
且**不得含真实会话、prompt 全文或真实绝对路径**（AGENTS 红线①）。

`evals/`（对照评测，独立于 tests）：`tasks/`（参照任务集）、`runner/`（跑批）、
`results/` + `result.schema.json`（结果记录），布局参照 wuu `evals/`。

**出口判据（overview §11）的基线只取可运行的参照**：**FlowCoder 为主基线**（同任务集、同模型、
同预算），EvoFlow 按任务类型可选。**wuu 不作基线**——它在本机跑不起来（overview §2），
只作规格来源；把跑不起来的东西写进判据会让出口条件变成无法执行的承诺。

---

## 8. 运行时状态目录（不在仓库内）

```
~/.questor/
├── sessions/<thread-id>/    # append-only JSONL 正文、input-attachments/、input-images/（带过期）
├── index/                   # 可重建搜索索引（删掉不丢数据）
├── config.toml              # 用户配置（provider、模型、默认档位）
├── credentials.json         # 受敏感路径守卫保护，直读直写一律拒绝
└── logs/                    # 带 trace_id，脱敏后落盘
```

路径一律经单点解析器取得，**禁止在业务代码里散写 `~/.questor` 字面量**（overview §14）。
`WUU_HOME` 式的环境变量覆盖为 `QUESTOR_HOME`（开发用独立目录，避免污染已安装版本的数据）。
过期与清理语义见 overview §10：**清理只动工作文件，不动历史快照与工作区内文件**。
测试里全部路径必须走 fake 目录，禁止触达真实 `~/.questor`。

---

## 9. `docs/`

| 目录 | 内容 |
| --- | --- |
| `docs/architecture/` | `overview.md`（语义与约束的唯一入口）+ `structure.md`（本文，物理布局） |
| `docs/adr/` | 决策记录，编号索引 `docs/adr/README.md` |
| `docs/specs/` | M1 扫描三资产：`behavior-*.md` / `pitfalls.md` / `cases-*.md`；另含提示词结构规范 |

---

## 10. 目录物化节奏（随里程碑，不预建空目录）

| 里程碑 | 新增目录 |
| --- | --- |
| M1 | `docs/specs/`、`src/questor/schemas/`、`justfile`、`tests/contract/`、`tests/architecture/` 首批用例 |
| M2 | `src/questor/{engine/builtin,tools,limen,gesta,prompts,cli}`、`evals/{tasks,runner,results}` 骨架 |
| M3 | `src/questor/{review,habena,serve}`、`desktop/{src,src-tauri}`、`desktop/src/rpc/generated/` |
| M4 | `src/questor/{vigilia,orchestration}`、`tests/e2e/` |
| M5 | `src/questor/evidence/` |
| M6 | `src/questor/engine/adapters/` |
| M7 | `src/questor/extensions/{host,mcp,skills,hooks,code_index}`（先按 R5 在 overview §6 补登记） |
| M8 | 执行环境、渠道等 L4（各自 feature flag 默认关）；若做多端遥控再考虑 `clients/` |

原则：目录随首个任务创建，**结构文档描述目标布局，文件系统只长真实内容**。

**唯一例外**：测试套件的目录可以先带 README 占位（写明该套件的用途，以及
"用例建立前收集 0 条属预期、不作门禁依据"），因为套件的**存在本身就是规则**（对抗只增不减、
架构检查必须跑）。其余目录（`schemas/`、`desktop/`、`evals/` 等）一律不预建。
