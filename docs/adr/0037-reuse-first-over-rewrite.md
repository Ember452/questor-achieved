# ADR-0037 — 复用优先取代全量重写：以 wuu 为母本逐文件移植/翻译进 Python

状态: accepted
日期: 2026-10-14 | 关联: `AGENTS.md` §二（本 ADR 取代其旧"不照搬代码全部重写"）、待写 ADR-0038/0044、`docs/research/scan-questor-docs.md` §3.2

## 结论

把工程主线从「参照多个项目、不照搬代码、全部重写」**反转**为「**复用优先**：以 wuu（MIT）为唯一母本，逐文件把其已验证逻辑**翻译/移植**进 Python，以 wuu 的 `_test.go` 当验收 oracle」。EvoFlow 仅读设计（PolyForm，不搬码）。移植 wuu 代码**必须保留其许可证与上游署名**：新建 `third_party/THIRD-PARTY-NOTICES`、`NOTICE`，每个移植文件头写 `# Ported from wuu@<commit> internal/<pkg>/<file>.go — pitfalls: B-NN ...`。

## 理由与取舍

- 现有一版"照坑清单从零重写"的内核（~20k 行）正是"重复造轮子的坑没尽头"的来源；改为**翻译已验证的实现**，消除的是"发明边界层"这一整类坑。
- wuu 是 MIT，逻辑可直接移植进自有项目（用户已确认授权与许可证无阻塞）；保留署名与 provenance 既满足许可，也留下"独立实现证据 + 半年后知道为何这么写"。
- 取舍：牺牲"完全自主设计的洁净感"，换来"少踩母本已趟平的坑 + 可核查的行为等价"。

## 被否决的选项

- **继续全量重写**：即现状，正是本次要逃离的痛点根源。
- **直接 fork wuu 转 Go 作基座**：违背"Python 主流 + 手写循环"，且弃已趟的 Windows/Electron 知识。
- **搬码不留 provenance/署名**：违 MIT，且失去复刻完成度的对账依据。

## 适用条件与失效条件

**适用**：wuu 有对应且已验证的实现；Go→Python 翻译成本低于重写。
**触发重评审**：某 wuu 逻辑与 Python/Windows 冲突到"翻译比重写更贵"时，该模块单独在 `port-ledger.md` 记为"改重写"，不整体回退本纪律。
