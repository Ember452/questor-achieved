# Questor 文档去留与改写清单（v2，全文精读版）

扫描对象：`d:\DEVELOP\My-project\questor` 下 questor 的全部 **97 份** markdown（已排除 `node_modules`/`.venv`/`dist`/`.pytest_cache` 等工具产物；含 4 份尚未进版本库的 ADR）。分布：根层 4、`assets` 1、`docs` 79（adr 34＋architecture 19＋specs 16＋notes 6＋plans 3＋README 1）、`evals` 3、`tests` 6、`ui` 1、`.github` 3。
判据基准（优先级）：① 本次转向的新前提；② git／文件系统实测现状；③ wuu 母本的真实形状（`wuu-main` 源码实测）。

> **没看过这个项目的读者**：先读下面的「导读 A–D」，四节读完就能理解全篇；`§0–§6` 是给人动手改文档用的作业层，密度高、大量内部记号，不必从头啃。想复核我的每一条事实，直接看文末「附录：复核命令」。

---

## 导读 A：这是个什么项目，这次改了什么

**Questor 是什么**：一个跑在个人电脑上的「可审计 AI Agent 工作站」——AI 在本地项目里替你干活，它读过哪些文件、跑过哪些命令、改过哪几行全程摊开给你看，随时能插手打断，做完还得拿证据说话（不能只说"我测过了"）。三条承诺有优先级：**可见 → 可干预 → 可验证**。技术形态：Python 后端内核 + Electron/TypeScript 桌面壳，第一平台 Windows。

**这次「方向反转」是什么**——一句话：从"参照三个开源项目自己重写一套"，改成"认准其中一个（wuu）当母本，能搬就搬"。

| 方面 | 旧方向（文档目前写的那套） | 新方向（这次改判的） |
|---|---|---|
| 参照对象 | wuu、EvoFlow、FlowCoder 三个项目并列取用 | **wuu 单锚**；EvoFlow 降为"以后再加的长任务层"规格来源；FlowCoder 退出参照系 |
| 对待参照代码 | **不照搬，全部重新实现**（只借设计和坑清单） | **复用优先**：wuu 的逻辑逐文件翻译/移植 |
| 自家现有代码 | 按里程碑一路建到 M5＋界面线，已算"建成" | **基本废弃重写**，只留踩坑经验 |
| 后端语言 | 不引 Go，纯 Python 自研 | 仍纯 Python，但是把 **wuu 的 Go 逻辑翻成 Python** 跑在 Windows |
| 循环实现 | 自研循环，禁止框架持有裁决权 | **照 wuu 语义手写**，不引 LangGraph（这条新旧一致） |
| Windows 沙箱 | 无 OS 沙箱 → 逻辑边界 + Job Object，如实标注 | 同上，且 **AppContainer 列为后期升级路径**（旧文档里它被明确否决过） |
| 前端 | 自研一套 React 面板体系 | **照 wuu 的形态重搭**（目录归属、组件装配、依赖选型都要重看） |

**三个参照项目分别是谁**（本报告反复提到，不读这段就看不懂后文）：

| 项目 | 位置 | 技术栈 | 在新方向里的地位 | 许可 |
|---|---|---|---|---|
| **wuu** | `wuu-main/`（本工作区内） | Go 内核 + Electron/TS 桌面壳 | **唯一母本**，可移植其代码 | MIT（可移植，须保留许可证与署名） |
| **EvoFlow** | `EvoFlow-main/`（本工作区内） | Python 内核 + Tauri(Rust) 壳 | 只提供"长任务/编排/验收"的规格，**后期再加** | PolyForm Noncommercial（读设计可以，搬码进自有/商用项目不行） |
| **FlowCoder** | 声明在 `D:/DEVELOP/python/FlowCoder`，**不在本工作区**，本次未核验可达 | Python | 退出参照系（但 questor 现有实现的 4 个核心模块当初都以它为蓝本） | 未核 |

**为什么这会造成文档问题**：这个项目把规矩写得很实（有一份当"宪法"的 `AGENTS.md`、36 份决策记录 `docs/adr/`、4 份架构契约文档）。新方向推翻的恰恰是写进宪法和契约里的那些前提，所以**不是"补几句说明"能解决的**——本文就是逐份判"这份文件还留不留、怎么改"的清单。

---

## 导读 B：97 份文档各自是干什么的

| 位置 | 数量 | 这些文件的作用 | 谁在依赖它 |
|---|---|---|---|
| `AGENTS.md` | 1 | 项目"宪法"：定位、复用策略、代码纪律、里程碑出口判据、文档规矩 | 所有会话开工前必读；`docs/adr/README.md` 也引用它 |
| `README.md` | 1 | 对外的项目介绍（给陌生用户看的） | 无（但它自己的内容严重过期） |
| `CHANGELOG.md` / `SECURITY.md` | 2 | 变更账本 / 漏洞披露政策与信任边界 | 外部 |
| `docs/architecture/overview.md` | 1 | **唯一架构入口**：定位、分层、模块职责登记、数据契约草案、权限模型、里程碑表、风险清单 | 几乎每份文档都往回指它 |
| `docs/architecture/structure.md` | 1 | 物理布局：仓库该有哪些目录包、import 允许矩阵、什么时候建哪个目录 | 护栏测试按它的矩阵查依赖方向 |
| `docs/architecture/data-model.md` ★ | 1 | **数据契约真相源**：实体、状态机、存储位置 | 改它必须先改它，代码跟随 |
| `docs/architecture/protocol.md` ★ | 1 | **跨进程协议真相源**：方法表、通知表、错误码 | 前后端 + 桌面壳都靠它；有护栏解析它的表格 |
| `docs/architecture/modules/*.md` | 15 | 单模块设计篇：这个模块为什么这么切、踩了什么坑 | 各模块开工时写 |
| `docs/adr/NNNN-*.md` | 33＋1 索引 | **决策记录**：每条一个决定（选什么、为什么、否决了什么、什么时候要重看）。索引文件带编号状态表 | 宪法 §七 规定改契约/换选型/砍范围必须先写 ADR |
| `docs/plans/development-plan.md` | 1 | **阶段计划**：M0–M8＋Phase U＋Phase E 各期做什么、读参照项目哪些目录、出口判据 | 每个里程碑收口要勾销它 |
| `docs/plans/2026-10-13-phase-u-*` | 2 | 一份 3327 行的界面/桌面壳实施计划（已做完）＋它的出口记录 | 坑编号 B-103~B-118 的出处 |
| `docs/specs/behavior-*.md` | 14 | **参照实现的"行为规格表"**：输入→输出→边界行为→证据行号→"Questor 采纳决定"；文件名后缀标来源 | 模块设计篇拿它当蓝本；坑目录拿它同步 |
| `docs/specs/pitfalls.md` | 1 | **坑台账**：121 条编号 `B-01`–`B-121`，每条有归属模块、证据、对应测试、状态 | 宪法要求"每个 B-NN 对应一个真实存在的测试" |
| `docs/notes/*.md` | 6 | 机制解释笔记（"这条链路实际怎么跑通"），带锚点，过期会被 CI 判红 | CI 脚本 `check_notes` |
| `ui/README.md`、`tests/*/README.md`、`evals/*/README.md` | 10 | 前端地图 / 6 类测试目录各自断言什么 / 评测跑分规矩与结果区 | 结构文档与 CI 引用 |
| `.github/` 下 3 份模板 | 3 | issue 与 PR 的填写模板（对外贡献者的行为契约） | `ADR-0011`、`structure §9` 直接引用它们 |
| `assets/README.md`、`docs/README.md` | 2 | 图标源与占位妥协说明 / 全仓文档索引表 | — |
| `desktop/` | **0** | （实测**没有任何 markdown**——壳的知识全散在笔记和那份 3327 行计划里） | — |

---

## 导读 C：记号与术语（看不懂表格时查这里）

**四种判定**：`KEEP` 仍准确不用改｜`UPDATE` 方向成立但有过时处（正文标了具体哪一节/哪一行）｜`REWRITE` 核心前提被这次转向推翻，整篇重写｜`DELETE` 可扔（本文同时说明扔前必须先把哪段有效内容搬走）。

| 记号 | 含义 |
|---|---|
| `§二`／`§五` | 指 `AGENTS.md` 的章节号（它用中文序号：§一定位、§二复用策略、§三语义来源表、§四代码纪律、§五出口判据、§六 Git、§七文档规矩） |
| `L66` | 该文件的第 66 行。本文所有行号来自实际读取，可逐条核对 |
| `ADR-0037` | 决策记录编号；`0037+` 是本文建议**新增**的编号（现有最大是 0036） |
| `B-NN` | 坑台账里的条目编号（`pitfalls.md`） |
| `M0–M8` | 里程碑编号（内核建设阶段）；`U`／`Phase U`＝后来插进 M5 与 M6 之间的界面/桌面壳主线；`E`＝界面与生态加料阶段 |
| `A 阶段 MVP` | 新方向下"先做出可用产品"的交付范围，用来替代 M 系列骨架 |
| **`契约三件`** ★ | 该项目内部术语：**协议、数据模型、模块边界**。宪法规定这三件改动最敏感，必须"先改文档、代码跟随"，且要超前于当期里程碑 |
| `母本` | 指 wuu——即"照它做"的那个项目 |
| `C0`／`C3`… | **本文第 3.1 节的"矛盾清单"编号**，不是文件里的东西。`C0` 是我最后补的那条最要命的冲突 |
| `-fc` / `-ef` / `-wuu` | 行为规格文件名的来源后缀：FlowCoder / EvoFlow / wuu |
| `provenance 注记` | 代码或文档头部写的"这段是从哪个项目的哪个文件来的"来源声明 |

---

## 导读 D：只需要记住这四条

前面三个导读解决"读得懂后文"，这一节解决"只想要结论"。下面这四条是全文唯一**承重**的判断：其余逐文档的 KEEP/UPDATE/REWRITE 基本要么是这四条的下游，要么只是单纯的内容过期。想快，读完这四条就可以走。

**① 最难绕过的冲突：Review 面板的 git diff，该由内核算还是由桌面壳算（C0）**
项目现有的规矩是：AI 每次改文件时顺手算出 diff、存进会话记录，界面只能去取这份"当时算好的"记录，**并且壳必须是个空壳、不许有任何业务判断**。而母本 wuu 的实际做法是：桌面壳的 Electron 主进程里有一个 `GitService`，**自己跑 `git diff`** 把工作区改了什么都算出来，内核协议里压根没有 `review/turn_diff` 这种方法。
→ **要照母本重搭界面，就必然撞破"壳不含业务判断"或"数据只从内核来"这两条规矩之一。** 更麻烦的是：内核算"当时那份"是项目自己定的，而母本那套恰好更能回答"它说改完了，盘上到底变成什么"（AI 跑一条格式化命令、跑一条 `git apply` 时，内核那份是空的）。这条必须最先裁决，否则后面所有协议和前端文档都没法定稿。

