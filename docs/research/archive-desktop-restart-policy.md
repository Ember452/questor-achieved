# 桌面壳 sidecar 重启与关停策略（历史归档：知识留存，不得再作实现依据）

> Phase 0 归档（ADR-0040/0044）：原 `docs/notes/2026-10-13-desktop-restart-policy.md` 锚定的
> 旧 `desktop/src/main/*.ts` 已随壳废弃移出工作树（快照在 `reference-only-archive` 分支）。
> 机制结论（等 exit 不等 pipe／三层定时／fail-open／Windows SIGTERM≡SIGKILL 语义）对
> Phase 2b 新壳重建仍有参考价值，故存此；重建后须按新代码重验才可回到 notes/ 格式。

日期: 2026-10-13 | 归档于: 2026-10-14
锚点（历史快照内路径）: `desktop/src/main/child-shutdown.ts`、`desktop/src/main/sidecar.ts`、
`desktop/src/main/index.ts`、`desktop/src/main/sidecar-lock.ts`、
`docs/plans/2026-10-13-phase-u-ui-and-electron-shell.md`

## 结论

sidecar 关停走三层定时 + fail-open 重启；Windows 与 POSIX 语义有别、代码在平台分岔处
注释了差异，本笔记把决策与实测的**不显然之处**摊开，方便日后回看。

## 三层定时（`killTree`）

时序：`requestStop`（可选协议级优雅停机，B6 IPC 桥落地后接 `session/control stop`）→
SIGTERM at graceMs（默认 20 s）→ SIGKILL at graceMs + 3 s → **reject** at graceMs + 5 s。
所有 timer `unref()`，一个挂死的 shutdown 不会阻止 node 进程退出。

**等 exit 事件、不等 pipe close**（B-113）：子进程派生的后代可能仍持继承的 stdio pipe；
只听 stdout 的 close 事件会让主进程以为"sidecar 已停"、实际整个进程树还在活着写盘。
`killTree` 里 `handle.exited.then(() => resolve(true))` 就是这条不变量的机械表达。

## Fail-open backoff（`armRestartPolicy`）

- 非零 exit → 依 `backoffMs` 表延迟 → 触发 `onRespawn`
- `code === 0` → 用户主动关窗，**不重启**（`if (r.code === 0) return` 这一行是护栏）
- `retries >= maxRetries` → 停、调 `onBudgetExhausted`；B5 阶段仅 `console.warn`；
  B6 IPC 起来后切 `qst:sidecar-state` 广播（R-13）
- 本项目 `backoffMs = [500, 2000, 8000]`、`maxRetries = 3`——三次重启用完 = 运维来看

`retries` 计数**在单 handle 的 closure 里**；`main/index.ts` 的 `spawnSidecar()` 每次
respawn 都造新 handle、各 handle 独立计数。真正的"3 次上限"由 `armRestartPolicy` 里
`retries >= maxRetries` 挡下——但**只在同一 handle 的 exited 里 fire 一次**，跨 handle
不会累加。跨 handle 的上限语义（"重启 3 次都失败就不再尝试"）在**桌面壳这一层**不真存
在：每次新 handle fresh；如果 Python 侧持续秒退，会看到"respawn → 秒退 → respawn → …"
——这是 wuu 与 EvoFlow 的共同形态，本项目沿用；若需要"5 分钟内累计 3 次失败拉黑"式
的时间窗上限，另开 ADR。

## Windows 与 POSIX 的 SIGTERM/SIGKILL 语义差

Node docs 明说：Windows 上 `child.kill(signal)` 除 SIGTERM 与 SIGKILL 都走
`TerminateProcess`、等价（其余 signal 会抛 `ERR_INVALID_ARG_VALUE`）。所以 `killTree`
在 `process.platform === "win32"` 分支下**不发第二枪 SIGKILL**——避免误导 reviewer
"双发更有效"。测里用 `vi.stubGlobal("process", { ...process, platform: "linux" })`
强制走 POSIX 分支、验证 SIGTERM→SIGKILL→reject 三层都 fire。

## 与 `lifecycle_lock` 的互作

respawn 走同一路径：`spawnSidecar() → withLifecycleLock(home, async () => startSidecar + bumpState)`。
**孤儿锁场景**：上一代 sidecar 因硬崩没跑到 `finally { fs.unlinkSync }` → `.lifecycle.lock`
遗留 → 下一次 spawn 会 5 s 超时抛 `lifecycle lock busy: <path>` → `catch` 吞下、
renderer 里看到 sidecar 缺席。运维手动清锁即可；mtime 心跳判定属 M8 remote/relay 场景、
Phase U 不留门。

`shuttingDown` flag（`main/index.ts` 顶层）在 `before-quit` 时置 true，让任何在飞的
respawn 立刻短路——关窗与重启链的竞态就此挡下。

## 一句话结论

sidecar 生命周期是"**等 exit、不等 pipe；三层定时；fail-open 到运维**"，Windows 语义
差异在代码里显式注释、测试 stub `process.platform` 覆盖两条分支；跨 handle 的重启次数
上限属另开 ADR 的话题、Phase U 只保证单 handle 内的正确性。
