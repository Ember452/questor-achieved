# ADR-0036 — AppServer 的拆分时机：本轮只收单一来源，整文件拆分待排期

状态: proposed（拆分方案已定，时机待裁）
日期: 2026-10-13 | 关联: `serve/app_server.py`、`serve/dispatch.py`、ADR-0020（HandlerCtx）、
ADR-0025/0026/0027（编排与长跑）、`AGENTS.md` §三、`test_serve_names_are_contracted.py`

## 现状（实测）

`serve/app_server.py` 1189 行：一个 `@dataclass AppServer` 挂约 55 个方法，横跨
thread / turn / run / review / files / content / workspace / sessiontrace / task / goal /
schedule / evidence 十二个域。其中**不属于传输层**的有：

- `_task_transition` / `_goal_transition` / `_set_schedule_enabled`——编排与调度的**状态机驱动**；
- `_gate_or_deny`——编排门（无 Plan 不许建任务）在 serve 层落地；
- `_publish_task` / `publish_goal` / `_orchestration_publisher`——编排事件的水合与 hop。

即：编排域的判定与迁移逻辑当前住在传输层，而不是 `orchestration/` 与 `vigilia/`。

**本轮已完成的部分**（不在本 ADR 待裁范围内）：方法表曾由 `_methods()` 元组与
`_handler()` 字典各写一份（同一事实两份名单），现已合成唯一一份
`_handler_registry()`，`_methods()` 改为它的键序派生视图；护栏
`test_method_table_has_single_source` / `test_initialize_publishes_the_same_method_table`
已附负向验证（把 `_methods()` 改回手写短元组 → 三条同时红）。见坑目录 B-119。

## 待裁的拆分方案

**保持单一 handler 注册表不变**（已落地的那份），只改它的**分布**：

1. 按域把 handler 拆到 `serve/handlers/{thread,turn,review,files,task,goal,schedule,evidence}.py`，
   每域一个类，接收同一个 `AppServer` 状态对象（或显式依赖注入它需要的协作者）；
2. `AppServer` 退化为**状态持有者 + 注册表汇总**：`_handler_registry()` 由各域类
   贡献（`{**ThreadHandlers(server).registry(), ...}` 之类的一处汇总），仍是唯一一份；
3. `_task_transition` / `_goal_transition` / `_set_schedule_enabled` / `_gate_or_deny`
   **下沉到 `orchestration` 与 `vigilia`**——迁移与门判定本来就有单一入口测试
   （`test_orchestration_transition_single_entry`、`test_status_transition_single_entry`），
   驱动逻辑住在 serve 层使这些测试的保护面出现例外；
4. 每个域文件一个测试文件，DoD 输出按域贴，不再都往一个 1189 行文件挤。

## 理由与取舍

- **为什么值得拆**：`AGENTS.md` 自己写的判据——文件变大往往是"做了太多件事"的信号。
  现在加一个面板所需的方法要动的就是这个文件，而 Phase U 之后还有 U2（浏览器接管）
  会往方法表加 `browser/*` 族。
- **为什么本轮不做**：
  ① 纯内部搬动，不产生用户可见能力，与 U2（ADR-0030 选 Electron 的核心收益兑现点）
  争同一个文件，会制造持续冲突；
  ② **ADR-0035 尚未裁决**——若 diff 权威源改为真 git，`review/turn_diff` 的实现要重写；
  先搬家再重写等于搬两次；
  ③ 方法表已由本轮收成单一来源，"两份名单静默漂移"这个最危险的失效模式已经关掉，
  拆分不再紧迫，剩下的主要是可读性。
- **代价（诚实）**：文件继续带着 12 个域长大一个里程碑；期间任何新增方法都写进这个
  文件，拆分时的 diff 会更大。这是接受的账。

## 被否决的选项

- **现在立刻拆**：与 U2 撞车、且要预判 ADR-0035 的结果，拆完可能重拆。
- **永远不拆，只靠单一来源护栏**：护栏管的是"名单一致"，管不了"编排逻辑住在传输层"
  这件事——它让 `test_*_single_entry` 系列出现一个无法覆盖的例外面。
- **拆成按传输分文件（stdio 一套、ws 一套）**：与 ADR-0023"同一契约、同一方法表，
  不为桌面开私有端点"直接冲突，会造出两套方法表。
- **把 handler 改成装饰器登记**：登记面从"一处 dict"变成"散在各文件顶部的装饰器"，
  读顺序与发布顺序不再显式可见（`initialize.methods` 的数组序就是它），
  收益不明显而可观察性下降。

## 适用条件与失效条件

**适用**：M6 开工前完成（推荐），或 U2 落地后、`serve/app_server.py` 超过 ~1600 行时提前触发。

**触发重新评审**：
1. ADR-0035 定案后 review 域实现重写 → 拆分应与那次重写合并做，不单开一次搬家；
2. 引入 MCP / skills / plugins（M7 扩展面）需要"运行时注册方法"→ 注册表必须变成
   动态的，届时本方案的静态汇总要重做（那时才是装饰器/声明式登记的正确时点）；
3. 编排域的 `*_transition` 若因 M6 契约工作再次移动，则以契约提取为准、拆分跟随。