**② 会话记录到底谁说了算（C3）**
契约文档钉死了"会话正文的 JSONL 文件是唯一真相源，SQLite 只能当可丢弃的搜索索引"，而且这个立场还被**四份决策记录拿去当否决别人的理由**（比如"不许用 SQLite 存编排实体""不许引数据库依赖"）。母本 wuu 恰恰相反：它的会话权威库就是 SQLite（`session_messages`、`session_controls` 等表），连 AI 插话的收件箱和待处理消息都落在 SQLite 里——**这个证据就写在项目自己的规格文件里，只是没人去读正文**。
→ 移植母本的会话层之前必须先裁这一条，否则每份依赖它的文档都建在会移动的地上。

**③ 前端代码该放在哪个目录（C2）**
现在的规矩是"只有一套前端代码，住在 `ui/`，桌面壳不持前端代码"，并已被固化成一条硬性纪律。母本的渲染层却住在 `desktop/src/renderer/`，没有独立的 `ui/` 包，而且它连依赖选型都不同（母本不用 `zustand`、不用 `@pierre/diffs`—— questor 的这两个选型理由是"另一个参照项目实测在用"）。
→ 这条一改，会连带 5 份决策记录 + 4 份架构/前端文档 + 一条已固化的开发规范一起重裁。

**④ 一个跟方向无关、但必须先修的质量缺陷（§3.3）**
5 份"行为规格"文件里的坑编号系统性对不上：最严重的是权限门那份，**文末 9 行全标成同一个编号**（而权威台账里它们本来各有编号），文件自己还写着"编号已对齐"；另一份里同一编号出现两次、还跟别的模块撞号。原因是做过一次全局重编号，只改了表格没改正文，而核查脚本只检查"引用的文件是否存在"，不检查编号唯一性。
→ 后果很具体：项目的硬规矩是"每个坑编号必须对应一个真实存在的测试"，编号塌成一条，就意味着**权限门那 9 条实测细节无法各自配对测试**——而权限门恰恰是接下来照母本移植的第一个模块。

**建议阅读路径**：只想知道结论 → 读本节四条；要动手改文档 → 读导读 A–C，然后直接看 `§5 落笔顺序` 与 `§4 AGENTS.md 逐节处置`；要复核我的证据 → `§1 实测基准`＋文末`附录：复核命令`；想知道我哪里可能还会错 → `§6 本轮仍未读完的部分`。

---

## 0. v1 → v2 的修订说明（先记账，再给结论）

v1 版为赶进度走了两条捷径，**已被本轮全文精读推翻**，逐条列出：

| # | v1 的做法 | 精读后的结果 |
|---|---|---|
| R1 | 33 份 ADR 只用 `Select-String` 抓「标题＋状态＋结论前 4 行」，其中 32 份没读正文 | 全部 34 份读完后，**7 份判定改判**：`0001`/`0008`/`0011` KEEP→UPDATE、`0024`/`0036` DELETE→UPDATE（标 superseded）、`0028` KEEP→UPDATE、`0031`/`0032` 由"整份 UPDATE/KEEP"改为**拆分改判**（结论级取舍不同） |
| R2 | 14 份 behavior 规格只读标题＋来源行，按 `-fc`/`-ef` 后缀判了 6 份 DELETE | 全读后 **6 份里 5 份不该删**：它们含"Questor 采纳决定"节（＝已付费的工程裁决，与母本无关）。仅 `mode_map.md` 一类真正作废 |
| R3 | `modules/{tools,providers,serve}.md`、`SECURITY.md`、`CHANGELOG.md`、`evals/README.md`、`notes/*` 被终端截断或只取前 N 行，却当作已读 | 已全部补读；`SECURITY.md` 的 KEEP 经核实成立 |
| R4 | 断言"ADR-0035 可直接按母本定案（wuu Review 显示真 git diff）" | **说错了一半**：wuu 的 diff 是**两套并存且分工不同**，且采集点在**桌面壳主进程**，不在内核。见 C0 |
| R5 | C16（id 正则 vs wuu `THREAD_ID`）是文档样例推断，未实测 | 已从矛盾清单降级为"待实测项" |
| **R6** | 扫盘用了 `**/*.md` 形式的 glob，**它不返回点目录**，导致 `.github/` 下 3 份模板整组漏掉；报告头也因此写成"94 份" | 已用 `Get-ChildItem -Recurse -Include *.md` 重测真实总数＝**97 份**，补读并补判 3 份 `.github/*.md`（见 §2.7）。**这是本轮第三处"以为扫全了其实没扫全"**，教训已写进附录：计数不能只信一种工具 |

**精读额外挖出的两类问题，是 v1 不可能发现的**：① 一条足以决定架构走向的顶级冲突 C0（git/diff 职责在壳还是核）；② 5 份规格的**坑编号系统性错位**（门禁抓不到）。

仍未读完的部分诚实列在第六节。

---

## 1. 实测基准（本报告所有"母本实际是…"的依据）

- **questor 现状**：`src/questor/` 24 个模块目录；`desktop/` 有 Electron 壳（main/preload/renderer + 33 条 vitest）；`ui/src/rpc/generated/` 有 3 份 `.d.ts`；`tests/` unit 42／integration 14／architecture 13／adversarial 10／e2e 3。
- **git 现状**：`HEAD=51a652e` 领先 `origin/main=cf527d9` 3 个 commit；`CHANGELOG.md`、`docs/adr/README.md`、`docs/plans/development-plan.md` **已改未提交**，`docs/adr/0033~0036` **未跟踪**。
- **wuu 协议**：`internal/appserver/protocol.go` 实测 105 个方法/通知常量；**无** `review/*`、`diff/*`、`task/*`、`goal/*`、`schedule/*`、`evidence/*` 族；只有 `workspace/list`、`workspace/state/cleanup`。
- **wuu 存储**：`internal/session/session.go` 建 SQLite 表 `sessions`/`session_folders`/`session_messages`/`session_controls`；`session/inbox.go` 的插话幂等用 `INSERT OR IGNORE ... client_id` 打在 `session_messages` 上，`SettleInbox` 用 `ON CONFLICT(client_id) DO UPDATE`；`held_user_work.go` 是**整表 delete+insert 事务**（证据在 questor 自己的 `behavior-protocol-wuu.md` §3/§4 里，v1 没读）。`internal/agentthread/store.go` 另有一套 JSONL＋securefs＋storelock。
- **wuu 的 diff（C0 关键）**：`desktop/src/main/gitService.ts` 在 **Electron 主进程**里跑 git——`gitDiffStats(root, true)`（含 untracked）、`gitDiffOutput(cwd, base, relativePaths)`、`gitDiffBase(root)`、`GitChangeFile[]`、commit／branches／worktree roots 全在此。内核侧 `internal/tools/diff.go` 是 `computeDiff(oldText,newText)` 的**工具时刻 unified diff**（供模型与工具结果用）。
- **wuu 前端**：渲染层在 `desktop/src/renderer/`（含 `ui/`、`styles/`、`i18n/`、`plugins/`），共享在 `clients/core`，契约在 `packages/protocol`；**没有独立 `ui/` 包**。`desktop/package.json` 有 `@xterm/xterm`／`react@19`／`react-markdown`／`lucide-react`，**没有** `zustand`／`@pierre/diffs`／`shiki`／`@xyflow/react`。`desktop/vitest.config.ts` 存在（vitest 与母本一致）。
- **wuu 循环与许可**：`internal/loopdriver` + `internal/agent/loop.go`；引擎契约真实符号在 `internal/agentengine/agentengine.go`（`Descriptor/OpenRequest/ResumeRequest/TurnInput/EventSink/ApprovalHandler/TurnResult/Session`）；Windows 走 `processsandbox/sandbox_other.go`＝无 OS 沙箱、fail closed；MIT。

---

## 2. 逐文档分类总表

★＝属**契约三件**（协议／数据模型／模块边界）。

### 2.1 根层与 docs 索引（6）

| 路径 | 分类 | 理由（含具体过时位置） |
|---|---|---|
| `AGENTS.md` | **REWRITE** | §二 L66「不照搬代码，全部重写」、§三 L110「engine＝本项目自研」、§五 出口判据、§七 触发清单四处前提被推翻；**§四 L140-141「本机拿不到 just」已被 ADR-0009 的实测更新否证（C17）**；§六 L220-222 scope 清单缺 `desktop`/`ui`/`sessiontrace`/`worktree`/`testenv`（C14）。逐节处置见第 5 节 |
| `README.md` | UPDATE | L12「Nothing is runnable yet／holds naming and reuse decisions only」＋L38「`src/questor/` empty until first milestone」被 24 模块＋Electron 壳否证；L21-22 的"接管页面／任意历史消息分叉"超出 A 阶段 MVP |
| `CHANGELOG.md` | KEEP | 历史账本，append-only；165 行全读后无失真断言。唯一动作：转向落地时必须补一条 `Changed/Removed` 记录代码废弃与母本改判，否则账本给出"方向未变"的假信号 |
| `SECURITY.md` | KEEP | 全文 35 行已核：local-first＋stdio＋127.0.0.1 无鉴权＋limen 单门＋敏感守卫三档全开＋transcript append-only，五条信任边界在转向后全部成立；引用 overview §9／ADR-0007 的指针仍对 |
| `docs/README.md` | UPDATE | 文档地图缺 `architecture/{data-model,protocol}`、缺两份 phase-u 计划、缺 CHANGELOG；末行「specs/（M1 落盘）：行为规格表、坑目录、**用例清单**」中的用例清单实际一份都不存在（C12） |
| `assets/README.md` | UPDATE | icon.ico 妥协与再生成命令（照 wuu `scripts/generate-icon.ts`）仍有效；但通篇以「Phase U / B7 / Task B7 commit」为坐标，重搭后任务编号体系失效 |

### 2.2 `docs/architecture/` 四件 ★＋15 份模块篇

