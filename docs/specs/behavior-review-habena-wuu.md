# behavior-review-habena-wuu —— wuu Review/分叉行为规格（Questor `review` 蓝本）

来源：wuu `internal/tools/diff.go` + `internal/appserver/fork.go` + `internal/agent/loop.go`。
扫描日期 2026-10-11。Questor 模块归属：`review`（部分涉 `habena`）。

---

## 1. 真实 diff：写时刻计算并随结果持久化

- **行为**：`computeDiff(oldText, newText, contextLines)` 生成统一 diff hunks
  （`internal/tools/diff.go#L33-35`）——在**写工具执行的时刻**由工具层计算，作为工具结果
  的一部分持久化；前端直接消费结构化 diff（path/action/diff/snapshotText/additions/
  deletions），**不事后重读文件猜测**。
- **边界行为**：删除/创建/重命名各有 action 类型；大 diff 带 truncated 标记。
- **证据**：`diff.go#L33-35`。

### Questor 采纳决定
沿用"写时刻 diff 随结果持久化"——这是 Review 面板"真实"承诺的实现根基（三柱之一），
`review` 模块的 diff 服务消费 gesta 记录而非重扫文件。

## 2. 分叉（fork）

- **历史克隆**：`cloneForkHistory(history []providers.ChatMessage)`（`fork.go#L234`）——
  分叉点的历史克隆有三级回退（raw persisted → display → live）与 live 分叉（流式中刚
  完成的最终答案也可作为分叉点，工具项投影为可移植 call/result 对）。
- **worktree 模式**：分叉到新 worktree 时记录 BaseHEAD/BaseRepo，失败清理（第一轮扫描
  报告，`internal/worktree/`）。
- **坑**：B-66（live 分叉：未结算的最终答案可作分叉点，且工具项投影不带执行账本所有权）。

### Questor 采纳决定
M3 落地 fork 时按三级回退语义实现；worktree 记录结构沿用。

## 3. BeforeStep 统一汇聚点（`internal/agent/loop.go#L400-401`）

- **行为**：`cfg.BeforeStep()` 在每个模型步之前被调用——插话与已完成后台进程的
  completion 都在这个边界注入下一请求。
- **坑**：B-67（BeforeStep 是插话消费与后台 completion 的唯一汇聚边界——Questor 的
  habena 必须在等价的步边界消费，不能在任意时刻注入）。

### Questor 采纳决定
habena 的消费点 = 引擎状态机的"步前边界"（与 overview §12 M3 出口"插话在下一个工具
边界被消费"一致）。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-66 | review | diff 在写工具执行时刻计算并随结果持久化，前端不吃"事后重扫"的二手 diff | wuu `internal/tools/diff.go#L33-35` |
| B-67 | habena | 插话消费只在步前边界（BeforeStep）；live 分叉允许未结算的最终答案作分叉点 | wuu `internal/agent/loop.go#L400-401`、`internal/appserver/fork.go#L234` |
