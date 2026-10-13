# Questor 开发计划（development-plan）

版本: v0.4（新 Phase U 界面/桌面壳主线提前、E1 并轨；桌面壳改判 Electron，ADR-0030）| 更新: 2026-10-13 | 状态: 待用户评审
关联: `overview.md` §12（里程碑交付与出口判据，**不变真相**）、`structure.md`（目标态布局 v0.3）、`AGENTS.md`（工程纪律）、`docs/adr/`

## 0. 本计划怎么用

- **与 overview §12 的分工**：§12 回答"每期交付什么、出口判据是什么"；本文回答"怎么做、按什么顺序、什么时候写什么文档、做的时候去参照项目读哪些区域"。两者冲突以 §12 为准；布局以 structure.md 为准。
- **多会话协作**：任何会话开工前读本文当前阶段小节 + overview 对应节 + AGENTS.md；完成一个阶段后**勾销状态行**并追加一行实际结果（偏离时写明原因——AGENTS.md 已允许有理由的偏离）。
- **阅读地图颗粒度 = 区域级**（目录/子系统），扫描时按 AGENTS.md §二落盘三资产，**不受本文清单封顶**——清单是"至少读这些"，不是"只读这些"。
- **对齐纪律**：本文 v0.2 基于 structure v0.3；structure 再演进时，先对齐本文再动工，防止计划带着过时布局指挥写码。
- 2026-10-11 三个只读代理完成一轮深度扫描（FlowCoder / EvoFlow / wuu 各一），本文阅读地图即其产出；M1 落盘时仍须亲自细扫补坑条目。

**引用核查记录（可复核，铁律 1）**：2026-10-11 对本文引用抽查 40 条，命中 37，另经复验修正/澄清 4 处并留痕：① EvoFlow 审批门 `supervisor_plan_gate` 为代理误名，真实承载是 `agents/middlewares/tool_approval_middleware.py` + `tool_approval_executor.py` + `agents/human_gate_tools.py`（M1 阅读地图已改）；② `app-shell/`、`terminal/` 补全为 `evopanel/src/zcode-ui/` 之下（M3 已改）；③ "1076 行巨型 `_run_loop`" 精确化为 "core.py 全文实测 1076 行，`_run_loop` 自 L289 起"（M2 已改）；④ 抽查中判为"不存在"的 `evopanel/src/zcode-ui/styles.css` 复验**实存**（2053 行、含 Tailwind v4 `@theme`），引用保留并补全路径。对 overview / structure 既有断言的抽查全部一致。

## 全局约束（每阶段都适用，出处 AGENTS.md / overview / structure）

- 三柱优先级固定：**可见 → 可干预 → 可验证**；透明度恒为最大，分级的是写域。
- R1-R5 硬规则；契约改动先改 overview/契约文档并递增版本号，代码跟随。
- 全 Python ≥3.12（开发机 3.13），不引入 Go；新增第三方依赖先落 ADR。
- 质量门禁四件套（ruff / format / pyright / pytest）每任务必跑；**M1 起 `just check` 为单一入口，CI 调同一批命令**；依赖方向由 import-linter 矩阵机械强制（structure §5，**0 违规起步，不设 baseline**）。
- 测试先枚举失败方式再实现；对抗套件只增不减。
- Windows 第一平台；权限与沙箱语义按 ADR-0007（standard 档无 OS 写隔离，如实标注）。
- 参照纪律：**扫描式重写，不拷贝代码**；沿用参照项目的设计决定时，重写实现并加 provenance 注记（不用"照抄"级措辞——每处沿用都要过一遍对应坑目录）；坑目录条目 B-NN 与测试一一对应。
- **跨进程契约的唯一校验权威在 Python 侧**（pydantic v2）；schema 为纯 JSON Schema，前端类型生成（R4，禁止手写 DTO）。

---

## Phase M0 — 仓库骨架与文档基线（已完成）

**状态**：`- [x]` 已完成（2026-10-11，提交至 `09dd223`）

**实际结果**：仓库骨架、门禁四件套（负向验证已演示：注入 3.12→3.13 漂移即红）、ADR-0001/0007、overview / structure / 文档地图就位；测试七类目录骨架；组织名 `questor` 核查关闭（被占，保持个人账号仓库）。

---

## Phase M1 — 扫描三资产 + 契约与 schema + 工程外围（契约先行）

**状态**：`- [x]` 已完成（2026-10-11；M1a/M1b 出口逐项核对见下"实际结果"）

**实际结果**：坑目录 67 条（≥50）且编号连续、各有归属（`scripts/ci/check_specs.py` 绿）；
11 篇 behavior 规格（FlowCoder 5 / EvoFlow 3 / wuu 3），证据抽验 10/10 命中；契约两篇转
正式（data-model v1.0 / protocol v1.0）；`src/questor/schemas/` + 生成链落地（gen-check 绿）；
N=12 钉死（evals/tasks/tasks.json）；工程外围（justfile / .editorconfig / .pre-commit /
SECURITY.md / 3 workflows / 模板 / dependabot / testenv）；tests/architecture AST 依赖矩阵
0 违规（import-linter 随 M2 首批模块引入，见该测试 docstring）；evals 骨架（12 任务定义 +
runner 协议 + result.schema）；ui/ 骨架（token 四文件 + mock + 第一屏，typecheck/build 绿；
浏览器可视化确认留待首次 `npm run dev`）。import-linter 声明式契约因"模块未物化"延至 M2
（structure §5 预案），contracts.yml 同步收敛为 AST 测试。

**M1 复审修正（2026-10-11，全部实测）**：上述勾销在四项上不完备，已当场修正，
余下两项待裁——记录于此，不让"已完成"带着洞进 M2：

- ✅ 已修：**门禁范围有洞**——`just lint` 与 CI 只跑 `ruff check src tests`，把 `evals/`、`scripts/`
  两类生产 Python 排除在外；后果是仓库里已存在 4 个 ruff 错 + 1 个未格式化文件而 CI 全绿。
  现已把四个目录同时纳入 just 与 CI。
- ✅ 已修：**`just check` 不等于 AGENTS §四 的四件套**（原只含 lint/arch/gen-check）。现 check =
  lint+types+test+arch+specs+gen-check+前端 typecheck。**本行原写"CI 从不跑 pyright"与
  "`check_specs.py` 从未被任何 CI 调用"与现状不符；M2.3 二次核对时我一度把它改成另一句错话
  （"没有任何 CI 步骤比对 generated/"），两句都已按现实修正**：`ci.yml` 的 lint job 仍跑
  `ruff check`/`format --check`/`lint-imports`/`pyright`/`check_specs`/`check_notes`/
  `npm run gen:check`/`ui typecheck`/`uv build`/`pre-commit run --all-files`（L35-54），
  test job 的 windows leg 再跑一次 `gen:check` 拦 B-68 跨平台漂移（L93）。
  **真的缺的只有两件**：生成器脚本住在 `ui/scripts/` 而非 `structure.md` §9 规定的
  `scripts/gen/`（定义点归属错），与 `third_party/THIRD-PARTY-NOTICES` 的生成器完全不存在——
  两者都是阶段 G 的实体工作，补救口径见 ADR-0019（已按此改写前提）。
- ✅ 已修：**`testenv` 的反向守卫只是文档声称**（fake_home 模块 docstring 说"tests/architecture 会检查"，
  实际没有该测试）；已落 `test_production_code_never_imports_testenv`，并做负向验证（注入违规文件→FAILED，
  删除→3 passed）。同时新增 `test_reverse_guards_have_teeth`，防止矩阵在"无可检对象"时空转。