| 路径 | 分类 | 理由 |
|---|---|---|
| `architecture/overview.md` ★ | **REWRITE** | §2 L36「总策略：不照搬任何代码，全部重新实现」＋L41「Go→Python 不存在迁移，只有重实现」＝转向正面对立面；§3 L65 (b)「必须新写」；§4 L127「模型调用用官方 SDK」（C7）；§6 参照来源列挂 FlowCoder/EvoFlow；§11 L309-310「**wuu 不作基线**」（C18）；§12 M 系列整表；§13 未决项 1 已被转向回答、未决项 4「组名占用尚未核查」与 ADR-0001 L84「已实测不可得」矛盾（C21）；§14「GUI 能力必须经协议可达」这道门会被 C0 撞破；§15 L391 风险首行前提消失 |
| `architecture/structure.md` ★ | **REWRITE** | §2 L68-74＋§7 L202-205 把 `ui/` 定为唯一前端代码源、`desktop/` 只包壳（C2，与 wuu 形态相反）；§6 声称契约住 `schemas/{app_server,model,orchestration}/`，实测是 `schemas/*.py` 六个模块；§11「当前实际状态」写 `adr×2／specs×13／plans×1`，实为 34/16/3；自相矛盾：§2 L88「cargo 随 Tauri 撤下」vs §9 L294「dependabot 四类含 cargo」（C15）；§3 L101-104「一行一个模块、可脚本报奇偶校验」vs L119/L130 两处合并行（C13） |
| `architecture/data-model.md` ★ | **REWRITE** | §2 层级 `Turn ⊃ Run` vs wuu「Run 记录 ordered turns」（C5）；§3.1 状态机缺 wuu 的 `accepted`/`interrupted`/`timed_out`（C5）；§4 L238 选中定位「字节 offset」vs wuu「UTF-16 code units in rendered DOM」（C6）；§5 L244-245 JSONL 唯一真相源＋SQLite 可丢弃索引 vs wuu SQLite 权威库＋inbox/held_work 皆在 SQLite（C3）；§3.2/3.3/3.4 编排/验收/证据属后期 EvoFlow 层（C9） |
| `architecture/protocol.md` ★ | **REWRITE** | 方法名大面积不同源：`thread/create`(wuu `thread/start`)、`thread/show`(`thread/resume`)、`run/stop`(`run/interrupt`)、缺 `turn/started|completed|error`、`run/status`(wuu `run/updated`)、`delta`/`replace` 未嵌在 `item/agentMessage/` 下、`content/read`(wuu `thread/content/read`)、§5 `deferred_content`(wuu `deferred_notification_content`)、`max_concurrency`(wuu `max_parallel`)、`host:{os,arch}`(wuu `runtime_host`)；§3 编排方法族 21 个 wuu 无（C9）；§6 L124 `browser/host` 标 M8 延后 vs wuu 9 个 `browser/*` 反向方法（C8）；§6 `approval/request` 与 `overview §9`「不提供 per-command 弹窗」互斥（C19）；**wuu 根本没有 `review/turn_diff`——见 C0** |
| `modules/engine.md` ★ | **REWRITE** | provenance `Reimplements FlowCoder agent/{core,events,budget,output_recovery,conversation}.py`；母本是 wuu `loopdriver`＋`agent/loop.go`，「loop.py ≤80 行」「B-03 并行批不清零」等决策全挂 FlowCoder 证据 |
| `modules/tools.md` | **REWRITE** | provenance `Reimplements FlowCoder tools/{base,registry,file_state_cache}.py`；母本 `internal/tools`(122 文件)。Job Object/`sandboxed:false` 段与母本一致可留 |
| `modules/context.md` | **REWRITE** | provenance `Reimplements FlowCoder context/{manager,tool_results,replacement,recovery}.py`，蓝本直指 `behavior-context-fc.md`；母本 `internal/context`+`contextbudget`+`compact` |
| `modules/providers.md` | **REWRITE** | provenance `Reimplements FlowCoder client/{core,resilience,errors,error_mapping}.py`；母本 `internal/providers`(62 文件)。B-81~B-84 的真实端点观测与母本无关，重写时原样保留 |
| `modules/limen.md` ★ | UPDATE | 主锚正确（`boundary.go`+`sensitive_paths.go`）；但「六层→三档映射表」整节以 FlowCoder 六层为坐标系，且与 `behavior-limen-wuu.md`（自称权威蓝本）并列为两套来源——先修 limen 坑编号塌缩（§4.2），再删六层映射节改按 boundary.go 移植 |
| `modules/gesta.md` ★ | UPDATE | 锚 `agentthread/store.go` 经核实准确；热路径三件套（增量摘要/游标句柄/全局锁）是可复用经验；**缺一条必须补的裁决**：wuu 的会话权威库是 SQLite，本篇「SQLite FTS 按 B-46 属 M4、本期 JSON 索引」正与母本相反（C3→ADR-0041） |
| `modules/serve.md` ★ | UPDATE | 「GUI 能力必须经协议可达」「不 import cli」「方法名对着 protocol.md 表判」转向后更值钱；但标题仍写「M2.3 雏形，未完」，而 `app_server.py` 已 1189 行；`approval/request`、`thread/show`、`files/*`、`review/*` 随 protocol 重写联动 |
| `modules/state.md` | UPDATE | 锚 `statepath/securefs/storelock` 正确；provenance 措辞「未搬代码」须按 ADR-0037 改为「按 wuu 移植」 |
| `modules/config.md` | UPDATE | 锚 `settings_layer.go` 正确；三层模型（用户/项目共享/项目本地）须对齐 wuu 的 workspace＋conversation 双作用域（`config/model/update`） |
| `modules/cli.md` | UPDATE | 锚 `cmd/wuu` 正确；「workspace id 自算 sha256[:16] 是已知重复、M3 必删」这条挂账要随新计划重定时点 |
| `modules/workspaces.md` | UPDATE | 锚正确；UNC/映射盘符「两个 id、M2.1 不处理」在 Windows 单平台定位下从边缘升级为必办 |
| `modules/capability.md` | UPDATE | 旗标清单含 `browser_panel`/`web_host`/`im_channels`/`containers`，须按 A 阶段裁剪；「stdlib only」裁决可留 |
| `modules/prompts.md` | UPDATE | 锚 wuu `prompts/`；须补「wuu prompts 带独立 `LICENSE-Codex`＋`NOTICE`」这一移植署名义务（structure §1 已记但本篇没接） |
| `modules/secrets.md` | UPDATE | 锚 `credentialstore`；keyring→明文回落的诚实告警设计可原样移植 |
| `modules/version.md` | UPDATE | 锚 `VERSION`+`internal/version`；CalVer 与 version-sync 对齐需重跑 |

### 2.3 `docs/adr/`（34，全部读完全文）

