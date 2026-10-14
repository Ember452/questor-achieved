# AGENTS.md — Questor 开发规范

状态: 母本对齐转向中 | 更新: 2026-10-13 | 本项目正以 wuu 为母本重构（见 `docs/plans/`）；§二/§三/§五 的复用纪律已按转向改写，承重 ADR（0037/0038/0039/0040/0041/0042/0043/0045）待随 Phase 0 补齐，补齐前以本文件与计划为准。

面向 AI 辅助开发的行为准则。与具体任务的临时指示合并使用；冲突时本文件优先。
规范偏向"谨慎而非速度"，但**元规则优先**：文档之间存在确定性冲突、或碰到文档
未覆盖的决策点时，**停下来问用户**，不得默默选边；裁决后写 ADR 再动手。
用户的明确指令始终高于本文件；口头决定不落文档，视为未发生。

**文档是参考，不是约束（偏离许可）**

本文件与 `docs/` 下的一切——规范、结构图、模块表、里程碑、判据——都是**可推翻的默认值**，
不是铁律。在"照文档做"与"照现场事实做"之间选择时，以**哪个更合理**为准，而不是
以"文档怎么写"为准——文档会错、会过时、会过度约束。

允许并鼓励偏离的：目录摆放、内部分块、命名、流程步骤与颗粒度、里程碑顺序、
参照项目的取与不取、阈值数字。发现文档与现实不一致时，**按现实改文档**，
不要为了对上文档而扭曲实现。

偏离的三条纪律（自由度靠这三条才成立）：

1. **说出口**：指出偏离了哪一条、为什么，不静默绕开；
2. **留痕迹**：改动契约／状态机／协议／依赖选型时写 ADR（`docs/adr/`），
   其余在 commit 正文写清理由；
3. **回写**：文档确实错了或太紧，就顺手改文档，不留长期的"事实与文档两张皮"。

**不可偏离的四条硬线**（只作索引，原文分别在 §一、§三、§四、§七，不在此复述）：

1. §一 铁律 1——诚实呈现（无证据的断言不写，缺口显式标注）；
2. §一 铁律 2 + §三——模型提议、工具裁决；权限判定只有一个入口，受限档位不得静默降级；
3. §四 红线——数据外发与会话记录的不可改写约束；
4. §七——契约源头与"先改文档后改代码"的顺序（schema 可改，不可绕）。

判据一句话：**这个偏离会让用户看到假的完成状态，或让同一事实出现两套真相吗？**
会→不许偏离；不会→按上面三条纪律自由处置。

---

## 〇、全局工程纪律（母本对齐期间恒定）

本项目正按 `docs/plans/` 的分阶段计划，以 **wuu 为母本**重构，交付一个可双击安装的 Windows 桌面应用。以下纪律每个阶段都适用；规则冲突时按「**可用 > 扩展性 > 性能优化**」排序裁决。

- **对标但不照搬缺陷**：能力以 wuu / EvoFlow 为参照，同时**主动规避二者已知的架构问题**（见计划 §9 缺陷台账）；母本存在的缺陷不得当作“母本如此故我也如此”沿用。
- **交付目标**：可用、易用、易扩展维护；最终物是一个**完整可安装的 exe 应用**，不是库或开发态 CLI。
- **每阶段先扫描，不可跳过、不可浅扫**：任一阶段开工前必须只读评估 wuu（长任务层加扫 EvoFlow）对应子系统，范围与深度由执行者判断；扫后若有必要先写辅助文档（行为规格 / 移植台账）支撑，再动代码。
- **阶段提示词保持柔性**：只锁阶段大方向，允许局部微调；前期实现造成偏离时仅微调细节，**不动摇阶段核心目标**。
- **更优方案分级处理**：开发中发现更优方案但需大规模重构、会干扰当前阶段计划与稳定性 → **优先沿用 wuu / EvoFlow 成熟方案**，把优化方案完整记录存档到 `docs/proposals/`，待主体开发结束后再评估落地。
- **架构面向长期扩展**：新增功能尽量无冲突接入；遇到更利于扩展维护的方案，改动小且不影响后续计划可直接调整，改动大就记方案与风险入 `docs/proposals/` 留主体完成后处理。
- **禁止复用现有 questor 代码（硬红线）**：转向后的旧内核 / `ui/` / `desktop/` 一律**只可只读参考、提取知识**，不得复制其实现行、不得“改一行接着用”；新代码一律按 wuu 蓝本重写（机制：旧码移出工作树 + import 护栏 + provenance 只指 wuu）。违反=评审打回。
- **统一归档可追溯**：所有计划、文档、提示词、坑点清单、优化提案统一归档（`docs/` 下）；计划、扫描（`docs/research/`）、ADR、port-ledger、proposals 各归其位。
- **落地可行**：方案必须可实现、可验证，避免不切实际的设计。