- ✅ 已修：**`check_specs.py` 只校字面格式**，不校引用是否存在；现逐条核实证据列的文件路径真实存在
  （67/67 通过），参照仓根由环境变量提供，不在本地时只校形式不误报。
- ✅ 已修：`.pre-commit-config.yaml` 已提交但 dev 依赖里没有 pre-commit → **`just setup` 必失败**；已加依赖。
- ✅ 已修（复审提出的三项扩展性风险）：**矩阵双向允许构成环**（`serve`↔`cli`）——structure §5 收敛为
  `cli`→`serve` 单向，并新增 `test_matrix_has_no_bidirectional_edges`（对矩阵自身查环，
  不依赖实现是否存在）；**`check_specs` 与"编号不复用"的冲突**——不放松连续性，而是新增
  `moot` 状态（不再适用的条目保留占号、不计入下限），`docs/specs/README.md` §二同步；
  **`classify()` 的 `outcome_exit_code` 是死参数**——现参与兜底，无特征且退出码为 0 时
  报参数错误而非猜分类，附 7 条单测（含负向）。
- ✅ 已补：**前端文档空缺**——`ui/` 此前无任何说明，现新增 `ui/README.md`（目录职责、命令、
  mock 与生成物不可手改边界、**会话真相永不镜像到前端状态**的约束），并接进 `docs/README.md`
  与 structure §7。
- ✅ 已补：M1b 清单项 **`tests/contract/` 与 `tests/fixtures/`** 已按 §11 的占位例外建立
  （各自 README 写明本套件断言什么、为何存在、以及"收集 0 条属预期不作门禁依据"）。
- ⚠ 已登记不可用：**`just` 本机装不上**——`winget install Casey.Just` 能找到包（1.58.0）但下载
  GitHub Release 被网络拦截（`0x80072f19`）；`cargo`/`choco`/`scoop` 均无；PyPI 上同名包无法
  核实来源，故**不装未知来源**。退路已成文（AGENTS §四 + `ADR-0009`）：按 `justfile` 的 `check`
  配方逐条手动跑，不另写一份包装；"本地与 CI 同源"当前由 CI 逐条执行 + `pre-commit run --all-files` 证明。
- ℹ 工具教训：核查行号/行数一律用 Python `splitlines()` 或 .NET `ReadAllLines`；PowerShell 5.1 的
  `Get-Content` 实测把 1076 行的参照文件读成 1004 行，曾据此误判"引用错位"（详见 ADR-0008）。

**做什么**（= overview §12 M1 + structure §11 M1 行；**裁定：`ui/` 骨架提前至 M1 起，structure §11 已同步**——schema 与生成链正是 mock 驱动 UI 的前提，真异构部分〔sidecar、窗口〕仍属 M3）：
- **M1a（契约与资产）**：三资产扫描落盘；`data-model.md` + `protocol.md` 转正式；`src/questor/schemas/` + 生成链；**钉死对照评测的 N**；
- **M1b（工程外围与前端骨架）**：`justfile` / `.editorconfig` / `.pre-commit-config.yaml` / `SECURITY.md` / `.github` 起步 3 workflow + 模板 + dependabot、`scripts/{ci,gen}`、`src/questor/testenv/`、`tests/{contract,fixtures}`、import-linter 矩阵、`evals/` 骨架、`ui/` 骨架（design token + 生成类型 + mock 协议服务）。

**怎么做**（顺序）：
1. 先定三资产模板（`behavior-*` 字段：输入→输出→边界行为→坑编号），避免三份扫描格式漂移；
2. 按下方阅读地图分项目细扫，每扫完一个区域即落对应 `docs/specs/` 文件与坑条目（B-NN，含归属模块）；
3. 汇总坑目录去重、按模块归属分派（对照 structure §3 模块清单逐项归位）；
4. 写契约：`docs/architecture/data-model.md`（overview §7 草案转正式）+ `protocol.md`（§8 转正式，含 `qst-app-server/v0.1` 方法与事件清单、桌面 stdio 与网页 WS/SSE 双传输的同一会话层）；
5. 写 `src/questor/schemas/`（`app_server/` + `model/` 两族，**纯 JSON Schema**），打通"schema → `ui/src/rpc/generated/`"生成链，`just gen` 后 `git diff --exit-code` 为空（R4 可检查形式）；
6. **钉死 N=12**（4 可见 + 4 干预 + 4 验证）——本文所有"与参照实现同 N 个真实任务"自本阶段起一律指 12，写入 `evals/` 约定；
7. 工程外围按 structure §9-§10 物化；import-linter 三条硬断言同落（append-only、状态迁移唯一入口、权限无绕过）。

**文档产出**：`docs/specs/{behavior-*.md, pitfalls.md, cases-*.md}`；`docs/architecture/{data-model.md, protocol.md}`；本计划状态勾销。

**阅读地图**：
- **FlowCoder**（执行核规格主源）：`agent/`（循环生命周期、四维预算收敛语义、事件协议、输出恢复）、`tools/`（工具契约、并发安全分区、Bash 退出码语义映射）、`permissions/`（六层判定——对照简化为三档+敏感守卫的依据）、`context/`（两层压缩规则与常量）、`conversation.py`（数据模型）、`client/resilience`（流式重试边界）、`sandbox/`（容器池语义，M8 用）、`filehistory/`、`eval/`（评测管线与失败四分类）、`core/`（原子写）；
- **EvoFlow**：`collab/`（任务状态机白名单）、`agents/middlewares/tool_approval_middleware.py` + `tool_approval_executor.py`、`agents/human_gate_tools.py`（审批门真实承载："破坏性动作被门拒绝"的语义在此核对）、`persistence/`（存储分层）、`gateway/routers/tasks.py`（会话操作语义清单）、`gateway/zombie_run_sweeper.py`（自建清扫的必要性）；
- **wuu**：`internal/tools/`（boundary 唯一门、敏感路径守卫、工具输出规则）、`internal/config/`（设置分层 strip 用户专属字段）、`internal/appserver/`（协议形状、initialize、deferred content、通知族）、`internal/session/`（inbox / held_user_work）、`internal/agentengine/` + `internal/enginecatalog/`（引擎契约与探测）、`internal/process/`（停树三元组校验）、`evals/`（公开结果 schema 与"结果先于声明"纪律）。

**前端同步点**：`ui/` 骨架 M1a 出 schema、M1b 出 token 与 mock 服务（React 19 + TS + Vite 6 + Tailwind 4）；token 参照 **`evopanel/src/zcode-ui/styles.css`**（2053 行、Tailwind v4 `@theme` 所在；evopanel 另有 51 个分散 css，按面板归属扫描）；面板交互参照 wuu。rpc 层用生成类型 + **mock 协议服务**驱动 UI，不等内核。`desktop/` 壳改判为 Electron、物化改到 Phase U（ADR-0030），M2 末不再摆 Tauri 骨架。

**出口判据**：
- M1a：坑目录 ≥50 条且各有归属模块；`just gen` 后 `git diff --exit-code` 为空（前端类型可生成）；N=12 已写入 `evals/` 约定；
- M1b：`just check` 本地与 CI 同源；import 矩阵对既有代码 0 违规；`ui/` 用 mock 服务渲染出第一屏（会话列表 + 对话流空态）。

---

## Phase M2 — 单轮内核跑通（engine + 基建模块群 + cli）

**状态**：**M2.1 地基 `- [x]` 已完成（2026-10-11，提交至 `599cd02`）**；**M2.2 内核 `- [x]` 已完成（2026-10-11，提交至 `3ec32c4`）**；**M2.3 体验闭环 `- [x]` 已完成（2026-10-12，已推送 `e5407c8`..`6fcd177`）**；**M2 总出口 `- [x]` 已达成**

