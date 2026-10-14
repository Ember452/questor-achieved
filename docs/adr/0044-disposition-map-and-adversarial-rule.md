# ADR-0044 — 现有实现处置地图 + "对抗套件只增不减"与代码废弃的相容规则

状态: accepted
日期: 2026-10-14 | 关联: `AGENTS.md` §四 L148「只增不减」、§七 新增触发项⑦、计划 §12-B、ADR-0037

## 结论

**① 处置地图**（Phase 0 step1 执行、逐个定性写入 `docs/research/port-ledger.md`）：
- **按 wuu 蓝本重写/移植**：`engine` `tools` `limen` `serve` `context` `state` `sessiontrace`（→wuu session）`review`；
- **后置 Phase 6**：`orchestration` `vigilia` 大部分、`evidence` 验收闭环；
- **废弃重写（不进新树，reference-only 存档）**：旧 `ui/`（→`desktop/src/renderer`）、旧 `desktop/` 壳；
- **保留（知识/外围，不重写）**：`gesta` 契约模型知识、`schemas` 生成链、`config`/`secrets`/`version`/`worktree`/`capability`、CI/justfile/门禁、`docs/adr`+`pitfalls`。

**② 相容规则**（解 §四 与转向的正面冲突）："只增不减"**升为跨实现契约**的适用——凡**契约层/黑盒 e2e/架构不变量**类对抗用例（append-only、状态迁移唯一入口、权限不可绕过、协议单一来源），随新实现**继续存在并只增不减**；凡**绑定旧实现内部细节**的对抗用例，可随实现**作废**，但每条作废必须在 `port-ledger.md` 记"为何废、被哪条新契约用例替代"，**不得静默删**。

## 理由与取舍

- 不登记就是遗漏（违忠实度机制 5「不做也要登记」）；不给"只增不减"开受控例外，新实现永远被旧形状的红测卡死。

## 被否决的选项

- **所有对抗用例硬留不删**：绑死旧实现形状，重写期 CI 永久红，逼出"改测试迁就"作弊。
- **随意删对抗用例**：丢掉"可验证"柱的保护网。

## 适用条件与失效条件

**适用**：转向期 Phase 2/3 逐模块重写。**触发重评审**：每模块重写时按本规则具体裁，边界不清的按 §四 元规则停下问用户。