| 路径 | 分类 | 理由（改判处已注明） |
|---|---|---|
| `adr/README.md` | UPDATE | L33 索引行「0002 全量重写策略与 provenance 纪律｜planned」正是被推翻那条，须标 superseded 并指向新 ADR；0002/0003/0004 至今无正文，内容散在 overview §2/§3 与 AGENTS §三 |
| `0001-naming-and-availability` | **UPDATE**（v1 误判 KEEP） | 命名/占用核查/组织名不可得均可留；但**模块命名表 L64 写着「engine＝自研 agent 循环」**——与 §三 同源的"自研"前提在这里也有一份，须随 ADR-0038 改；L72 `orchestration`「Plan→执行→验收/打回」随长任务层后置标注 |
| `0005-workspace-revision` ★ | **REWRITE 级改判**（v1 只给 UPDATE） | 结论 2「写时算 diff」＋结论 4「files/read 绑定」＋「UI 层锁死：ReviewPanel 只能经 `review/turn_diff`，不得拉 `files/read` 重算」＋**被否决项③「每次读文件都算 diff 与 HEAD 比较（走 git diff）」**——被否决的这条正是 wuu 母本的实际做法（C0）。ADR-0035 定案时本 ADR 必须同步改判，不是补注 |
| `0006-desktop-shell-and-browser-panel` | UPDATE | 结论 1/3 已被 0030 取代（文中已带「修订记录」范式，新改判应沿用该写法）；**结论 2「ui/ 同时喂两宿主」被 C2 直击**；L21-26「为什么不选 Electron（wuu 的方案）」整段已成历史论证，需标"已翻转"；L42「Windows 无 PTY 退回 pipe 的语义（wuu 明写）我们照抄」的"照抄"措辞与新纪律反而一致，不必改 |
| `0007-windows-sandbox` | UPDATE | 结论 1/2/3 与新方向逐字一致（转向后最硬的资产）；但**「被否决的选项」第 4 条白纸黑字否决 AppContainer**（L60），新方向要把它当升级路径→必须新立 ADR-0039 走它的失效条件 1 或显式 supersede 该条 |
| `0008-gate-scope-and-citation-checks` | **UPDATE**（v1 误判 KEEP） | 门禁范围/四件套/引用核查均可留；但 L20 把 `QUESTOR_REF_WUU`/`QUESTOR_REF_EVOFLOW`/`QUESTOR_REF_FLOWCODER` **三仓根**写进工具约定，单锚后两个参照仓退出；且它「只校文件存在性与形式」的设计正是坑编号错位（§4.2）漏网的根因，应补一条唯一性断言 |
| `0009-gate-entry-just` | KEEP | 全文读完：它才是**正确**的那一份——L28-31「已装上 1.58.0」、Windows 上 just 默认 `sh` 的新坑、CI 不调 just 的理由。过期的是 AGENTS §四 与 development-plan L84（C17） |
| `0010-notes-anchored-and-expiring` | KEEP | 锚点化＋过期即删＋预测→验证；docs 锚只查存在、浅克隆拒跑，均与方向无关 |
| `0011-branch-protection-mode` | **UPDATE**（v1 误判 KEEP） | required 名单表（L15-22）只列 `lint/test×2/arch/gen-check/audit`；实测 `.github/workflows/` 已有 5 个 workflow、job 含 **`desktop`**（B8 落）与 **`docs`**（M4e 落）未入表——**违反本 ADR 自己的失效条件 ③「新增 workflow 或 job 改名 → 本表与 GitHub 设置必须同时更新（本表是唯一真相）」** |
| `0012-module-dependency-rulings` ★ | UPDATE | 两条结论（gesta 不引 engine、capability 不引 config）与「让叙述服从可执行断言」的元理由都可留；但矩阵将随 structure §5 重排，两处结论需重跑一遍 |
| `0013-m2-foundation-dependencies` | UPDATE | pydantic/keyring/import-linter 三件保留；被否决项「SQLAlchemy 等一并引入」的理由是「SQLite 索引推迟、无第二使用者」——若 C3 改判为 SQLite 权威，这条否决直接反转，必须重裁 |
| `0014-run-status-queued-cancelled` ★ | UPDATE | 只补了 `queued→cancelled`；wuu 状态集是 `accepted/running/completed/failed/interrupted/timed_out/cancelled`，本 ADR 覆盖不全，随 data-model 重写重裁 |
| `0015-pywin32-job-object` | KEEP | 与新方向「逻辑边界＋Job Object」完全一致；L25「用维护中的绑定比重新发明编组更符合复用三分法」在复用优先下更强。唯一跟动：它引用的「§二 (a) 类」编号随 ADR-0037 改名需同步 |
| `0016-providers-wire-layer` | UPDATE | 与 overview §4 L127「官方 SDK」互斥（C7）；L30/L44 用 FlowCoder「SDK 外面又包 ResilientClient」作反证——母本退出后论证需按 wuu `internal/providers` 实测重证，不能悬空 |
| `0017-context-records-in-transcript` ★ | UPDATE | L28 的理由链**直接挂在「data-model §5 已定死 JSONL 唯一真相源」上**；C3 一改判，「正文记录优先于 sidecar」的取舍要重述；被否决项「sidecar（照 FlowCoder）」的编号证据亦需复核 |
| `0018-prompt-blocks-and-cache-prefix` | UPDATE | **转向后论证方式已经对了的一份**：L31-34/L44-45 直接引 wuu `internal/context/context.go#L1-L8/L56-58/L66-80` 为形状来源；只需删 L41-43/L52-53 两处拿 FlowCoder 当反证的句子 |
| `0019-generated-artifacts-mechanical-check` | UPDATE | 已有 0030 的修订记录范式；但 C2 改判后 `ui/src/rpc/generated/` 路径、`npm --prefix ui`、`ui/devDependencies` 里的 `json-schema-to-typescript` 全部连带，需第三轮修订记录 |
| `0020-interface-surfaces-moved-earlier` | UPDATE | 「视图注册表提前」的思路可留；但注册表形状是按 evopanel 的 `ToolCallBlocks/` 面板装配判定的，照 wuu renderer 重搭前须先实测 wuu 的组件装配方式，否则提前锁死一个错接口 |
| `0021-m2-exit-split-evals-deferred` | UPDATE | 判据可执行性三口径（`not_in_baseline`/`not_comparable`/映射表）可留；但 L41 被否决项写着「**拿 wuu 当基线……不改**」（C18）——新方向恰好要改这条，属显式改判，不能只润色 |
| `0022-serve-ws-starlette-uvicorn` | UPDATE | 「不引 FastAPI、不引 aiohttp」的理由（handler 形状唯一、GUI 能力经协议可达）仍成立；但需先确认 A 阶段还有没有网页宿主的使用者；L48 引用的「§二 (a) 类」需随改名跟动 |
| `0023-m3-transport-ws-only` | UPDATE | 三问判据的示范文本可留；但 L38 用「反向请求 `approval/request` 需要双向」作为不做纯 SSE 的理由——该反向请求本身与 overview §9 冲突（C19），论据要重找 |
| `0024-desktop-shell-deferred-to-m4` | UPDATE（v1 判 DELETE，**改判**） | 全文读完：它自带「修订记录」段（L67-74）已记录被 0030 两次翻转，正文的理由（壳与内核并行＝两条学习曲线）与代价段仍有史料价值；且 L33 把 `runtime_state.json`+`lifecycle_lock` 归因为「**EvoFlow `backend.rs` 的设计决定沿用**」——而 Phase U B4 实际改锚 wuu，这条归因已过期需改。做法：状态标 `superseded by 0030`，保留文件 |
| `0025-orchestration-domain-and-store` ★ | UPDATE | 后置标注；**新发现**：被否决项 L34「用 SQLite 存编排实体」的理由是「§7 已定 SQLite 不承载真相源」——C3 改判会连带翻转这条否决，属连锁改判点 |
| `0026-vigilia-scheduling-and-sweep` | UPDATE | 后置标注；但 L28「EvoFlow 自愈清扫绑在框架 runs API 上、换底座即失效，故必须自建状态机清扫」这条在"不引 LangGraph"下**更强**，不该跟着后置；调度语义应换锚 wuu `internal/schedule` 而非仅挂 EvoFlow |
| `0027-evidence-minimal-and-export-interface` | UPDATE | 拆开重裁：并排核对＋`recorded_output_ref` 可追溯属"可验证柱"，留 A 阶段；但 L14 把 `export` 形状定在 `evidence/get`＋`evidence/reported` 上，这两个方法 wuu 协议无（C9/C4），"接口先行"的落点随 protocol 重写悬空 |
| `0028-protocol-additive-evolution` ★ | **UPDATE**（v1 判 KEEP） | 加性演进规则本身可留；但 L17-19 明写「M4 的 `task/*`/`goal/*`/`schedule/*`/`evidence/get` 与 5 个通知族**按本规则不升版本、直接追加进 v0.1**」——后置这些能力后，它们仍"合法地"挂在冻结版本上，客户端探测不到无实现。须补一条"族级停用"规则或随 ADR-0042 重划 |
| `0029-acceptance-loop-evidence-writepoint` | UPDATE | 结论 3「声称必须显式绑 `tool_use_id`」＋被否决项「只存布尔／启发式抽取」是纯可验证柱裁决，必须留；结论 1/2/4 随编排后置；L26 残留「桌面壳 `desktop/src-tauri`」的 Tauri 字样需清 |
| `0030-desktop-shell-electron-and-ui-track` | UPDATE | 改判 Electron 与转向同向、仍是有效大决策；但**结论 4「`ui/`、serve 协议、schemas、注册表全部不变」正是本次要打破的那条**；L33-34「`desktop/` 当前 0 文件、无沉没代码」已被 B2~B9 实现推翻；L31 用「§二 (c) 类：搬设计、代码新写」论证换壳低风险，该类别定义随 ADR-0037 变；**失效条件 2「想往壳里塞业务判断→按 R1/§三 拦下」将与 C0 正面相撞** |
| `0031-ui-diff-renderer-and-vitest` | UPDATE（**拆分改判**） | 结论 1（`@pierre/diffs`）的**唯一**理由是 L18「evopanel 实测在用」、被否决项 L31 也用「无 evopanel 背书」作依据——母本退出后该根据整体消失，须重裁（wuu desktop 无此依赖）；结论 2/3（vitest＋happy-dom＋不引 jest）与母本无关且 wuu 实测用 vitest，保留 |
| `0032-electron-shell-and-toolchain` | **UPDATE**（v1 误判 KEEP） | 结论 1（electron/electron-vite/electron-builder）与母本同款、结论 2（不引 `@tauri-apps/*`/`electron-store`）与 L45 否决 `pkg/nexe` 保持「`uv run questor serve stdio`」均可留；但**结论 3「renderer 不复制 ui/ 源码、root 指 `../ui`」是 ADR-0040 直击条款**，结论 4 的双 lockfile 理由（`ui/`＋`desktop/` 两棵树）随 `ui/` 撤销而需重写 |
| `0033-engine-contract-as-m6-entry-gate` ★ | UPDATE | 「契约未对内建引擎跑绿不许写适配器」的门禁思路要留；但契约形状 L12-13 写 `RunTurn/Interrupt/Close`，与母本 `agentengine` 真实符号不一致；且 L27-31 的论证（`engine/loop.py` 778 行已直接 import gesta/prompts、逆向成本单调上升）在重写后归零——**转向恰好是把契约一次定对的最佳时点**，建议改为随重写落地 |
| `0034-longrun-driver-host-ownership` | UPDATE（部分撤回） | 议题（stdio sidecar 挂不挂 `LongRunDriver`）随长任务后置；但**须拆开**：L16/L22/L52 的 Goal/看板前提可撤回，而 L17 实测结论「`ui/src` 与 `desktop/src` 全仓无一处消费 `issues`/`needs_setup`」是可见柱缺口，与长任务无关，应独立成条继续跟 |
| `0035-review-diff-authoritative-source` ★ | UPDATE（**须新增方案 D**） | v1 说"直接按母本定案"是错的：母本是**双源分工**——内核 `internal/tools/diff.go` 出工具时刻 diff、桌面壳 `desktop/src/main/gitService.ts` 出工作区 git diff，**采集点在壳**。本 ADR 的方案 A 把 git 采集放内核，两个候选都不是母本形态。必须补 **方案 D：照 wuu——workspace 级 diff 归壳侧 GitService、内核不提供 `review/turn_diff`**，并说明它撞破 overview §14「GUI 能力必须经协议可达」与 ADR-0030 失效条件 2。`behavior-review-fidelity-wuu.md` §0 已把这一差异诚实标注（「只借视觉与动效，不借工作区语义」），是本 ADR 的现成输入 |
| `0036-app-server-split-timing` | UPDATE（v1 判 DELETE，**改判**） | 「1189 行何时拆」的时机问题随重写消失，但它的**被否决项 3「拆成按传输分文件＝两套方法表」正是重写 `app_server` 时必须遵守的约束**，L13-17 记录的「编排域 `*_transition`/`_gate_or_deny` 住在传输层，使 `test_*_single_entry` 出现例外面」是重写要避的形状缺陷。做法：状态标 `withdrawn（随重写作废）`，正文保留作重写输入 |

### 2.4 `docs/plans/`（3）

| 路径 | 分类 | 理由 |
|---|---|---|
| `plans/development-plan.md` | **REWRITE** | L24「参照纪律：扫描式重写，不拷贝代码」＝转向对立面；M0–M8＋U＋E 整张阶段结构与各期"已完成"勾销失去坐标系；M1/M2/M3/M4/M5/M7/M8 阅读地图（L107/L197/L255/L333/L373/L469）逐条挂 FlowCoder/EvoFlow；L207 基线口径（C18）；M6 契约形状与母本 `agentengine` 不一致；L4 自称"基于 structure v0.3"而实际 v0.5（自身对齐纪律失效）；**L84-87「just 本机装不上」与 ADR-0009 冲突（C17）** |
| `plans/2026-10-13-phase-u-ui-and-electron-shell.md` | UPDATE（转历史档案） | 3327 行已执行完的实施计划。**不可删**：其「从 wuu 桌面壳借鉴清单」8 处锚点＋「不采纳项及原因」正是转向要求的范式，且是 B-108~B-118 的唯一出处。但正文前提「`ui/` 构建产物原封搬进 renderer」「后端零改动」「Option A 为唯一方案」随 C2 改判失效，须加头部声明「历史执行记录，不得再作实现依据」，否则下个会话会照它继续铺面板 |
| `plans/2026-10-13-phase-u-completion.md` | UPDATE | 出口记录本身诚实准确；但它挂着的 `[real-terminal]` 步 1~4、`npm run package` 产 exe、`extraResources: []` 无核、可干预柱还原度等 pending，在代码废弃后全部作废——不显式撤销就留下"有人欠验收"的假账 |