**M2.3 实际结果（2026-10-12）**：契约先行——ADR-0016（自建 httpx wire 层，不接厂商 SDK）、
0017（上下文工程事实入正文，data-model v1.2）、0018（提示词类型化分块与缓存边界）、
0019（生成链定义点归位）、0020（接口面提前：UI 注册表骨架与 `HandlerCtx`/`principal`）、
0021（M2 出口拆分：evals 基线移出）。代码：`providers`（两协议 + 韧性 + 能力三档）、
`prompts` 分块、`context` Layer1/Layer2/rehydrate、`serve` 雏形（信封/分发/通知映射/五方法/stdio）、
`cli`（薄壳，能力全经 serve）。`ModelPort` 定形为 `stream(ModelRequest)` + `capabilities` + `aclose`，
B-08 的输出上限改为逐请求携带。**M2 总出口已真机验证**：`questor exec` 在真实 Anthropic 兼容
端点上跑通“写文件→读回”并落盘可回放（`session list` 可见 last_seq=22），`cache_read=1792` 同步观测到。
坑目录 88 条（新增 B-81–B-88）；`Message`/`ToolResultBlock` 改 frozen 使 B-25 由类型兼管。
**本轮真机/护栏当场抬出的三个真缺陷**（都已修并钉住）：B-85 静默丢记录、B-86 审计缺全文、
B-88 assistant 轮次不入历史（fake model 永远测不出，只有真端点会 400）。

**M2.3 偏离留痕**：① evals N=12 对照基线首跑按 ADR-0021 移出本期出口，挂 M3 出口前；
② 阶段 G 只完成了“定归属”部分（ADR-0019），`scripts/gen/` 实际搬迁与 `third_party/notices`
生成器本期未做（CI 已在跑 `gen:check`，R4 不是裸承诺）；③ 阶段 I（ui 用 generated 类型驱动
流式渲染）未做，前端仍住 mock——记为偏离，补救里程碑 **M3**（AGENTS §五 前端跟随）；
④ `cli init` / `session show` 未做（后者需先给 `protocol.md` §3 加 `thread/show`）；
⑤ `turn/start` 的后台 run 需 `wait_idle()` 才能观测到完整通知流（B-01 修正后已绿）；
WS/SSE 传输与反向请求通道属 M3。

**M2.1 实际结果**：地基七模块全部落地并各自成 commit——`version`（VERSION 单点 +
pyproject dynamic）、`state`（路径单点 / 原子写 / 跨进程锁，B-71/72/73）、
`schemas/model.py`（data-model v1.1 的 pydantic 绑定 + 一致性护栏）、`gesta`
（append-only JSONL + fold 回放 + 可重建索引，B-45/46/74；工具结果 O_EXCL，B-24）、
`config`（分层合并 + strip 用户专属字段，B-57/75）、`secrets`（keyring 优先 + 文件回落）、
`capability`（opt-in 旗标）、`workspaces`（哈希身份 + 可见性判定）；三条硬断言落地两条
（append-only、状态迁移唯一入口，权限无绕过留 M2.2 limen）。契约修订：data-model v1.0 →
v1.1（queued→cancelled，ADR-0014）；依赖引入 pydantic v2 / keyring / import-linter
（ADR-0013）；依赖裁决 ADR-0012（gesta、capability 以矩阵为准，overview §6 已回写）。
M2.1 出口判据逐项：落盘可回放（`tests/integration/test_gesta_roundtrip.py` 绿）；
原子写 / 文件锁 / 会话删除对抗用例绿（崩溃注入、真实子进程锁争用与死亡释放、活跃拒删）；
坑覆盖率 100%（B-71–B-75 全 covered，B-24/B-45/46/47/57 回填测试名）；每条护栏测试
附负向验证（VERSION 格式与 static version 注入、append-only 护栏初版没咬住单参数
`open("w")` 后修正为双形式、transitions 旁路 import 注入、依赖矩阵 bogus 包注入）。
**偏离留痕**：① gesta 摘要索引以 JSON 承载，SQLite FTS 搜索索引按 B-46 推迟至 M4
（无第二个真实使用者）；② `third_party/` 通知生成推迟至 M2.3（同因）；
③ 本期无用户可感知能力，前端跟随（mock 事件流流式渲染）按计划留待 M2 收口统一验证。

**M2.2 实际结果**：内核四模块 + 热路径前置决策全部落地——`gesta` 热路径
（ThreadWriter 游标 + 增量摘要，全局锁保留，理由与被否决项见 gesta.md）；
`limen`（六层→三档+恒开守卫链，B-30/31/32/33/34/50..54 全 covered，第三条硬断言
"权限判定无绕过"落地并负向验证）；`tools` 八工具（用户裁决含 todo；run 的
Job Object 整树管理经 ADR-0015 pywin32；实测坑 B-77 PyHANDLE GC、B-78 管道
read1 入目录并回填测试）；`engine`（显式状态机 + 形状护栏 B-05/06 当场咬住
重复提示词常量与超长函数；B-02/03/08 covered）；`prompts` 资产四件随包发布。
M2.2 出口判据逐项：**单轮跑通**（`tests/integration/test_single_turn_kernel.py`
三步真实链 + 纯 fold 回放，无真实模型依赖——providers 在 M2.3 接入后才具备
真实任务全链条件）；**权限矩阵全绿**（三档 × 调用形状表驱动）；**第三硬断言**
落地（三条全部到位）；坑覆盖率：engine/tools/limen 当期适用条目 100%
（B-01/04/07/09/11 属未触发模块，留痕 open）。
**M2.2 偏离留痕**：① search 的修订号绑定随 M3 review（ADR-0005）；
② todo 会话内存态、落盘随 M4；③ B-09/11 随 memory/context 模块回填；
④ 前端跟随（mock 事件流渲染）随 M2.3 收口统一验证——M2 未收口；
⑤ 会话为 turn 作用域，跨 turn resume 随 M2.3 context。

**做什么**（= structure §11 M2 行）：`engine`（内置循环）、`tools`（八工具——用户裁决 2026-10-11，read/edit/write/search/list/run/process/todo 全做，回写 overview §12）、`limen`、`context`、`gesta`、`providers`、`prompts`、`config`、`state`、`secrets`、`capability`、`workspaces`、`version`、`cli`、`serve` 雏形；`VERSION`、`third_party/`；`evals/runner`。

**怎么做**：
1. 事件流 schema 先于循环代码（沿用 FlowCoder `agent/events.py` 的同一设计决定：一套事件多端共同消费；重写实现并加 provenance 注记）；
2. 循环**拆显式状态机**（FlowCoder `agent/core.py` 全文实测 1076 行、`_run_loop` 自 L289 起的单一巨型函数是反例，R2 落点）；预算常量集中一张表（魔法数散布是反例）；裸 `ensure_future` 统一强引用持有（GC 吞异常的坑）；
3. 止损三重照 overview §10；收敛轮**保留只读工具**（FlowCoder 撤光 schema 的缺陷）；
4. `context/` 按两层压缩：Layer1 大结果落盘回读、Layer2 auto-compact（阈值=窗口-摘要预留-margin；前缀过小不压；CompactBoundary 内联进会话记录供 resume 重建）；
5. `limen/` 按 wuu 语义：单门、可达性推导（符号链接 EvalSymlinks、Windows 大小写折叠）、`error_kind + reason + model_next_action` 模型可读错误方言、敏感路径守卫三档全开（源码扩展名豁免、symlink 双向解析）、审批只收紧（硬拒三件：凭据调用/参数提权/敏感写）、设置分层 strip 用户专属字段；
6. `state/`（路径单点解析+原子写+跨进程文件锁）与 `gesta/`（append-only JSONL + 可重建索引）是其他模块的地基，先行；
7. 停进程树前校验 pid+pgid+start_time 三元组；stdout/stderr 保头尾；ANSI 剥离；
8. **（M2.1 审查前置项——已裁决 2026-10-11，M2.2 开工时落地）** gesta 热路径方案定为：
   **增量摘要 + ThreadWriter 游标句柄 + 保留全局锁 + per-call 锁超时**——写路径去掉
   第二次全量 load（摘要增量构造）；`gesta/writer.py` 的句柄缓存 `(last_seq, 文件字节数)`，
   追加前 stat 校验，O(1) 追加、被其他进程追加过则从缓存偏移重读尾部同步；放弃 per-thread
   锁（跨进程索引一致性与 wuu 蓝本优先，理由见 `docs/architecture/modules/gesta.md`）。
   决策依据与完整方法记录在该设计篇。

