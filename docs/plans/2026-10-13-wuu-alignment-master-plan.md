# Questor 对齐 wuu 全面重构 · 分阶段开发计划

> **母计划（总计划），自 Qoder 计划缓存区归档入库**：原文件 `Questor_对齐_wuu_重构计划_99f1c707.md`（缓存在编辑器可写区之外，入库时正文**逐字未改**），定稿 2026-10-13。仓库内所有「计划 §1.5 机制 N」「§12-A~E」「§13 C0–C21」「§14」级编号引用，出处即本文。
> ⚠️ **本文是计划态快照，不含执行进度**——§13 表里的「ADR 待写 / 待 Phase 0」与 §12-B 的清理清单**均已完成**（C0–C21 全部落定、`ui/` 与旧 `desktop/` 已物理移出、Phase 0/1 已收口）。当前状态与当期开工依据读 [`phase-a-mvp.md`](phase-a-mvp.md) + [`../research/port-ledger.md`](../research/port-ledger.md)；**不得**把本文的「待做」当现状读（违 AGENTS §一 铁律 1）。本文的 §0 全局不变量、§1.5 复刻五机制、§1.6 exe 三门槛、§1.7 扩展缝、§9 母本缺陷台账、§10 已否方案仍是承重条款。

> 版本 v1.0｜基线：本会话 6 份扫描产出（`.scan-wuu-kernel/-frontend/-windows/-evoflow/-questor-docs/-questor-pitfalls.md`）+ 四项架构裁决（用户已拍）。
> 交付优先级铁序：**可用 > 扩展性 > 性能**；规则冲突以此为准。

## 0. 全局不变量（每个 Phase 都适用，不得违反）

- **母本**：wuu（`d:\DEVELOP\My-project\wuu-main`，MIT）。复用动作 = **逐文件把 wuu 已验证逻辑翻译/移植进 Python**，用 wuu 的 563 个测试当验收 oracle；不是"照坑清单从零发明"。EvoFlow 仅在 Phase 6 作长任务/编排**规格来源**（PolyForm：读设计、不搬码）。FlowCoder 退出参照系。
- **循环**：按 wuu `internal/agent/loop.go` + `agentengine.go` 语义**手写 Python 循环，绝不引 LangGraph/LangChain**；语义来源=wuu，实现所有权=本项目。
- **第一平台 Windows**；语言 Python 主流（可少量原生 FFI）。
- **三柱优先级**：可见 → 可干预 → 可验证；透明度恒为最大，分级的是写域。
- **不照搬母本缺陷**（见 §9 缺陷台账）：凡 wuu/Evo 已知问题，移植时显式规避，不得当作"母本如此故我也如此"。
- **禁止复用现有 questor 代码（硬红线）**：转向后的旧内核 / `ui/` / `desktop/` 一律**只可只读参考、提取知识**，不得复制其实现行、不得"改一行接着用"；新代码一律按 wuu 蓝本重写。执行机制见 §12-E（物理移出工作树 + import 护栏 + provenance 只指 wuu）。违反=评审打回。
- **每 Phase 开工前必做扫描**：只读扫 wuu（Phase 6 加扫 EvoFlow）对应子系统，深度由执行者判断，**不许为省事浅扫**；扫后若有必要先写辅助文档（行为规格/移植台账）支撑，再动代码。不可跳过扫描。
- **提示词柔性**：各阶段提示词只锁大方向，允许局部微调；若前期实现造成偏离，仅微调细节，**不动摇阶段核心目标**。
- **优化不打断主链**：开发中发现更优方案但需大规模重构、会干扰当前阶段稳定性 → **优先沿用 wuu/Evo 成熟方案**，把优化方案完整记录存档到 `docs/proposals/`，Phase 6 后主体完成再评估落地。
- **扩展优先但分级**：更利于扩展维护的方案，改动小且不影响后续计划→直接调；改动大→记方案与风险入 `docs/proposals/` 留后期。
- **归档可追溯**：所有计划/文档/提示词/坑台账/优化提案统一归档（`docs/` 下），每条移植带 provenance（`Ported from wuu@<commit> internal/<pkg>/<file>.go`），每个 `B-NN` 配一个真实测试。**本计划全部产出由 AI 负责书写落盘。**

## 1. 四项已锁架构裁决（贯穿全程的前提）

- **C0 diff 归属**：照 wuu 双源。内核只在 tool result 内带 tool-time diff（`difflib`/`git diff` 复刻 `internal/tools/diff.go`）；Review 面板工作区级"盘上真相"由 **Electron 主进程 GitService 直接跑 git**（含 untracked），内核**不**新增 `review/turn_diff`。→ 放宽 §14 为「过程事件经协议可达；工作区盘态真相允许壳侧只读 git 采集」。
- **C3 会话真相源**：照 wuu，**SQLite 为会话权威库**（`sessions/session_messages/session_controls/inbox/held_user_work`），JSONL 降为可选导出镜像；append-only 用表约束+触发器表达。
- **C2 前端归属**：照 wuu，渲染层住 `desktop/src/renderer/` + `clients/core` 共享 + `packages/protocol` 契约；**废弃独立 `ui/`**；网页宿主后期按 wuu mobile-web「同一 renderer 换传输」方式再评。
- **Windows 沙箱**：MVP = 逻辑 `WorkspaceBoundary` + Job Object（生命周期），无 OS 写隔离**如实标注**；后期 Phase 上 **AppContainer**（原生、轻量、只挡文件写）；**不引 Docker Desktop**。

## 1.5 复刻忠实度保证机制（回答「能否真复刻 wuu」，每阶段适用）

> 复刻不是靠「照着感觉写」，靠下面五条**可核查**机制把「像不像 wuu」变成能跑命令验证的事实。任一阶段缺其中一条即视为未完成。

1. **wuu 测试即 oracle**：wuu 有 563 个 `_test.go`。移植任一 wuu 包前，先读它对应测试，把「输入→期望输出→边界」抽成 `docs/research/behavior-<pkg>.md`（行为规格 + 逐符号对照表：wuu 符号名→Questor 符号名→语义差异登记）。Python 测试**照搬 wuu 测试的断言场景**（不照搬代码），wuu 测试通过即等价基准。
2. **帧序列等价 fixtures（基准＝软模式，因本机无 Go）**：`tests/contract/` 是全程安全带。因本机跑不了 Go wuu，fixtures 基准**不来自实跑**，而来于：① wuu `_test.go` 里写死的 golden/期望 JSON 与表驱动用例（离线可抽）；② 逐方法读 `internal/appserver/*.go` 结构体核对手写期望帧形状。断言**逐帧方法名/字段形状/顺序/终态一致**。**盲区（诚实标注、进 port-ledger）**：wuu 运行期才暴露的行为（真实 SSE 分片时序、并发竞态、overflow 活数据）无 oracle，只能靠精读 `loop.go` 主链 + 自建对抗用例兜，不假装等价已证。
3. **逐符号 provenance + 差异台账**：每个移植文件头 `Ported from wuu@<commit> internal/<pkg>/<file>.go`；凡与 wuu 不一致处（命名、Go→Py 惯用法、Windows 适配、缺陷规避）**必须在该文件的 `docs/research/port-ledger.md` 记一行差异及理由**，不允许「静默不一样」。这份台账就是「复刻完成度」的对账清单。
4. **硬语义清单（漏一条=没复刻到位）**：每阶段列出「不可丢失的 wuu 硬语义」并各自配测试。例：循环的 `max_consecutive_continuations=8`、`FinishReason.continue` 归一、悬空 tool-call 位置修复、取消仍结算、`checkPermission` 五步序 + Authorizer fail-closed、脱敏独立于逃生阀、inbox 以 ClientID 幂等、64MiB 帧上限、`item/*/delta|replace` 增量语义、`turn/usage` 节流、activity 租约 + takeoverVersion 防竞态。这些**逐条进 `port-ledger.md` 并挂 B-NN + 测试**。
5. **负向验证 + 覆盖率对账**：每条护栏附负向注入（造一次真偏离贴红）；Phase 收口跑「wuu 该子系统导出符号 vs Questor 已实现符号」对照表，未覆盖项要么补要么显式标「属不做/后置 + ADR」。**「不做」也必须是登记过的决定，不能是遗漏。**

