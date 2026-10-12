# ADR-0029 — 验收闭环：状态机强制、evidence 生产写入点、声称显式绑定

状态: accepted
日期: 2026-10-12 | 关联: `docs/plans/development-plan.md` M5、`docs/architecture/overview.md` §7 §12 M5、
`docs/architecture/data-model.md` v1.4 §3.2、`docs/adr/0025`/`0027`、B-45 B-98 B-101 B-102

## 结论

M5 把第三柱"可验证"从"库里有函数"接成"产品链路真跑通"，四件相互咬合的事：

1. **验收状态机强制**：`TaskAcceptance.status` 由裸字符串收敛为 `AcceptanceStatus` 枚举，
   §3.2（`proposed → accepted_by_user → executing → reported → verified | regressed`）
   落**单点迁移入口**（`orchestration/acceptance.py`，形态同 `orchestration/transitions.py`），
   旁路写入即契约破坏；`requirement_revision` 递增作废既有验收由 `plan.revise_plan` 真实驱动
   （`invalidate_acceptances` 此前存在但无调用方）。
2. **evidence 生产写入点接线**：`evidence` 从"纯核对函数库"扩出**只读消费 gesta 的核对入口**
   （`collect_recorded(thread_id)` / `verify_claims(...)`，仍不落盘、不 import 编排域）；
   写入与驱动验收态落在 `orchestration`，持久化仍走唯一入口 `store.add_evidence`。
3. **声称采集：模型显式绑定 `tool_use_id`**：模型侧 `task` 工具新增 `report` 动作，每条声称
   携带 `claimed` 文本 + 证明它的那次工具调用 `tool_use_id`；核对器据此在录得 tool_result
   里查真实输出，无记录即 `unverified`（诚实呈现铁律）。`evidence/reported` 通知自此真实 publish。
4. **依赖边 `orchestration → evidence`**：新增该**有向边**（evidence 不反向 import 编排域，无环），
   structure §5 矩阵补行，由 `test_matrix_has_no_bidirectional_edges`/查环守卫守住。

**明确不做**：沙箱复跑核验、验证空洞统计、bootstrap/CUSUM（`overview.md` §2 排除 AfterMatter 机制）；
桌面壳 `desktop/src-tauri`（ADR-0024，与"可验证柱"正交、变化理由不同，另立后续任务）。

## 理由与取舍

- **复跑核验留成"可替换的实现源"而非本期实现**：把"核对的输入"收成一个只读入口
  （`collect_recorded`），将来接复跑只需替换该入口的实现源，`export`/`Evidence`/验收态契约零改动
  （兑现 ADR-0027"接口先行"与 `overview.md` §14"evidence 出口是接口"）。代价是本期只核对
  "已录得的事实"，不重放工具——这正是"没有复跑也不轻信"的诚实形态。
- **声称做成 `task` 工具动作而非新增 serve 协议方法**：模型只能经工具行动；`evidence/get` 与
  `evidence/reported` 已在 ADR-0027 定形，report 走工具 + 加性演进即可，不动已跑通的方法表。
- **验收态与任务态并存不合并**：§3.3 任务态管"执行到哪"、§3.2 验收态管"结论 verdict"，
  由 report 在 `reviewed` 处交汇。两套各有单点入口，避免一个状态机背两种变化理由（structure §4）。
- **绑定关系落在 `tool_use_id` 而非 run_id↔task 强绑**：报告时该工具结果已落盘（工具结果先于
  下一步持久化），据 `thread_id` + `tool_use_id` 即可定位真实记录，无需新增 task→run 绑定面。

## 被否决的选项

- **把证据核对塞进 `review`**：review 只管工作区 diff 与修订号，已 M3 定型，不长第二职责（ADR-0027）。
- **本期就做复跑核验**：违反"断流不重放"与 §2 排除；且结果可能未知，不能作为"当时录得"的替身。
- **声称只存布尔 / 从最终文本启发式抽取**：布尔无法"点击跳到记录条目"（第三柱退化为口头承诺）；
  启发式抽取精度与可追溯都弱，且引入"两套真相"风险——模型说了什么与系统据哪条记录判定必须一一对应。
- **再抽一层 `CheckComparator` 注入端口解耦 orchestration 与 evidence**：evidence 是无 IO 纯算库、
  编排域是验收真相属主，直接组合更贴职责；为无第二真实使用者的"解耦"引入端口违反极小化（§二）。

## 适用条件与失效条件

- **前提**：被核对的真实输出确实落过盘（tool_result Item / spill 回链）；`AcceptanceStatus`
  枚举值与 model/v1.json、orchestration/v1.json 两处 `$defs` 保持一致（同 Id/Timestamp 惯例）。
- **失效信号**：① 引入复跑核验 → 替换 `collect_recorded` 的实现源，验收态与 export 契约不改；
  ② 出现第二种"声称来源"（如外部引擎自带验证结论）→ report 侧扩展消费方，工具动作形状不变；
  ③ 证据条目爆炸影响查询 → 引入可丢弃可重建的证据索引，须新 ADR（同 ADR-0027）。