**文档产出**：M2 各模块内部设计篇（随各自开工任务写，不提前）；`evals/` 任务集约定与首跑记录（对照 wuu 公开结果纪律：失败也要发布）。

**阅读地图**：FlowCoder `agent/core.py`、`agent/events.py`、`agent/output_recovery`、`agent/budget`、`tools/base.py`、`context/manager.py`+`tool_results.py`、`permissions/checker.py`、`conversation.py`；wuu `internal/tools/boundary.go` 区、`internal/approvefor/`、`internal/config/settings_layer.go`、`internal/process/manager.go`、`internal/statepath`+`securefs`+`storelock`（state 蓝本）。

**前端同步点**：`ui/` 对话流接 **mock 事件流**完成流式渲染（streamdown + shiki）、工具卡片（evopanel `ToolCallBlocks/` 注册表模式）、composer 双 pending 态（wuu `ComposerPendingState`）；zustand 显式用 v5（参照项目是 v4 写法，不写清会混用出隐性 bug）。

**出口判据**（§12 总出口：一个真实小任务完整跑通并落盘可回放；内部分三段）：
- M2.1 地基（state / gesta / config / version / secrets / capability / workspaces）：落盘可回放；原子写、文件锁、会话删除的对抗用例绿；
- M2.2 内核（engine / tools / limen / prompts）：单轮跑通；权限矩阵（三档 × 工具类）测试全绿；
- M2.3 体验闭环（context / providers / serve 雏形 / cli）：压缩后 resume 可恢复；
  真实任务全链（单轮 + 跨 turn resume，从 cli 与 serve stdio 各跑一次）并落盘可回放。
  **evals 对照基线首跑已移出本期出口**（ADR-0021）：改挂 M3 出口前，基线仍为
  FlowCoder 为主、EvoFlow 按任务类型可选、wuu 不作基线（与 structure §8 一致）。

每段出口附：该模块坑目录 B-NN 覆盖率 100% + 每条护栏测试的负向验证输出。

---

## Phase M3 — 工作台数据面（前后端首次真接）

**状态**：`- [x]` **已完成 2026-10-12**（M3a-1 schema 方法族 + 生成链归位 / M3a-2 review 与写时 diff / M3a-3 habena + Fanout + Engine 消费点 / M3b-1 thread 四操作 + sessiontrace / M3b-2 worktree / M3b-3 WS + serve http / M3c UI 真接 + 视图注册表 / M3d evals 适配层 + 归档），**总出口** 1–4 达成、出口 5 因本机无凭据记 pending（诚实标注不凑基线）

**M3 实际结果（2026-10-12）**：契约先行——ADR-0022（serve 传输层引 starlette+uvicorn）、0023（M3 只
落 WS、SSE 推 M8）、0024（桌面壳从 M3 摘出推 M4/M5）、0005（工作区修订号与 turn↔revision 绑定，
M3d 归档 accepted）。代码：`review`（unified diff + hunks + fingerprint + 写时算 + turn↔revision 聚合）/
`habena`（Inbox 幂等 + held_work record kind 入正文 + CAS 接管栅栏）/ `sessiontrace`（fold 投影）/
`worktree`（git CLI 子进程薄包装）；serve 方法表从 5 扩到 20，`Fanout` 多宿主扇出（B-96）+
反向请求 pending 路由（B-59）；`Engine` iteration 起点前 `_consume_inbox_iteration` 消费点（B-67/94）；
`ws` + `http` 传输（assert_localhost_only 硬拒 0.0.0.0）；CLI `serve http` 子命令。前端：`Transport`
抽象 + `WebSocketTransport` + 强类型 `client.ts`；`panels/registry.ts` 视图注册表骨架 + `PanelHost`
单分发 + `Review` / `Files` 两块真接面板 + `MessageStream` 通知分派 + Composer 解禁。护栏：
`test_schemas_method_families`（方法族形状）+ `test_tools_impl_no_blocking_io`（file 工具 IO 沉 thread）+
`test_no_hardcoded_panel_case`（外壳无面板名硬编码）+ `test_serve_http_ws`（WS 与 stdio 方法表一致）+
`test_review_turn_diff` + `test_habena_steer` + `test_habena_control` + `test_serve_fanout` +
`test_habena_steer_adversarial`（幂等 + expected_turn_id）。生成物 `app_server-v0-1.d.ts` 从 9 行空
interface 展开到 463 行严格类型，兑现 R4。

**M3 偏离留痕**：① **evals N=12 基线首跑未跑**——本机 `QUESTOR_MODEL_API_KEY` 未配，出口判据 5
记 pending；诚实标注优于用假端点凑基线（evals/README 纪律 1 与 overview §11）。② **桌面壳
`desktop/src-tauri/` 推 M4/M5 交界**（ADR-0024），M3 用 `serve http` + 浏览器 localhost 已能验
双宿主同契约；structure §11 与 overview §12 已同步。③ **SSE 推 M8**（ADR-0023），三问判据第 3 问：
M3 无第二订阅者，WS 已覆盖浏览器宿主；overview §8 与 structure §7 里"WS/SSE"已回写为"WS（M3）+
SSE（M8）"。④ **Terminal 面板 / Browser 面板 / `thread/search` / `selection/annotate` / `engine/list` /
`config/*`** 六项按 plan "明确不做" 推后；不塞进 M3 出口判据，避免为了面板好看牺牲三柱（AGENTS 铁律 3）。
⑤ **Fanout 慢订阅者不阻 publisher**：本期 queue 无上限、`put_nowait` 不阻；M4 长跑引入背压时
另开 ADR-0025（overview §14 “队列满即阻 publisher”属默认）。

**做什么**（= structure §11 M3 行）：`review`（修订号 + turn↔revision）、`habena`（插话/接管/取消）、`sessiontrace`（轨迹回放，不重跑工具不联系模型）、`worktree`；`ui/` 与 `desktop/src-tauri/`、`assets/`；`contracts.yml`/`desktop.yml` 两个 workflow。
**本期额外两个接口面（ADR-0020：它们属接口，不得后置）**：① `ui/` 视图注册表**骨架**（`PanelDescriptor` + 单一渲染分发点 + 护栏：新面板只能登记不得改外壳）——M3 是第一个真接面板，此时建最便宜；② `principal` 传递位已随 M2.3 的 `serve` `HandlerCtx` 落定（本期不写任何鉴权判定）。