> 结论：忠实度 = (行为规格 + 帧等价 fixtures + 符号对照台账 + 硬语义清单全绿 + 不做项显式登记) 五件齐。这五件的产出物本身即「复刻验收报告」，可逐条复核，不依赖任何主观「像不像」。

## 1.6 最终交付物 = 一个可双击安装的完整 Windows exe 应用（本计划的硬验收物）

> **这是整个计划的目标物**：Phase 6 结束时，用户手上必须拿到一个**能双击安装、开箱即用的 Windows 桌面应用 .exe**——不是库、不是 CLI、不是「要自己 `uv run` 才起得来」的开发态。前端(Electron) + 冻结的 Python sidecar 打成一体，装完就能指着本地仓库跑 agent。

- **打包形态**：`electron-builder` 出 **NSIS 安装包**（`.exe`，可选 portable/zip 变体），`extraResources` 内带 **PyInstaller/`uv` 冻结的 Python sidecar 单可执行**；`winCodeSign`/离线镜像/`node-pty` 原生重建等已知坑按记忆项处理；**不引 Docker Desktop**。
- **exe 三门槛（贯穿，不许拖到最后才打包）**：
  1. **Phase 2 收口 = 最薄可安装 exe**：竖切（read→edit→bash→权限门→真 diff→中断）一旦跑通，立刻打成安装包并装机冒烟——先有「能双击跑起来的半成品 exe」，后续在 exe 上加厚，而不是最后一次性集成。
  2. **Phase 3 收口 = 功能加厚 exe**：补全工具面/接管/压缩后重新出包冒烟。
  3. **Phase 4 收口 = 可验证+硬化 exe**；**Phase 6 收口 = 完整 exe（含长任务层）** = 最终交付物。
- **exe 出口判据（每个门槛都跑）**：NSIS 安装→卸载干净无残留；冷启动主进程拉起冻结 sidecar（`QUESTOR_DESKTOP_CORE` 式钩子，Windows 探 `.exe`）→`initialize` 握手→跑通对应范围的一轮真实任务；**绝不从 workspace/PATH 捡陈旧 exe**（B-114）；sidecar 随主进程退出被 **Job Object** 兜杀不留孤儿；包体与依赖冻结完整、脱离开发环境仍自洽。
- **范围界定（对「完整」的定义）**：「完整 exe」= **复刻 wuu 本地单-agent 可审计工作台的全部核心体验**（可见/可干预/可验证 + 手写循环 + SQLite 会话 + compact + worktree + bash/编辑/git diff + activity 接管 + 内嵌终端/浏览器同页）。**不含**你在 §0/§9 亲自定的「不做」清单（远程/relay、插件宿主、MCP、subagent/多-agent 编排、skills/extensions、排班值班、多用户 SaaS）。即「核心体验全等」，非「wuu 33 万行字节全等」。若你要把某条「不做」也塞进 exe，明说，我加波次。
- **界面/动效/桌面壳形态 = 照 wuu 复刻**（你明确要「界面、动效都要」）：面板划分（会话侧栏/对话流/Review双栏diff/内嵌终端/浏览器/worktree）、主题色族（wuu `desktop/src/renderer/styles` 的 Tailwind v4 `@theme` 亮/暗双套）、动效（过渡曲线 + `prefers-reduced-motion` 降级，照 wuu）、图标/字体/间距与交互手感都**以 wuu renderer 为基准重搭**，不是自研一套 UI。依赖选型回到 wuu 实测集（Monaco diff/编辑器、@xterm 终端、react-markdown、@pierre/trees 文件树），撤销旧 `ui/` 的 zustand/@pierre/diffs/@xyflow/shiki 选型（连带重裁 ADR-0031/0032）。**诚实标注**：wuu 渲染层 648 文件、打磨极重——Phase 2 先出「形似 wuu 的最小可用壳」，界面保真度沿 Phase 2→3→4 逐波向 wuu 贴近（每波对照 `phase0-wuu-renderer-assembly.md` + 动效保真清单）；不承诺第一版就把 648 文件级细节一次吃平。

## 1.7 扩展点清单（现在别堵死，不是现在实现）

> 目的：多数「不做」项将来要能**无冲突接入**。原则＝保住**干净边界缝**（§二 可逆性三问），而非写投机抽象。这些缝 wuu 本来就有，移植时**自然带过来、零额外成本**；本清单是「移植时别把缝焊死」的护栏，不是本期功能。

**现在必须保住的 6 条边界缝（Phase 2/3 移植时守，port-ledger 各记一行「缝已保留、当前仅 X 实现」）**：
1. `agentengine` 薄契约保留 `EngineID/Factory/Registry/Descriptor` 命名（单引擎也不删符号）→ 将来接**外部引擎宿主**（codex/claude CLI）。
2. `tools` 注册表 + `capability.Surface` + `ToolExposure{Direct/Deferred/Hidden}` 三态作唯一入口 → 将来接 **MCP / skills / 新工具**（附加式，不改门）。
3. app-server 协议**传输无关**（消息体不假设 stdio；现仅实现 stdio）→ 将来接 **remote/WebSocket 宿主**（前端不改，加一层传输）。
4. 协议/schema **声明式 + 加性演进**（版本冻结、族级追加不升版本，沿用既有 ADR-0028 精神）→ 新通知族无冲突接入。
5. `limen` 单门 + `ToolKind` 枚举（wuu 已含 Schedule/MCP/Plugin/Browser 等值）→ 新增写域档位/工具类**只扩枚举不重构门**。
6. `thread/turn/run/item` 数据形状 + session 表 seq/head → 将来接 **subagent/多-agent 编排**（靠 thread 图扩展）。

**「不做」项后加成本分档**：
| 档 | 项 | 依赖的缝 |
|---|---|---|
| 廉价后加 | MCP、skills、新工具、外部引擎宿主 | 缝 1/2/5 |
| 要写不少但不动内核 | remote/relay、排班/值班、subagent/多-agent | 缝 3/4/6 |
| **后期可能加、现在不实现但不焊死** | 多用户 / 组织 / 租户 | 成本高（另一套 auth+数据作用域），但**保住数据形状缝**：session 表的 `owner/visibility/parent_id` 列不删（wuu 本就有）、身份/作用域解析走**单点**、limen 判定入参预留 actor 维度。**只做"别焊死"，不现在搭多租户机制**（违三问的是提前建 registry/config 开关，不是保留边界字段） |

> 执行约束：**不得**为"将来"提前建 registry/基类/config 开关（三问第 2、3 拒）；保缝＝“不焊死”，非“现在就搭”。

## Phase 0 — 知识抢救 + 文档/契约重立基（不写内核代码）

**目标**：把"方向反转"落成 ADR 与契约三件，修地基性缺陷，归档六份扫描。**Phase 0 未完成不得进 Phase 1**（否则每份文档建在流沙上——本次所有冲突根因就是契约三件没超前于 plans/modules）。

**前置扫描**：① 全量枚举 wuu `internal/appserver/protocol.go` 的 105+ 方法与通知常量成一张表（喂 protocol.md）；② 实测 wuu `desktop/src/renderer/` 组件装配方式（doc 扫描标"落笔前必须实测"，决定 ADR-0040/0020）；③ 实测 wuu `internal/session/session.go` 的 SQLite 表结构与 `inbox/held_work` 幂等 SQL（喂 ADR-0041/data-model）。