---

## 一、项目定位（每次会话先对齐）

**Questor 是什么**：可审计的个人 AI Agent 工作站。Agent 在本地项目上长活，
过程全摊开、随时能插手、跑完能验收。三柱优先级固定：
**可见 → 可干预 → 可验证**。新功能必须服务其中之一，服务不了就不做。

**不是什么**（评审时对照，防 scope 漂移）：
- ❌ LLM tracing / observability 大盘
- ❌ 给别人二开的 Agent 框架
- ❌ 多用户 SaaS / 组织排班 / 岗位值班；长任务编排与验收看板属**后期阶段（Phase 6）**，A 阶段不进核心路径
- ❌ 模型能力评测榜单

**三条产品级铁律**：
1. **诚实呈现**：没有证据的断言不写；证据缺口显式标注，不臆断打分。
2. **模型提议、工具裁决**：LLM 只能产出 candidate；severity、状态迁移、
   放行与否由确定性代码判定。
3. **透明度恒为最大，分级的是写域**：权限三档限制"能碰什么"，绝不用于
   隐藏过程。任何"为了简洁而少显示"的设计直接打回。

命名：品牌展示体 **Questor**；一切技术标识符小写 **questor**
（包名 / import / CLI / 目录 / 仓库名）。词源见 `docs/adr/0001-*`。

---

## 二、复用优先的母本移植纪律（本项目的工程主线）

**母本 = wuu（MIT，`d:\DEVELOP\My-project\wuu-main`）**，单锚。复用动作是**逐文件把 wuu 已验证的逻辑翻译/移植进 Python**，以 wuu 的测试当验收 oracle——不是“照坑清单从零发明”，也不是“不照搬代码全部重写”（旧纪律已随转向作废，见待立 ADR-0037）。EvoFlow 仅在长任务/编排层作**规格来源**（读设计、不搬码；见待立 ADR-0038/0043）；FlowCoder 退出参照系。

| 类别 | 内容 | 处置 |
|---|---|---|
| **(a) 边界层** | 进程/PTY、Git 与 diff、沙箱、sqlite WAL+迁移、SSE 扇出、重试与限流 | **按 wuu 蓝本逐文件移植/译为 Python**，每条坑对应一个必写测试 |
| **(b) 语义与契约** | 会话数据模型、事件流 schema、权限门判定、工作区修订号、协议词表 | **按 wuu 规格取齐**（会话存储=SQLite 权威、协议照 wuu app-server；差异走 ADR） |
| **(c) UI 与工程外壳** | 桌面壳、面板骨架、样式、动效、路由 | **照 wuu renderer 形态重搭**（Tailwind `@theme` 色族 + 动效 + 依赖选型回 wuu 实测集） |

**MIT 署名硬线**：移植 wuu 代码必须保留其许可证与上游署名（`third_party/THIRD-PARTY-NOTICES` + `NOTICE`，见 ADR-0037）；EvoFlow（PolyForm Noncommercial）只可搬设计、不可搬码。

### 忠实度保证（复刻不是口号）

1. **wuu 测试即 oracle**：移植前先读对应 `_test.go`，抽“输入→输出→边界”进 `docs/research/behavior-<pkg>.md`（含逐符号对照表）；Python 测试照搬断言场景、不照搬代码。
2. **帧序列等价 fixtures**：`tests/contract/` 用 wuu 测试 golden/期望帧与手写核对基准回放驱动 Questor，逐帧形状/顺序/终态一致（本机无 Go，不靠实跑；运行期行为标盲区）。
3. **逐符号 provenance + 差异台账**：每个移植文件头写 `# Ported from wuu@<commit> internal/<pkg>/<file>.go — pitfalls: B-NN ...`；凡与 wuu 不一致处登 `docs/research/port-ledger.md` 一行理由。每个 `B-NN` 必须对应一个真实存在的测试。