**怎么做**：
1. diff 在**写工具执行时刻**计算并随工具结果持久化（wuu 语义：前端吃结构化 diff，不事后重读文件猜测）；
2. 分页续读用 `expected_revision` 拒绝陈旧；选中文字用内容指纹 + 字节 offset 映射定位回源（处理 BOM/混合换行）；
3. 插话消费点定在**每个模型步之前的统一汇聚边界**（wuu `internal/agent/loop.go:400` 的 `cfg.BeforeStep` 汇聚点模式：插话 + 已完成后台进程 completion 同口进）；`expected_turn_id` 防陈旧提交；`client_id` 幂等去重；core 重启 rehold 重放；steered 消息持久化挂原 turn；
4. 接管 = 控制栅栏（CAS + revision），stale 进程不能撤销人的接管；
5. 桌面传输 = stdio NDJSON sidecar（`runtime_state.json` 单调 generation + lifecycle_lock 防拉起竞态——沿用 EvoFlow `backend.rs` 的同一设计决定，重写实现；sidecar 拉起放后台线程 fail-open）；网页宿主同构建产物走 Gateway WS/SSE，**默认只绑 127.0.0.1**；
6. 桌面壳职责收缩为纯壳：窗口、sidecar 生命周期与崩溃重启、capabilities。

**文档产出**：`review/habena/sessiontrace/worktree` 内部设计篇（随开工）；ADR-0006（桌面壳选型与浏览器面板边界）从 planned 转正式。

**阅读地图**：wuu `internal/tools/review.go`+`diff.go` 区、`internal/appserver/turn_handlers`+`held_user_work`+`fork.go`（三级历史回退 + live 分叉）、`internal/session/inbox`、`internal/sidethread/`、`internal/worktree/`、`internal/process/storage_maintenance`（8MiB 尾部 + LogBaseOffset）；EvoFlow `src-tauri/src/commands/backend.rs`、`lib.rs`、`src/zcode-rpc/` 四层通信；evopanel `src/zcode-ui/app-shell/`（resizable 面板组合）、`src/zcode-ui/PermissionDialog.tsx`、`src/zcode-ui/terminal/`。

**前端同步点**：本阶段即同步点本身——协议真通（桌面 stdio + 网页 localhost 双宿主同一会话层）、面板真数据。技术栈现成件直接沿用 evopanel 实测选型：`@xterm/xterm`、`@pierre/diffs`、`streamdown`/`shiki`、`lexical`。

**出口判据**（§12）：面板显示真实 diff；插话在下一个工具边界被消费；接管即停。

---

## Phase M4 — 长跑与编排（vigilia + orchestration + evidence 最小版）

**状态**：`- [x]` **已完成 2026-10-12**（M4a 契约先行 / M4b vigilia / M4c orchestration /
M4d evidence 最小版 / M4e 接口面 + UI + e2e + docs.yml），**总出口达成**（e2e 主钉绿 +
状态机无旁路写入守卫绿）

**M4 实际结果（2026-10-12）**：契约先行——ADR-0025（编排域实体/状态机/独立 store）、0026
（vigilia 调度与清扫）、0027（evidence 最小版与 export 接口）、0028（协议加性演进）；
data-model v1.3、protocol v1.1、schema（`schemas/orchestration/` + app_server 21 方法族
5 通知族 + `Run.task_id`/`goal_id`）。代码：`vigilia`（声明式触发器 + tick/per-task 锁复判
+ 游标清扫 + 双 reconcile + 检查点 + `process` wake）；`orchestration`（单点状态机 + 独立
append-only store + 编排门 + Plan/Goal/Task/board + `OrchestrationService`）；`evidence`
（核对器 + export 接口 + 投影）；`tools`（`OrchestrationPort` 注入 + `plan`/`task` 工具）；
`serve`（21 编排方法 + 5 通知族 + `LongRunDriver` 长跑驱动挂 http 宿主）；`cli`（task/goal 薄命令）；`ui`（Board 分栏看板 + 确认/打回）；
`tests/e2e/`（转后台→任务总结→打回→重做→diff 可回看）；`docs.yml` + `check_docs.py`。护栏：
`test_orchestration_transition_single_entry`、`test_orchestration_fold_kinds_are_projected`、
`test_vigilia_*`（含对抗）、`test_orchestration_gate/store/service`、`test_evidence_*`、
`test_ci_parity`（扩 docs.yml）。**负向验证**：两条新编排护栏各注入一次真实漂移即红（已复原）；
B-96 的拒绝分支临时禁用即红（已复原）；B-94 由并发用例当场抓到（5→1）。

**M4 收尾四件事**：① 本计划状态勾销 + 此实际结果；② `overview.md` §12 M4 行标记已完成；
③ 四条 ADR 已落（索引同步）；④ 坑目录 B-40/41/42/43/44/49 转 covered、新增 B-94/95/96、
B-38/39 裁 moot。

**M4 收口审查（2026-10-12，全部 TDD 先红后绿）**：全面审查抓到 5 项确凿缺陷与 1 项接线缺口，已收口——
① tick/sweep 检查点双写回退竞态（B-97：持锁字段级读-改-写 `record_tick`/`set_sweep_cursor`）；
② `task/review` 产品入口缺失（B-98：看板待验收列与确认/打回真实可达；e2e/集成链改经 serve，不再直调 store）；
③ Goal `record_round` 绕开域内白名单（B-99：仅 RUNNING 可记轮，完成/失败均经 `_move`）；
④ 编排 store fold 裸异常（B-100：B-76 异常类型化口径补齐，脏记录统一报存储错）；
⑤ `sync_subtasks_from_plan` 无消费者 + “定稿才派生”未机械执行 + 崩溃重复派生（`task` 工具补 `sync` 动作、
`OrchestrationPort` 扩 `sync_subtasks`、逐步回填 step.task_id 幂等重放）；
⑥ 长跑驱动未接线（计划 M4e.2 启动 hook）：新增 `serve/longrun.py::LongRunDriver` 挂 http 宿主生命周期——
tick 循环到点 `turn/start`、启动+周期双 reconcile（B-44，活体不误杀、僵尸必收）、Goal 轮自驱
（`goal/start` 即时唤醒 + 重启拾取）；`schedule/create` 方法补登（总 21，M4 目标形态仅 thread_id+prompt）。
遗留边界（诚实标注）：stdio 宿主不挂驱动（`goal/start` 在那只登记状态）；task 派发目标随 M5；
`task/start` 的 authorized 仍为本地信任自报（随 M8 鉴权收紧）；evidence 生产写入点随 M5 验收卡接线。

**M4 偏离留痕**：① 看板 **DAG 图推 E1**（D7；M4 落注册表驱动的分栏看板，满足前端跟随即止）；
② 桌面壳 `desktop/src-tauri/` + `assets/` + `desktop.yml` **推 M5**（ADR-0024 M4 收口）；
③ `OrchestrationPort` 为"编排门有真实调用方"而落（D4），若评审否决则退化为 served-only 编排；
④ evals N=12 基线首跑仍 pending（本机无凭据），按 ADR-0021 口径继续诚实标注，不凑基线。

**分段与偏离留痕（2026-10-12，用户裁定"扩展优先"）**

- **M4a 契约先行**：ADR-0025（编排域实体/状态机/独立 store）、0026（vigilia 调度与清扫）、
  0027（evidence 最小版与 export 接口）、0028（协议加性演进）；data-model v1.3、protocol v1.1、
  schema 新族 `schemas/orchestration/v1.json` + app_server 方法族；overview/structure/本计划回写；
  生成链重跑（`just gen-check` 绿）。
- **M4b vigilia**：声明式触发器（once/interval/cron）+ tick（per-task 锁 B-49）+ 分批游标清扫（B-40）
  + once 幂等（B-42）+ 启动/周期双 reconcile（B-44）+ 唤醒检查点；`process` 工具补"改唤醒周期"。
- **M4c orchestration**：`transitions.py` 单点状态机 + 独立 append-only store + 编排门（结构化载荷 B-43）
  + Plan/Goal/Task/board；模型侧 `plan`/`task` 工具经 `OrchestrationPort` 注入（tools 不 import orchestration）。