### 2.5 `docs/specs/`（16，全部读完全文）

| 路径 | 分类 | 理由 |
|---|---|---|
| `specs/README.md` | UPDATE | L7-9 三仓并列为来源、L15 `fc`/`ef` 后缀规则与单锚冲突；§三 `cases-*.md` 模板对应的资产一份不存在（C12）；**§二"编号连续不复用、不适用标 moot"正是下面 §4.2 那批错位条目的应然规则，需补一条可机械检测的唯一性断言** |
| `specs/pitfalls.md` | KEEP | 台账型文档；121 条编号连续、每条有归属、状态机 `open/covered/moot` 齐；权威归属表本身**没有**重复编号（已抽查 B-32..B-54 全部唯一）——问题在各 spec 的内联引用，不在这份 |
| `behavior-limen-wuu.md` | **UPDATE（先修编号塌缩）** | 内容与母本最高价值（`{Enforce,AllowMutations,Guards}` 三构造器、mutates 的 ToolKind 分类、Guard 不得 ask、approvefor 硬拒三件与五态、settings strip、processsandbox fail closed）；但**文末 9 行坑全部标 `B-50`**、正文 7 处也全标 B-50，而 pitfalls 里这些语义本有 B-50/51/52/53/54 等独立编号——L94 还自述「编号已对齐 pitfalls.md」，实为把 9 条塌成 1 号（§4.2）。它自称"权威蓝本"却与 `behavior-permissions-fc.md`（对照蓝本）并存，也需按 §三 定主次 |
| `behavior-gesta-wuu.md` | UPDATE | 锚准确、行号当日核实；§3 那句「Questor M2.1 以 JSON 索引承载、SQLite FTS 按 B-46 属 M4」是与母本相反的一侧（C3），改判后本篇要接住 SQLite 那一支 |
| `behavior-state-wuu.md` | KEEP | 全文质量最高的一份：securefs 六条边界（同目录 temp／Chmod+Sync／defer 清临时／rename 后复核 mode／Windows `MoveFileEx` 可原子替换且 mode 尽力而为）、storelock 五条（锁文件永不删除、25ms/60s、无心跳、`LockFileEx`/`flock` 平台分支、读者免锁）。转向后这些正是移植清单，编号 B-71/72/73 与 pitfalls 一致 |
| `behavior-protocol-wuu.md` | UPDATE | 方向正确但覆盖面撑不起 protocol 重写：只扫了 pending 路由/慢发现/幂等/held_work 四块，缺 105 方法全表、`runtime_host`/`max_parallel`/`deferred_notification_content` 字段事实，且**没有把「inbox 与 held_work 落 SQLite」这条 C3 关键证据登记成坑**（它写在 §3/§4 正文里却没进坑表） |
| `behavior-review-habena-wuu.md` | UPDATE | §1 记「wuu `diff.go#L33-35` 写时刻计算并随结果持久化」——**只讲了母本的两个 diff 之一**，没登记 `desktop/src/main/gitService.ts` 的工作区 git diff（C0）。本篇是 `review/` 换锚的核心输入，必须补一节「母本的双源分工」 |
| `behavior-review-fidelity-wuu.md` | UPDATE | **§0「与 wuu 的语义差异（诚实标注）」全仓唯一把母本偏离写明白的一段**（wuu Review 是 workspace 级 `GitChangeFile[]`、Questor 是 per-turn 级、"只借视觉与动效不借工作区语义"）——这份声明应升格为 ADR-0035/0040 的直接输入；L39「evopanel 与 wuu 皆实测选型」与实际不符（wuu desktop 无 `@pierre/diffs`），需改 |
| `behavior-engine-fc.md` | **UPDATE**（v1 判 DELETE，**改判**） | 读完正文：§4 止损四路表、§5 并发分区、§6「拒绝双实现」、§7 事件族、§8 强引用纪律都写成了「Questor 采纳决定」＝与语言／母本无关的工程裁决。正确处置是**换锚重验**（逐条对 wuu `loopdriver`/`agent/loop.go`，同标来源、不同标"取 FC 经验不取 wuu"），而不是删 |
| `behavior-tools-fc.md` | **UPDATE**（同上改判） | 退出码语义映射表（`grep/rg/diff/find/test/[` 阈值 2、按管道最后一段、`VAR=` 前缀、basename）、连续合并分区、`gather(return_exceptions=True)` 降级、结果顺序＝提交顺序、未知 vs 禁用区分——全是 Python 侧可直接用的细节，且 wuu 有同构实现待对表 |
| `behavior-permissions-fc.md` | **UPDATE**（同上改判） | **v1 判它"双真相源"是误读**：L5 自己写明「三档语义以 wuu 为权威，本文提供判定顺序与防御细节的对照」，它本来就不主张权威。真正要保留的是 B-30「resolve 祖先后必须再 `resolve(strict=False)` 重查，否则拼回尾部重新引入 `..` 可穿越」这类防御细节 |
| `behavior-context-fc.md` | **UPDATE**（同上改判） | 13 条压缩常量表 + 悬空 tool_result 配对对齐 + transcript 逃生门 + 熔断器 + 「用户消息原文不可改写」摘要协议，都落在「采纳决定」里；其中 B-27 是**有意识地收紧**（不继承 FlowCoder 的无状态 drift）。换锚时这些决定要保留 |
| `behavior-sandbox-eval-fc.md` | UPDATE（后置＋修编号） | §1 容器硬化默认值属 M8 后置；但 §3 评测三协议（Solver/Executor/Grader）＋trial/`heal_rounds`＋k-sample `FIRST_COMPLETED` 首胜取消＋温度 0＋失败四分类是 `evals/runner/` 的实际依据，与母本无关。**坑表有硬缺陷**：L69/L71 两行都写 `B-32`（与 limen 的 B-32 撞号），正确应为 B-35／B-37 |
| `behavior-orchestration-ef.md` | UPDATE（后置＋修编号） | 状态机白名单全表、编排动作 frozenset、「工具返回错误而非中间件注入」、人工门≠取消、gate 消息先持久化定序——后置期间必须留；**正文内联坑号 B-33/34/38/40 与表尾 B-38/39/43/45 不一致**（正文那两个号在 pitfalls 里属 limen/vigilia） |
| `behavior-queue-ef.md` | UPDATE（后置＋修编号） | 「一批一间隔＋游标」「once_fired 幂等」「同分钟去重」「错过不重放」「双 reconcile」都被 ADR-0026 采纳且绑 LangGraph 无关；**正文内联 B-33/36/37/35/34 与表尾 B-40/41/42/44/49 全线错位** |
| `behavior-persistence-ef.md` | UPDATE（v1 判 DELETE，**改判**） | 它不是"废弃代码配套文档"而是**反面教材**：B-46「不做百表 SQLite 单体」＋B-47 流镜像独立位＋B-48 CJK bigram FTS5 技巧。**关键点：转向后 B-46 的结论可能反转**——wuu 的会话权威库恰恰是 SQLite，"百表单体＝坏味道"这条来自 EvoFlow 的教训不能再当天然正确。正文内联坑号（B-41/42/43/38）与表尾（B-46/47/48）也错位 |

### 2.6 `docs/notes/`（6）／`ui`·`tests`·`evals`（10）

| 路径 | 分类 | 理由 |
|---|---|---|
| `notes/README.md` | KEEP | 分类去向表＋三条规矩（锚点／过期即删／预测→验证），转向后反而更需要 |
| `2026-10-11-gate-parity.md` | KEEP | 门禁同源机制，`复核于: 2026-10-13` 仍新；教训（`--full-path` 不存在、钩子排在 `npm ci` 前）跨方向有效 |
| `2026-10-11-pr-branch-carries-its-own-workflow.md` | KEEP | Git/GitHub 机制事实，与代码形态无关 |
| `2026-10-12-m23-wire-probe.md` | UPDATE | 端点实测事实可全留；但锚点列了 `docs/specs/behavior-context-fc.md` 等——若按 v1 删 spec 会触发 `check_notes` 判红（现改为 UPDATE 后此风险消，但**换锚改文件名时仍会触发**，需同批改锚） |
| `2026-10-13-desktop-restart-policy.md` | UPDATE | 「三层定时／等 exit 不等 pipe close（B-113）／timer unref」是从 wuu `childShutdown.ts` 学到的机制，价值高；但锚的是将被重写的 `desktop/src/main/*.ts`，重搭后必须重验才不算过期 |
| `2026-10-13-review-fidelity-walk.md` | UPDATE | `@pierre/diffs/react` 入口、`processFile` vs `parseDiffFromFile` 的选型解释准确；随渲染器重裁（ADR-0031）与 diff 权威源改判（C0）整条链路失效 |
| `ui/README.md` | **REWRITE** | 首句「唯一前端代码源」是改判正面目标；§选型 L39 列 zustand v5/`@pierre/diffs`/`@xyflow`/shiki，实测 wuu desktop 一个都不用。**须原样保留**「状态归属边界：会话/运行/权限的真相永远在 Python 侧，前端只存 UI-local 状态」——与宿主形态无关 |
| `desktop/`（0 份 md） | （缺篇） | 实测无任何 markdown；壳知识散在 notes 与 3327 行计划里，见第 3.2 节 |
| `tests/contract/README.md` | UPDATE | 「先写测试再写第二个引擎否则契约退化为内建形状复述」这条判据要保；但「M6 起 ACP/Claude/Codex」与 `engine/contract/` 形状按母本 `agentengine` 符号重定；现状段「用例随 M2 引擎物化落地」与实测 0 用例不符（ADR-0033 已登记该洞） |
| `tests/architecture/README.md` | UPDATE | 「第一个用例应是 R1 检查」早已过期（实测 13 py）；三条硬断言中「append-only」「状态迁移唯一入口」随 C3 裁决而定生死 |
| `tests/integration/README.md` | UPDATE | 四件套方向不变，用例随 protocol/data-model 重写重排 |
| `tests/adversarial/README.md` | UPDATE | 「只增不减」纪律不变；但 10 个 py 是对将被废弃的实现写的——**AGENTS §四 的"只增不减"与转向的"代码废弃"直接相撞**，需 ADR 明确哪些升为跨实现契约、哪些随实现作废 |
| `tests/e2e/README.md` | UPDATE | 整链定义「转后台→任务总结→打回→重做→diff 可回看」整条属后期 EvoFlow 层；A 阶段的整链该是什么要随新计划重定 |
| `tests/fixtures/README.md` | UPDATE | 三条硬规矩（无真实数据／`.gitattributes` 钉死字节长度／命名可归因）与方向无关可留；「本目录暂空」需按实测改写 |
| `evals/README.md` | UPDATE | 五条纪律（诚实标注、失败也发布、五要件、禁示例分数）要保；可比集／`not_in_baseline`／`not_comparable`／档位映射四节全以 FlowCoder 为对手，随 C18 重裁 |
| `evals/adapters/mode_map.md` | **DELETE** | 全文只有一件事：Questor 三档 ↔ **FlowCoder 六档**映射；FlowCoder 出局后无对手方，且 wuu 本身就是 `read_only/standard/unconfined` 同名三档，映射退化为恒等。**扔前先归档**：L24「实测 `flowcoder --mode read_only` 直接报参数错」与 ADR-0021 L25-26 的六档清单要并入 evals/README 或 pitfalls，不能让证据跟着文件消失 |
| `evals/results/README.md` | KEEP | 「不可变区、被引用后不可修改、不放示例分数、脱敏须登记」——纯规则，跨方向有效 |