### 可逆性判据（拒绝把母本范围膨胀带进来）

想为"将来"留门时先过三问（`overview.md` §14 有完整门清单）：① 要改的代价是搬运还是重写？② 留门是否只落在边界（数据形状/进程边界/路径单点/能力声明）？③ 是否已有第二个真实使用者？

```python
# Ported from wuu@<commit> internal/tools/boundary.go — pitfalls: B-50 B-51 B-52
```

---

## 三、语义唯一来源表（交叉处只允许 adapter，禁止两套真相）

| 语义 | 唯一来源 | adapter 位置 |
|---|---|---|
| Agent 循环 / 事件流 / turn 生命周期 | **来源 wuu**（`agentengine`+`agent/loop.go`）；**实现所有权＝本项目手写 Python，不引 LangGraph** | `questor/engine/` |
| 权限门与写域边界 | **wuu 的规格**（单一权威门，从可达性推导，审批只收紧不提权） | `questor/limen/` |
| 会话存储权威源 | **wuu：SQLite 权威库**（JSONL 降为可选导出镜像）（见待立 ADR-0041） | `questor/gesta/` `questor/state/` |
| 协议词表 / 消息与事件面 | **wuu app-server**（`thread/*` `turn/*` `run/*` `item/*` `process/*` `browser/*` `activity/*` `user-question/*`）（见待立 ADR-0042） | `questor/schemas/` `questor/serve/` |
| Review / diff 权威源 | **wuu 双源**：内核 tool-time diff + 壳侧 Electron GitService 工作区 diff（见待立 ADR-0045） | `questor/review/` + `desktop/src/main` |
| 编排与验收（Plan→执行→验收/打回） | **后置长任务层（Phase 6）**，规格来源 EvoFlow（读设计不搬码） | `questor/orchestration/` |
| 运行中插话与接管 | **wuu 的规格**（held_user_work queue/steer + activity 租约） | `questor/habena/` |

内部模块名（`limen` 门槛 / `habena` 缰绳 / `vigilia` 值守 / `gesta` 行事簿）
只用于目录与 commit scope，**不受 PyPI 占用约束**；一旦要抽成独立包发布，
**发布前必须重新核查包名占用**（规则见 ADR-0001）。

---

## 四、代码质量约束

**Python 版本策略**：`requires-python = ">=3.12"`（对外下界，为复用参照项目的
依赖与轮子留活路）+ `.python-version` 固定开发机解释器（本机 3.13）。
下界靠两条显式声明兜住，不靠自觉：`[tool.ruff] target-version="py312"`、
`[tool.pyright] pythonVersion="3.12"`。

**质量门禁（每个任务 DoD，必须贴实际输出，不接受"看起来能跑"）**

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest tests/unit -q
```

`just check` 是上述四条命令的单一入口（理由与退路见 `docs/architecture/structure.md` §2.2）；
**CI 必须调用同一批命令**，本地与 CI 不一致视为缺陷。
本机拿不到 `just` 时，**按 `justfile` 里 `check` 配方的命令逐条手动跑**——命令清单的唯一
真相就是 `justfile` 本身，不得另写 ps1/py 包装（两份定义必然漂移）。理由与选型见 `ADR-0009`。

**门禁范围 = 全部 Python 产出**（`src tests evals scripts`）。只写 `src tests` 会把
`evals/`、`scripts/` 排除在外——违规静默存在而 CI 仍绿，等于门禁给出假的安全感。
新增 Python 顶层目录时必须同步扩 `justfile` 与 CI（ADR-0008）。

契约/数据模型改动加跑 `tests/integration`；依赖方向与不可变性改动加跑
`tests/architecture`。`tests/adversarial/` **只增不减**——让对抗用例变绿的
"改用例本身"行为视为作弊。

**纪律**：跨边界数据一律 pydantic v2 模型，禁止裸 dict；公共 API 必须标注类型；
事件循环内禁止阻塞调用；所有 IO 有超时；`asyncio.CancelledError` 必须放行；
不写裸 `except`；用 `logging` 不用 `print`；
**测试先于实现**——要测一个系统前，先枚举它能怎么坏，再照着失败场景写测试。
新代码禁止新增 `# type: ignore`。禁止 `utils/`、`common/`、`helpers/` 兜底目录。