- **M4d evidence 最小版**：声称 vs 录得核对器 + `export` 接口形状 + 投影；不做复跑。
- **M4e 接口面**：serve 编排方法族与通知族 + assembly 注入 + CLI 薄命令 + `ui/` 看板面板
  + `tests/e2e/` + `docs.yml`。
- **偏离**：① 看板 **DAG 图推 E1**（M4 落注册表驱动的分栏看板，满足 `AGENTS.md` §五 前端跟随即止）；
  ② 桌面壳 `desktop/src-tauri/` + `assets/` + `desktop.yml` **推 M5**（ADR-0024 M4 收口）；
  ③ `OrchestrationPort` 为"编排门有真实调用方"而落，若评审否决则退化为 served-only 编排（见 ADR-0025 失效条件）。

**做什么**（= structure §11 M4 行）：`vigilia`、`orchestration`、`evidence` 最小版、`tests/e2e/`。

**怎么做**：
1. 任务状态机白名单 + 双向映射沿用 EvoFlow `collab/state_transitions` 的语义；破坏性编排的门沿用 EvoFlow 审批门语义（真实承载：`agents/middlewares/tool_approval_middleware.py`、`agents/human_gate_tools.py`——"工具直接返回错误，而非中间件注入拦截"在此核对）；
2. 无人值守队列：tick 节流、并发上限、重试退避、per-task 锁防 tick 重入；**扫描/清扫必须有游标分批**（zombie sweeper 紧密空转的坑）；
3. 自动化：once 任务错过即跳过不重放；cron 本地时钟休眠/漂移风险显式声明；同分钟去重；
4. Goal 长跑循环：每轮 1-3 句指令、唯一结束信号、并发与时长上限（EvoFlow goal_service 形状）；
5. 会话操作语义沿用 wuu：删除需 idle + 双租约、运行中拒删拒归档、搜索命中带上下文定位到具体消息。

**文档产出**：`vigilia/orchestration` 内部设计篇；用户指南草稿（首次面向使用者的文档）。

**阅读地图**：EvoFlow `collab/`、`gateway/task_queue_runner.py`、`gateway/automation_runner.py`+`automation_scheduler.py`、`gateway/zombie_run_sweeper.py`、`app/channels/services/goal_service.py`、`app/gateway/channel_result_push.py`；wuu `internal/appserver/thread_delete.go`+`session_organization_handlers`+`search.go`；FlowCoder `scheduler/`+`watchdog/`（仅参照，投机性设计不照单）。

**前端同步点**：看板 UI（M4 落**注册表驱动的分栏看板**——任务列表 + 状态分栏；`@xyflow/react` 的 DAG 图**推 E1**，理由见上"偏离"①）、任务总结卡与确认/打回交互（可审计轨迹以 evopanel `ModelTrajectory*` 一族为范本）。

**出口判据**（§12）：端到端链跑通"转后台→出任务总结→打回→重做→diff 可回看"；状态机无旁路写入。

---

## Phase M5 — 验收证据完整版（evidence）

**状态**：`- [x]` **已完成 2026-10-12**（M5a 契约与 ADR / M5b 验收状态机强制 / M5c evidence
生产写入点 + 声称采集 / M5d schedule task 派发 / M5e 前端证据卡 / M5f evals 三柱扩充），总出口达成

**M5 实际结果（2026-10-12）**：契约先行——ADR-0029（验收状态机强制 + evidence 生产写入点 +
声称显式绑定 + `orchestration → evidence` 有向边）；data-model v1.4、structure §5 矩阵、
`schemas/orchestration` `TaskAcceptance.status` 收敛为 `AcceptanceStatus` 枚举（schema 重生成）。
代码：`orchestration/acceptance.py` 验收态单点入口（+ `store.transition_acceptance`/记录 kind
`acceptance.status`/fold 过白名单/`update_task` 拒改验收态 B-102）；`evidence/source.py`
只读录得源 `collect_recorded`/`verify_claims`；`OrchestrationService.report_task` 接通生产写入
（落证据→驱动 `executing→reported→verified|regressed`→`reviewed`）+ 真实 publish
`evidence/reported`（经 `Engine.attach_orchestration_publisher` hop 回事件循环）；模型侧 `task`
工具 `report` 动作 + `OrchestrationPort.report_task`；`schedule/create`+`longrun._fire` 补 task
派发；`board.tsx` 验收证据卡（点击 `recorded_output_ref`→`sessiontrace/get`）；`evals/runner/grading.py`
把 `replay_audit`/`recorded_output` 接真实函数，tasks.json 12→17。坑目录新增 B-101/B-102（均
covered + 负向验证）。出口判据逐项：`test_report_verified_when_recorded_ok` 钉“结论指向记录
条目”；`test_report_regressed_on_mismatch_and_missing_record`/`test_recorded_output_negative_detects_unverified`
钉“无记录不轻信”；`test_update_task_cannot_change_acceptance_status` 钉验收态单点入口。

**M5 偏离留痕**：① **桌面壳 `desktop/src-tauri` + `assets` + `desktop.yml` 不在本期**（ADR-0024
推到 M5 边界的独立 Rust 大块，与“可验证柱”正交、变化理由不同，单列后续任务更优）；② **复跑核验
不做**（overview §2），只把“录得核对输入”收成单一可替换只读入口（`collect_recorded`）；③ **前端
真机走查与 evals 基线同样因本机无凭据 pending**（证据卡代码路径已接 + tsc 绿；live 走查需
`serve http` + 真实跑，标 pending 不凑）。

**做什么**（= structure §11 M5 行）：`evidence` 完整版 + `evals/` 三柱任务集扩充。

**怎么做**："声称的检查"与当时真实记录输出**并排核对**；核对器只读消费 gesta 记录；验收状态机按 overview §7（requirement_revision 递增自动作废既有验收）；复跑核验明确**不做**（本轮决策，将来走 ADR）；evals 任务集补齐三柱覆盖（不只测编码）。

**文档产出**：`evidence` 设计篇收尾；`AGENTS.md` §五出口判据如需细化在此同步。

**阅读地图**：wuu `internal/tools/review.go` 区（声称 vs 实际的呈现语义）、`internal/toolledger`（工具账本）；EvoFlow `collab/task_state_service.py`。

**前端同步点**：验收证据卡（结论必须能点击跳到具体记录条目）。

**出口判据**（§12）：任一验收结论都能指向具体记录条目；没有复跑也不轻信。

---

## Phase U — 界面 / 动效 / 桌面壳主线（Electron；ADR-0030 提前，紧接 M5）

**状态**：`- [x]` **Phase U（Track A + Track B）已完成 2026-10-13**（Track A：A1~A9 全勾销，见下"Track A 实际结果"；Track B：B1~B9 全勾销，见下"Track B 实际结果"与 `docs/plans/2026-10-13-phase-u-completion.md`；pending 项集中列在 completion doc §2/§5）。插入 M5 与 M6 之间；M6/M7/M8 后移；原 Phase E 的 E1 并入本相。

