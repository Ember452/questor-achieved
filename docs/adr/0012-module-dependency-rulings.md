# ADR-0012 — gesta 与 capability 的依赖方向裁决

状态: accepted
日期: 2026-10-11 | 关联: `overview.md` §6、`structure.md` §5、`AGENTS.md` 元规则（文档冲突停下问用户）、M2.1 开工

## 结论

M2.1 开工前发现 `overview.md` §6 与 `structure.md` §5 依赖矩阵在两处不一致，用户授权按
"对项目长远最优"裁决，两处**均以矩阵为准**，并回写 overview §6：

1. **gesta 不 import engine**。矩阵为 `engine → gesta`（engine 依赖 gesta 落盘），gesta 只允许
   import `schemas` / `state` / `config`。overview §6 原文"依赖 engine 事件"改为：
   事件与实体的类型形状由 `schemas`（data-model v1.0 的绑定）承载，gesta 对 engine 无感知。
2. **capability 不 import config**。矩阵只允许 capability → `schemas`（与 state/version 同组）。
   capability 只定义能力开关注册表与查询接口；配置值由上层组装时注入（M2.3 的 serve/cli 装配点）。

## 理由与取舍

- gesta：engine→gesta→engine 必然成环，`test_matrix_has_no_bidirectional_edges` 会直接咬住；
  且 gesta 的职责是"落盘与回放"，它只需要 data-model 的实体形状，不需要知道谁在产生事件。
  牺牲的是"gesta 直接消费 engine 事件类型"的表面便利——那份便利本来就该走 schemas。
- capability：feature flag 的语义是"能力存在与否的声明"，读配置是"装配"职责。依赖更少意味着
  capability 可以独立测试、被内核模块（如 engine）安全依赖而不把 config 拖进内核；
  与协议侧"能力 opt-in 声明"（B-61）的语义同源。
- 两处都选矩阵还有一条元理由：AST 矩阵（`tests/architecture/test_dependency_matrix.py`）是
  可执行的真相，overview §6 是叙述性登记——让叙述服从可执行断言，两套真相只剩一套。

## 被否决的选项

- **改矩阵允许 gesta→engine**：与 engine→gesta 构成双向边，矩阵查环测试失败；语义上落盘器
  依赖执行器也颠倒。
- **改矩阵允许 capability→config**：把 config 拖进 capability 的依赖闭包，engine 等内核模块
  将间接依赖 config，违背"内核模块依赖极简"的登记初衷。

## 适用条件与失效条件

**适用**：M2.1–M2.3 全程；模块物理布局不变的前提下长期有效。

**触发重新评审**：① 出现真实的第二个使用者证明 capability 必须运行时读配置（而不是组装注入）
→ 走"先改 structure §5 再改代码"流程；② engine 与 gesta 的关系重组（如 gesta 改为事件管道的
下游消费者）→ 重新登记依赖方向并同步两处文档。