**注释与文档语言（本项目裁决）**：代码注释与 docstring 一律使用**标准中文**，
commit message 与面向国际读者的 README 保持英文——这两条不冲突，分层如下。

- **模块 docstring**：一句话说明本模块承担哪一柱与边界层身份，需要时补一段"为什么这样切"。
- **公共 API docstring**：中文写清可观察契约（参数含义、返回、抛出的异常、调用前置条件）。
  只描述使用者能看到的行为，不复述内部实现步骤。
- **行内注释**：只写代码本身说不出来的"为什么"——约束、取舍、外部怪癖、坑编号（`B-NN`）。
  禁止翻译式注释（`# 打开文件` 这种一律删）。
- **术语与标识符不译**：API 名、类型名、命令、字段名、协议方法名保留英文原文，
  夹在中文里时不加空格也可读就照原样引用，不要造中文译名。
- 注释里出现的项目名、文件路径、外部约定，一律写成可 grep 的确切形式
  （如 `wuu internal/tools/boundary.go`），不写"那个项目""某处"。

**护栏测试的准入判据**（防止把测试写成配置的复述）

一条测试合法，当且仅当**让它可以失败的是"真实的设计改动"，而不是"随手改个值"**。

- 允许：跨字段/跨文件的一致性契约（Python 下界三处必须一致、协议版本必须匹配）、
  依赖方向、数据模型不可变性、状态迁移的唯一写入入口、权限边界不可绕过。
- 禁止：镜像字面量映射、复述显然的控制流、为凑覆盖率而写、断言 prompt 或文案措辞。
- 新增护栏测试必须同时做**负向验证**：临时注入一次真实漂移，贴出它失败的输出，
  再复原。没有负向证明的护栏测试视为未完成（护栏必须会咬人）。

**红线**：① 原始会话、prompt 全文、真实绝对路径永不进入出机数据与测试 fixture；
② 会话记录是 append-only，验收作废与需求改版都只追加新修订，不改写历史；
③ 权限判定只有一处入口，任何"绕过 limen 的便利路径"直接打回；
④ **Windows 上禁止用 `Set-Content` / `Out-File` 修改源码与配置文件**——该版本的
PowerShell 会给它们写入 UTF-8 BOM，`tomllib` 与 hatchling 会在构建期直接报
`Invalid statement (at line 1, column 1)`，使 `uv sync` / `uv run pytest` 全线失败，
且 BOM 会被后续编辑沿用而长期残留。改文件一律走编辑工具；确需脚本写入时，
用 `[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))`，
并在改完后做字节级确认：`[System.IO.File]::ReadAllBytes($path)[0] -ne 239`。
同理：行尾由 `.gitattributes` 统一钉为 LF，不依赖本机 `core.autocrlf`。

---

## 五、出口判据（阶段不达标不得进下一个）

**主判据＝与 wuu 行为等价**：相同任务、相同模型下，Questor 走与 wuu 同一套协议帧序列，逐帧方法名/字段形状/顺序/终态一致；差异只在 `port-ledger.md` 登记处。**次判据**＝该模块坑目录覆盖率 100% + 每条护栏附负向验证。若 wuu 实跑不可得（Go/macOS-first 限制），显式降级为「契约等价（同套帧回放 against wuu 测试断言）」并同步登记。

**exe 门槛**：A 阶段各 Phase 收口必须产出可安装 exe（见计划 §1.6）并装机冒烟；能力不光活在 CLI，必须能从 UI 路径走通一次。判据一句话：*这个偏离会让用户看到假的完成状态，或让同一事实出现两套真相吗？* 会→不许偏离。

**范围诚实**：wuu 的 remote/插件宿主/MCP/subagent/skills/排班 等属本项目「不做」；不移植是**登记过的决定**（写进 port-ledger / ADR），不是遗漏。

---

## 六、Git 与 Commit

**未经允许，绝对禁止 `git commit` 与 `git push`。** 任务完成后：汇报改动清单与
测试输出 → 询问是否 commit / 打 tag → 未答复前不提交。

Commit message 一律英文 Conventional Commits（本项目面向国际开源社区）：

```
<type>(<scope>): <imperative, lowercase, no period, ≤72 chars>

[body: what changed + WHY, wrapped at 72]
[footer: Refs ADR-NNNN / B-NN]
```