### 2.7 `.github/` 下 3 份模板（v2 补扫，已全部读完全文）

| 路径 | 分类 | 理由 |
|---|---|---|
| `.github/PULL_REQUEST_TEMPLATE.md`（15 行） | KEEP | 五条自查（`just check` 贴输出、实现与测试同 commit、护栏附负向验证、新坑回填测试、契约先改文档递增版本、不含真实会话/路径/凭据）全部与母本无关、转向后照用。它就是 `structure §9`「PR 模板必须列门禁命令与实际输出」与 `AGENTS §四` 收尾自检的同一套，两边已对得上 |
| `.github/ISSUE_TEMPLATE/bug_report.md`（25 行） | KEEP | 要求 OS／commit／**引擎与权限档位**（`read_only`/`standard`/`unconfined` 三档转向后不变）＋贴 `just check` 实际输出；引用 `questor version` 仍可用。唯一轻微波动：若 `desktop/` 重搭后启动方式变，复现步骤的示例要跟着改 |
| `.github/ISSUE_TEMPLATE/feature_request.md`（23 行） | UPDATE | 骨架（从三柱出发描述"服务哪一柱"＋契约改动先改文档＋排除项 checklist）都好；但 L17-22 的四条排除项是**硬编码自 overview §1 的"不是什么"**：① AGENTS §一 处置已要求把「多用户 SaaS／岗位值班」的括注改成「长任务与编排属后期层」（配合 ADR-0043），这里要同步，否则"看板/多 Agent/排班"类需求在 A 阶段会被模板放行；② overview 正在 REWRITE，**若 §1 编号变动则此处引用断链**（§2.1 的 `docs/README.md` 犯的是同一错），建议改成"对照 `AGENTS.md` §一"这个更稳的源头 |

---

## 3. 附加产出

### 3.1 矛盾清单

| # | 冲突双方 | 证据位置 | 后果 |
|---|---|---|---|
| **C0**（最高优先） | **「GUI 能力必须经协议可达／壳内不含业务判断」vs 母本把 git diff 放在壳** | questor：`overview §14` L370 那道门、`ADR-0006 结论1`、`ADR-0030 结论1＋失效条件2`、`ADR-0005 结论2/4＋被否决项③＋「UI 层锁死」`；wuu：`desktop/src/main/gitService.ts`（`gitDiffStats(root,true)`/`gitDiffOutput`/`gitDiffBase`）＋协议中**无** `review/*`；questor 自己的 `behavior-review-fidelity-wuu.md §0` 已诚实标注这一偏离 | 照 wuu 形态重搭 Review ⇒ 要么把 git 采集搬进 Electron 主进程（撞破纯壳纪律与 §14 那道门），要么在内核新增 `review/workspace_diff`（母本没这方法）。**这是本次转向唯一能改变架构走向的冲突，必须最先裁决** |
| C1 | `AGENTS §二`「不照搬代码，全部重写」vs 复用优先 | `AGENTS` L66、`overview` L36/L41、`development-plan` L24、`adr/README` L33 | 四处同一前提全在纪律层，不改则每次会话都把复用当违规 |
| C2 | 「`ui/` 唯一前端代码源、`desktop/` 只包壳」vs wuu 形态（渲染层在 `desktop/src/renderer/`＋`clients/core`） | `structure` L68-74/L202-216；`ui/README` L3；`ADR-0006 结论2`；`ADR-0030 结论4`；`ADR-0032 结论3` | 决定整个 TS 侧走向；且已固化为一套开发规范，须连规范一起重裁 |
| C3 | 「JSONL 唯一真相源＋SQLite 可丢弃索引」vs wuu SQLite 权威库（`session_messages`/`session_controls`/inbox/held_work 皆在 SQLite） | `data-model` L244-245；`overview` L232-235；`ADR-0017` L28；`ADR-0025` L34；`ADR-0013` L37；`behavior-gesta-wuu` §3；`behavior-persistence-ef` B-46 | 存储权威归属相反，**五份文档＋四份 ADR 的结论链吊在它上面** |
| C4 | 契约文档自研命名 vs wuu 真实词表（105 方法） | `protocol` L44/L56/L67/L99/L100/L109/L114；`overview §13` 未决项 1 | 护栏 `test_serve_names_are_contracted` 直接解析契约文档表格首列——改词表＝同批改护栏 |
| C5 | `Turn ⊃ Run` vs wuu「Run 记录 ordered turns」；状态集缺 `accepted`/`interrupted`/`timed_out` | `data-model` L26/L171-175；`ADR-0014` | 实体包含方向反了 |
| C6 | 选中定位「字节 offset」vs wuu「UTF-16 code units in rendered DOM」 | `data-model` L238；`development-plan` L247；wuu 协议文档 Input Content Parts | 跨端选中/批注互操作前提，二选一 |
| C7 | `overview §4` L127「模型调用用官方 SDK」vs `ADR-0016`「不接厂商 SDK」 | 同一仓库两句相反裁决 | 按 §七 第 5 项必须回写修正两处 |
| C8 | `protocol §6` `browser/host`「M8 延后」vs wuu 9 个 `browser/*` 反向方法＋真接管是换 Electron 的动机 | `protocol` L124；`ADR-0030 结论2`；`structure §7` L209 | 后置标注与换壳动机互相拆台 |
| C9 | 协议里的编排方法族 21 个 vs wuu 协议无此族；而 `overview §12` 把 M4/M5 记为已完成 | `protocol` L74-84；`ADR-0025~0029`；`ADR-0028` L17-19 | 重写期会把这些当"已定契约"继承 |
| C10 | `ADR-0007` 把 AppContainer 列为被否决选项 vs 新方向当升级路径 | `adr/0007` L57/L60 | 不改判则后续照 0007 再拒一次 |
| C11 | `data-model §1` id 小写正则 vs 外部引擎原生 id 大小写混用 | `data-model` L16；`modules/state.md` 两套校验 | **待实测项**（v1 当作实测结论，已降级） |
| C12 | 三处纪律要求 `cases-*.md` vs 实测零份，而 M1 已记「已完成」 | `AGENTS §二` L80；`overview §3` L73；`specs/README §三`；`development-plan` L39 | 已发生的出口虚记 |
| C13 | 「两表模块名逐项对齐、一行一个模块、可脚本奇偶校验」vs 两处合并行 | `structure` L101-104 vs L119/L130 | 校验一旦落实即红；`src/questor/` 24 目录 vs 15 篇设计篇 |
| C14 | `AGENTS §六` scope 清单 vs git 实际 scope | log 有 `feat(desktop)`/`feat(ui)`/`test(e2e)`/`ci(desktop)`/`chore(node)`，清单无 `desktop`/`ui`/`testenv`/`sessiontrace`/`worktree` | ADR-0030/0032 引入新目录时无人回写 |
| C15 | `structure §9` L294 dependabot 四类含 cargo vs 同文档 §2 L88 已撤 cargo | `structure` L294 vs L88 | 单文档内部矛盾；`dependabot.yml` 实际配置需按 §2 核 |
| **C17** | `ADR-0009`「just **已装上** 1.58.0（含 Windows 默认 sh 的坑）」vs `AGENTS §四` L140「本机拿不到 just 时…」vs `development-plan` L84「⚠ 已登记不可用」 | 三份文档，ADR-0009 才是对的 | 三份都自称反映现状，实为两旧一新；AGENTS 的退路条款本身没错但前提描述过期 |
| **C18** | 「wuu 不作基线」四处（含 ADR-0021 被否决项写死「**不改**」）vs 新方向以 wuu 为唯一考官 | `overview` L309-310；`structure` L265；`ADR-0021` L41；`evals/README`；而 `overview §2` L41 又自陈 wuu 的 Go 核心 CI 级支持 Windows 编译 | 出口判据指向一个自己否认的考官；同一文档内部先已自相矛盾 |
| **C19** | `protocol §6` 把 `approval/request` 列为已实装反向请求 vs `overview §9` L265「本项目**不提供** per-command 弹窗（与 wuu 同调）」 | `protocol` L121；`overview` L265；`ADR-0023` L38 还拿它当"必须做 WS"的论据 | 三处牵动；wuu 侧对应物是 `approve_for_me`＋`internal/approvefor`（收紧型、非逐命令弹窗），需实测对表后择一 |
| **C20** | `ADR-0011` required 名单表 vs 实际 5 个 workflow／`desktop`＋`docs` 两个 job 未入表 | `adr/0011` L15-22 与 L52（失效条件③） | ADR 违反了自己的"唯一真相"条款；GitHub 设置是否已同步需人工核 |
| **C21** | `overview §13` 未决项 4「组/用户名占用**尚未核查**」vs `ADR-0001` L84「2026-10-11 **已实测不可得**」 | 两处 | 未决项清单里有一条其实早已关闭 |

### 3.2 必须新增／改写

**新立 ADR（转向至少这几条）**

