# ADR-0038 — wuu 单锚：EvoFlow 降为后期长任务层规格来源，FlowCoder 退出参照系

状态: accepted
日期: 2026-10-14 | 关联: `AGENTS.md` §三（语义来源表）、ADR-0037、ADR-0043、`overview.md` §2/§6/§11

## 结论

唯一母本 = **wuu**。EvoFlow 降为**后期长任务/编排/验收层（Phase 6）的规格来源**（只读设计、不搬码，PolyForm）；**FlowCoder、AfterMatter 退出参照系**。据此给"非母本已落规格"定处理规则：`behavior-*-fc` / `behavior-*-ef` 默认**保留为参考或换锚重验**（它们含已付费的 Questor 采纳裁决），**仅无对手方的映射表**（如 `evals/adapters/mode_map.md` 的 FlowCoder 六档映射）才删除，且删前把有效证据并入 `pitfalls.md`。

## 理由与取舍

- 单锚消除"三个参照在语义/契约层互不兼容、长出一套混合契约"的总根因。
- wuu 是纯"过程可见工作台"，正对齐三柱；EvoFlow 是"长任务 runtime + 控制平面"（SaaS/IM/排班），整体产品形不同，只取其编排机制作规格。
- 取舍：放弃"wuu+EvoFlow 综合"的原定位，换主线清晰。

## 被否决的选项

- **继续三参照并列综合**：即现 `AGENTS.md` §三 语义来源表互相打架的成因。
- **全量搬 EvoFlow Python 后端**：LangGraph 持循环（用户已否）+ 32 万行含大量"不做"面 + 维护面暴涨。

## 适用条件与失效条件

**适用**：A 阶段以 wuu 核心体验为唯一蓝本。
**触发重评审**：Phase 6 若某 EvoFlow 机制无法"只读借鉴、围自研 run 重写"，另立 ADR。
