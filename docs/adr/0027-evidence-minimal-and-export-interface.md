# ADR-0027 — evidence 最小版：声称 vs 录得的并排核对，export 形状先定死为接口

状态: accepted
日期: 2026-10-12 | 关联: `docs/plans/development-plan.md` M4/M5、`docs/architecture/overview.md` §2 §14 M5、
`docs/architecture/data-model.md` v1.3、`B-45`

## 结论

M4 的 `evidence` 只做三件事，且只读消费 `gesta` 与编排 store 的**落盘事实**：

1. **并排核对**：把"声称的检查"（模型/工具报告说做过、通过了的验证）与"当时录得的真实输出"
   并排放，判定 `verified` / `mismatch` / `unverified`；
2. **可追溯**：任何结论必须带 `recorded_output_ref`，能指回具体记录条目（Item/Event id 或 spill 回链）；
3. **export 形状先定死为接口**：`evidence/reported` 通知与 `evidence/get` 方法返回的结构**先定形**，
   将来接复跑核验或纵向统计时只改消费方，不改事件契约（`overview.md` §14"evidence 出口是接口"）。

**明确不做**：沙箱复跑核验（`claimed_ok → replay_ok`）、验证空洞统计、bootstrap/CUSUM；
这些属 M5 及以后，且 `overview.md` §2 已裁定本轮不引 AfterMatter 机制；`evidence` 完整版落 M5。

## 理由与取舍

- **诚实呈现铁律**：没有记录支持的结论一律标 `unverified`，不臆断打分；这正是第三柱"可验证"的最小可执行形态。
- **不做复跑**：复跑要重放工具（结果可能未知、违反"断流不重放"），且 `overview.md` §2 已排除；
  最小版的价值在"把已有证据摊开对账"，不在再造一次执行。
- **接口先行**：证据结论是**要长期存活的对外形状**，现在定形最便宜；M5 补内容时不必回头改已跑通的契约。

## 被否决的选项

- **把 evidence 塞进 `review`**：review 只管"工作区 diff 与修订号"；证据核对是独立关注点，
  且 review 已在 M3 定型，不应再长第二职责。
- **本期就做复跑核验**：见上，违反"断流不重放"与 §2 排除说明。
- **结论只存布尔不存引用**：无法"点击跳到记录条目"，第三柱退化为口头承诺。
- **证据写回/改写历史记录**：会话记录 append-only，证据只能**追加**结论记录，绝不改写被核对的原文。

## 适用条件与失效条件

- **前提**：被核对的"真实输出"确实落过盘（工具结果/事件/溢出回链）。
- **失效信号**：① M5 引入复跑核验 → `export` 消费方扩展，契约不改；② 证据条目爆炸影响查询 →
  引入证据索引（可丢弃可重建），须新 ADR。