| 编号 | 标题 | 为什么必须新立 | 连带 |
|---|---|---|---|
| **ADR-0037** | 复用优先取代全量重写：按 wuu 蓝本移植／翻译，边界层逐文件对表 | 推翻的是纪律级前提（C1 四处＋ADR-0002 空号）；**且必须含 wuu MIT 的署名义务**（`LICENSE`/`NOTICE`/`third_party/licenses/` 三处现在一份上游条目都没有） | 使 15 份 modules 的 provenance 行、`development-plan` L24、`overview §2/§3/§15`、AGENTS §二 同时改判；多处 ADR 引用的「§二 (a)/(c) 类」编号需全仓跟动 |
| **ADR-0038** | wuu 单锚：EvoFlow 降为后期长任务层规格来源，FlowCoder/AfterMatter 退出参照系 | 触发 §七 第 1/2/3/5 项；须一并回答**"非母本已落规格怎么处理"**（保留为参考／换锚重验／删除）——这是 v1 判 DELETE 之所以错的根因，必须由 ADR 定规则而不是逐篇拍脑袋 | 改写 `overview §2/§6/§11`、`specs/README §一/§二`、`ADR-0021` 基线口径、9 份 `-fc`/`-ef` 的定位 |
| **ADR-0039** | AppContainer 作 Windows 写隔离后期升级路径，改判 ADR-0007 被否决项第 4 条 | 属"改判已有裁决"，走 0007 失效条件 1 | 只动否决项与失效条件；结论 1/2/3 逐字保留 |
| **ADR-0040** | 前端归属改判（渲染层回归 `desktop/src/renderer/`＋`clients/core`） | C2；连带撤销已固化的"渲染层复用 ui 源码"规范 | `ADR-0006 结论2`、`0019`、`0030 结论4`、`0031`、`0032 结论3/4`、`structure §2/§7`、`ui/README` |
| **ADR-0041** ★ | 会话存储权威源（SQLite 库 vs JSONL 真相源） | C3；牵动 4 份 ADR 的结论链与 2 条架构硬断言 | `ADR-0013/0017/0025`、`data-model §5`、`modules/gesta`、`tests/architecture` |
| **ADR-0042** ★ | 协议词表取齐 wuu（关闭 `overview §13` 未决项 1） | C4/C8/C9/C19 四条同时落定 | `protocol.md` 全表、`schemas/app_server`、3 份护栏测试、`behavior-protocol-wuu` 扩面 |
| **ADR-0043** | 长任务层后置（Plan/Goal/看板/打回从主线摘出） | §七 第 3 项；`overview §12` 已把 M4/M5 记为完成，不改判就是两套进度真相 | `ADR-0025/0026/0027/0029/0034`、`tests/e2e` 整链定义 |
| **ADR-0045** ★ | **Review/diff 的职责归属：内核出协议方法，还是照 wuu 放壳侧 GitService** | **C0。v1 完全没有这一条。** 它决定 protocol 方法表、ADR-0005 的"UI 层锁死"、overview §14 那道门、以及 `review/` 模块是否继续存在 | 与 0042 同批；`behavior-review-fidelity-wuu §0` 是现成输入 |
| （可选）**ADR-0044** | 现有实现处置地图：24 个模块目录＋`ui/`＋`desktop/` 逐个定性（废弃／保留／延后），并裁定"对抗套件只增不减"与"代码废弃"如何相容 | `AGENTS §四` L148-149「只增不减」与转向相撞；这是最大的失血点且无纪律覆盖 | 可与 0037 合并 |

**新增文档（非 ADR）**

1. `docs/plans/phase-a-mvp.md`：A 阶段纵向切片计划，每波含「wuu 借鉴清单」（参照文件锚点→本仓任务号→坑编号→配对护栏测试）＋「不采纳项及原因」两栏——转向要求的落地范式目前一份都没有（phase-u 那份是唯一先例）。
2. 换锚规格 4 份：`behavior-engine-wuu.md`、`behavior-tools-wuu.md`、`behavior-context-wuu.md`、`behavior-providers-wuu.md`。
3. `behavior-storage-wuu.md`：把 `agentthread`（JSONL）与 `session`（SQLite）两套存储的权威归属实测清楚，喂 ADR-0041。
4. **`docs/specs/pitfall-ids.md` 或一条 CI 断言**：见 §3.3。
5. `desktop/README.md`：实测 `desktop/` 零 markdown，壳职责/生命周期/打包/IPC 全散在 notes 与历史计划里。
6. `modules/review.md`、`modules/habena.md`：两模块已实装且直接承载 `revision` 绑定与接管栅栏两条契约，却无设计篇。
7. `overview §13` 未决项重写为"转向后仍未决"短名单（现有 5 条至少 3 条已被回答或已关闭，含 C21）。

### 3.3 本轮新发现的数据完整性缺陷（门禁抓不到，必须先修）

**坑编号在 5 份 spec 里系统性错位**，实测对照：

| 文件 | 正文内联坑号 | 文末表格坑号 | 与 `pitfalls.md` 权威归属的关系 |
|---|---|---|---|
| `behavior-limen-wuu.md` | B-50 ×7 | B-50 ×9 | pitfalls 中这些语义本有 **B-50/51/52/53/54** 等独立编号；本文件把 9 条塌成同一个号，却仍在 L94 自述「编号已对齐 pitfalls.md」 |
| `behavior-queue-ef.md` | B-33/36/37/35/34 | B-40/41/42/44/49 | 正文那几个号在 pitfalls 里属 **limen(B-33/34)、serve/M8(B-35/36)、evals(B-37)** |
| `behavior-orchestration-ef.md` | B-33/34/38/40 | B-38/39/43/45 | 同上，正文 B-33/34 指向 limen、B-40 指向 vigilia |
| `behavior-sandbox-eval-fc.md` | B-35/36/37 | **B-32/36/32** | 表内 B-32 出现两次且与 limen 的 B-32（危险命令黑名单）撞号；正确应为 B-35／B-37 |
| `behavior-persistence-ef.md` | B-41/42/43/38 | B-46/47/48 | 正文 B-41/42 属 vigilia、B-43 属 orchestration |

推断成因：一次全局 renumber 只更新了文末表格，正文内联引用没跟着改。`check_specs.py` 按 `ADR-0008` L19 只校「文件存在性与形式可定位性」，**不断言编号唯一性、也不比对 spec 内联号与 pitfalls 归属**，所以全部放行。
后果直接打在转向的关键动作上：**"每条 B-NN 对应一个真实存在的测试"是 AGENTS §二 的硬要求，编号塌缩＝9 条 wuu 权限门实测细节共用一个号，无法各自配对测试**；而 `behavior-limen-wuu.md` 正是 limen 按母本移植的第一依据。
建议新增两条机械断言：① `pitfalls.md` 编号全局唯一（行首 `| B-NN |` 不重复）；② 每份 spec 的内联 `B-NN` 必须在 pitfalls 中存在且归属模块与本文 `Questor 模块归属` 一致。并按 §七 第 6 项补 ADR-0008 的核查工具条款。

### 3.4 删除动作的安全前提

- 删 spec 会炸 notes：`notes/2026-10-12-m23-wire-probe.md` 锚了 `docs/specs/behavior-context-fc.md`；`modules/*.md` 的「蓝本:」行锚了多份 spec。改锚与改编号必须同批，否则 `check_notes`/`check_specs` 红。
- 编号不可回收：`specs/README §二` 与 `adr/README` 都规定不复用、标 `moot` 不删行——DELETE 类文档里的坑与裁决必须先确认已被权威表承载。
- `ADR-0033~0036` 仍未跟踪：新一轮改判会直接编辑这四份，先让 git 干净（AGENTS §六：未验证不提交）。

---

## 4. `AGENTS.md` 逐节处置

| 节 | 关键句（行号） | 处置 | 改写口径 |
|---|---|---|---|
| 前言＋元规则＋四条硬线 | L6-8「冲突时停下问用户」；L10-25 偏离许可三纪律；L27-35 硬线索引 | **KEEP** | 原样保留——这正是处理本次冲突的合法程序。仅需复核硬线第 4 条指向的 §七 在改写后仍对得上 |
| §一 项目定位 | L41-43 三柱；L45-49「不是什么」；L52-56 铁律；L58 命名 | **KEEP（两处）** | ① L48 把「多用户 SaaS／组织排班」的括注改为「长任务与编排属后期层，A 阶段不进核心路径」（配合 ADR-0043）；② L43「Agent 在本地项目上长活」→ A 阶段先写"干活"，避免承诺尚未交付的长跑 |
| **§二 复用三分法** | L66「不照搬代码，全部重写」；L69-73 (a)(b)(c)；L75-81 三资产；L83-90 provenance；L92-102 可逆性三问 | **REWRITE（整节）** | ① 母本唯一＝wuu；② (a) 边界层→**逐文件移植并译为 Python**，provenance 行改 `Ported from wuu@<commit> internal/<pkg>/<file>.go`，仍要求每个 B-NN 有真实测试；③ (b) 语义与契约→**按 wuu 规格取齐**（与旧"必须新写"正面反转），差异只能以 ADR 记；④ (c) UI 与外壳→**照 wuu 形态重搭**；⑤ **新增一条不可偏离**：移植 wuu 代码必须保留 MIT 许可与上游署名；⑥ 三资产：`cases-*.md` 要么补建要么三处一起降级；⑦ **可逆性三问整段 KEEP**——它与母本无关，且转向后更要靠第 2、3 问拒绝把 wuu 的多租户／远程／PiP 结构带进来 |
| **§三 语义唯一来源表** | L110「engine＝**本项目自研**（形状参照 wuu agentengine）」；L112 编排＝EvoFlow；L113 证据＝wuu+EvoFlow | **REWRITE（整表）** | 逐行：① 循环/事件流/turn→唯一来源 **wuu**（`loopdriver`+`agent/loop.go`），并同句写明**所有权条款**：语义来源＝wuu、实现所有权＝本项目手写 Python（R2「裁决权不得交给框架」、不引 LangGraph 不变，转向后反而更需要它，因为"翻 Go 循环"最容易被误读为"找个框架"）；② 权限门＝wuu `boundary.go`/`sensitive_paths.go`（删 FlowCoder 六层并列）；③ 编排与验收→「后期再加的长任务层，规格来源 EvoFlow（PolyForm：可读不搬码）」，`orchestration`/`vigilia` 标后置；④ 验收证据只留 wuu Review 语义；⑤ 插话接管＝wuu（不变）；⑥ **补两行现在没有的语义**：会话存储权威源、协议词表——正是 C3/C4 两套真相的爆点，待 ADR-0041/0042 填入 |
| **§四 代码质量约束** | L140-141「本机拿不到 `just` 时按 justfile 逐条手动跑」；L124-128 版本策略；L129-145 门禁四件套；L147-155 纪律；L157-168 注释语言；L170-178 护栏准入＋负向验证；L180-189 红线四条 | **UPDATE**（v1 判 KEEP，**改判**） | 四件套／门禁范围／护栏准入／红线四条全部 KEEP——这节是转向后最不需要动的。两处必改：① **L140-141 与 ADR-0009 的实测更新冲突（C17）**，退路条款可留但"本机拿不到"的前提要改成"给拿不到 just 的贡献者"；② L168「注释里的项目名/路径写成可 grep 的确切形式（如 `wuu internal/tools/boundary.go`）」在复用优先后**从风格升级为合规**：移植的每一段都要能指回 wuu 的具体文件与 commit，否则 MIT 署名无从核对。另在 L151 pydantic 那条旁补一句：移植 wuu 结构体时字段命名先取齐 wuu，差异走 ADR |
| **§五 出口判据** | L195-197「与参照实现相同 N 个真实任务上失败率不高于参照」；L199-202 前端跟随 | **REWRITE（判据本体）** | 旧判据在转向后不可执行：参照方 FlowCoder 出局，而"拿 wuu 当基线"被 ADR-0021 写成"不改"、被 overview/structure/evals 三处否认（C18）。新判据换成**等价性＋可跑性**：主判据＝**与 wuu 行为等价**（同任务同模型，走同一协议帧序列，逐帧形状与终态一致，差异只在 ADR 登记处）；次判据＝坑覆盖率 100%＋每条护栏附负向验证（保留）。若 wuu 实跑不可得，**显式降级为"契约等价（同套帧回放）"并同步改 overview §11**，不许留一个无法执行的承诺当门禁。L199-202 前端跟随 KEEP，但"从 UI 路径走通一次"要写明宿主是 Electron 壳 |
| §六 Git 与 Commit | L208-209 未经允许禁 commit/push；L211-218 模板；L220-222 scope 清单；L225-229 推送形态 | **UPDATE** | 规矩全留。L220-222 scope 清单缺 `desktop`/`ui`/`testenv`/`sessiontrace`/`worktree`/`scripts`，而 log 已实际使用（C14）；ADR-0040 落地时 `ui/`→`desktop/src/renderer` 还要再改一轮，建议在 §六 加一句"新增顶层目录＝同批改本节清单" |
| **§七 文档地图＋ADR 触发清单** | L235-245 必读表；L247-249 文档视距与「契约三件必须超前」；L251-262 触发清单 6 条 | **UPDATE** | ① L237 的「唯一架构入口 overview＋§二§三」在四件重写期间必须临时改为"先读转向 ADR，overview/structure 标『改写中、不得作依据』"；② L240 的契约指针要落到实际的 `data-model.md`/`protocol.md`；③ **L247-249「契约三件（协议、数据模型、模块边界）必须超前，否则长出两套契约」是本节最该保住的一句**——本次所有冲突的根因就是契约三件没超前、而 plans/modules 超前了；建议把它从附注升格为 §七 首条，并给"契约三件"一份清单化落点（哪些文件算、哪些算引用）；④ 触发清单第 3 项的例子「如 Phase E」已过期（E1 已并入 Phase U），改为"如 Phase U 并轨、长任务层后置"；⑤ **新增第 7 项触发条件「废弃／替换既有实现」**——转向新增的动作类型，现在无纪律覆盖，导致"扔 24 个模块"没有 ADR 可对；⑥ 清单第 6 项（新坑必落测试）在 §3.3 的编号塌缩面前要补一句"编号须先通过唯一性断言" |