**范围与产出（按依赖序）**：
1. **git 先干净**：ADR-0033~0036 未跟踪 + 3 份已改未提交文件先归置；把现有 `src/questor/`、`ui/`、`desktop/` 代码标记为 `reference-only`（归档分支，不作实现依据）。
2. **修坑编号塌缩**（与转向无关，可独立先提交）：补 2 条机械断言进 `scripts/ci/check_specs.py`——`pitfalls.md` 编号全局唯一；每份 spec 内联 `B-NN` 必须在 pitfalls 存在且归属一致。修 5 份 `behavior-*.md` 的内联/表尾错位（limen 9 条 B-50→ B-50/51/52/53/54 等）。
3. **归档六份扫描**：`.scan-*.md` 迁入 `docs/research/`（去掉点前缀），登记为 Phase 0 输入。
4. **新立 ADR**（`docs/adr/`）：`0037` 复用优先取代全量重写（含 wuu MIT 署名义务：新建 `third_party/THIRD-PARTY-NOTICES`、`NOTICE`）、`0038` wuu 单锚 + 非母本规格处理规则（保留/换锚/删的裁决规则）、`0039` AppContainer 升级路径（走 0007 失效条件1）、`0045` diff 双源归属（**先于 0042**）、`0040` 前端归属改判、`0041` 会话存储 SQLite 权威、`0042` 协议词表取齐 wuu、`0043` 长任务后置、`0044` 现有实现处置地图（24 模块 + ui + desktop 逐个定性，并裁"对抗套件只增不减"如何与"代码废弃"相容）。给 0002/0003/0004 空号补正文或标 reserved；0024/0036 标 superseded/withdrawn。
5. **重写契约三件**：`protocol.md`（照 wuu 方法/通知全集表，词表取齐：`thread/start`、`turn/steer|queue|requeue`、`run/updated`、`item/*/delta|replace`、`process/*`、`browser/*` 反向 8、`activity/*`、`user-question/*`）→ `data-model.md`（SQLite 权威 + Run⊃Turn 层级 + 状态集含 `accepted/interrupted/timed_out` + UTF-16 code-unit 选中定位）→ `structure.md`（渲染层 `desktop/src/renderer`、import 矩阵重排）。护栏 `test_serve_names_are_contracted` 等同批跟动。
6. **重写 `AGENTS.md`**：§二 复用三分法→复用优先移植纪律；§三 语义来源表 engine 行改"来源 wuu/所有权本项目"，补会话存储权威源+协议词表两行；§五 出口判据→**与 wuu 行为等价（同任务同模型走同一协议帧序列，逐帧形状与终态一致）**；§六 scope 清单补 `desktop/ui/sessiontrace/worktree/testenv/scripts`；§七 "契约三件必须超前"升格首条 + 新增触发项"废弃/替换既有实现"。§一/§四/元规则基本 KEEP。
7. **写 `docs/plans/phase-a-mvp.md`**（取代 development-plan M 系列骨架）：即 Phase 1–4 的纵向切片计划，每波含「wuu 借鉴清单（参照文件锚点→本仓任务→B-NN→配对护栏）」+「不采纳项及原因」两栏。
8. 新建 `docs/proposals/`（优化提案存档区）、补 `desktop/README.md`、`modules/{review,habena}.md`。

**出口判据**：C0–C21 冲突全部有 ADR 落定或标"后置含 ADR"；契约三件内部自洽且与 wuu 实测一致；`check_specs`+`check_notes` 绿；`AGENTS.md` 无自我矛盾（C17 just 三方口径统一）；六份扫描已归档。

**Phase 0 提示词（扫描·可执行级）**：
```
角色：Questor 转向 Phase 0 契约重立基的只读扫描执行者。母本=wuu（d:\DEVELOP\My-project\wuu-main，MIT）。禁止改任何文件；产出仅写 docs/research/。
目标：为「照 wuu 重写契约三件 + 前端归属 + 会话权威源」取三组硬事实，深度到符号/字段级，不许浅尝。
必做（逐条落盘为可复核表格，不写结论段落，写事实+文件行号锚点）：
(1) 协议全表：逐条抽 internal/appserver/protocol.go 全部 `Method*` 与 `Notification*` 常量（约 105 方法 + ~40 通知），产 `docs/research/phase0-wuu-protocol-table.md`：列【方法名 | 域 | 入参结构体字段(名:类型) | 返回/结果字段 | 关联通知 | Questor A 阶段处置(做/后置/不做)】。标注 snake_case 命名、64MiB 帧(`stdio.go appServerMaxStdioRequestBytes`)、反向 `srv-` id、`initialize` 的 InitializeResult 全字段(`config_handlers.go handleInitialize`)。remote/plugin/mcp/sideThread/participant/device/project 族初判「不做」。
(2) 渲染层装配：实测 desktop/src/renderer/ 目录与入口——面板划分(会话侧栏/对话流/Review/终端/浏览器/worktree)、如何按 `method=="..."` 分支消费 app-server 通知(给 3-5 个真实分支样例+文件)、状态管理是否用 zustand(wuu 不用)、Monaco/xterm 接入点、preload 173 IPC 通道清单归类。产 `phase0-wuu-renderer-assembly.md`，给「照此重搭 Questor renderer 的目录/装配建议」。这是 ADR-0040/0020 落笔前必测项。
(3) 会话存储：读 internal/session/session.go 全部 `CREATE TABLE` + inbox.go `INSERT OR IGNORE/ON CONFLICT(client_id)` + held_user_work.go 整表 delete+insert 事务 + history_checkpoint/recovery，产 `phase0-wuu-sqlite-schema.md`：Questor SQLite 权威库表清单草案(session_messages/session_controls/inbox/held_user_work/compaction_note…)+ 幂等/恢复语义 + WAL/并发锁。喂 ADR-0041/data-model。
(4) 顺带登记 wuu 侧已知的 Windows 阻断（credentialstore `keyring.go:54` 硬编码 macOS-only、securefs 0600 假安全），供 Phase 2/4 规避。
出口自检：三张表逐符号可复核、每行有 wuu 文件:行号锚点；不得出现「大概/应该」级措辞(违反 §1.5 机制1)。完成后贴文件路径清单。
```
**Phase 0 提示词（落地·可执行级）**：
```
角色：Questor Phase 0 文档/契约重立基执行者。依据=docs/research/phase0-wuu-*.md 三张表 + .scan-questor-docs.md(§3.2 ADR 表/§4 AGENTS 逐节处置/§5 落笔顺序)。四条架构裁决已锁(diff 照 wuu 双源/会话 SQLite 权威/前端照 wuu renderer/Windows 逻辑边界+JobObject→后期 AppContainer)，不得重开。
严格依赖序（前一步未完成不得进下一步，遵守 AGENTS §七「先改文档后改代码」，本阶段不动内核代码）：
1 git 干净：归置 ADR-0033~0036 未跟踪 + 3 份已改未提交；把 src/questor、ui、desktop 现有实现移到 reference-only 分支并在 CHANGELOG 记 Changed/Removed。
2 修地基缺陷(独立可先提)：给 scripts/ci/check_specs.py 加两条机械断言——pitfalls.md 编号全局唯一；每份 spec 内联 B-NN 必须在 pitfalls 存在且归属模块一致(跑负向注入证明会咬人)。修 5 份 behavior-*.md 的错位(limen 9 条 B-50→拆回 B-50..B-54 等)。
3 归档六份扫描→docs/research/。
4 立 ADR(一页能写就写，写不完升 specs)：0037 复用优先(含 wuu MIT 署名义务，建 third_party/THIRD-PARTY-NOTICES+NOTICE)、0038 wuu 单锚+非母本规格处理规则(保留/换锚/删 三态判定)、0039 AppContainer 升级(走 0007 失效条件1，结论1/2/3 逐字留)、0045 diff 双源归属(先于0042)、0040 前端归属改判、0041 会话 SQLite 权威、0042 协议词表取齐 wuu、0043 长任务后置、0044 现有实现处置地图(24 模块+ui+desktop 逐个定性 + 裁「对抗套件只增不减」与「代码废弃」相容规则)。0002/0003/0004 补正文或标 reserved；0024/0036 标 superseded/withdrawn。
5 重写契约三件(顺序 protocol→data-model→structure)：protocol.md 逐条对齐 phase0-wuu-protocol-table；data-model.md 改 SQLite 权威 + Run⊃Turn 层级 + 状态集含 accepted/interrupted/timed_out + UTF-16 code-unit 选中定位；structure.md 渲染层落 desktop/src/renderer + import 矩阵重排。护栏 test_serve_names_are_contracted 等同批跟动。
6 改 AGENTS.md：按 §4 逐节处置(§二→复用优先移植纪律+MIT 署名硬线、§三 语义表 engine 行改来源wuu/所有权本项目+补会话存储/协议词表两行、§五 出口判据→与 wuu 帧序列等价、§六 scope 补全、§七「契约三件必须超前」升首条+新增「废弃/替换实现」触发项)。
7 写 docs/plans/phase-a-mvp.md(Phase1-4 纵向切片，每波【wuu 借鉴清单: 参照文件锚点→本仓任务→B-NN→配对护栏】+【不采纳项及原因】两栏)；建 docs/proposals/、docs/research/port-ledger.md(复刻对账台账)、desktop/README、modules/{review,habena}.md。
8 给 phase-u 两份加历史头「不得再作实现依据」并撤销其中 pending。
出口判据：C0–C21 逐条有 ADR 落定或标「后置含 ADR」；契约三件自洽且与 phase0 三表一致；check_specs+check_notes 绿；AGENTS 无自我矛盾(C17 just 口径统一)。全量可追溯，产出均由你落盘。
```