**Track A 实际结果（2026-10-13）**：契约先行——ADR-0031（`@pierre/diffs` + `vitest` + `happy-dom` + `@testing-library/*`）；行为规格 `docs/specs/behavior-review-fidelity-wuu.md` 与坑 `B-103~B-107` 同步（五条均已 `covered` 并回填测名）。代码：`ui/src/design/tokens.css` 与 `themes.css` 扩族 `--elevation-*`/`--motion-*`/`--color-diff-*` 三族；`base.css` 加 `.qst-focus-ring` 与 `@media (prefers-reduced-motion: reduce)`；`ui/src/panels/review.tsx` 重写为卡片布局（折叠/已阅 dot/fingerprint 前 7 位/100+ hunks 默认折叠/空态早 return）；`ui/src/panels/review.css` 就近样式仅走 token，无 hex；`ui/src/panels/review.diff-view.tsx` 封装 `@pierre/diffs` React 入口（`processFile` + `<FileDiff themeType overflow="wrap">`），`buildFileDiff` 导出为纯函数供测射约层断言。测面：`ui/vitest.config.ts`（happy-dom + jest-dom setup）+ `ui/src/testing/{setup,fixtures}.ts`；`ui/tests/review.panel.test.tsx` 5 条判据 + `ui/tests/review.fidelity.test.tsx` 6 条（B-103/B-104/B-106）+ `ui/tests/design.tokens.test.ts` 2 条护栏；**12/12 vitest 全绿**，`tsc --noEmit` 0 error，`tests/architecture` 30 passed。**诚实标注**：人工浏览器走查需 `QUESTOR_MODEL_API_KEY`（本机无）记 pending；还原度判据已在封装契约层与 CSSOM 静态层钉住，不依赖真机。实现细节与 wuu 参考参照 `docs/plans/2026-10-13-phase-u-ui-and-electron-shell.md` Track A 各 Task commit。

**Track B 实际结果（2026-10-13）**：契约不变（ADR-0030/0032 本相未新行）；Track B 未动 `src/questor/**`、`schemas/**`、`protocol.md`、`serve/**` 方法表与 `PanelProps` 形状。代码：`desktop/` 新目录——B2 壳骨架 + electron-vite 三段构建；B3 `atomic-file.ts` / `questor-command.ts` / `sidecar.ts` 三个边界层模块，主进程 `child_process` 以 stdio NDJSON 拉起 `questor serve stdio`（严格照 wuu `atomicFile.ts` / `wuuCommand.ts` / `appServerClients.ts` 同调、重写加 provenance）；B4 `questor-home.ts` / `sidecar-state.ts` / `sidecar-lock.ts`（`runtime_state.json` 单调 generation + `.bak` crash 容错 + `wx` 独占锁 5 s 超时）；B5 `child-shutdown.ts` killTree 三层定时 + armRestartPolicy fail-open backoff，Windows 上 SIGTERM/SIGKILL 等价、平台分岔跳过双发；B6 Option A IPC 桥全链（`app-server-bridge.ts` pending 表 + server-request public-id 路由；`renderer-batcher.ts` 50 ms 合批 + 控制事件先 flush + raw delta 不转发；preload `window.questorHost` 6 方法 + `qst:sidecar-state` 新增广播；`ui/src/rpc/{ipc-transport,server-events-fanout,questor-host}.ts` 新增、`client.ts` 构造函数默认参数分岔、**浏览器 12 测零改**），`electron.vite.config.ts` renderer root 指 `../ui` 完成一套前端代码两宿主；B7 `electron-builder.yml` NSIS 目标 + `assets/README.md` 与 `icon.svg` 占位（icon.ico 与 exe 产物推到下一个小计划）；B8 `.github/workflows/desktop.yml` + `.node-version` + `justfile` 新入 `desktop-test` 与 `desktop-build` 两配方，`test_ci_parity.py` 三处 tuple 同步扩展把 desktop 拉进扫描。护栏：`desktop/tests/{atomic-file,questor-command,sidecar,generation,restart,bridge,renderer-batcher,ipc-parity}.test.ts` 共 33/33 绿；`ui/tests/ipc-transport.test.ts` 新 5 条 + 原浏览器 12 条共 17/17；`tests/architecture/test_ci_parity.py` 新两向嗂住 desktop 一侧入门禁；`tests/e2e/test_desktop_shell_vertical_slice.py` 新钉“两宿主同帧序列结果同形”。L3 逐段无 findings。**诚实标注（pending，集中列在 `docs/plans/2026-10-13-phase-u-completion.md`）**：真终端 `[real-terminal]` 验收（拉起与关窗、`~/.questor/desktop/runtime_state.json` 与 `.lifecycle.lock` 观察、`Stop-Process -Force` 后 sidecar-state 广播与 backoff 日志、安装后双击冒烟）需用户回报；`npm run package` 产 exe 需预放 `%LOCALAPPDATA%/electron-builder/Cache/electron-v44.1.0-win32-x64.zip`（与 B2 同一网络前提、非代码 bug）；Electron 层 Playwright e2e 推后续；`qst:sidecar-state` plumbing 无 Phase U 消费方（Phase E 审批 UI 时接）；packaged Python core 未交付（推后续 ADR）。实现细节与 wuu 参考参照同一文件 Track B 各 Task commit（git log 顶部 28 段 split）。

**为何在这里（不是"做完 M8 再改界面"）**：内核三柱已建成（M2–M5 + e2e）、界面接口地基已锁死
（ADR-0020 视图注册表骨架 + design token + 生成类型 + 双宿主契约）。界面/动效/桌面壳属"功能面"，
按本文横切规则 7「接口面同期、功能面可后置」可安全重排、提前，且不回头改已完成模块的接口。

**范围边界（硬约束，防"改一路改到内核"）**：本次**不动** `ui/` 之外的内核、`serve` 协议与 stdio/WS 传输、
`schemas` 与生成链、视图注册表形状（ADR-0030 §结论 4）。若界面暴露出新协议方法/事件需求，那是契约改动，
**停下走单独 ADR + 先改 `protocol.md` 递增版本**（AGENTS §七），不在本相顺手做。

**怎么做**（纵向切片先行，控制 wuu desktop 241k 行体量的风险）：
- **U0 壳 + 一个高保真面板（纵向切片）**：Electron 起壳（main/preload + electron-vite，renderer 复用
  `ui/` 构建产物；主进程 `child_process` 以管道拉起 `questor serve stdio` sidecar，`runtime_state.json`
  单调 generation + lifecycle_lock 防拉起竞态、sidecar 崩溃重启 fail-open——沿用 wuu/EvoFlow 同款设计决定，
  重写实现加 provenance）；挑 **Review 面板**做到 wuu 级还原度（`@pierre/diffs` 真 diff + 逐文件 + 已阅态 +
  过渡动效），先证明"Electron + React 能复刻 wuu 终端/发光观感 + 真 diff"，再横向铺其余面板。
- **U1 四面板复刻 + 动效体系**：Files 预览（语法/图片/PDF）、Terminal（`@xterm/xterm` + `node-pty`）、
  看板 DAG（`@xyflow/react`，原 E1 项）、主题 token 与动效（glow/拖拽布局/面板过渡，参照 wuu `dev/motion`、
  `dev/plan-motion`、`dev/design-system`）、视图注册表铺满（新面板只能登记，护栏 `test_no_hardcoded_panel_case` 守）。
- **U2 内嵌浏览器真接管（换 Electron 的核心收益）**：Browser 面板做成"面板那个 tab 即 Agent 操作页、
  地址栏真驱动、popup 保留 opener 链、一点即暂停"（不再是 CDP 镜像）；原生壳能力（PiP/多窗口/自绘光标/托盘）
  沿用 wuu 主进程 TS 模式重写。

**文档产出**：`desktop/`（Electron）壳设计篇；`ui/README.md` 补桌面宿主段；ADR-0006/0024 修订已随 ADR-0030 落。

**阅读地图**：wuu `desktop/electron.vite.config.ts`、`desktop/src/main/`（`appServerClients.ts` stdio sidecar、
`browserHostWindows.ts`/`browserPiPWindow.ts` 内嵌浏览器与 PiP、`agentCursor.ts` 自绘光标、`childShutdown.ts`
进程树关停）、`desktop/dev/motion`、`desktop/dev/plan-motion`、`desktop/dev/design-system` 动效与组件；
evopanel `src/zcode-ui/app-shell/`（resizable 面板组合）、`src/zcode-ui/styles.css`（Tailwind v4 `@theme` token）。