---

## 5. 给下一个窗口的落笔顺序

1. 先修 §3.3 的编号塌缩与撞号（一条 CI 断言＋5 份 spec 的正文引用），这是所有后续动作的地基，且与转向无关、可独立提交。
2. 落 ADR-0037／0038／0039／0045／0040／0041／0042／0043（**0045 优先于 0042**：先定 diff 职责在壳还是核，才能定协议方法表），并把 `adr/README` 索引、0002/0003/0004 空号、0024/0036 的 superseded/withdrawn 标注一并处理。
3. 重写契约三件：`protocol.md`（照 105 方法表）→ `data-model.md`（层级/状态集/存储/offset 四条）→ `structure.md §2/§5/§7`。三件未定前，modules 与 plans 的重写都是白工。
4. 写 A 阶段 MVP 计划（每波 wuu 借鉴清单＋不采纳清单），取代 development-plan 的 M 系列骨架；给 phase-u 两份加历史头并撤销 pending。
5. 按 ADR-0038 的"非母本规格处理规则"逐篇换锚 9 份 `-fc`/`-ef`（**默认不删**，除 `mode_map.md` 一类无对手方的映射表）；同步改 notes 与 modules 的锚点。
6. 最后改 AGENTS §二/§三/§四/§五/§六/§七 与 README／docs/README／ui/README 三张门面。
7. 全程先让 git 干净（ADR-0033~0036 未跟踪＋三份文件已改未提交）。

---

## 6. 本轮仍未读完的部分（证据边界）

为避免重蹈 v1 的"读了摘要当读完全文"，明确标注：

- **已全文读完（可作依据）**：AGENTS、README、CHANGELOG（165 行）、SECURITY、docs/README、assets/README、architecture 四件、`docs/adr/` 全部 34 份、`docs/plans/development-plan.md`＋`phase-u-completion.md`、`docs/specs/README.md`＋14 份 behavior 全部、`ui/README.md`、6 份 tests README＋3 份 evals README、notes/README＋5 份 notes 全文、3 份 `.github/*.md` 模板（补扫）。共 **97 份**。
- **仍只读了大纲或片段（结论需谨慎）**：
  1. `docs/plans/2026-10-13-phase-u-ui-and-electron-shell.md`（3327 行）——只读了标题体系＋前 30 行；本报告对它的判定基于「前提句 + 借鉴清单表头 + completion 文档的对照」，若要逐 Task 核对是否还有与新方向冲突的实现假设，需再扫正文。
  2. `docs/specs/pitfalls.md`（130 行、121 条）——只读了表头＋前 20 行＋若干抽查行；按用户要求本窗口不重判坑内容，但 §3.3 的抽查显示**其余条目的内联引用可能有同类错位**，未做全量比对。
  3. `modules/tools.md`／`providers.md`／`serve.md` 的部分正文（终端截断，provenance 行与关键决策已核，逐节内容未全读）。
  4. wuu 侧 `desktop/src/renderer/` 的组件装配方式（本报告只确认了目录形态与依赖表，未读实现）——这条直接影响 ADR-0040 与 ADR-0020 的结论，**落笔前必须实测**。

---

## 附录：复核命令（每条事实都能自己验，不必相信本报告）

环境说明：PowerShell 5.1 读中文文件**必须**先设 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` 并带 `-Encoding UTF8`，否则输出乱码；这也是该仓库自己踩过的坑（`ADR-0008` L17-19 明令禁止用 `Get-Content` 数行数，要改用 Python `splitlines()` 或 .NET `ReadAllLines`）。以下命令均在 `d:\DEVELOP\My-project\questor` 下执行（涉母本的已写相对路径 `..\wuu-main\...`）。

| 想核的事实 | 命令 |
|---|---|
| 文档到底多少份（本报告口径＝**97**，含 4 份未跟踪 ADR） | `Get-ChildItem -Recurse -Include *.md \| ? { $_.FullName -notmatch 'node_modules\|\.venv\|\\dist\\\|\.pytest_cache\|\.ruff_cache\|\.import_linter_cache' } \| measure -Line`；再对比 `git ls-files *.md \| measure -Line`（93），两者之差＝4 份未跟踪 ADR。**切勿只用 `**/*.md` 形式的 glob：它会跳过 `.github`、`.trae` 等点目录**（本报告 v2 初版就这样漏了 3 份模板） |
| questor 有 24 个模块目录、`desktop/` 零份 md | `Get-ChildItem src\questor -Directory`；`Get-ChildItem desktop -Recurse -Include *.md \| ? { $_.FullName -notmatch node_modules }` |
| git 现状（领先 3 个 commit、四份 ADR 未跟踪） | `git log --oneline -6`；`git status --short` |
| **C0**：母本的 git diff 在壳里 | `Select-String -Path ..\wuu-main\desktop\src\main\gitService.ts -Pattern 'gitDiffStats\|gitDiffOutput\|GitChangeFile'`；再确认协议无此族：`Select-String -Path ..\wuu-main\internal\appserver\protocol.go -Pattern '"review/'`（应无命中） |
| **C3**：母本会话库是 SQLite | `Select-String -Path ..\wuu-main\internal\session\session.go -Pattern 'CREATE TABLE'`；另看 `internal\session\history_recovery.go` 里的 `modernc.org/sqlite` |
| wuu 真实方法表（105 个） | `Select-String -Path ..\wuu-main\internal\appserver\protocol.go -Pattern '"([a-z]+/[a-z/_-]+)"' -AllMatches \| % { $_.Matches.Groups[1].Value } \| sort -u` |
| **C2**：母本没有 `ui/` 包、依赖选型不同 | `Get-ChildItem ..\wuu-main\desktop\src -Directory`（看得到 renderer）；`Select-String -Path ..\wuu-main\desktop\package.json -Pattern 'zustand\|pierre\|shiki\|xyflow'`（应无命中） |
| **§3.3** 坑编号塌缩与错位 | `Select-String -Path docs\specs\behavior-limen-wuu.md -Pattern '^\| B-\d+ \|'`（9 行全是 B-50）；对照权威表 `Select-String -Path docs\specs\pitfalls.md -Pattern '^\| B-5[0-4] \|'`（各有独立条目） |
| **C10**：AppContainer 确实被否决过 | `Select-String -Path docs\adr\0007-windows-sandbox.md -Pattern 'AppContainer' -Context 1,1` |
| **C17**：just 三方说法不一 | `Select-String -Path docs\adr\0009-gate-entry-just.md -Pattern '已装上'`；`Select-String -Path AGENTS.md,docs\plans\development-plan.md -Pattern '拿不到\|装不上'` |
| **C20**：required 名单缺 job | `Get-ChildItem .github\workflows`（5 个）；`Select-String -Path .github\workflows\*.yml -Pattern '^jobs:\|^  [a-z][a-z0-9-]*:$'`；对照 `docs\adr\0011-branch-protection-mode.md` 的表格 |
| **C12**：`cases-*.md` 一份都没有 | `Get-ChildItem docs\specs -Filter 'cases-*.md'`（空）；对照 `docs\specs\README.md` §三 与 `AGENTS.md` §二 |
| **C18**：“wuu 不作基线”写死了“不改” | `Select-String -Path docs\adr\0021-m2-exit-split-evals-deferred.md -Pattern '拿 wuu 当基线' -Context 0,1` |

> 这些命令本身也是给接手的人的入口：先跑一遍，确认自己看到的和我看到的是同一个仓库，再决定要不要按本文改文档。乱码时不要怀疑结论，先检查上面那条编码设置。
