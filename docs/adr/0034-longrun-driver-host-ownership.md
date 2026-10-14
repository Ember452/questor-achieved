# ADR-0034 — 长跑驱动的宿主归属：stdio sidecar 挂、http 改 opt-in

状态: proposed（待用户裁决，两个选项都可行但交付面不同）
日期: 2026-10-13 | 关联: `serve/longrun.py`、`serve/http.py`、`serve/stdio.py`、
`serve/app_server.py`（`goal_waker`）、ADR-0026（vigilia 调度与清扫）、ADR-0030（Electron 壳）

## 问题（先摆实测事实，非推测）

1. `LongRunDriver` 只在 `serve/http.py` 被无条件实例化；`serve/stdio.py`（85 行）不挂。
2. `serve/longrun.py` 模块注释把它写成**有意边界**："驱动挂在 http 宿主，stdio sidecar
   不挂——`goal/start` 在未接驱动的宿主只登记状态，不假装在驱（诚实呈现）"。
3. 但"诚实呈现"目前只活在注释里：`initialize` 回包字段有 `issues` / `status` /
   `feature_flags` / `methods`，**没有任何一项声明本机是否接了长跑驱动**；
   `goal/start` 返回成功并把 Goal 置 `RUNNING` 落盘。
4. Phase U 收口后，桌面端（Electron 壳）走的正是 stdio sidecar 这条路，
   而 `ui/src/panels/board.tsx`（228 行）已经把 Goal/任务看板做出来了。
5. 复核 `ui/src` 与 `desktop/src` 全量：**没有一处消费 `issues` 或 `needs_setup`**
   （只有生成的 `app_server-v0-1.d.ts` 里有该字段类型）。

结论：这不是漏接，是**一条只写在注释里的降级路径撞上了一个已上线的界面**。
按 `AGENTS.md` §五 的判据（"这个偏离会让用户看到假的完成状态吗？会→不许偏离"），
现状不合格：用户在桌面端点"启动目标"，看板翻成 running，而没有任何轮在驱。

## 候选方案

**A. stdio 宿主挂驱动 + http 侧改显式 opt-in（推荐）**
长跑单主归桌面 sidecar；`serve http` 的驱动改由 flag/env 决定，默认关。
需一并把"未接驱动"从注释升级成握手可见（`initialize.issues` 里一条机器可读项）。

**B. 维持不挂，只把降级面做实**
`goal/start` 在无驱动宿主上返回显式告警、Goal 不进 `RUNNING`（或进
`PENDING_DRIVER` 类状态），UI 据 `initialize` 的声明禁用或标注该入口。
代价：桌面端等于**没有交付 Goal/Schedule**，而"长任务托管"是本项目的两条能力来源之一。

**C. 两宿主都挂**
不推荐：见下方风险，需要额外引入单主选举才安全，成本高于 A。

## 理由与取舍

- **跨进程锁已经够用一半**：`state/locks.py` 的 `StoreLock` 是 OS 级跨进程锁
  （Windows `msvcrt.locking` / POSIX `flock`，`.store.lock`），
  `vigilia/store.py` 与 `orchestration/store.py` 的读-改-写全程持锁。
  Goal/触发器的幂等标记（`once_fired`、`last_fired_slot`）写入是原子的。
- **但仍存在真实的双触发窗口**：`Scheduler.tick` 里"判到点"（读 `last_fired_slot`）
  与"起轮"都在锁外，只有幂等标记的写入在锁内。两个进程在同一分钟并发评估时，
  完全可能都判到点、都起轮——**这是 A 方案要求"单主归属"的真实理由，不是猜测**。
  A 方案把双主变成"默认只有一个主"，窗口就不需要选举协议来堵。
- **代价（A 的诚实账）**：http 宿主默认不再驱长跑，依赖它做常驻后台的人需要显式开关；
  若同时开两个宿主仍会双驱，所以 A 必须配一条"同机只允许一个驱动宿主"的启动期检查
  或至少在 `initialize.issues` 里如实报双主。
- **为什么 B 不够**：它把 §五 的判据满足了（界面不撒谎），但让桌面端交付一个
  永远不动的看板——Phase U 选 Electron 的核心理由之一就是"能跑真东西的桌面壳"。

## 被否决的选项

- **C（两宿主都挂，靠锁去重）**：锁只覆盖写，判到点与起轮在锁外，去重不成立；
  要补就得上单主选举/租约，那是一套新的分布式协议，与"个人本机工作台"体量不匹配。
- **只在 UI 层加"需后台宿主"文案**：同一事实变成两套真相（内核说 running、
  界面说可能没跑），违反 AGENTS §三；且远程端（未来的 IM/网页）读同一状态仍会被骗。
- **删掉 Goal/Schedule 功能面**：为省事砍掉两条能力来源之一，属于范围改判，
  得走 ADR 改定位而不是靠砍代码解决接线问题。

## 适用条件与失效条件

**适用**：桌面端（stdio sidecar）作为主交付形态期间。

**落地顺序**（若裁 A）：① `initialize` 增一条机器可读的驱动归属声明；② stdio 宿主
在 `serve_stdio` 的生命周期里 start/stop driver（照 `http.py` 的 `asynccontextmanager` 范式）；
③ http 侧改 opt-in；④ 双主启动期检查 + 一条 `tests/integration/` 的跨宿主用例
（负向验证：不接驱动时 Goal 不得进入 RUNNING）。

**触发重新评审**：引入远程/多机宿主（M8 的自托管网页或 IM 渠道）时，本机 sidecar
不再是唯一宿主，单主归属规则必须重做成显式租约；或 `StoreLock` 换成无跨进程语义的实现时。