---

## Phase 1 — 地基：消息/Part 规范 + 协议契约测试安全带（接缝先行）

**目标**：把"前端吃 wuu 协议、后端是 Python"这道**唯一跨语言接缝**先钉死，防止后续所有模块建在漂移动的协议上。这是最高风险项（wuu 协议**无代码生成**，TS/Go/Python 三份并行）。

**前置扫描**：精读 wuu `packages/protocol/src/index.ts`（3010 行）导出类型 + `internal/appserver/{protocol.go,stdio.go,config_handlers.go}` 的**实际序列化 JSON 形状**（以 Go 输出为准，不是 TS 类型）。

**范围**：
- **消息/Part 规范**（第一前置件）：`src/questor/schemas/message.py`——定义 ChatMessage/Role/Part（text/reasoning/tool_call/tool_result/image…）+ `FinishReason` 归一枚举（照 `providers.NormalizeFinishReason`）。一切重写挂靠它。
- **app-server 协议骨架**：`schemas/app_server/` pydantic 模型（Request/Response/Notification/Error/Initialize 全套）、`serve/envelope.py`、`serve/stdio.py`（64MiB 帧、NDJSON、id 关联、`srv-` 前缀反向 id）。
- **契约测试安全带（本 Phase 的核心交付）**：`tests/contract/`——用 **wuu Go 实测 JSON fixtures 回放**，断言 Python 的 `initialize` 与每个方法/通知的 JSON 形状逐字段一致；这是弥补"无代码生成"漂移的唯一防线。`protocol.md` 表 ↔ `schemas/` ↔ handler 单一来源（保留现有 `B-119/B-121` 护栏思路）。
- `config/state.paths/secrets/version/schemas 生成链` 骨架。

**出口判据**：`initialize` + 至少 thread/turn/run/item 四族方法有 fixture 回放测试且绿（对 wuu fixtures）；`just check` 绿；契约单一来源护栏附负向验证（注入字段漂移即红）。

**风险与规避**：字段大小写（wuu snake_case 为主）、`Provider` 字段永不上线、`Origin` 与 provider Role 分离、路径字符串按 Win 原生生成。

**Phase 1 提示词（可执行级）**：
```
角色：Questor Phase 1 跨语言接缝执行者。目标=把「Electron 前端吃 wuu app-server 协议 + Python 后端」这道唯一接缝用契约钉死。本阶段只做契约层，不写业务 handler。
前置扫描(先做)：逐字段读 wuu packages/protocol/src/index.ts(3010 行) 导出的 Request/Response/Notification/Error/Initialize* 类型 + internal/appserver/{protocol.go,stdio.go,config_handlers.go} 的实际序列化 JSON(以 Go 结构体 tag 为准，不是 TS 类型，二者会漂移)；**基准帧从 wuu `_test.go` 里的 golden/期望 JSON 抽取 + 逐方法读结构体核对手写期望帧**（本机无 Go，不靠实跑）。产 docs/research/behavior-protocol-wuu.md(逐符号对照表)+ port-ledger 差异行。
交付：
- src/questor/schemas/message.py：ChatMessage/Role/Part(text|reasoning|tool_call|tool_result|image…)/FinishReason 归一枚举(照 providers.NormalizeFinishReason 各家停止信号映射)。此为一切重写挂靠的第一前置件。
- src/questor/schemas/app_server/：pydantic 模型对齐 phase0-wuu-protocol-table 全 A 阶段方法/通知/错误形状；snake_case 为主；Provider 配置身份字段永不上线；Origin 与 provider Role 分离；路径字段按目标 OS 原生生成。
- serve/envelope.py + serve/stdio.py：NDJSON 帧、64MiB 上限、id 关联、反向 srv- 前缀、initialize 握手与 capabilities.reverse_rpc 协商、InitializeResult 全字段。
- tests/contract/【本阶段核心交付】：用 **wuu 测试 golden / 手写期望帧 fixtures** 回放驱动 Python，断言 initialize + 每方法/通知逐字段一致(键名/类型/顺序/可选性)。这是弥补无代码生成漂移的唯一防线。
- protocol.md↔schemas↔handler 单一来源：保留 B-119(方法表派生)/B-121(声明面⊆实现且双向)护栏思路，新增「wuu fixtures 回放」这一类。
硬语义(§1.5机制4)：64MiB 帧、srv- 反向 id、snake_case、Provider 不上线、Origin≠Role、FinishReason 归一——逐条进 port-ledger + 测试。
出口判据：initialize + thread/turn/run/item 四族 fixture 回放绿(对 wuu fixtures)；just check 绿；契约单一来源护栏附负向验证(改一个字段名/大小写漂移即红，贴输出)；port-ledger 本阶段差异逐行有理由。
```

---

## Phase 2 — 可跑竖切 MVP（Windows 上端到端跑通第一轮真实任务）

**目标**：让 Electron 壳 + Python sidecar 在 Windows 上跑通 **read→edit→bash、过权限门、Review 看真 diff、能中断** 的完整一轮。**这是"先做出可用产品"的里程碑**。（本 Phase 拆 **2a headless 内核端到端** + **2b 前端+打包**，细则见 §12-A；一个窗口只承担 2a 或 2b。）

**前置扫描**：按 §11 精读 wuu `agent/loop.go` 剩余主链（L560–1010 请求拼装→Step→overflow 恢复→工具下发）、`stream_runner.go`、`tool_runtime.go`、`agentengine.go`、`tools/{boundary.go,env.go,toolkit.go::checkPermission,rebuildRegistry}`、`session/{session.go,inbox.go,held_user_work.go}`、`process/{manager_windows.go,command.go}`、`providers/{anthropic,openai}`。