**前端同步点**：本相即界面主线本身——不再"内核做完、界面滞后"。

**出口判据**（诚实标注：真机走查/evals 基线仍需 `QUESTOR_MODEL_API_KEY`，与 M3/M4/M5 同口径记 pending，不凑）：
1. 能双击运行的 Electron 壳跑通——`questor serve stdio` 被壳以管道拉起、Review 面板显示真实 diff；
2. 可见柱（Review 真 diff）与可干预柱（插话/接管）各有一个 wuu 级还原度的可演示面板；
3. 内嵌浏览器做到真·同页接管（面板 tab 即 Agent 页面、一点即暂停），且 UI 文案如实描述（不谎称镜像为同页）；
4. 新面板只能走视图注册表、不改内核（`test_no_hardcoded_panel_case` 绿）；不为界面好看牺牲三柱判据（AGENTS §五）。

---

## Phase M6 — 外部引擎（engine/adapters）

**状态**：`- [ ]` 未开始

**做什么**（= structure §11 M6 行）：`engine/adapters`（ACP / Claude / Codex）+ 权限映射表；契约测试全引擎同绿（`tests/contract/` 参数化）。

**怎么做**：
1. 引擎契约保持极小（RunTurn/Interrupt/Close + 线程绑定 + resume），照 wuu `agentengine` 包注释的边界定义：引擎自持 loop/认证/工具/原生会话状态，宿主只统一 thread/turn/run/事件/stop/resume；
2. 适配器**只消费 latestUserMessage、只做转发映射**；不支持的能力显式报错不静默忽略；`RequestApproval` 传 nil 即 fail closed；
3. 引擎探测**零副作用**：probe session 永不持久化、永不发 prompt；目录元数据静态化，`QUESTOR_<ID>_BINARY` 覆盖 + PATH 探测、四态目录状态（unsupported/error/empty/ready）；
4. 权限映射表逐引擎整理：映射到三档的规则 + 映射不承诺等价保护的显式声明；`Instructions` 不是用户 prompt、不得静默丢弃。

**文档产出**：`engine/adapters` 设计篇 + 权限映射表；契约若有修订，`data-model.md`/`protocol.md` 先行递增版本。

**阅读地图**：wuu `internal/agentengine/`、`internal/externalengine/`、`internal/claudeengine/`、`internal/codexengine/`、`internal/enginecatalog/`、`internal/runtime/engine_wuu.go`（线程绑定与 fork 继承引擎语义）。

**前端同步点**：引擎选择/状态 UI（目录四态呈现）。

**出口判据**（§12）：契约测试全引擎同绿。

---

## Phase M7 / M8 — 扩展面与可选平台（概述，开工前再细化）

**M7 扩展面**（= structure §11 M7 行）：`skills` `mcp` `hooks` `extensions`、`plugins/`、`examples/`、`packages/`（仅在有第二使用者时）。阅读地图：wuu `internal/pluginhost/`+`internal/capability/`+`internal/extensions/`（能力四分类：工具注入/生命周期钩子/host 服务/桌面视图；安装即信任、禁用即停全部产品行为、运行时世代与 safe mode）；EvoFlow harness 的 skills/mcp 区。出口：关插件即停产品行为。

**M8 可选平台**（= structure §11 M8 行）：`containers/`（FlowCoder `sandbox/` 容器池语义：non-root、只读根、默认断网、tmpfs 白名单、双层超时、池预热租借）、`deploy/web/` 自托管网页（**对外暴露需先过鉴权 ADR**）、IM 渠道（EvoFlow channels 四件套：Channel 抽象/消息总线/凭据注册/结果回推）、远程/移动端（真异质端才建 `clients/`，手机走 `ui/` 响应式）、（延后的）浏览器面板。各自 feature flag 默认关；先按 R5 补 overview §6 登记再建包。

---

## Phase E — 界面面与生态加料（E1 已并入 Phase U；剩 E2/E3）

**状态**：`- [ ]` 未开始（E1 已提入 Phase U；E2 引擎矩阵随 M6、E3 插件生态随 M7 交付，非"以后再说"）

为何单列一个阶段而不是并入 M1–M8：实测规模差距的大头不在 agent 内核——wuu `desktop` 241k 行
≈ 其 `internal` 340k 的 70%；EvoFlow `evopanel` 887k 是其 `backend` 377k 的 2.4 倍。**界面与生态
决定项目的可见体量**，而内核再精致也只是那 30–50%。本阶段把项目从"内核工程"变成"有躯体的产品"。

| 档 | 内容 | 出口判据 |
| --- | --- | --- |
| ~~E1 界面面全量~~ | **已提前并入 Phase U（ADR-0030）**：Files 预览、Review 逐文件、Terminal、看板 DAG、主题 token 与视图注册表铺满、Electron 桌面壳与内嵌浏览器真接管——全部见本文 Phase U | 由 Phase U 出口判据承接 |
| **E2 引擎矩阵** | 外部引擎从 3 个扩到 5+（ACP 家族为主）；权限映射表补齐；引擎目录四态呈现 | 契约测试全引擎同绿；映射不承诺等价保护必须显式标注 |
| **E3 插件与示例生态** | 内置插件 6–8 个（每个自带单测与集成测，与第三方同契约）、`examples/` 扩到 5 例、`packages/` 发布物（仅在有第二使用者时） | 关插件即停产品行为；示例照 README 能独立跑通 |

**明确不加**（个人做必薄，理由见 overview §14"不留的门"）：多端原生客户端、SSO/多租户、
资源市场、七种执行环境、IM 渠道全量。

---

## 横切规则（贯穿所有阶段）

1. **每阶段收尾四件事**：勾销本计划状态行 + 一行实际结果；overview §12 对应里程碑标记；新决策落 ADR（索引同步）；**出口附该模块坑目录 B-NN 覆盖率与每条护栏测试的负向验证输出**（AGENTS §四 §五 的可执行形式）。
2. **文档产出时点总表**：契约文档（M1 一次、此后只增版本）；模块内部设计篇（随开工，文档视距冻结约束）；用户指南（M4 起）；CHANGELOG（首次发布）；ADR（随时）；`NOTICE` 上游致谢随首个复用设计落笔。
3. **评测不断线**：evals 从 M1 骨架、M2 runner 起每阶段追加任务与结果记录，失败也发布（结论必须带可复现证据与 hash）。
4. **文档不合适当场修**：修改动处 + 留一行变更记录；与 AGENTS.md 冲突时停下问用户。
5. **砍单预案**（§12 已定）随时生效：M3 受阻先砍 Terminal 与交付物预览保 diff 与修订号；M6 受阻整体延后外部引擎；任何阶段不为面板好看牺牲三柱判据。
6. **前端跟随**（`AGENTS.md` §五）：每阶段收口时，本期新增的用户可感知能力必须能从 UI 路径走通一次；
   走不通写明原因与补救里程碑编号。**功能面可后置，界面通道不可长期缺位**——否则第一柱"可见"
   在真机上无法验证，而计划会退化成"只有 CLI 能用的内核"。
7. **后置分层**（判据三问见 overview §14）：判断某能力能否推到 Phase E / 未来时，按此切分——
   **接口面必须与内核同期定**：引擎能力协商位与版本、扩展公开 API、schema 版本策略、
   `limen` 错误方言、UI 视图注册表与 token 层；**功能面可后置**：引擎数量、插件个数、
   预览格式、看板美化、主题打磨。区分方法：晚做会不会回头改已完成模块的接口——会就是接口。
