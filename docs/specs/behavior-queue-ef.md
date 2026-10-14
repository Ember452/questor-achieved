# behavior-queue-ef —— EvoFlow 无人值守队列与自动化行为规格（Questor `vigilia` 蓝本）

来源：EvoFlow `backend/app/gateway/task_queue_runner.py` + `unattended_task_pipeline.py` +
`automation_runner.py` + `zombie_run_sweeper.py`。扫描日期 2026-10-11。
Questor 模块归属：`vigilia`（值守长跑、调度、清扫）。

---

## 1. 无人值守任务队列（`task_queue_runner.py`）

- **tick 语义**：`DEFAULT_TICK_SECONDS = 60`（`#L19`）；一个 tick = 最多启动 N 个 pending
  无人值守任务（`#L70-81`）；`max_concurrent` 由环境函数读取（`#L29`）；快照含
  `slots = max(0, max_concurrent - active)`（`#L59-61`）。
- **重入防护**：per-task `asyncio.Lock` 字典 + 守卫锁（`unattended_task_pipeline.py#L40-41`
  的 `_advance_locks` / `_advance_locks_guard`，`#L211-217` 的 `_advance_lock_for`）——
  同一任务不会被并发推进。
- **坑**：B-49（per-task 锁字典模式）。

### Questor 采纳决定
tick + 并发上限 + per-task 锁沿用；tick 间隔与并发上限进 vigilia 常量表。

## 2. 自动化调度（`automation_runner.py`）

- **once 语义**：触发成功后立即标记 `once_fired = True`（`#L945-951`，标记失败记 warning
  但不阻塞）；已触发过 / 未到触发点的 once 任务不重放。
- **本地时钟**：调度匹配依赖本机时钟；同分钟去重靠 `_last_slot: dict[str, str]`
  （`#L33`）——休眠/时钟漂移的敏感性由调用方知晓。
- **边界行为**：automation_name 等字段截断 120 字符入库（`#L622,L644`）——入库前统一
  截断防超长。
- **坑**：B-41（本地时钟敏感 + 去重单闸）、B-42（once_fired 幂等标记）。

### Questor 采纳决定
once 幂等标记沿用；"错过不重放"写进 vigilia 调度语义（overview §5 已定）；本地时钟
限制写进用户文档，唤醒检查点（structure §3 vigilia 职责）是长跑侧的补偿机制。

## 3. 僵尸运行清扫（`zombie_run_sweeper.py`）

- **节奏**：`EVOFLOW_ZOMBIE_SWEEP_INTERVAL_S` 默认 120s（下限 10），batch 下限 10
  （`#L19,L44-45`）。
- **历史坑自述**（`#L39-42` docstring）：旧版多批循环**无 offset 重查同一 top-N**，
  当 sticky running 会话 ≥ batch 时可每 0.5s 紧密空转——现版"一次 interval 一批，
  剩余下轮再收"。
- **边界行为**：可用环境变量整体关闭（`EVOFLOW_ZOMBIE_SWEEPER=0`，`#L47-48`）。
- **坑**：B-40（清扫必须分批游标）、B-44（状态真值在运行时侧，重启必有 stale——
  启动 + 周期双 reconcile，清扫的存在本身就是补救）。

### Questor 采纳决定
"一批一间隔 + 游标"沿用；Questor 自建状态机清扫（不依赖任何框架 runs API——overview
§3 已裁定）；清扫可整体开关（feature flag）。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-40 | vigilia | 清扫必须有分批游标：无 offset 重查同一 top-N 会紧密空转 | `zombie_run_sweeper.py#L39-42` |
| B-41 | vigilia | cron/调度依赖本地时钟（休眠/漂移敏感），同分钟去重是唯一防重放闸 | `automation_runner.py#L33` |
| B-42 | vigilia | once 任务触发成功立即幂等标记 once_fired，标记失败记 warning 不阻塞 | `automation_runner.py#L945-951` |
| B-44 | vigilia | 运行状态真值在运行时侧时，重启必有 stale running——需启动 + 周期双 reconcile | `zombie_run_sweeper.py#L19-48` |
| B-49 | vigilia | per-task asyncio.Lock 字典 + 守卫锁防 tick 重入同一任务 | `unattended_task_pipeline.py#L40-41,L211-217` |