**范围（模块，均带 provenance）**：
- **engine**：`agentengine` 退化为薄契约（单引擎 EngineID/TurnInput/EventSink/Session/TurnResult）；手写 `loop.py`——`max_consecutive_continuations=8` 硬止损、`repair_dangling_tool_call`、FinishReason 归一、Step 抽象（transport 无关，直实现 StreamRunner 语义）、`ToolExecutionGate`（asyncio.Semaphore+写锁，读并发/写排他，调度时刻锁内定死 concurrency_safe）、**取消不丢账**（`asyncio.shield` 结算 + 错误当结果回模型不抛）、fresh/compact 两条上下文路径不混。
- **providers**：anthropic + openai 最小两家（httpx + SSE），默认 0 重试按 operation 分档、HTTPError 异常层次驱动决策、`turn/usage` 节流。
- **tools**：read_file/list_files/glob/grep/write_file/edit_file/bash + `boundary.go` 单一权威门（从可达性推导、无 per-tool 信任、三档）+ `ResolvePath` **Windows 路径强化**（casefold + `Path.resolve` + 显式拒 `\\?\`/UNC + 8.3 短名扩展比较）+ sensitive_paths + 脱敏常开（解耦于逃生阀）+ result_budget fail-open。
- **limen**：照 wuu `checkPermission` 顺序 hook→boundary→特例→Reviewer→Authorizer（同 ctx 一次门、Authorizer fail-closed 只认 `"allow"`）。
- **session/state**：SQLite 权威库 + inbox 幂等 + held_user_work queue/steer + storelock（Windows `LockFileEx`/portalocker）+ securefs→**NTFS ACL + DPAPI/wincred**（放开 wuu macOS-only 硬编码）。
- **serve**：stdio sidecar + 通知流最小集（`turn/started|completed|error`、`item/*/delta|replace`、`run/updated`）。
- **前端（照 wuu renderer 重搭）**：`desktop/src/renderer` 会话列表 + 对话流 + Review（**壳侧 GitService 跑 git**）+ 内嵌终端（node-pty/主进程自持，后端不做 tty）+ 工具活动视图；`desktop/src/main` sidecar spawn（`WUU_DESKTOP_CORE` 式钩子指 Python 可执行）+ initialize 握手 + IPC 透传。
- **Windows shell 策略（本 Phase 定）**：沿用 **Git Bash**（照 wuu 已趟：`-c` 非 `-lc`、`NormalizeBashCommand`、`cygpath`、`.exe` 补全、NTLM 泄漏防护），不引 PowerShell 重写 shellpath。**Job Object** 兜进程树终止。

**出口判据**：**e2e 竖切在 Windows 真跑通**（脚本化或手动，贴真实输出）；与 wuu 同任务帧序列等价性测试；权限门 3 档 + 路径越界用例（含 Windows 短名/UNC）+ 中断不丢账；三柱之"可见/可验证"最小可感；**并产出 §1.6 门槛 1「最薄可安装 .exe」**（electron-builder NSIS：装→冷启动拉起冻结 sidecar→跑通竖切→卸载干净）。

**风险与规避**：1189 行 god object 不复现（方法表单一来源）；`isBarrierTool` 死枝不搬（要么接要么删）；SIGTERM 在 Windows 静默失败改 Job Object/CTRL 事件。

**Phase 2 提示词（扫描·可执行级）**：
```
角色：Questor Phase 2 可跑竖切移植前的只读扫描。禁改文件。目标=为「手写 wuu 循环 + 最小工具 + 权限门 + SQLite 会话 + stdio sidecar + 照 wuu 重搭 renderer」取逐符号移植蓝本，深度到函数/分支/常量级，补齐 .scan-wuu-kernel.md §11 自陈「仍未逐行」的欠账。
必精读并抽行为规格(每块产 docs/research/behavior-<pkg>.md + port-ledger 差异行 + 硬语义清单)：
(1) agent/loop.go 全文——重点 §11 未读段 L120-396(tryProactiveCompact/emitCompactAttempt/resolveEffectiveCompaction/usage 初始化) 与 L560-1010(请求拼装→Step→overflow 恢复→工具批次下发)；抽 maxConsecutiveContinuations=8 的触发/清零条件、FinishReason.continue 语义、repairLiveToolCallHistory、overflow 只重试一次+no-op 不重试同 payload、fresh-context attempt 归档与回滚闭包。
(2) agent/step.go(LoopConfig/StepResult/LoopResult 字段)、runner.go/stream_runner.go(StreamRunner 事件吐法)、tool_gate.go(读写信号量+防饿死)、tool_runtime.go(TurnToolRuntime：ToolMetadata.ConcurrencySafe 调度时锁内定死、Orchestrator 不占槽、ledger.Settle(WithoutCancel) 取消不丢账、错误 FromErrorText 当结果回模型、isBarrierTool 死枝标注「不搬」)。
(3) agentengine.go(退化成单引擎薄契约要保留的符号)、tools/{boundary.go 三构造器+mutates by ToolKind,env.go ResolvePath+relInsideRoot(Windows 已 lowercase，需补 8.3 短名/\\?\\/UNC),toolkit.go checkPermission 五步序+fail-closed+同ctx一次门,rebuildRegistry 权威清单},sensitive_paths.go,redaction.go(JWT JOSE 二次校验,脱敏独立于逃生阀),result_budget.go fail-open,diff.go tool-time diff)。
(4) session/{session.go 建表与事务,inbox.go 幂等,held_user_work.go queue/steer 整表事务,driver_checkpoint 续跑},storelock(LockFileEx 分支),securefs(0600→NTFS ACL/DPAPI 替代点),statepath 目录布局。
(5) process/{manager_windows.go ptySupported=false 降级,command.go ProcessTree/DefaultStopGracePeriod=2s},mcp/process_windows.go Job Object(KILL_ON_JOB_CLOSE+CREATE_SUSPENDED+NtResumeProcess),credentialstore keyring.go:54(macOS-only 放开点),shellpath/resolve_windows.go(Git Bash -c/NormalizeBashCommand/cygpath/.exe/NTLM 防护)。
(6) providers/{anthropic,openai} adapter 正文(SSE 解析、错误→HTTPError、cache breakpoint)、retry.go(默认0重试)/retry_profiles/attempt_executor。
(7) desktop/src/{main/appServerClients.ts(ensureStarted/write 64MiB/serverRequestRoutes/WUU_DESKTOP_CORE),main/gitService.ts(壳侧 diff 权威),main/terminalSessions.ts(node-pty 自持),shared/protocol.ts}——定「换 Python 可执行 + 后端 process/* 用 ConPTY 或让位前端」的接缝。
出口自检：每个 wuu 导出符号要么有 Questor 对应计划要么标「不做/后置+ADR」；硬语义清单逐条列全；不得「我以为」级措辞。贴文件清单。
```
**Phase 2 提示词（实现·可执行级）**：
```
角色：Questor Phase 2 可跑竖切实现者。依据=Phase 2 扫描的 behavior-*.md + port-ledger + fixtures。每条移植带 provenance，与 wuu 不一致处必登 port-ledger 一行理由。允许局部微调，不动摇「照 wuu 语义移植、手写循环不引 LangGraph、Windows 第一平台」核心目标。发现需大重构的更优方案→沿用 wuu 成熟做法，方案存 docs/proposals/，不打断本竖切。
按模块移植(依赖序)：
- engine：agentengine 退化薄契约(EngineID/TurnInput/EventSink/ApprovalHandler/TurnResult/Session 命名保留，作 ADR-0033 落地)；手写 loop.py 复刻 §(1)(2) 硬语义——max_consecutive_continuations=8、FinishReason 归一、悬空 tool-call 位置修复、overflow 只重试一次、fresh/compact 双路不混、LoopResult.history_rewritten 决定替换vs追加；ToolExecutionGate(asyncio.Semaphore+写锁，读并发/写排他，调度时定死 concurrency_safe，orchestrator 不占槽)；取消不丢账(asyncio.shield 结算，错误当结果回模型)；isBarrierTool 死枝要么接要么删不留空枝。
- providers：anthropic+openai 最小两家(httpx+SSE)，默认 0 重试按 operation 分档，HTTPError 异常层次，turn/usage 节流。
- tools：read_file/list_files/glob/grep/write_file/edit_file/bash；boundary 单一权威门三档(从可达性推导、无 per-tool 信任)；ResolvePath Windows 强化(casefold+Path.resolve+拒 \\?\\/UNC+8.3 短名扩展+EvalSymlinks 双侧)；sensitive_paths；redaction 常开(脱敏独立逃生阀)；result_budget fail-open。权限门序 hook→boundary→特例→Reviewer/approveForMe→Authorizer(fail-closed 只认"allow")，同 ctx 一次门。
- session/state：SQLite 权威库(session_messages/session_controls/inbox/held_user_work)+inbox ClientID 幂等+held_work queue/steer+storelock(Win LockFileEx/portalocker)+securefs→NTFS ACL+DPAPI/wincred(放开 keyring.go:54 macOS-only)。
- serve：stdio sidecar + 通知最小集(turn/started|completed|error、item/*/delta|replace、run/updated) 走 Phase 1 契约。
- 前端(照 wuu renderer)：desktop/src/renderer 会话列表+对话流+Review(壳侧 GitService 跑 git 含 untracked)+内嵌终端(node-pty 主进程自持)+工具活动；desktop/src/main sidecar spawn(WUU_DESKTOP_CORE 式钩子指 Python 冻结可执行)+initialize 握手+IPC 透传 app-server 通知；不复制前端代码到 ui/。后端 process/* worker 用 ConPTY 或本阶段让位前端终端(标 port-ledger)。
- Windows 策略：沿用 Git Bash(照 wuu 已趟修补)，不引 PowerShell 重写；Job Object 兜进程树终止(KILL_ON_JOB_CLOSE)；SIGTERM 静默失败改 CTRL/Job Object；路径 file:// 前导斜杠剥离。
出口判据(§1.5 五件全绿)：行为规格/帧等价 fixtures/符号对照台账/硬语义清单全绿/不做项登记 齐；Windows 真机 e2e 跑通 read→edit→bash→权限门→真 diff→中断，贴实测输出+`just check`；中断不丢账 + 路径越界(短名/UNC) 用例 + 权限三档 各有测试；契约回放不因本阶段改动转红。
```

---

## Phase 3 — 能力补齐（完整工具面 + 可干预）

**目标**：补齐让工作台"够用"的工具与"可干预"柱。

**前置扫描**：wuu `tools/{tool_git,tool_process_tool,tool_web,tool_history,tool_notes,tool_browser,tool_discovery}`、`agent/{held_user_work 消费侧,fresh_context,activity}`、`appserver/{turn,run,activity,browser,user_question}_handlers`、`worktree`。

**范围**：
- 工具：git / process（后台进程生命周期）/ web_search / web_fetch / history_read|search / notes / new_context / **tool_search 发现机制**（Deferred/Direct/Hidden 三态 + 历史恢复已加载态，必须写进计划不能默认全量暴露破坏 prompt cache）/ present_artifact。
- 可干预全套：`turn/steer|unsteer|queue|dequeue|requeue` + held_user_work、`user-question/*` HITL、**`activity` 接管仲裁**（租约 + takeoverVersion 防竞态，支撑 Electron「同页接管即暂停」）、browser 反向 RPC 8 方法 + CDP 真接管（Electron webContents 同页）。
- 上下文：compact 摘要路径（contextbudget 单点推导、gate=真实 wire tokens、80K/8K/4K/500 分部件预算、20min 超时不拖死）；worktree 分叉可见（剥离 subagent 绑定）。
- 结果规范化/投影/脱敏完整；diff 双源完整。
- **深度补齐（对照 wuu 别做浅——复刻"完整体验"的关键，逐项进 port-ledger）**：① 工具面是**编译**出来的：`modelprofile→capability.Surface→Definitions()` 过滤 + `ToolExposure{Direct/Deferred/Hidden}` 三态 + `rebuildRegistry` 的 21 工具全清单对齐（不是硬编码写死 8 个）；② compact 三件套不止摘要——`compaction_registry`(fork 多 provider 优先/回退)、`adaptive_compact`(按观测请求大小反应定目标，非死算窗口)、`compaction_fallback`、`context_note`(fork 隐藏 checkpoint+主请求复用)；③ **workspaces 池**（多工作区生命周期 + `set_session_workspace` 切换），非只有单根 worktree；④ provider **native compaction** seam（`NativeCompactor` 接口，与摘要压缩并存）+ `SessionPrewarmer`/`QuotaReader` 可选能力用 isinstance 探测；⑤ 小模块落点各给一行：`sessiontrace`(最小 trace≠大盘)、`workingnotes`(乐观并发拒丢更新)、`structuredoutput`(结构化输出校验)、`toolledger`(工具结算账本，取消不丢账的落点)。

**出口判据**：插话/接管/分叉三条各能从 UI 走通一次（§五 前端跟随纪律）；工具并发分区有测试；activity 接管竞态有负向护栏。

**Phase 3 提示词（可执行级）**：
```
角色：Questor Phase 3 能力补齐实现者(已过 Phase2 可跑竖切)。先扫描后实现，同一窗口内先只读扫再写。禁止浅扫：每个补的模块先读 wuu 对应实现与测试、抽行为规格进 docs/research/behavior-<pkg>.md + port-ledger。
扫描锚点：tools/{tool_git,tool_process_tool,tool_web,tool_history,tool_notes,tool_browser,tool_discovery,tool_present_artifact}、agent/{held_user_work 消费侧,fresh_context,compaction_*},activity 包(Kind/Controller/State/Registry/Lease/takeoverVersion),appserver/{turn,run,activity,browser,user_question}_handlers,worktree,compact+contextbudget+adaptive_compact。
交付：
- 工具：git/process(后台生命周期)/web_search/web_fetch/history_read|history_search/notes/new_context/present_artifact；**tool_search 发现机制**(ToolExposure Direct/Deferred/Hidden 三态 + Deferred 未加载执行被拒 + 从历史 DiscoveredToolNamesFromMessages 恢复已加载态)——必须显式决定全量暴露 vs 发现，写 port-ledger，不能默认全量破坏 prompt cache 前缀。
- 可干预：turn/steer|unsteer|queue|dequeue|requeue|update-queued + held_user_work 消费；user-question/{hold,respond,list,cancel} HITL；**activity 接管仲裁**(租约+takeoverVersion 防竞态、跨 thread 占用互斥 ErrTargetBusy、UpdateWithLease 防完成覆盖并发 takeover)；browser 反向 RPC 8 方法 + CDP 真接管(Electron webContents 同页「接管即暂停」)。
- 上下文：compact 摘要路径(contextbudget 单点推导阈值、gate=真实 wire tokens、分部件字节预算 80K/8K/4K/500、20min 超时按不折叠降级不拖死整轮、失败/no-op 不重试同 payload)；fresh_context 换窗旁路(无模型、先归档再释放，与摘要不混)；worktree 分叉可见(保留供 git diff/cherry-pick，剥离 subagent 绑定)。
- 完整 diff 双源(tool-time 内核 + workspace 壳侧)、结果规范化/投影/脱敏完整。
硬语义(§1.5机制4)：activity takeoverVersion 竞态防护、Deferred 未加载拒执行、compact 只重试一次、turn/steered+held 通知——逐条 port-ledger+测试。
出口判据(§1.5 五件全绿)：插话/接管/分叉三条各从 UI 走通一次(AGENTS §五 前端跟随)；工具并发分区有测试；activity 接管竞态有负向护栏；契约相关 fixtures 不转红；just check 绿。不做项(如 remote/subagent)显式登记。
```

---

## Phase 4 — 可验证 + Windows 硬化

**目标**：补"可验证"柱 + 把 Windows 安全/韧性做实。

**前置扫描**：wuu `execution_security`(注：这是 EvoFlow 的；wuu 对应 execution/store exitcodes)、`session/storage_governance`、`providers/{retry,recovery,stream}`、`toolledger`；AppContainer 官方文档（Windows 写隔离升级）。

**范围**：evidence（声称 vs 当时录制输出并排、`recorded_output_ref`、结构化输出校验）、退出码语义映射（照 `execution/exitcodes.go` + FlowCoder 经验）、**AppContainer 写隔离**（`CreateAppContainerProfile`→受限 SID→仅 WritableRoots 授 ACL→`CreateProcess` 带 capability；pywin32/ctypes FFI）、崩溃恢复（checkpoint/journal）、韧性（retry_profiles 按档、stream_recovery）、脱敏 JWT JOSE 二次校验。

**出口判据**：e2e 整链「跑命令→声称通过→并排核对真实输出→打回」走通；AppContainer 写隔离正/负向用例；无"假安全"（0600 不再当隔离依据）；**出 §1.6 门槛 3「功能完整 exe 收口包」**（含 Phase3 工具/接管/压缩 + Phase4 证据/AppContainer，装机冒烟全绿）。

**Phase 4 提示词（可执行级）**：
```
角色：Questor Phase 4 可验证柱 + Windows 硬化实现者。先扫描后实现，禁浅扫。
扫描锚点：wuu execution/{exitcodes,store,types}.go、toolledger/ledger.go、providers/{retry,retry_profiles,attempt_executor,recovery,stream_recovery}、session/{storage_governance,history_checkpoint,inference_journal}；AppContainer 官方文档(CreateAppContainerProfile/ProcThreadAttributeList SECURITY_CAPABILITY/SetNamedSecurityInfoW)；EvoFlow execution_security/{runner,profiles,helpers} 的 profile JSON schema(仅借 schema 形状不搬码)。
交付：
- evidence：声称 vs 当时录制真实输出并排核对、recorded_output_ref 可追溯、结构化输出校验(照 structuredoutput/validator.go)；退出码语义映射(照 execution/exitcodes.go + behavior-tools-fc 经验)。
- **AppContainer 写隔离**(Windows，§1 裁决升级路径)：Policy{Mode,WritableRoots}→受限 capability SID→仅在 WritableRoots 授 ACL→CreateProcess 带 PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITY；pywin32/ctypes FFI；Provider seam 照 wuu processsandbox.Provider 让后端可插拔；passthrough 与 sandboxed 始终回报区分「真沙箱跑了」。
- 崩溃恢复：driver_checkpoint/inference_journal 落库续跑；韧性：retry_profiles 按 operation 分档、stream_recovery；脱敏 JWT JOSE 二次校验完整。
硬语义(§1.5机制4)：取消/崩溃不丢账、0600 不再作隔离依据(全改 ACL/DPAPI)、passthrough 明示不静默放行。
出口判据(§1.5 五件全绿)：e2e 整链「跑命令→声称通过→并排核对真实输出→打回」走通；AppContainer 写隔离正/负向用例(越界写被挡 + 工作区内可写)；消除 0600 假安全(负向证明)；just check 绿。
```

---

## Phase 5 — 性能/扩展/清理（优先级最后）

**范围**：prompt-cache 前缀稳定（`tool_surface_lock` + footer「strip-stale+append-fresh」注入不进 system）、大载荷 offload 哨兵、deferred 工具发现省 token、web 宿主按 wuu mobile-web「同 renderer 换传输」评估、死代码清理、性能。凡 §0"更优方案需大重构"的存档提案在此评估。

**Phase 5 提示词（可执行级）**：
```
角色：Questor Phase 5 性能/扩展/清理执行者(优先级最后，主链已可用才做)。先读 docs/proposals/ 存档 + port-ledger 标注的 deferred 项。
交付(仅前向兼容、不破坏稳定主链者；破坏性的继续留档)：prompt-cache 前缀稳定(tool_surface_lock 会话锁 tools + footer「strip-stale+append-fresh」注入不进 system)、大载荷 offload 哨兵(__LARGE_FILE_REF__::path 旁路)、deferred 工具发现省 token、web 宿主按 wuu mobile-web「同一 renderer 换传输」评估、死代码清理、性能优化。
出口判据：相关 fixtures 回放仍绿(性能改动不改语义)；just check 绿；每条优化在 port-ledger 记「改了什么/收益/风险」。
```

---

## Phase 6 — 长任务/编排/验收层（借 EvoFlow 规格，最后做）

**目标**：把"跑完能验收 + 长任务托管"这半壁驱动力补上，围着**自研 run 模型**重写，不引 LangGraph、不搬 EvoFlow 码。

**前置扫描**：EvoFlow `collab/`（双状态机 + 迁移留痕 + supervisor 派发 claim/波次/依赖交接/lease/decision_required + 验收闭环）、`tool_approval_*`（七层 + 行态机 + 两段消费 peek→execute→consume + 循环外 replay）、`run_status_reconcile`（三层回收 + 三源健康交叉判定）、`context_compaction`（参数体系）、`persistence/db.py`（并发模型）。

**范围**：orchestration（Task/CollabPhase 状态机 + 迁移留痕）、supervisor 派发协议、tool_approval 家族、zombie/lease/reclaim 三层回收、plan→authorize→execute 门、验收打回 rollup。Goal/Todo/Memory 能力此阶段按需内建（不做 wuu 式插件宿主）。

**Phase 6 提示词（可执行级）**：
```
角色：Questor Phase 6 长任务/编排/验收层实现者(B 层，主体可用产品完成后做)。依据=扫 EvoFlow 取的机制规格。硬约束：读设计不搬码(PolyForm)，围着 Questor 自研 run 模型重写，不引 LangGraph；docstring 会说谎，以加载器/仓储层为准。
扫描锚点(EvoFlow-main)：collab/(双状态机 models/state_transitions + TaskStateService 迁移留痕 + supervisor/execution 派发 _claim_subtasks/波次 eligible/依赖交接/monitor lease/decision_required + 验收闭环 work_checklist/subtask_outcome_report/rollup 封顶99%/upstream_receipt 软唤醒 + dependency DAG)、tool_approval_{middleware,service,repositories,executor,answers}(七层 + 行态机 PENDING→APPROVED→EXECUTED + peek→execute→consume 两段 + begin_approval_batch 批一致性 + 签名授权 sha256 + 循环外 replay 脱离图执行 + 先可见后挂起)、run_status_reconcile(三层回收 zombie/lease/reclaim + 三源健康交叉 心跳/代理连接/服务端探针 + 三态探针 None=不可达不瞎猜)、context_compaction 参数体系(threshold_ratio/cooldown/release_ratio/gate=wire 真值)、persistence/db.py(RLock 逐语句+busy_timeout+指数重试)。
交付：orchestration(Task/CollabPhase 状态机 + 每次迁移留 from/to/changed_by 历史行)、supervisor 派发协议、tool_approval 家族、zombie/lease/reclaim 三层回收、plan→authorize→execute 门、验收 rollup 打回；Goal/Todo/Memory 能力本阶段按需内核内建(不做 wuu 式插件宿主)。
规避 EvoFlow 缺陷：不继承 LangGraph interrupt/Command 耦合(自研等价挂起原语，先 emit pending 帧再挂起)、不搬 32 万行含 SaaS/排班/IM channel 的不做面。
出口判据(§1.5 五件全绿)：长任务 e2e「规划→授权→派发→插话→验收→打回→崩溃恢复」走通；三层回收各有竞态负向用例；tool_approval 两段消费不丢账；不搬 EvoFlow 代码(全自写、只对齐规格)；just check 绿。
```

---

## 7. 阶段依赖图

Phase 0 →（前置，不可跳）→ Phase 1（接缝安全带）→ Phase 2（可跑竖切）→ Phase 3（补齐）→ Phase 4（可验证+硬化）→ Phase 5（优化）→ Phase 6（长任务）。Phase 1–4 = "A 阶段可用产品"；Phase 6 = B 层后置。Phase 5 可与 4 交错但优先级最低。

## 8. 每阶段统一门禁

- 开工先跑对应扫描提示词并落 `docs/research/`；出口必贴 `just check`（ruff/format/pyright/pytest）+ 阶段专属判据（等价性/负向护栏/e2e）。
- Windows 平台跑测（第一平台）。契约三件改动必"先改文档后改代码"。
- 每模块头部 provenance；每 B-NN 配真实测试；新坑先过唯一性断言再落库。
- **窗口交接必读（§12-C）**：每阶段新窗口开工前，先读「本计划 + 相关 `docs/research/*` + `port-ledger` + 上一阶段出口证据 + AGENTS §〇§二§三 + 本阶段扫描提示词」；跨窗口不共享记忆，不重读就会漂移。
- **文档同步＝出口判据（§12-D）**：每阶段收口必须同步更新 `port-ledger` + 对应 behavior 规格 + `modules/*.md` + CHANGELOG + 新坑入 `pitfalls.md`；漏更新=未达出口。

## 9. 母本缺陷台账（移植时显式规避，不照搬）

| 来源 | 缺陷 | Questor 规避 |
|---|---|---|
| wuu | 协议无代码生成、TS/Go 两份人工漂移 | Phase 1 fixture 回放契约测试钉死；长期可引入单一 schema 生成 |
| wuu | `app_server` 巨型 god object（105 方法） | 方法表单一来源 + 按域分文件且不复制表 |
| wuu | `credentialstore` 硬编码 macOS-only（Windows 阻断） | 放开，走 wincred/DPAPI |
| wuu | `securefs` 0600/0700 在 Windows 静默失效（假安全） | NTFS ACL + DPAPI |
| wuu | `loop.go` 1735 行、`isBarrierTool` 死枝 | 循环分模块清晰化；死枝要么接要么删 |
| wuu | Goal/Todo/Memory 是插件（机制≠能力混淆） | 不做插件；能力在 Phase 6 内核内建或明确不做 |
| wuu | remote/plugin/subagent/mcp 范围膨胀 | 属"不做"，不移植（§三可逆性三问拒绝带入） |
| wuu | provider 面过宽（5 家+quota+OAuth） | MVP 收敛 1–2 家 |
| EvoFlow | LangGraph 深绑（自愈/循环） | 围自研 run 重写；不引框架 |
| EvoFlow | PolyForm 许可 + docstring 会说谎 | 读设计不搬码；以加载器/仓储层为准 |
| 现 Questor | 契约三件没超前于 plans（本次冲突总根因） | Phase 0 契约先行 + AGENTS §七 升格首条 |
| 现 Questor | 坑编号塌缩、README 过期、21 GOOS 分支 | Phase 0 修 |

## 10. Rejected Alternatives（为何不选）

- **整体 fork wuu 转 Go**：违背"Python 主流"，放弃已趟的 Windows/Electron 知识，且 wuu 正式包 macOS-first。
- **全量搬 EvoFlow Python 后端**：32 万行含大量"不做"的 SaaS/排班、循环是 LangGraph（用户已否）、维护面暴涨 16 倍。
- **先 LangGraph 做出来再剥离**：控制平面+持久化双份重写，隐藏深坑。
- **开全新仓库**：重付 Electron/ui 知识、CI、ADR、GitHub 历史成本，易"两套真相"。故取"现仓内重构分支、代码归档 reference-only"。
- **保留 ui/ 双宿主 / 内核出 workspace diff**：见 §1 四项裁决，已选照 wuu 形态。
- **Docker Desktop 做 Windows 隔离**：重、破坏"同一可见工作区"柱、给个人工具塞重依赖；取逻辑边界→AppContainer。

## 11. 归档与追溯

`.scan-*.md`→`docs/research/`；ADR 0037–0045；`docs/plans/phase-a-mvp.md`；`docs/proposals/`（优化存档）；`docs/research/phase{N}-*.md`（每阶段扫描）。所有阶段提示词与本计划随 git 提交，保证决策链可回溯。

---

## 12. 审计缺口闭合细则（本轮自检补，均为硬约束）

### A、Phase 2 拆细 + A 阶段 done 定义
- **2a（headless 内核）**：engine+tools+limen+session+serve+providers，先无前端，用 CLI/脚本驱动跑通一轮 read→edit→bash→权限门→中断不丢账；`tests/contract` 帧回放绿。**一个窗口只干 2a。**
- **2b（前端+打包）**：照 wuu renderer 重搭壳 + GitService 壳侧 diff + node-pty 终端 + 打包 exe 门槛 1。**一个窗口只干 2b。**
- **A 阶段 done 定义**：= Phase 4 收口「功能完整 exe 装机冒烟全绿 + §1.5 五件齐」（非 Phase 6；Phase 6 是 B 长任务层）。不得以"内核单测绿"冒充"可用产品完成"。

### B、废弃文件清理清单（Phase 0 执行，验“清理干净”）
| 处置 | 对象 |
|---|---|
| **从工作树物理删除（不进新树）** | 旧 `src/questor/*` 内栈（逐目录按 ADR-0044 定性）、旧 `ui/`（被 `desktop/src/renderer` 替）、归档后删根目录 `.scan-*.md` |
| **归档到 reference-only 分支**（从 main 工作树移出，新代码 import 不到） | 上述删除前的快照 + 旧 desktop Electron 壳（知识来源） |
| **保留（不删）** | `docs/adr` 纪律、`docs/specs/pitfalls.md`、`docs/research/`、assets 与图标源、CI/justfile/门禁、`.pre-commit` |
| 清理验收 | `git status` 干净；新 `src/questor/` 只剩按计划重建的模块；工作树无与 `docs/` 矛盾的旧代码 |

### C、窗口交接必读协议（防跨窗口漂移）
新窗口开工前按序加载：① 本计划对应 Phase 小节；② 该阶段需的 `docs/research/*`（扫描产物）；③ `docs/research/port-ledger.md`（已录差异）；④ 上一阶段出口证据（测试输出/commit）；⑤ `AGENTS.md` §〇§二§三；⑥ 本阶段扫描提示词（先扫后写）。**缺一不得开工。**

### D、文档同步出口规则（每阶段必产）
阶段出口除代码+测试外，必须同批改：`port-ledger.md`（新增差异行）+ 对应 `docs/research/behavior-*.md`（或换锚）+ `docs/architecture/modules/<mod>.md` + `CHANGELOG.md` + 新坑入 `pitfalls.md`（先过唯一性断言）。漏改=未达出口。

### E、防复用现有代码机制细则（把§0 硬红线变成可执行）
1. 旧内核/`ui`/`desktop` 从 `src/` 物理移出→新代码**结构上 import 不到**（非靠自觉）。
2. **import-linter / AST 护栏**：断言新 `src/questor/*` 不依赖任何归档模块；负向验证（造一条依赖→红）。
3. **provenance 只能指 `wuu@<commit>`**，禁指 questor 旧文件当来源；`check_specs` 校 provenance 格式。
4. "可参考"定义=只读旧代码/pitfalls 提取知识；**复制旧实现行或"改一行接着用"=违反转向，评审打回**。

## 13. 冲突消解登记表（C0–C21，验“冲突改干净”）
> 逐条勾完、对应契约文档同步改后，才算“改干净”；未执行 Phase 0 前本表全未关。
| ID | 冲突 | 落点 ADR/文档 | 状态 |
|---|---|---|---|
| C0 | diff 壳/核归属 | ADR-0045 + protocol + §1.6 | 已裁双源，ADR待写 |
| C1 | 不照搬全重写 vs 复用优先 | ADR-0037 + AGENTS §二 | AGENTS 已改，ADR待写 |
| C2 | ui 唯一 vs wuu renderer | ADR-0040 + structure + ui/README | 已裁，ADR待写 |
| C3 | JSONL 真相 vs SQLite | ADR-0041 + data-model | 已裁，ADR待写 |
| C4 | 自研词表 vs wuu 105 方法 | ADR-0042 + protocol | 已裁，ADR待写 |
| C5 | Turn⊃Run 层级 + 状态集 | data-model 重写 | 待 Phase0 |
| C6 | 字节 offset vs UTF-16 | data-model 重写 | 待 Phase0 |
| C7 | 官方 SDK vs 不接 SDK | providers ADR 重证 | 待 Phase0 |
| C8 | browser/host 延后 vs wuu 9 反向 | ADR-0042/0030 | 待 Phase0 |
| C9 | 编排方法族 wuu 无 | ADR-0043 后置 | 待 Phase0 |
| C10 | AppContainer 曾被否 | ADR-0039 | 已裁升级，ADR待写 |
| C11/C16 | id 正则/大小写 | data-model（待实测） | 待实测 |
| C12 | cases-*.md 缺失 | ADR-0037 三资产降级或补建 | 待 Phase0 |
| C13 | 模块表合并行 | structure 重写 | 待 Phase0 |
| C14 | scope 清单缺目录 | AGENTS §六 | **已修** |
| C15 | dependabot 含 cargo | structure/dependabot 核 | 待 Phase0 |
| C17 | just 三方口径 | ADR-0009 为准，AGENTS §四 | **AGENTS 已标** |
| C18 | wuu 不作基线 | ADR-0037/0021 改判 | 待 Phase0 |
| C19 | approval/request 弹窗矛盾 | ADR-0042 + overview 裁决 | 待 Phase0 |
| C20 | required 名单缺 job | ADR-0011 更新 | 待 Phase0 |
| C21 | 组名占用未决 | ADR-0001 已关 | **已关** |

## 14. 扫描→阶段可追溯表（证六扫描已综合）
| 扫描产物 | 主要消费它的阶段 |
|---|---|
| `scan-wuu-kernel.md` | §1.5 硬语义清单；Phase 2 扫描提示词；§9 缺陷台账 |
| `scan-wuu-frontend.md` | §1.6 前端归属；Phase 1 接缝；Phase 2 2b |
| `scan-wuu-windows.md` | §1 Windows 沙箱；Phase 2 Windows 策略；Phase 4 AppContainer |
| `scan-evoflow.md` | Phase 6 长任务层 |
| `scan-questor-docs.md` | Phase 0 ADR 表 + AGENTS 逐节处置 + §13 冲突登记 |
| `scan-questor-pitfalls.md` | 全局 B-NN 台账；Phase 0 坑编号修复单元 |
| `phase0-wuu-{protocol-table/sqlite-schema/renderer-assembly}.md` | Phase 0 契约三件重写 + Phase 1 fixtures |
