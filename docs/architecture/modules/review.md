# review —— 模块设计篇（目标态，Phase 2/3 移植）

状态: 设计先行，实现待 wuu 蓝本移植 | 2026-10-14 | provenance 锚: `wuu-main internal/tools/diff.go`（tool-time diff）+ `wuu-main desktop/src/main/gitService.ts`（工作区盘态真相）；行为规格 `docs/specs/behavior-review-habena-wuu.md` §1、`behavior-review-fidelity-wuu.md` §0；pitfalls: B-66 B-93 B-105 B-107

> 旧 `src/questor/review/`（turn_bindings/aggregate 等）为待替换实现，只读参考；
> 本篇描述 ADR-0045 裁决后的目标态，落码时按 §1.5 五机制对账。

## 职责与边界

真实 diff 的**计算与账本绑定**：写/编辑工具执行时刻算 unified diff、随工具结果持久化，
并维持 turn↔revision 绑定，使"这一轮 Agent 改了什么"可事后审计。**不做**工作区级
盘态采集——那是 Electron 主进程 GitService 的职责（壳侧只读 git，含 untracked），
本模块不感知（ADR-0045 双源分工，内核不新增 `review/turn_diff` 通知）。

## 核心语义（不可丢失的硬件）

| 语义 | 母本锚 | 坑号 |
| --- | --- | --- |
| diff 在写工具执行时刻由 `computeDiff(old,new,contextLines)` 计算，随工具结果持久化；前端不吃"事后重扫"的二手 diff | `internal/tools/diff.go#L33-35` | B-66 |
| `FileDiff` 形状：path/action(new·modified·deleted·renamed)/diff/snapshotText/additions/deletions/truncated | 同上 + renderer fixture | B-105 |
| 工作区修订号单点 `bump_revision` + turn↔revision 绑定 + `expected_revision` CAS 拒 stale | ADR-0005（契约仍成立） | B-93 |
| 空态显式化：turn 无写调用显示占位而非空白；`unified==""` 显示 "(no changes)" | renderer 边界行为 | B-107 |

## 取舍与被否决项

- **否决"内核出工作区 diff"**：内核拿不到壳侧 git 作用域（untracked、stash、多工作树），
  硬做必然漂移；wuu 用双源就是答案（C0 裁决）。
- Python 侧 diff 算法照 `diff.go` 语义用 `difflib` 复刻 hunk 形状（上下文行数/`@@` header
  对齐），逐符号差异进 port-ledger，不静默不一样。
- 消费侧（Review 面板）住 `desktop/src/renderer`（ADR-0040），经协议拿 tool-time diff、
  经 IPC 拿壳侧 GitService 结果，两路在面板汇合——接缝形状以 `protocol.md` 为准。

## 对应测试（移植时物化）

`test_review_turn_diff` 族（写时 diff 聚合，旧实现已废、按新契约重建）；B-66 负向注入
（改文件不重算 diff → 红）；hunk 形状 golden 对照 wuu `_test.go` 断言场景。
