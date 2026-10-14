# port-ledger —— 移植对账台账（wuu 符号 ↔ questor 符号 ↔ 差异/理由）

> 复刻完成度的对账清单（计划 §1.5 机制 3）。每个移植文件/模块与 wuu 不一致处在此记一行理由；"不做/后置"也登记为决定，不留遗漏。随各 Phase 追加。

## Phase 0 · 契约重立基

### 差异登记（契约先于实现）
| # | 项 | 状态 | 说明 / 何时收口 |
| --- | --- | --- | --- |
| TL-1 | `protocol.md` 词表取齐 wuu（`thread/start`/`run/updated` 等），但 `serve/app_server.py` 仍注册旧名（`thread/create`/`run/stop`/`delta`） | **transition-red** | 护栏 `test_serve_methods_are_documented`、`test_serve_notification_families_are_documented` 现红 2 条 = 契约先行、实现待迁移的**正确信号**；**Phase 1/2 重写 serve 后转绿**。不作废护栏、不改测试迁就。 |
| TL-2 | `overview.md`/`structure.md`/`protocol.md`/`data-model.md` 已改母本对齐口径；`modules/*.md`、`development-plan.md`、`phase-u-*` 仍是旧 M 系列/FlowCoder 口径 | 待收口 | 各 `modules/X.md` 在对应 Phase 移植前重写；`development-plan.md`/`phase-u-*` 加历史横幅（见下"文档处置"）。窗口在重写前以本台账 + 转向 ADR 为准（AGENTS §七 必读已 redirect）。 |
| TL-3 | 协议版本串 `questor-app-server/v0.1` vs wuu `wuu-app-server/v0.1` | 待 Phase 1 定 | 复用 wuu 前端需两端版本串一致：要么保留 `wuu-app-server/v0.1`，要么 patch 前端 `packages/protocol`。Phase 1 接缝实测时定，记此不静默。 |

### 文档处置（回答"删什么/会不会影响开发"）
> 判据：会不会被开窗口当"现状/实现依据"读错。多数是**标历史/改写中**，不是删；仅无保留价值者删。

| 文档 | 处置 | 会误导开发? |
| --- | --- | --- |
| `docs/plans/development-plan.md`（M 系列 + "已完成"勾销） | 加"已被 `phase-a-mvp.md` 取代、M 系列作废"横幅；`phase-a-mvp` 未写前不得据此开工 | 🔴 会（必读）→ 必须标 |
| `docs/plans/2026-10-13-phase-u-*.md`（3327 行已做完 + completion） | 加"历史执行记录，不得再作实现依据"横幅 + 撤销 pending（代码废弃后 pending 全废）；**不删**（B-108~118 唯一出处） | 🔴 会 → 必须标 |
| `docs/architecture/modules/*.md`（tools/providers/context/engine/serve 挂 FlowCoder provenance + 旧内核假设） | 各在其 Phase 移植前重写为"照 wuu X 移植"；重写前窗口**只读 wuu 源码 + 本台账**，不信 modules/*.md 旧结论 | 🟠 局部会 → 该模块开工前重写 |
| `ui/README.md` | 重写/标注：ADR-0040 已废弃 `ui/`，改 `desktop/src/renderer` | 🟠 会 |
| `evals/adapters/mode_map.md`（FlowCoder 六档映射） | **可删**——删前把"实测 `flowcoder --mode read_only` 报错"证据并入 `pitfalls.md` | 否 |
| 根目录 `.scan-*.md`（6 份，已复制进 `docs/research/`） | **可删**（重复）；属临时产物 | 否 |
| 未跟踪 ADR `0033~0036` | 保留文件：0033 仍有效(Phase 2)、0035 superseded by 0045、0036 withdrawn by 0037（README 已标） | 否 |
| `docs/specs/cases-*.md` | 从未存在（C12）；AGENTS §二 已移除该引用；清理 `specs/README`/`overview §3` 的悬空引用 | 🟡 小 |

**当前门禁基线**（Phase 0 中途）：`check_specs` OK、`check_notes` OK；`tests/architecture/test_serve_names_are_contracted` 2 红（TL-1 transition）。未 commit、未 push。
