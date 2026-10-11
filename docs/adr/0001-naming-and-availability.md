# ADR-0001 — 项目命名、拼写裁决与占用核查

状态: accepted
日期: 2026-10-11 | 关联: `README.md`、`AGENTS.md` §一、`pyproject.toml`

## 结论

- 项目名 **Questor**；一切技术标识符全小写 **`questor`**（仓库名、包名、import、
  目录、`pyproject` 的 `[project].name`）。CLI 入口 `questor`，短别名 `qst`（不用 `q`）。
- **拼写取变体 `Questor`，不写拉丁正字 `Quaestor`。** 文档与词源说明固定一句：
  *Questor — from Latin quaestor, the Roman magistrate who audits the accounts and is
  sent out to act. Spelled short on purpose.*
- 词义来源：罗马官职 *quaestor*（动词 *quaerere* ＝ 寻求／询问／审计），
  *cursus honorum* 的最低一级，职掌**账目审计（rationes）与刑事调查（quaestores parricidii）**。
  一词同时覆盖本项目三柱：审计核验、受命行事、追问调查。
- 桌面壳若需发 npm 包，一律走 scope：`@questor/ui` 等。
- 内部模块名与对外包名分两层治理（见"模块命名表"）。

## 理由与取舍

**为什么小写仓库名**：GitHub 仓库名大小写不敏感且全局唯一，填 `Questor` 只会让
URL 与包名／目录／CLI 产生两套拼法；工具类仓库惯例是纯小写（`ripgrep`、`bat`、`httpie`）。

**为什么用变体拼写**：`quaestor` 的搜索位被阿西莫夫《基地》系列的星警职衔与
百科／维基词条占死，永远排不到前面；`questor` 几乎无自然竞争，可独占搜索。
代价是会有人指出"少了一个 a"——用上面那句词源说明一次性挡掉。

**为什么名称只承担"可验证"这一柱**：三柱里"看得见"和"拉得回"已有成熟同类产品
占位，唯有"审计与核验"是本项目能独占的语义。透明度交给 README 副题承担。

**已知残留风险**：`Quest*` 前缀在 SaaS 领域高度饱和（Quest、QuestDB 等）；
若将来涉及商业使用，需就商标第 9／42 类单独核查。本决策不覆盖商标结论。

## 占用核查记录（2026-10-11 实测）

方法：PyPI 走 `https://pypi.org/pypi/<name>/json`（404 ＝ 空闲），npm 走
`https://registry.npmjs.org/<name>`，GitHub 走搜索。

| 候选 | 词义 | PyPI | npm | GitHub 同品类 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **questor** | 审计官／受命者 | ✅ 404 空闲 | ❌ 被占：`ehd/questor`，*"Promise based HTTP client inspired by clj-http"*，2022 年后休眠，不同品类 | ✅ 命中均为 quest 模糊匹配；噪音仅 Telegraph 投资专栏与一家加拿大能源公司 | **采用**（npm 走 scope） |
| auxilia | 辅军（多 Agent） | ✅ 404 空闲 | ❌ 被占 | ✅ 命中均为 auxiliary 模糊匹配 | 否决：只覆盖多 Agent 一柱；`aux-` 发音在拉丁 /ks/ 与英语 /ɡz/ 间不自洽；观感像 auxiliary 拼错，自身搜索被淹没 |
| officina | 工坊 | ✅ 404 空闲 | ✅ 空闲 | ✅ 干净 | 否决：意／西语日常义＝汽修站；重音位置不确定；只覆盖"场所"一柱 |
| limen | 门槛 | ✅ 404 空闲 | — | ❌ `overment/limen` 223★，自我描述 *"one-human-many-agents harness"* —— **正是本项目定位** | 否决作项目名；**保留作内部模块名** |
| scrinium | 文书匣／档案箱 | ✅ 404 空闲 | ❌ 被占：`Fologan/scrinium`，离线文档存储，不同品类 | — | 落选（覆盖柱数不敌 questor）；保留作内部模块名候选 |
| haben**a** | 缰绳 | ✅ 404 空闲 | 未核 | 未核 | 落选作项目名；**保留作插话／接管模块名** |
| examen | 精确检验 | ❌ 被占 v0.3.1，*"Self-administered comprehension quiz for AI-assisted code"* | — | — | 出局：同域 |
| agentia | 事务／代办处 | ❌ 被占 v0.1.41，*"Ergonomic LLM Agents"* | — | — | 出局：同类 |
| tablinum | 罗马宅邸档案房 | ❌ 被占 v0.2.7（表格打印库） | — | — | 出局 |
| procura | 代为管理＋须交账 | ❌ 被占 0.0.1，*"Provable authorization for agent-initiated purchasing"* | — | — | 出局：同域 |
| acta | 行事簿 | ❌ 被占 0.1.0，*"File-based async message passing for AI agents"* | — | — | 出局作包名；**保留作内部模块名** |
| vigilia | 夜间班次 | ❌ 被占 2026.1.4.dev1，*"generating technical summaries of code changes using LLMs"* | — | — | 出局作包名；**保留作内部模块名** |
| gesta / factum / mira / specto / fovea / clavis / signum / scribo / machina | — | ❌ 多数被占 | ❌ | — | 不再评估 |

**核查得出的方法论结论**：本领域语义空间在 2026 年已被密集抢注，
"拉丁短词＝无冲突"是错觉；任何名字进入候选必须先跑完 PyPI＋npm＋GitHub 三步。
**上一版本本 ADR 草稿曾把 `acta`、`vigilia` 标为"实测空闲"，那是未测就写的错误断言，
本表为更正后的实测结果。**

## 模块命名表（内部用，不受包名占用约束）

| 目录 / commit scope | 拉丁义 | 承担语义 |
| --- | --- | --- |
| `engine` | — | 自研 agent 循环、事件流、turn 生命周期 |
| `tools` | — | 工具登记与执行 |
| `limen` | 门槛 | 唯一权威权限门与写域边界 |
| `habena` | 缰绳 | 运行中插话、接管、暂停 |
| `vigilia` | 夜间班次 | 无人值守长跑与调度 |
| `gesta` | 行事簿 | 会话记录与验收导出 |
| `review` | — | 真实 diff、工作区修订号、turn↔revision 绑定 |
| `evidence` | — | 验收证据：声称的检查与当时真实记录输出并排核对 |
| `orchestration` | — | Plan→执行→验收/打回 |
| `serve` / `cli` | — | 协议服务与命令行入口 |

## 适用条件与失效条件

**适用**：本项目以 Python 包在 PyPI 分发、以 GitHub 为公开主仓库、单人或小团队使用。

**触发重新评审的信号**：
1. 任一内部模块要**抽成独立包发布** → 必须重新核查该名的 PyPI/npm/GitHub 占用
   （`acta`、`vigilia`、`limen` 当前都被同品类项目占用，直接发布会撞名，
   需加前缀或改名）。
2. 决定商用或收费 → 核查 `Questor` 在第 9／42 类的商标状态。
3. 需要 GitHub **组织名** `questor` → **2026-10-11 补记：已实测不可得**。
   `github.com/questor` 被一个早年注册的个人账号占用（GitHub 用户名与组织名共享
   同一命名空间），组织无法注册；仓库保持 `github.com/Ember452/questor`。
   包名（PyPI `questor` 空闲）、CLI 名、品牌体均不受影响。npm `@questor` scope
   的可得性留待首次发布 TS 包时实测。