scope = 模块目录名（`engine` `tools` `limen` `habena` `vigilia` `gesta` `evidence`
`orchestration` `providers` `review` `serve` `cli` `docs` `ci` `state` `config` `secrets`
`capability` `workspaces` `version` `context` `prompts` `schemas`）。一个 commit = 一个可独立回滚的逻辑变更，
实现与其测试同 commit；禁止巨型 commit，也禁止每次保存一提交。

**推送目标与保护形态**（`ADR-0011`）：取 B 方案——required checks 但不强制 PR，因此
**直接 `git push origin main` 仍然可行，CI 结果不会拦住我们**。推之前跑全套门禁
（`just check`；本机无 `just` 时按 §四 退路逐条跑）从建议升为**硬要求**。经 PR 合并的
外部改动（Dependabot 等）受 required checks 约束；required 名单以 `ADR-0011` 的表为准，
**非矩阵 job 不带 `(os)` 后缀**——填一个永不 report 的名字会让所有 PR 卡在 "Expected"。

---

## 七、文档地图

| 要做的事 | 必读 |
|---|---|
| 任何任务开工前 | `docs/plans/`（分阶段计划）+ 承重转向 ADR（0037/0038/0040/0041/0042/0045）+ 本文件 §〇 §二 §三；`overview.md`/`structure.md` 标「母本对齐改写中、以转向 ADR 为准」 + `docs/adr/README.md` 索引 |
| 想知道目录/包怎么摆 | `docs/architecture/structure.md`（物理布局地图；职责登记仍以 overview §6 为准） |
| 想知道当前阶段怎么做/读什么 | `docs/plans/development-plan.md`（阶段顺序、参照项目阅读地图、文档产出时点） |
| 改数据模型 / 状态机 / 消息协议 | `overview.md` §7 §8（契约源头）→ **先改文档并递增版本号，代码跟随**；顺序不可反 |
| 新增顶层包 | 先在 `overview.md` §6 登记一行职责（R5），否则评审打回 |
| 重写任何边界层模块 | `docs/specs/pitfalls.md` 对应条目 + 参照实现的行为规格 |
| 要解释一条链路实际怎么跑通 | `docs/notes/`（带锚点与日期；`check_notes` 会对过期条目判红，详 ADR-0010） |
| 加依赖 | 先在 `docs/adr/` 落一条记录，正文说明理由 |
| 放不进上面任何一行 | 先写一条轻量 ADR，再动手 |

**契约三件必须超前（本节首要）**：协议（`protocol.md`）、数据模型（`data-model.md`）、模块边界（`structure.md` + overview §6）三件必须**先于当期里程碑定稿**，否则会长出两套契约——本次转向所有冲突的总根因就是契约三件没超前、而 plans/modules 超前了。

**文档视距**：当期阶段之外的模块内部设计篇不修订、不新增，防止"用写文档代替交付"。

### 决策留痕（ADR 触发清单）

开发过程中碰到下列任一项，**先写 `docs/adr/NNNN-标题.md` 再动手**（一页能写完就写，
写不完升 `docs/specs/`）；事后补写等于未发生：

1. 改变数据契约 / 状态机 / 消息协议 / schema（与上表“先改文档”并存：
   ADR 记“为何改”，契约文档记“改成什么样”）；
2. 技术或依赖选型变更（新增第三方依赖、换工具链、改门禁入口）；
3. 范围变更：砍单、推期、新增阶段（如 Phase E）；
4. 实现与文档矛盾，需要现场裁决；
5. 发现两份文档不一致（裁决结果必须**回写修正两处**）；
6. 发现新的、可泛化的坑（补 `B-NN` 并同时落对应测试；编号须先过 `check_specs.py` 唯一性断言，否则注记不算数）。
7. **废弃、替换或从母本移植既有实现**（转向期间新增动作：扔代码/换蓝本/改判既有 ADR 结论——须落 ADR 记「为何废、依据哪条母本、差异登记在 port-ledger 何处」）。

不必写 ADR 的：局部实现细节、命名、测试拆分、当次任务内的临时权衡、格式与注释调整。
判据一句话：**会不会影响两周后另一个模块的开发者？** 会→写；不会→记在 commit 正文里即可。
