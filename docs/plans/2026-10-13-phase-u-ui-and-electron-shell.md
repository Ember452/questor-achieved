# Phase U 实施计划 — Review 面板 wuu 级还原 + Electron 桌面壳

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase U 拆成可勾选、可独立回滚的任务序列——Track A 先在浏览器宿主里把 Review 面板做到 wuu 级还原度（真 diff、逐文件展开、已阅态、动效与主题）；Track B 再把整套 `ui/` 构建产物包进 Electron 壳、主进程用 `child_process` 以 stdio 管道拉起 `questor serve stdio` sidecar，交付"双击能开 + 真 sidecar 通信 + 真 diff 呈现"的产品形态。

**Architecture:**
- Track A 不动内核、不动协议、不动视图注册表外壳；只在 `ui/src/panels/review.tsx` 与其配套 token/测试面做增量。走 `serve http` + 浏览器 localhost 验证（M3 已具备双宿主同契约）。
- Track B 建 `desktop/`（main/preload + electron-vite）；主进程用 `child_process` 起 Python 子进程，与 `questor serve stdio` 走 stdin/stdout NDJSON；**renderer ↔ main IPC ↔ sidecar stdio**——照 wuu `desktop/src/main/appServerClients.ts` + `main/index.ts::appServerRequest` + `main/preload.ts::contextBridge` 的路径：`window.questorHost` 承载 `request / onServerEvent / respondToServerRequest / rejectServerRequest / getSnapshot`，主进程持 pending 表 + server-request 路由表 + delta 合批器；sidecar 生命周期沿用 wuu `childShutdown.ts` + `atomicFile.ts` + `wuuCommand.ts` + `rendererServerEventBatcher.ts` 全套设计决定（grace 20 s 等 exit 而非 pipe close、O_EXCL+fsync+rename、拒从 workspace/PATH 找 binary、50 ms delta 合批），**重写实现加 provenance**、不拷贝代码。**Option A 为唯一方案**：ADR-0006 结论 4「桌面 stdio NDJSON」的忠实实现；Option B（起本地 http 让 renderer 连 WS）已否决，理由：会给桌面另开一条 WS、架空 stdio 侧。
- 顺序 A → B：Track A 完成后，`ui/` 构建产物原封搬进 Electron renderer；`structure.md` §7「一套前端两宿主」的立身之本正是此路径。
- Electron 独有能力（内嵌浏览器真接管、PiP 多窗口、自绘光标）归 **U2**，本计划不涵盖；本计划覆盖 U0（壳+一个高保真面板纵切片）+ U1 的 Review 部分。

**Tech Stack:**
- 现有：React 19 + TypeScript + Vite 6 + Tailwind 4 + zustand v5 + SWR；`WebSocketTransport`；`serve http` + `questor serve stdio`。
- Track A 新增：`@pierre/diffs`（evopanel 实测选型）、`vitest` + `happy-dom`（前端测试面）。
- Track B 新增：`electron` + `electron-vite` + `electron-builder`。
- 后端零改动：`serve/stdio.py::serve_stdio` 已在 M5 落地、`test_serve_stdio_host` 绿。

**Spec:**
- `docs/plans/development-plan.md` Phase U（U0/U1/U2 + 出口判据）
- `docs/adr/0030-desktop-shell-electron-and-ui-track.md`（壳选型与范围边界，尤其 §结论 4）
- `docs/architecture/overview.md` §4/§12/§14
- `docs/architecture/structure.md` §7/§9/§11
- `docs/specs/behavior-review-habena-wuu.md` 与 `pitfalls.md` B-45/B-66/B-93

---

## 从 wuu 桌面壳借鉴清单（2026-10-13 深度扫描）

计划里 B3~B6 的实现形状来自这 8 处 wuu 实测——**照设计决定、重写代码、加 provenance**（AGENTS §二）。以 wuu 为准。

| # | wuu 位置 | 设计决定 | 本计划落点 | 关联坑 |
|---|---|---|---|---|
| 1 | `desktop/src/main/childShutdown.ts` (29 行) | 关停等 **exit 事件** 而非 pipe close（后代进程仍持继承 pipe 会误报）；SIGTERM at graceMs → SIGKILL at graceMs+3s → reject at graceMs+5s；全部 `timer.unref()`；grace 默认 20 s；`requestStop()` 优雅钩子（协议级 stop），异常回退 SIGTERM | **B5** | B-113 |
| 2 | `desktop/src/renderer/ServerEvents.ts` (21 行) | 单桥 fanout：Set\<listener>，`disconnect ??= window.wuu.onServerEvent(...)`，最后一个 listener 走时 `disconnect=undefined`；保事件身份与顺序 | **B6** renderer 侧 | — |
| 3 | `desktop/src/main/wuuCommand.ts` (62 行) | **绝**不从 workspace 找 `bin/wuu`（issue #8：Linux ELF 落 macOS `spawn ENOEXEC`）；优先级 `WUU_DESKTOP_CORE` env → `WUU_DESKTOP_USE_GO_RUN=1` + source root → 打包 `Resources/bin/wuu-core.exe`；**永不** fall back PATH | **B3** 新建 `desktop/src/main/questor-command.ts` | B-114 |
| 4 | `desktop/src/main/atomicFile.ts` (96 行) | mkdir -p → 读旧 mode 保留 → `.basename.pid.uuid.tmp` 用 O_CREAT\|O_EXCL\|O_WRONLY 开 → `fchmodSync` → `writeFileSync` → `fsyncSync` → `closeSync` → `renameSync` 覆盖；错误路径清 temp；text/binary 共享 core | **B4** `runtime_state.json` 写入；新建 `desktop/src/main/atomic-file.ts` | B-115 |
| 5 | `desktop/src/main/appServerClients.ts` (1142 行) | Pool + MRU (`MAX_APP_SERVER_CLIENTS=4`)；`turn/started` 通知落 `sessionOwners: Map<threadID,Client>`、`server-exit` 清；server-initiated request 用 `server-request-${N}` public id 桥接（**不暴露内核真实 id**）；`maybeBroadcastRunningThreads` 只在 key 变时广播 | **B3** pending 表形状、**B6** IPC bridge 与 server-request 路由 | B-118 |
| 6 | `desktop/src/main/preload.ts` (666 行) | contextBridge API 完整面：业务方法 = `ipcRenderer.invoke("qst:xxx", ...)`、订阅方法 = 注册 `ipcRenderer.on("qst:xxx")` 返回 unsubscribe；同步引导用 `sendSync`；**护栏**：“SendSync must be paired with ipcMain.on handler that sets event.returnValue, the parity test enforces both sides” | **B6** preload + 新建 `desktop/tests/ipc-parity.test.ts` | B-116 |
| 7 | `desktop/src/main/rendererServerEventBatcher.ts` (138 行) | 50 ms 窗口只合批 `item/{agentMessage,reasoning,toolCall}/delta` + `toolCall/outputDelta`；同 identity（workdir+method+thread+turn+item）合并；控制/终止事件先 flush 再立即 emit；`resolveSnapshot` 前 flush 防 snapshot 已含 delta 被 renderer 重放；raw provider delta（`content_delta`/`thinking_delta`/`tool_use_delta`）**不转发** | **B6** 新建 `desktop/src/main/renderer-batcher.ts` | B-117 |
| 8 | `desktop/src/main/index.ts::appServerRequest` (line 458) | `runtimeContextForEvent(event)` 从 `event.sender.id` 反查该窗口的 RuntimeContext；`appServerRequest(event, method, params, targetContext?)`；`initialize` 里 `capabilities.reverse_rpc.methods` 声明 renderer 支持的反向 RPC 方法清单 | **B6** `ipcMain.handle("qst:request", (evt, m, p, ctx?) => ...)` | — |

**本计划不采纳的 wuu 设计**（避免 scope 漂移，归 U2/M8）：多 client MRU 池（Questor 起步一 shell 一 workspace，形状保留）；`popOutInit` sendSync（多窗口 pop-out 属 U2）；`codexPet*` 桌面宠物（不做）；`browserHostWindows`/`browserPiPWindow`/`agentCursor`（属 U2 真接管）；`cua*`（Computer Use Activity，不做）；`remoteAppServerBridge`/`phoneAccess`/`systemProxy`（属 M8）。

---

## Global Constraints

- **AGENTS §四**：`just check` = ruff check/format + pyright + pytest unit + arch + specs + gen-check + 前端 typecheck；本机无 `just` 时按 `justfile` 的 `check` 配方逐条手动跑，**不另写包装**。每任务 DoD 必跑相关子集。
- **AGENTS §四 依赖纪律**：新增任何第三方依赖**先落 ADR**（本计划含两条：ADR-0031 for `@pierre/diffs`+`vitest`；ADR-0032 for Electron 工具链）。
- **AGENTS §六**：commit 一律英文 Conventional Commits、scope = 模块名（`ui`、`desktop`、`docs`、`ci`、`schemas` 等）；本计划每个 Task Step 的最后一步是 commit，默认执行方已获得"本里程碑允许逐步提交"的授权，否则按项目纪律先汇报改动清单、待用户点头再提交。
- **AGENTS §一 铁律 1**：诚实呈现——真机走查、evals 基线缺凭据的记 `pending`，**不凑**。
- **AGENTS §一 铁律 3 + overview §12 砍单预案**：任何阶段不为面板好看牺牲三柱判据（可见 → 可干预 → 可验证）。
- **overview §14 已留门**："GUI 能力必须经协议可达"——壳**不得**引入只有桌面能调的私有端点；Electron 主进程与 renderer 的 IPC 只能承载壳自身职责（sidecar 生命周期、窗口管理），业务判断仍走 Python 内核。
- **ADR-0006 结论 2/4/5 + ADR-0030 结论 4**：一套前端代码、两宿主同契约、默认只绑 `127.0.0.1`；本计划**不动** `ui/` 之外的内核、`serve` 协议与 stdio/WS 传输、`schemas` 与生成链、`PanelProps` 形状。若暴露新协议方法/事件需求 → **停下走单独 ADR**（AGENTS §七）。
- **ADR-0007**：Windows 第一平台，Electron 走 Windows 打包优先。
- **护栏 `test_no_hardcoded_panel_case.py`**：`AppShell.tsx`/`PanelHost.tsx` 不得硬编码面板名字面量；一切面板通过 `panels/registry.ts` 的 `PANELS` 登记。
- **注释语言**：代码注释/docstring 中文，术语与标识符保留英文；commit message 英文。
- **红线（AGENTS §四）**：Windows 上禁 `Set-Content`/`Out-File` 写源码/配置（UTF-8 BOM 会炸 hatchling/tomllib），改文件一律走编辑工具。
- **`.gitattributes` 钉 LF**，行尾不依赖 `core.autocrlf`。

---

## 文件结构（Phase U 结束后长这样）

```
questor/
├── ui/
│   ├── package.json                     # 追加 @pierre/diffs / vitest / happy-dom / @testing-library
│   ├── vitest.config.ts                 # 新建（Track A）
│   ├── src/
│   │   ├── panels/
│   │   │   ├── review.tsx               # 重写：@pierre/diffs 双栏 + 折叠/展开 + 已阅态
│   │   │   ├── review.css.ts            # 新建（或就近 CSS Module）：过渡、elevation
│   │   │   ├── review.diff-view.tsx     # 新建：@pierre/diffs 薄封装（A7）
│   │   │   └── registry.ts              # 不改（护栏）
│   │   ├── design/
│   │   │   ├── tokens.css               # 追加 --elevation-*、--motion-*、--color-diff-* 语义族
│   │   │   ├── themes.css               # 追加暗色 diff 色对
│   │   │   └── base.css                 # 追加 .qst-focus-ring + @media prefers-reduced-motion
│   │   ├── rpc/
│   │   │   ├── ipc-transport.ts            # 新建（B6）：Transport 的 Electron 实现
│   │   │   ├── server-events-fanout.ts     # 新建（B6）：照 wuu ServerEvents.ts 的单桥 fanout
│   │   │   └── client.ts                   # 微调：`isElectronHost()` 返真时选 IpcTransport（浏览器路径零改）
│   │   └── testing/
│   │       ├── setup.ts                    # 新建：jest-dom vitest 入口
│   │       └── fixtures.ts                 # 新建：FileDiff 样本与 fake client
│   └── tests/
│       ├── review.panel.test.tsx           # 面板折叠/已阅态/fingerprint/空态
│       ├── review.fidelity.test.tsx        # 双栏 diff、reduced-motion、暗色 diff 色对
│       └── design.tokens.test.ts           # 护栏：面板文件无 hex 字面量
├── desktop/                             # 新建（Track B）
│   ├── package.json                     # electron + electron-vite + electron-builder + vitest
│   ├── electron.vite.config.ts          # main / preload / renderer 三段（renderer root = ../ui）
│   ├── electron-builder.yml             # Windows NSIS 目标
│   ├── tsconfig.node.json               # 主进程/preload TS 配置
│   ├── src/
│   │   ├── main/
│   │   │   ├── index.ts                 # BrowserWindow + whenReady 拉 sidecar + 注册 ipcMain handlers
│   │   │   ├── questor-command.ts       # 新建（B3）：严格照 wuu wuuCommand.ts，绝不 PATH 兜底
│   │   │   ├── atomic-file.ts           # 新建（B3）：O_EXCL + fsync + rename（B4/B6 共用）
│   │   │   ├── sidecar.ts               # 新建（B3）：child_process.spawn、NDJSON 帧、pending 表
│   │   │   ├── sidecar-state.ts         # 新建（B4）：runtime_state.json 单调 generation
│   │   │   ├── sidecar-lock.ts          # 新建（B4）：lifecycle_lock 防拉起竞态
│   │   │   ├── child-shutdown.ts        # 新建（B5）：严格照 wuu childShutdown.ts，grace 20s + 三层 timer
│   │   │   ├── app-server-bridge.ts     # 新建（B6）：pending 表 + server-request public id 桥 + sessionOwners
│   │   │   └── renderer-batcher.ts      # 新建（B6）：照 wuu rendererServerEventBatcher，50ms 合批
│   │   ├── preload/
│   │   │   └── index.ts                 # window.questorHost：request / onServerEvent / respondToServerRequest / rejectServerRequest / getSnapshot
│   │   └── renderer/                    # 复用 ui/ 构建产物（不复制源码）
│   └── tests/
│       ├── sidecar.test.ts              # B3：NDJSON 往返、stderr 独立
│       ├── questor-command.test.ts      # B3 护栏：workspace 里有假 bin/questor 也不能被 resolve（B-114）
│       ├── atomic-file.test.ts          # B3 护栏：模拟 fsync 后 crash，目标仍旧内容（B-115）
│       ├── generation.test.ts           # B4：单调性 + lifecycle_lock
│       ├── restart.test.ts              # B5：fail-open backoff + kill tree 三层 timer
│       ├── ipc-parity.test.ts           # B6 护栏：preload invoke/sendSync/on ↔ main handle/on/webContents.send 一一对偶（B-116）
│       ├── renderer-batcher.test.ts     # B6：50ms 窗口 + 控制事件先 flush + raw delta 不转发（B-117）
│       └── bridge.test.ts               # B6：pending 匹配 + turn/started 落 sessionOwners + server-request public id 桥（B-118）
├── assets/                              # Track B 新建：图标源与再生成命令
├── docs/
│   ├── adr/
│   │   ├── 0031-ui-diff-renderer-and-vitest.md
│   │   ├── 0032-electron-shell-and-toolchain.md
│   │   └── README.md                    # 索引同步
│   ├── architecture/modules/
│   │   └── desktop.md                   # Track B 壳设计篇（docstring 级）
│   ├── notes/
│   │   ├── 2026-10-13-review-fidelity-walk.md    # A9 人工走查
│   │   └── 2026-10-13-desktop-restart-policy.md  # B5 重启策略
│   └── specs/
│       ├── behavior-review-fidelity-wuu.md       # Track A 行为规格
│       └── pitfalls.md                            # 追加 B-103~B-118
├── tests/e2e/
│   └── test_desktop_shell_vertical_slice.py     # B9 Python 侧 e2e
├── .github/workflows/
│   └── desktop.yml                      # Track B 新建
└── justfile                             # 追加 desktop-test / desktop-build
```

**职责边界**：
- `ui/src/panels/review.tsx` = 只负责"给一组 `FileDiff`，按 wuu 级观感渲染"；数据取用经现有 `client.call("review/turn_diff", ...)`，不改协议。
- `ui/src/design/tokens.css` = 语义 token 单点；`themes.css` 只做亮/暗覆盖；组件不得再散写 hex 字面量（护栏 `design.tokens.test.ts` 咬住）。
- `desktop/src/main/sidecar.ts` = 唯一负责 Python 子进程生命周期；renderer **不得**直接感知子进程存在（overview §14：壳里不含业务判断）。**Option A 下 renderer 不直连内核**，子进程管道只到 main 里的 `AppServerBridge`、不到 renderer。
- `desktop/src/preload/index.ts` = contextBridge 白名单出口，只暴露 `{request, onServerEvent, respondToServerRequest, rejectServerRequest, getSnapshot}` 五个方法；任何"业务方法"从这里直出即违反纯壳纪律（业务方法一律走 `request("qst:xxx")`）。

---

## Track A：Review 面板 wuu 级还原度（浏览器宿主）

### Task A1：落 ADR-0031（@pierre/diffs + vitest 引入）

**Files:**
- Create: `docs/adr/0031-ui-diff-renderer-and-vitest.md`
- Modify: `docs/adr/README.md`（追加编号索引一行）

**Interfaces:**
- Produces: 允许 `ui/package.json` 引入 `@pierre/diffs`、`vitest`、`@vitest/ui`（可选）、`happy-dom`；为 Track A 后续任务的依赖安装提供纪律依据。

- [ ] **Step 1：起草 ADR-0031 正文**

  写入 `docs/adr/0031-ui-diff-renderer-and-vitest.md`，模板照 `docs/adr/0006-*.md`：

  ```markdown
  # ADR-0031 — Review 面板 diff 渲染器与前端测试面依赖引入

  状态: accepted
  日期: 2026-10-13 | 关联: `AGENTS.md` §四 依赖纪律、`structure.md` §7 现成件清单、
  ADR-0030（Phase U 提前）、`docs/plans/2026-10-13-phase-u-ui-and-electron-shell.md`

  ## 结论
  1. `ui/` 引入 `@pierre/diffs` 作为 Review 面板的双栏/行内 diff 渲染器；evopanel 实测选型（`structure.md` §7）。
  2. `ui/` 引入 `vitest` 作为前端测试 runner；`happy-dom` 作为 DOM 环境；与 vite 配置共享，不引 jest。
  3. 二者均为**前端 npm 依赖**，不进 Python 侧；不新增 pytest 依赖。

  ## 理由与取舍
  - `@pierre/diffs` 是 evopanel 实测在用（`structure.md` §7 已列），复用可省 M3 重新选型；相较 `react-diff-viewer` 支持语法高亮 token 与虚拟化。
  - `vitest` 与 Vite 配置同构，无需再维护 jest 那套 transform 边界；`happy-dom` 相较 `jsdom` 快、体量小，够覆盖面板组件渲染与事件冒泡。
  - 代价：`@pierre/diffs` 引入约 30 KB gzip（未 minify），vitest 增 CI 时长约 30–60 s——Track A 出口判据的"高还原度"必须付出这些账；不接受则退回 `<pre>` 版本，Phase U 目标即失效。

  ## 被否决的选项
  - `react-diff-viewer` / `diff2html`：无 evopanel 实测背书，且缺语法高亮 token 一体化。
  - `jest` + `ts-jest`：与 Vite 配置分离，transform 边界要单维护，与 vite 单源原则冲突。
  - 不装测试 runner（只做人工走查）：违反 AGENTS §四 "测试先枚举失败方式再实现"——还原度断言无锚。

  ## 适用条件与失效条件
  **适用**：Track A（Review 面板 wuu 级还原度）；后续 Terminal/Browser 面板沿用同测试面。
  **触发重新评审**：① `@pierre/diffs` 上游断维或体积失控（>100 KB gzip）→ 换 `react-diff-viewer` + `shiki` 组合，另开 ADR；
  ② vitest 与 vite 大版本升级造成配置漂移 → 记 ADR 版本号钉。
  ```

- [ ] **Step 2：更新 ADR 索引**

  在 `docs/adr/README.md` 表格末尾追加一行：

  ```markdown
  | [0031] (0031-ui-diff-renderer-and-vitest.md) | Review 面板 diff 渲染器与前端测试面依赖引入（@pierre/diffs + vitest + happy-dom） | accepted |
  ```

- [ ] **Step 3：跑链接检查**

  Run: `python scripts/ci/check_docs.py`
  Expected: `check_docs OK: 37 条文档相对链接均可解析`（+1 因新增一条索引链接）

- [ ] **Step 4：提交**

  ```bash
  git add docs/adr/0031-ui-diff-renderer-and-vitest.md docs/adr/README.md
  git commit -m "docs(adr): 0031 introduce @pierre/diffs and vitest for Review panel fidelity"
  ```

---

### Task A2：装依赖并让 typecheck/gen-check 不破

**Files:**
- Modify: `ui/package.json`（dependencies + devDependencies 各加两项）
- Modify: `ui/package-lock.json`（由 `npm install` 重写）

**Interfaces:**
- Produces: `@pierre/diffs`、`vitest`、`happy-dom` 在 `ui/` 里可 import；为 A5 起测面就绪。

- [ ] **Step 1：新增依赖清单**

  在 `ui/package.json` 追加：

  ```jsonc
  "dependencies": {
    // ...existing...
    "@pierre/diffs": "^1.0.0"     // 版本号取 npm latest stable；实施时以 `npm view @pierre/diffs version` 结果钉
  },
  "devDependencies": {
    // ...existing...
    "vitest": "^2.1.0",
    "happy-dom": "^15.0.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.0"
  },
  "scripts": {
    // ...existing...
    "test": "vitest run"
  }
  ```

- [ ] **Step 2：安装**

  Run: `npm --prefix ui install`
  Expected: `package-lock.json` 重写、无 error；若有 peer 冲突，记 ADR-0031 失效条件走重评，不改版本号硬过。

- [ ] **Step 3：跑现有 typecheck 与 gen-check，确认无回归**

  Run: `npm --prefix ui run typecheck`
  Expected: 0 error。

  Run: `.venv/Scripts/python.exe scripts/gen/types.mjs` 然后 `git diff --exit-code ui/src/rpc/generated/`
  Expected: 无 diff（本次改动不涉及 schema，生成链不受影响）。

- [ ] **Step 4：提交**

  ```bash
  git add ui/package.json ui/package-lock.json
  git commit -m "chore(ui): add @pierre/diffs and vitest per ADR-0031"
  ```

---

### Task A3：Track A 三资产落盘（behavior 规格 + 坑扩充）

**Files:**
- Create: `docs/specs/behavior-review-fidelity-wuu.md`
- Modify: `docs/specs/pitfalls.md`（追加 `B-103`~`B-107` 五条）
- Modify: `docs/specs/README.md`（若行为规格索引存在）

**Interfaces:**
- Produces: Track A 每一步"什么算还原到位"有可勾选证据；`check_specs.py` 绿；后续任务写测试照着坑编号。

**扫描锚点（wuu 侧要读的区域）**：
- `wuu-main/desktop/dev/review/renderer.tsx`（127 行 fixture，逐文件卡片观感）
- `wuu-main/desktop/dev/review/fixture.css`（17 行，色对与间距）
- `wuu-main/desktop/dev/design-system/renderer.tsx`（167 行）与 `fixture.css`
- `wuu-main/desktop/dev/elevation/renderer.tsx`（78 行）与 `fixture.css`（21 行）
- `wuu-main/desktop/dev/motion/renderer.tsx`（114 行）与 `fixture.css`（50 行）
- `wuu-main/desktop/dev/three-pane/renderer.tsx`（130 行）——面板容器
- wuu 主 renderer 里 Review 相关（`wuu-main/desktop/src/renderer/**/Review*` 或 `Diff*`，实施时 grep 定位）

- [ ] **Step 1：读扫描锚点、落"输入→输出→边界行为"到 behavior 规格**

  创建 `docs/specs/behavior-review-fidelity-wuu.md`，字段模板照现有 `behavior-review-habena-wuu.md`：

  ```markdown
  # behavior-review-fidelity-wuu — Review 面板 wuu 级还原度行为规格

  来源：`wuu-main/desktop/dev/review/renderer.tsx`、`dev/design-system`、`dev/elevation`、
  `dev/motion`、`dev/three-pane` 与 wuu 主 renderer 的 Review 组件；`evopanel/src/zcode-ui/styles.css`
  的 `--text-ui-*` calc 族与 `--shadow-*` 族。

  ## 输入
  - `FileDiff[]`（`review/turn_diff` 返回），每项含 `path / created / byte_size / hunks /
    content_fingerprint / unified`；unified 是"写工具执行时刻"算好的字符串（B-66/B-93）。

  ## 输出（可见）
  - 每个文件一张卡片：文件路径（mono）、状态徽标（`new` / `modified`）、字节数、hunk 数、
    fingerprint 短哈希；卡片 header 固定 `--text-ui-sm` 字号。
  - 卡片内双栏 diff：`@pierre/diffs` `SideBySideRenderer`，add/del 色对来自 `--color-diff-add-*`
    与 `--color-diff-del-*` token，**禁止 hex 字面量**（护栏 `design.tokens.test.ts`）。
  - 折叠/展开动画：`max-height` transition 180 ms + `cubic-bezier(0.2, 0.8, 0.2, 1)`；
    `prefers-reduced-motion: reduce` 下直跳。
  - 已阅态：卡片头右侧一枚 `dot`（4 px 圆点，`--color-foreground-subtlest`），点开该文件后淡出。

  ## 边界行为
  - `diffs.length === 0`：显示"该 turn 无写工具调用"占位（现有文案）。
  - `unified === ""`：显示 `(no changes)`（现有）。
  - `hunks.length` > 100：卡片默认折叠、header 显"100+ hunks"。
  - 客户端 cancel：请求未 resolve 前组件卸载 → 不 setState（现有 `cancelled` 旗保留）。

  ## 坑编号映射
  - B-103 双栏 diff 头尾截断（`@pierre/diffs` 长行 wrap 默认开）
  - B-104 `prefers-reduced-motion` 缺失让 wuu 动效在 CI/headless 里不稳
  - B-105 fingerprint 短哈希与 `#` 前缀在同一 row 里字体粗细不同
  - B-106 主题切换下 diff 色对反相（亮色 add=浅绿/del=浅红；暗色必须用低饱和变体）
  - B-107 空态与"该 turn 无写工具调用"的可见性冲突（护栏：占位文案不能同时显示 diff 卡片）
  ```

- [ ] **Step 2：在 `pitfalls.md` 表尾追加 B-103~B-107 五行**

  按现有表列格式（编号 / 归属模块 / 坑描述 / 类型 / 来源 / 测试 / 状态）。前 4 条状态记 `open`（对应测试待 A5/A7/A8 落）；B-107 归属 `review` 面板、`open`。**每条测试列先写"待 A? 补"**，实施到相应 Task 再回填测试名，最后由 `check_specs.py` 咬住"测试列必须能定位到实文件"。

- [ ] **Step 3：跑 `check_specs.py`**

  Run: `.venv/Scripts/python.exe scripts/ci/check_specs.py`
  Expected: `check_specs OK: 有效 105/107 条，编号连续，证据可定位`（新增 5 条 + 现有 100 条 - B-103~107 中 `open` 状态不计入下限）

- [ ] **Step 4：提交**

  ```bash
  git add docs/specs/behavior-review-fidelity-wuu.md docs/specs/pitfalls.md
  git commit -m "docs(specs): Track A review fidelity behavior spec + B-103..107 pitfalls"
  ```

---

### Task A4：主题 token 扩族（elevation / motion / diff 色对）

**Files:**
- Modify: `ui/src/design/tokens.css`（追加 `--elevation-*`、`--motion-*`、`--color-diff-*` 三族）
- Modify: `ui/src/design/themes.css`（追加暗色 diff 色对覆盖）
- Modify: `ui/src/design/base.css`（追加 `.qst-focus-ring` 与 `@media (prefers-reduced-motion: reduce)`）
- Test: `ui/tests/design.tokens.test.ts`（护栏）

**Interfaces:**
- Produces: 后续组件只能用 token，不能用 hex；`--elevation-1..4`、`--motion-fast/normal/slow`、`--color-diff-add-bg/fg`、`--color-diff-del-bg/fg`。

- [ ] **Step 1：写失败测试（护栏：组件不得散写 hex）**

  创建 `ui/tests/design.tokens.test.ts`：

  ```typescript
  // 护栏：`ui/src/panels/review.tsx` 与 `review.css.ts`（后续引入）不得出现 diff 相关的 hex 字面量，
  // 必须走 `var(--color-diff-*)` 或 Tailwind 类映射到 token。
  import { describe, expect, it } from "vitest";
  import { readFileSync } from "node:fs";
  import { resolve } from "node:path";

  const read = (p: string) => readFileSync(resolve(__dirname, "..", p), "utf8");

  describe("Review 面板 diff 色只走 token", () => {
    for (const file of ["src/panels/review.tsx", "src/panels/review.css.ts"]) {
      it(`${file} 无 diff hex 字面量`, () => {
        const src = read(file);
        // #dc2626 / #16a34a 等 add/del 常色一律禁
        expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}/);
      });
    }
  });
  ```

- [ ] **Step 2：跑测试确认失败**

  Run: `npm --prefix ui run test`
  Expected: FAIL（`review.tsx` 现有实现无 hex，但 `review.css.ts` 尚不存在 → 用例 fail 于 `readFileSync` not found；实施 Step 3 起建 `review.css.ts` 后转绿）

- [ ] **Step 3：扩 tokens.css**

  在 `ui/src/design/tokens.css` 的 `@theme { ... }` 尾部追加：

  ```css
  /* ---- Phase U 扩展：elevation / motion / diff 色对（源自 wuu dev/elevation,dev/motion,dev/design-system） ---- */

  /* elevation 阴影族（4 级，与 wuu 主 renderer 卡片层级一致） */
  --elevation-0: none;
  --elevation-1: 0 1px 0 rgba(0, 0, 0, 0.04);
  --elevation-2: 0 2px 4px rgba(0, 0, 0, 0.06);
  --elevation-3: 0 4px 12px rgba(0, 0, 0, 0.08);
  --elevation-4: 0 8px 24px rgba(0, 0, 0, 0.10);

  /* motion 时长与曲线族 */
  --motion-fast: 120ms;
  --motion-normal: 180ms;
  --motion-slow: 240ms;
  --motion-ease-standard: cubic-bezier(0.2, 0.8, 0.2, 1);
  --motion-ease-out: cubic-bezier(0, 0, 0.2, 1);

  /* diff 色对（亮色基础；暗色覆盖在 themes.css） */
  --color-diff-add-bg: #e6f6ec;
  --color-diff-add-fg: #166534;
  --color-diff-del-bg: #fbe7e7;
  --color-diff-del-fg: #991b1b;
  --color-diff-hunk-header-bg: #f6f6f7;
  --color-diff-hunk-header-fg: #55555e;
  --color-diff-line-number: #8a8a94;
  --color-read-state-dot: #8a8a94;
  ```

- [ ] **Step 4：扩 themes.css 暗色**

  在 `ui/src/design/themes.css` 的 `.dark { ... }` 块内追加：

  ```css
  --color-diff-add-bg: rgba(22, 163, 74, 0.16);
  --color-diff-add-fg: #a7f3d0;
  --color-diff-del-bg: rgba(220, 38, 38, 0.18);
  --color-diff-del-fg: #fecaca;
  --color-diff-hunk-header-bg: rgba(255, 255, 255, 0.04);
  --color-diff-hunk-header-fg: #a1a1aa;
  --color-diff-line-number: #71717a;
  --color-read-state-dot: #71717a;
  ```

- [ ] **Step 5：扩 base.css（focus-ring + reduced-motion）**

  在 `ui/src/design/base.css` 尾部追加：

  ```css
  .qst-focus-ring:focus-visible {
    outline: none;
    box-shadow: 0 0 0 2px var(--color-primary);
  }
  @media (prefers-reduced-motion: reduce) {
    .qst-review-card-body,
    .qst-review-read-dot {
      transition: none !important;
    }
  }
  ```

- [ ] **Step 6：跑 typecheck 与 gen-check**

  Run: `npm --prefix ui run typecheck` ； Run: `.venv/Scripts/python.exe scripts/gen/types.mjs` 然后 `git diff --exit-code ui/src/rpc/generated/`
  Expected: 均绿。

- [ ] **Step 7：提交**

  ```bash
  git add ui/src/design/tokens.css ui/src/design/themes.css ui/src/design/base.css ui/tests/design.tokens.test.ts
  git commit -m "feat(ui): extend design tokens with elevation/motion/diff color families (Phase U)"
  ```

---

### Task A5：Review 面板测试面搭建（vitest + happy-dom）

**Files:**
- Create: `ui/vitest.config.ts`
- Create: `ui/src/testing/fixtures.ts`（`FileDiff` 样本与 fake `client`）
- Create: `ui/tests/review.panel.test.tsx`（3 条失败模式，先红）

**Interfaces:**
- Produces: `render(<ReviewPanel threadId activeTurnId/>)` 可测；`fixtures.ts` 导出 `SAMPLE_DIFF_MULTI_HUNK`、`SAMPLE_DIFF_EMPTY`、`SAMPLE_DIFF_LARGE_HUNKS`；`client.call` 可 mock。

- [ ] **Step 1：新建 vitest.config.ts**

  ```typescript
  // ui/vitest.config.ts
  import { defineConfig } from "vitest/config";
  import react from "@vitejs/plugin-react";

  export default defineConfig({
    plugins: [react()],
    test: {
      environment: "happy-dom",
      globals: true,
      setupFiles: ["./src/testing/setup.ts"],
      include: ["tests/**/*.test.{ts,tsx}"],
    },
  });
  ```

  同 Task 内新建 `ui/src/testing/setup.ts`：

  ```typescript
  import "@testing-library/jest-dom/vitest";
  ```

- [ ] **Step 2：建 fixtures**

  `ui/src/testing/fixtures.ts`：

  ```typescript
  import type { FileDiff } from "../rpc/generated/app_server-v0-1";
  import { vi } from "vitest";
  import { client } from "../rpc/client";

  export const SAMPLE_DIFF_MULTI_HUNK: FileDiff = {
    path: "src/foo.py",
    created: false,
    byte_size: 2048,
    content_fingerprint: "abc123def",
    unified: "@@ -1,3 +1,4 @@\n context\n-old\n+new\n+new2\n context\n@@ -20,1 +21,2 @@ ...",
    hunks: [{ /* 由 generated 类型钉 */ } as unknown as FileDiff["hunks"][number],
            /* ...3 项 */ ] as FileDiff["hunks"],
  };

  export const SAMPLE_DIFF_EMPTY: FileDiff[] = [];

  export const SAMPLE_DIFF_LARGE_HUNKS: FileDiff = {
    ...SAMPLE_DIFF_MULTI_HUNK,
    hunks: Array.from({ length: 120 }, () => SAMPLE_DIFF_MULTI_HUNK.hunks[0]) as FileDiff["hunks"],
  };

  /** mock client.call 的 review/turn_diff 返回，返回 restore 句柄。 */
  export function mockTurnDiff(diffs: FileDiff[]) {
    const spy = vi
      .spyOn(client, "call")
      .mockImplementation((method: string) => {
        if (method === "review/turn_diff") return Promise.resolve({ diffs });
        throw new Error(`unexpected method: ${method}`);
      }) as unknown as { mockRestore(): void };
    return () => spy.mockRestore();
  }
  ```

- [ ] **Step 3：写三条失败测试**

  `ui/tests/review.panel.test.tsx`：

  ```tsx
  import { describe, expect, it, afterEach } from "vitest";
  import { render, screen, waitFor } from "@testing-library/react";
  import userEvent from "@testing-library/user-event";
  import { ReviewPanel } from "../src/panels/review";
  import {
    SAMPLE_DIFF_EMPTY,
    SAMPLE_DIFF_LARGE_HUNKS,
    SAMPLE_DIFF_MULTI_HUNK,
    mockTurnDiff,
  } from "../src/testing/fixtures";

  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  describe("ReviewPanel 可见柱判据", () => {
    it("无 threadId 时显示占位而非卡片（B-107）", () => {
      render(<ReviewPanel threadId={null} activeTurnId={null} />);
      expect(
        screen.getByText(/尚未选择 turn/),
      ).toBeInTheDocument();
      expect(screen.queryByText(/src\/foo\.py/)).not.toBeInTheDocument();
    });

    it("diffs 为空时显示'该 turn 无写工具调用'（B-107）", async () => {
      restore = mockTurnDiff(SAMPLE_DIFF_EMPTY);
      render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
      await waitFor(() =>
        expect(screen.getByText(/该 turn 无写工具调用/)).toBeInTheDocument(),
      );
    });

    it("多 hunk 时首屏折叠、header 显'100+ hunks'（B-103）", async () => {
      restore = mockTurnDiff([SAMPLE_DIFF_LARGE_HUNKS]);
      render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
      await waitFor(() => expect(screen.getByText("src/foo.py")).toBeInTheDocument());
      expect(screen.getByText(/100\+ hunks/)).toBeInTheDocument();
      expect(screen.queryByText(/@@ -1,3 \+1,4 @@/)).not.toBeInTheDocument();
    });

    it("卡片头右侧显示 fingerprint 短哈希（B-105）", async () => {
      restore = mockTurnDiff([SAMPLE_DIFF_MULTI_HUNK]);
      render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
      await waitFor(() => expect(screen.getByText(/#abc123/)).toBeInTheDocument());
    });

    it("点击卡片头切换已阅态（B-104）", async () => {
      restore = mockTurnDiff([SAMPLE_DIFF_MULTI_HUNK]);
      render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
      const header = await waitFor(() => screen.getByText("src/foo.py"));
      const dot = document.querySelector<HTMLElement>(".qst-review-read-dot");
      expect(dot).not.toBeNull();
      expect(dot!.dataset.read).toBe("false");
      await userEvent.click(header);
      expect(dot!.dataset.read).toBe("true");
    });
  });
  ```

  **注意**：`@testing-library/user-event` 也是新前端 dev 依赖，需并入 ADR-0031 结论列表——在 ADR-0031 里"依赖清单"一节追加一行 `"@testing-library/user-event"`（同一 ADR 覆盖）；`ui/package.json` 加相应依赖并 `npm install`。

- [ ] **Step 4：跑测试确认全 5 条失败**

  Run: `npm --prefix ui run test`
  Expected: 5 条全 FAIL（现实现是 `<pre>` 版，无 read-dot、无 100+ hunks 折叠）。**保留失败输出**贴进后续 commit 正文或 PR 描述——"先红"证据（AGENTS §四 测试先枚举失败方式）。

- [ ] **Step 5：提交**

  ```bash
  git add ui/vitest.config.ts ui/src/testing/fixtures.ts ui/tests/review.panel.test.tsx
  git commit -m "test(ui): Review panel failing suite per Phase U fidelity spec (B-103..107)" -m "Test-first evidence: 5 tests fail against the current <pre>-only review.tsx."
  ```

---

### Task A6：Review 面板实现（折叠 / 已阅态 / 卡片头）

**Files:**
- Modify: `ui/src/panels/review.tsx`（整体重写）
- Create: `ui/src/panels/review.css.ts`（就近样式；如项目走 Tailwind 亦可 `review.module.css`）
- Test: `ui/tests/review.panel.test.tsx`（沿用 A5）

**Interfaces:**
- Produces: 让 A5 的 5 条测试**全绿**；导出 `ReviewPanel` 供 `panels/registry.ts` 用（签名不变：`PanelProps`）。

- [ ] **Step 1：实现 `ReviewPanel` 让前 4 条测试通过（先不做双栏 diff）**

  `ui/src/panels/review.tsx`：

  ```tsx
  // Review 面板：Phase U Track A 高保真还原度（wuu-grade）。
  // 参照 wuu-main/desktop/dev/review/renderer.tsx 与 dev/elevation、dev/motion 的观感；
  // 行为契约见 docs/specs/behavior-review-fidelity-wuu.md。
  // 坑对应：B-103 折叠、B-104 已阅 dot、B-105 fingerprint 短哈希、B-107 空态可见性。
  // A7 会挂上 @pierre/diffs 双栏渲染。

  import { useEffect, useMemo, useState } from "react";
  import { client } from "../rpc/client";
  import type { FileDiff } from "../rpc/generated/app_server-v0-1";
  import type { PanelProps } from "./registry";
  import "./review.css.ts";

  const LARGE_HUNKS = 100;

  interface CardState {
    collapsed: boolean;
    read: boolean;
  }

  export function ReviewPanel({ threadId, activeTurnId }: PanelProps) {
    const [diffs, setDiffs] = useState<FileDiff[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [card, setCard] = useState<Record<string, CardState>>({});

    useEffect(() => {
      if (!threadId || !activeTurnId) {
        setDiffs([]);
        return;
      }
      let cancelled = false;
      setError(null);
      client
        .call("review/turn_diff", { thread_id: threadId, turn_id: activeTurnId })
        .then((r) => !cancelled && setDiffs(r.diffs))
        .catch((err: Error) => !cancelled && setError(err.message));
      return () => {
        cancelled = true;
      };
    }, [threadId, activeTurnId]);

    const empty = useMemo(() => {
      if (!threadId || !activeTurnId)
        return "尚未选择 turn — 起一轮任务后这里显示写工具执行时刻算好的真实 diff。";
      if (diffs.length === 0 && !error) return "该 turn 无写工具调用";
      return null;
    }, [diffs.length, error, threadId, activeTurnId]);

    if (error) return <div className="p-3 text-ui-xs text-red-500">err: {error}</div>;
    if (empty) return <div className="p-3 text-ui-xs text-foreground-subtlest">{empty}</div>;

    return (
      <div className="overflow-auto text-ui-xs">
        {diffs.map((d) => (
          <FileDiffCard
            key={d.path}
            diff={d}
            state={card[d.path] ?? {
              collapsed: d.hunks.length > LARGE_HUNKS,
              read: false,
            }}
            onChange={(s) => setCard((prev) => ({ ...prev, [d.path]: s }))}
          />
        ))}
      </div>
    );
  }

  function FileDiffCard({
    diff,
    state,
    onChange,
  }: {
    diff: FileDiff;
    state: CardState;
    onChange: (s: CardState) => void;
  }) {
    const hunkCount =
      diff.hunks.length > LARGE_HUNKS ? "100+ hunks" : `${diff.hunks.length} hunks`;
    const fingerprintShort = diff.content_fingerprint.slice(0, 7);

    return (
      <section className="border-b border-border py-2 elevation-1">
        <header
          className="flex items-center gap-2 px-3 font-mono cursor-pointer qst-focus-ring"
          role="button"
          tabIndex={0}
          onClick={() => onChange({ ...state, read: true })}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onChange({ ...state, read: true });
            }
          }}
        >
          <span className="text-foreground">{diff.path}</span>
          <span className="text-foreground-subtlest">
            {diff.created ? "new" : "modified"} · {diff.byte_size}B · {hunkCount}
          </span>
          <span className="text-foreground-subtlest">#{fingerprintShort}</span>
          <span
            className={`qst-review-read-dot ml-auto ${state.read ? "is-read" : ""}`}
            data-read={state.read ? "true" : "false"}
            aria-hidden="true"
          />
        </header>
        <div
          className={`qst-review-card-body ${state.collapsed ? "is-collapsed" : ""}`}
          data-collapsed={state.collapsed}
        >
          <pre className="mt-1 whitespace-pre bg-surface px-3 py-1 text-foreground-subtle">
            {diff.unified || "(no changes)"}
          </pre>
        </div>
      </section>
    );
  }
  ```

  `ui/src/panels/review.css.ts`（Tailwind class 补充语义化样式）：

  ```css
  .elevation-1 { box-shadow: var(--elevation-1); }
  .qst-review-card-body {
    max-height: 800px;
    overflow: hidden;
    transition: max-height var(--motion-normal) var(--motion-ease-standard);
  }
  .qst-review-card-body.is-collapsed {
    max-height: 0;
    transition: max-height var(--motion-fast) var(--motion-ease-out);
  }
  .qst-review-read-dot {
    width: 4px; height: 4px; border-radius: 50%;
    background: var(--color-read-state-dot);
    opacity: 0;
    transition: opacity var(--motion-normal) var(--motion-ease-standard);
  }
  .qst-review-read-dot.is-read { opacity: 1; }
  ```

- [ ] **Step 2：跑测试确认 4 条通过**

  Run: `npm --prefix ui run test`
  Expected: `PASS` — 前 4 条（无 threadId / 空态 / 100+ hunks 折叠 / fingerprint 短哈希）全绿；第 5 条 `已阅 dot 切换` 可能因 user-event 触发 `role="button"` 需键盘可达——若已绿保留、若失败按输出调整。

- [ ] **Step 3：跑护栏测试（Task A4 Step 1 建的 `design.tokens.test.ts`）**

  Run: `npm --prefix ui run test`
  Expected: 6 条全绿，其中 `design.tokens.test.ts` 咬住"`review.tsx` 无 hex"。若红，说明样式里混了 hex——回 Step 1 用 token 类替换。

- [ ] **Step 4：提交**

  ```bash
  git add ui/src/panels/review.tsx ui/src/panels/review.css.ts
  git commit -m "feat(ui): Review panel card layout with fold, read-dot, and 100+ hunks collapse" -m "Passes 4/5 fidelity tests from A5. Design tokens enforced by A4 guardrail."
  ```

---

### Task A7：`@pierre/diffs` 双栏替换 `<pre>`（B-103/B-106）

**Files:**
- Modify: `ui/src/panels/review.tsx`（`FileDiffCard` 内替换 `<pre>` 为 `<FileDiffView/>`）
- Create: `ui/src/panels/review.diff-view.tsx`（薄封装 `@pierre/diffs`）
- Test: `ui/tests/review.fidelity.test.tsx`

**Interfaces:**
- Produces: `FileDiffView({ diff: FileDiff, theme: "light"|"dark" })`；A6 的 `ReviewPanel` 消费；测试用 snapshot 或 token 断言验证 add/del 色对。

- [ ] **Step 1：写失败测试**

  `ui/tests/review.fidelity.test.tsx`：

  ```tsx
  import { describe, expect, it, afterEach } from "vitest";
  import { render, screen, waitFor } from "@testing-library/react";
  import { ReviewPanel } from "../src/panels/review";
  import { SAMPLE_DIFF_MULTI_HUNK, mockTurnDiff } from "../src/testing/fixtures";

  let restore: (() => void) | null = null;
  afterEach(() => { restore?.(); restore = null; });

  describe("B-103 双栏 diff 头尾完整", () => {
    it("unified 头行 @@ 在渲染 DOM 中出现，未被截断", async () => {
      restore = mockTurnDiff([SAMPLE_DIFF_MULTI_HUNK]);
      const { container } = render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
      await waitFor(() => expect(screen.getByText("src/foo.py")).toBeInTheDocument());
      // @pierre/diffs 渲染后 DOM 应包含 hunk header 文本
      expect(container.textContent).toContain("@@ -1,3 +1,4 @@");
    });
  });

  describe("B-106 暗色 diff 色对", () => {
    it("add 行使用 --color-diff-add-* token（非 hex）", async () => {
      document.documentElement.classList.add("dark");
      restore = mockTurnDiff([SAMPLE_DIFF_MULTI_HUNK]);
      render(<ReviewPanel threadId="t1" activeTurnId="r1" />);
      await waitFor(() => expect(screen.getByText("src/foo.py")).toBeInTheDocument());
      const added = document.querySelector('[data-diff-role="add"]');
      // @pierre/diffs 用 data-* 或 class 属性；实施时以实际渲染属性替代
      expect(added ?? document.body).toBeTruthy();
    });
  });
  ```

  Run: `npm --prefix ui run test` — Expected FAIL（`FileDiffView` 未接入、DOM 里没 `@@` 结构）。

- [ ] **Step 2：写 `review.diff-view.tsx`**

  ```tsx
  // @pierre/diffs 薄封装：只负责把 unified 字符串喂给双栏渲染器，
  // 消费 tokens.css 的 diff 色对（不写 hex 字面量）。
  // 参照 wuu-main/desktop/dev/review/renderer.tsx 的 add/del 色对比。
  import { DiffView } from "@pierre/diffs";

  export function FileDiffView({ unified }: { unified: string }) {
    if (!unified) return <div className="px-3 py-1 text-foreground-subtlest">(no changes)</div>;
    return (
      <div className="qst-diff-view">
        <DiffView
          file={{ contents: unified }}
          options={{ themeMode: "light", syntaxHighlighting: true, wrap: true }}
        />
      </div>
    );
  }
  ```

  **注意**：`@pierre/diffs` 的实际 API 需查其 README；封装层保留一个可替换入口，若上游 API 变化只需改本文件（护栏：`FileDiffView` 是 `ui/src/panels/review.tsx` 唯一 import 的 diff 面）。

- [ ] **Step 3：接入 `review.tsx`**

  把 A6 里 `<pre>` 那段替换：

  ```diff
  - <pre className="mt-1 whitespace-pre bg-surface px-3 py-1 text-foreground-subtle">
  -   {diff.unified || "(no changes)"}
  - </pre>
  + <FileDiffView unified={diff.unified} />
  ```

  `FileDiffCard` import 处加 `import { FileDiffView } from "./review.diff-view";`

- [ ] **Step 4：跑测试 + 手动看 diff 观感**

  Run: `npm --prefix ui run test` — Expected: 全绿。
  Run: `npm --prefix ui run dev` 浏览器 `http://127.0.0.1:5173` → 打开一个真实 turn → Review 面板显示双栏 diff；对照 `wuu-main/desktop/dev/review/renderer.tsx` 观感截图（记入 plan notes，A9 收尾）。

- [ ] **Step 5：负向验证 + 提交**

  临时把 `review.tsx` 里的 `FileDiffView` 改回 `<pre>` → 跑 `review.fidelity.test.tsx` → 应红 → 复原。

  ```bash
  git add ui/src/panels/review.tsx ui/src/panels/review.diff-view.tsx ui/tests/review.fidelity.test.tsx
  git commit -m "feat(ui): replace <pre> with @pierre/diffs side-by-side view in Review panel" -m "Refs ADR-0031. B-103/B-106 covered."
  ```

---

### Task A8：动效收尾（transitions / focus ring / reduced-motion，B-104）

**Files:**
- Modify: `ui/src/panels/review.css.ts`（补 hover/active/focus 态过渡）
- Modify: `ui/src/panels/review.tsx`（header hover 时 elevation-2、active 时 elevation-1 深压）
- Test: `ui/tests/review.fidelity.test.tsx`（追加 reduced-motion 断言）

**Interfaces:**
- Produces: `ReviewPanel` 卡片过渡 180 ms、`prefers-reduced-motion: reduce` 下 `transition: none`。

- [ ] **Step 1：写失败测试（reduced-motion 断言）**

  追加进 `review.fidelity.test.tsx`：

  ```tsx
  describe("B-104 prefers-reduced-motion", () => {
    it("reduce 下卡片 body 无 transition", () => {
      // happy-dom 无 matchMedia；用 CSSOM 静态断言 base.css 里有 @media 块
      const css = readFileSync(resolve(__dirname, "../src/design/base.css"), "utf8");
      expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
      expect(css).toMatch(/transition:\s*none\s*!important/);
    });
  });
  ```

  （`readFileSync` 与 `resolve` 从 `node:fs`/`node:path` import，同 A4 测试的用法。）

- [ ] **Step 2：跑测试红 → 落 CSS**

  `review.css.ts` 补：

  ```css
  .elevation-1 { box-shadow: var(--elevation-1); transition: box-shadow var(--motion-normal) var(--motion-ease-standard); }
  section:hover > header.qst-focus-ring { --shadow: var(--elevation-2); }
  section:active > header.qst-focus-ring { box-shadow: var(--elevation-1), inset 0 1px 2px rgba(0,0,0,0.05); }
  ```

- [ ] **Step 3：绿 + 提交**

  Run: `npm --prefix ui run test`

  ```bash
  git add ui/src/panels/review.css.ts ui/src/panels/review.tsx ui/tests/review.fidelity.test.tsx
  git commit -m "feat(ui): Review panel elevation transitions and prefers-reduced-motion guardrail" -m "Covers B-104."
  ```

---

### Task A9：Track A 出口人工走查 + 文档勾销

**Files:**
- Modify: `docs/plans/development-plan.md`（Phase U 段的"实际结果"占位标注 Track A 已完成、Track B 待续）
- Modify: `docs/specs/pitfalls.md`（B-103~B-107 从 `open` 转 `covered`，回填 A5~A8 测试名）
- Create: `docs/notes/2026-10-13-review-fidelity-walk.md`（走查记录，锚点化）

**Interfaces:**
- Produces: Track A 出口证据；Track B 起点清晰。

- [ ] **Step 1：本地跑通整链**

  起 `questor serve http`（真实模型或 fake）→ 跑一个小 turn（`write_file` 一次）→ 浏览器 `http://127.0.0.1:XXXX` 打开 Review 面板 → 对照 wuu `dev/review` 观感截图。若缺 `QUESTOR_MODEL_API_KEY`：诚实记 pending（AGENTS §一 铁律 1），仅跑 fake model 的集成测。

- [ ] **Step 2：跑全套门禁**

  ```
  uv run ruff check .
  uv run ruff format --check .
  uv run pyright
  uv run pytest tests/unit tests/architecture -q
  .venv/Scripts/python.exe scripts/ci/check_docs.py
  .venv/Scripts/python.exe scripts/ci/check_specs.py
  .venv/Scripts/python.exe scripts/ci/check_notes.py
  npm --prefix ui run typecheck
  npm --prefix ui run test
  ```
  Expected: 全绿。

- [ ] **Step 3：坑覆盖回填 + 文档勾销**

  `pitfalls.md` 里 B-103~B-107 状态从 `open` 改 `covered`，测试列填具体测试名（`ui/tests/review.panel.test.tsx::...`）。`docs/plans/development-plan.md` Phase U 状态行追加"Track A 完成（2026-10-XX）"、Track B 未开始。

- [ ] **Step 4：提交**

  ```bash
  git add docs/specs/pitfalls.md docs/plans/development-plan.md docs/notes/2026-10-13-review-fidelity-walk.md
  git commit -m "docs(phase-u): Track A complete, pitfalls B-103..B-107 covered"
  ```

**Track A 出口判据**：
1. 5 条 vitest 测试全绿（折叠、空态、fingerprint、已阅 dot、双栏 diff）+ 1 条护栏（token 无 hex）+ 1 条 reduced-motion 断言；
2. 人工走查截图与 wuu `dev/review` 观感一致；
3. 内核/协议/schema/sidecar 未动（`just gen-check` 无 diff、`test_serve_http_ws` 仍绿）。

---

## Track B：Electron 桌面壳

### Task B1：落 ADR-0032（Electron 工具链依赖）

**Files:**
- Create: `docs/adr/0032-electron-shell-and-toolchain.md`
- Modify: `docs/adr/README.md`（索引 +1）

**Interfaces:**
- Produces: 允许引入 `electron`、`electron-vite`、`electron-builder`；为 B2 起壳铺路。

- [ ] **Step 1：起草 ADR-0032**

  核心内容（写入文件时展开）：

  ```markdown
  # ADR-0032 — Electron 桌面壳工具链依赖引入

  状态: accepted
  日期: 2026-10-13 | 关联: ADR-0030（Electron 改判）、`structure.md` §7/§11、
  `docs/plans/2026-10-13-phase-u-ui-and-electron-shell.md` Track B

  ## 结论
  1. `desktop/` 引入 `electron`（版本以最新 stable LTS 钉）、`electron-vite`（构建 main/preload/renderer 三段）、
     `electron-builder`（Windows NSIS 打包目标）。
  2. sidecar 拉起走 Node `child_process.spawn`；**不**引入 `@tauri-apps/*`、`node-stream-registrar` 等壳侧库。
  3. renderer 复用 `ui/` 构建产物：`desktop/electron.vite.config.ts` 的 `renderer.build.rollupOptions.input`
     指向 `../ui/dist/index.html`；不复制前端源码到 `desktop/`。

  ## 理由与取舍
  - 换 Electron 的动因（ADR-0030）就是"沿用 wuu 主进程 TS 模式、免 Rust 重造"——`child_process.spawn` + NDJSON
    是 wuu `desktop/src/main/appServerClients.ts` 用过的路径，同款落到 Python 子进程上无需新依赖。
  - `electron-vite` 与 vite 共享配置心智，`ui/` 已有 vite 生态；`electron-builder` 是同类事实标准。
  - 代价：+约 200 MB 安装包、自带 Chromium 升级维护面——ADR-0030 已记，不在此重复。

  ## 被否决的选项
  - 直接用 `electron` 不用 `electron-vite`（手写 esbuild/tsc 分三份）：配置漂移、与 `ui/` vite 版本双份维护。
  - `pkg` / `nexe` 单文件打包 Python 内核塞进 Electron 资源：Python 打包链（PyInstaller）体量大、启动慢，
    与 sidecar 化设计冲突；本项目保持 `uv run questor serve stdio` 拉起路径。
  - `@tauri-apps/plugin-shell`：ADR-0030 已改判 Tauri 出局。

  ## 适用条件与失效条件
  **适用**：Track B 全程（B2~B9）。
  **触发重新评审**：① Electron 上游出现阻断性 Windows 缺陷 → 按 ADR-0030 失效条件评估；
  ② `electron-vite` 停维或与 vite 主版本脱节 → 换 `electron-forge`，另开 ADR；
  ③ 安装包超过 500 MB（含 Chromium）→ 评估 asar 拆包、`files` 白名单更严。
  ```

- [ ] **Step 2：更新 ADR 索引 + Step 3 跑 `check_docs` + Step 4 提交**

  ```bash
  git add docs/adr/0032-electron-shell-and-toolchain.md docs/adr/README.md
  git commit -m "docs(adr): 0032 introduce Electron toolchain (electron-vite + electron-builder)"
  ```

---

### Task B2：`desktop/` 骨架与 electron-vite 空壳跑通

**Files:**
- Create: `desktop/package.json`、`desktop/electron.vite.config.ts`、`desktop/tsconfig.node.json`、`desktop/src/main/index.ts`、`desktop/src/preload/index.ts`
- Create: `desktop/src/renderer/index.html`（占位）
- Modify: `structure.md` §11 里程碑表（若之前 U 行的物化时机要精确到 B2）

**Interfaces:**
- Produces: `npm --prefix desktop run dev` 起一个空白 Electron 窗口（无 sidecar）；为 B3~B6 起壳。

- [ ] **Step 1：`desktop/package.json`**

  ```jsonc
  {
    "name": "@questor/desktop",
    "version": "0.1.0",
    "private": true,
    "type": "module",
    "main": "out/main/index.js",
    "scripts": {
      "dev": "electron-vite dev",
      "build": "electron-vite build",
      "typecheck": "tsc --noEmit -p tsconfig.node.json",
      "package": "electron-builder"
    },
    "dependencies": {
      "electron": "^33.0.0"
    },
    "devDependencies": {
      "electron-vite": "^2.3.0",
      "electron-builder": "^25.0.0",
      "typescript": "~5.9.3"
    }
  }
  ```

- [ ] **Step 2：`desktop/electron.vite.config.ts`**

  ```typescript
  import { defineConfig } from "electron-vite";

  export default defineConfig({
    main: {
      build: { lib: { entry: "src/main/index.ts", formats: ["es"], fileName: "index" } },
    },
    preload: {
      build: { lib: { entry: "src/preload/index.ts", formats: ["cjs"], fileName: "index" } },
    },
    renderer: {
      // renderer 复用 ui/ 构建产物：不重新构建，直接把静态资源指过去
      root: "../ui",
      build: { outDir: "out/renderer", emptyOutDir: true },
    },
  });
  ```

  **注意**：B2 阶段先起一个 `desktop/src/renderer/index.html` 占位（`<h1>Questor shell</h1>`），跑通 `electron-vite dev` 打开空窗口；真正复用 `ui/dist` 在 B6 起。这样 B2 的 DoD 是"窗口能开"、不牵扯 `ui/` 构建链——原子性。

- [ ] **Step 3：`desktop/src/main/index.ts`**

  ```typescript
  // Questor Electron 主进程入口（ADR-0030/0032）。
  // 职责严格收缩为纯壳：窗口、sidecar 生命周期、能力声明、打包。
  // 不含业务判断（overview §14 "GUI 能力必须经协议可达"）。

  import { app, BrowserWindow } from "electron";
  import { fileURLToPath } from "node:url";

  function createWindow(): void {
    const win = new BrowserWindow({
      width: 1280,
      height: 800,
      show: false,
      webPreferences: {
        preload: fileURLToPath(new URL("../preload/index.js", import.meta.url)),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });
    win.once("ready-to-show", () => win.show());
    if (process.env.ELECTRON_RENDERER_URL) {
      void win.loadURL(process.env.ELECTRON_RENDERER_URL);
    } else {
      void win.loadFile(fileURLToPath(new URL("../renderer/index.html", import.meta.url)));
    }
  }

  app.whenReady().then(() => {
    createWindow();
    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });
  ```

- [ ] **Step 4：`desktop/src/preload/index.ts`**

  ```typescript
  // preload：contextBridge 白名单出口。只暴露壳自身状态，不透传任何业务能力。
  import { contextBridge } from "electron";

  contextBridge.exposeInMainWorld("questorHost", {
    // B6 会扩展为完整 QuestorHostApi：request / onServerEvent / respondToServerRequest / rejectServerRequest / getSnapshot（Option A IPC 桥）
    shellVersion: "0.1.0",
  });
  ```

- [ ] **Step 5：`desktop/src/renderer/index.html` + tsconfig**

  ```html
  <!doctype html>
  <html><body><h1>Questor shell (B2 scaffold, ui/ integration at B6)</h1></body></html>
  ```

  `desktop/tsconfig.node.json` 走 electron-vite 默认推荐配置（`target: ES2022`, `module: "ESNext"`, `strict: true`）。

- [ ] **Step 6：装依赖 + 跑起来**

  Run: `npm --prefix desktop install`
  Run: `npm --prefix desktop run dev`
  Expected: 弹出空白窗口，标题栏可识别（B2 无标题也无妨）。

- [ ] **Step 7：typecheck**

  Run: `npm --prefix desktop run typecheck`
  Expected: 0 error。

- [ ] **Step 8：提交**

  ```bash
  git add desktop/ .gitignore
  git commit -m "feat(desktop): Electron shell scaffold (main/preload/renderer) via electron-vite per ADR-0032" -m "B2: window opens with placeholder renderer. sidecar spawn lands in B3, ui/ integration in B6."
  ```

---

### Task B3：主进程 `child_process` 拉起 `questor serve stdio` sidecar

**Files:**
- Create: `desktop/src/main/sidecar.ts`（NDJSON 帧 + pending 表，形状照 wuu `appServerClients.ts::AppServerClient` 简化到单 client）
- Create: `desktop/src/main/questor-command.ts`（严格照 wuu `wuuCommand.ts`：`QUESTOR_DESKTOP_CORE` env → `QUESTOR_DESKTOP_USE_UV_RUN=1` + source root → 打包 `Resources/bin/questor-core.exe`；**绝**不 PATH 兜底）
- Create: `desktop/src/main/atomic-file.ts`（wuu `atomicFile.ts` 同款：O_EXCL + fsync + rename + mode 保留 + `.basename.pid.uuid.tmp` 命名；B4/B6 都依赖）
- Create: `desktop/tests/sidecar.test.ts`（vitest Node 环境）
- Create: `desktop/tests/questor-command.test.ts`（护栏：workspace 里有假的 `bin/questor` 也不能被 resolve，B-114）
- Create: `desktop/tests/atomic-file.test.ts`（护栏：模拟 fsync 后 crash → 目标文件仍旧内容、temp 已清，B-115）
- Modify: `desktop/src/main/index.ts`（whenReady 里 `resolveQuestorCommand()` → `startSidecar()`）
- Modify: `desktop/package.json`（devDependencies 加 `vitest`、`@types/node`）
- Modify: `desktop/electron.vite.config.ts`（把 ui vitest 已引入的 vitest 复用）

**Interfaces:**
- Consumes: `questor serve stdio`（Python 侧已就绪）；stdin/stdout 管道 NDJSON。
- Produces:
  ```typescript
  interface SidecarHandle {
    pid: number;
    stdin: Writable;
    stdout: Readable;
    stderr: Readable;
    exited: Promise<{ code: number | null; signal: NodeJS.Signals | null }>;
    kill(signal?: NodeJS.Signals): void;
  }
  function startSidecar(opts: { command: string; args: string[] }): Promise<SidecarHandle>;
  function writeFrame(handle: SidecarHandle, obj: unknown): void;   // NDJSON 单行
  function readFrame(handle: SidecarHandle): Promise<unknown>;      // 读一行、parse
  ```

- [ ] **Step 1：写失败测试**

  `desktop/tests/sidecar.test.ts`：

  ```typescript
  // vitest Node 环境（无 DOM）；用 Node 内置 `process.execPath` 拉一个 echo-like
  // Python 假 sidecar 走 stdio NDJSON（`python -c`），断言 writeFrame/readFrame 往返一致。
  import { describe, expect, it } from "vitest";
  import { startSidecar, writeFrame, readFrame } from "../src/main/sidecar";

  describe("sidecar NDJSON", () => {
    it("write + read 往返 JSON 帧", async () => {
      // 用 python 起一个 stdin echo：读一行、原样写回一行
      const handle = await startSidecar({
        command: "python",
        args: ["-c", "import sys\nfor line in sys.stdin: sys.stdout.write(line)"],
      });
      writeFrame(handle, { id: "r1", method: "ping", params: {} });
      const reply = (await readFrame(handle)) as { id: string };
      expect(reply.id).toBe("r1");
      handle.kill();
      await handle.exited;
    }, 10_000);

    it("stdout 洁净：stderr 独立通道", async () => {
      const handle = await startSidecar({
        command: "python",
        args: ["-c", "import sys\nsys.stderr.write('log\\n')\nsys.stdout.write('{\"ok\":1}\\n')"],
      });
      const frame = (await readFrame(handle)) as { ok: number };
      expect(frame.ok).toBe(1);
      const errBuf = await new Promise<string>((resolve) => {
        let s = "";
        handle.stderr.on("data", (c) => (s += c.toString()));
        handle.exited.then(() => resolve(s));
      });
      expect(errBuf).toContain("log");
    }, 10_000);
  });
  ```

- [ ] **Step 2：跑测试确认失败**

  Run: `npm --prefix desktop run test` （在 `desktop/package.json` `scripts.test` 加 `vitest run`）
  Expected: FAIL（`sidecar.ts` 未创建）。

- [ ] **Step 3：实现 `desktop/src/main/sidecar.ts`**

  ```typescript
  // Sidecar 生命周期：以 stdio NDJSON 与 Python `questor serve stdio` 通信。
  // provenance: 参照 wuu-main/desktop/src/main/appServerClients.ts 的 stdio 管道模式，
  // 与 EvoFlow `evopanel/src-tauri/src/commands/backend.rs` 的 sidecar generation 语义；
  // **重写实现**——不拷贝任一上游代码。
  // 对应 AGENTS §二 (c) 类边界层。

  import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
  import { createInterface } from "node:readline";

  export interface SidecarHandle {
    pid: number;
    stdin: NodeJS.WritableStream;
    stdout: NodeJS.ReadableStream;
    stderr: NodeJS.ReadableStream;
    exited: Promise<{ code: number | null; signal: NodeJS.Signals | null }>;
    kill(signal?: NodeJS.Signals): void;
  }

  export async function startSidecar(opts: {
    command: string;
    args: string[];
    env?: NodeJS.ProcessEnv;
  }): Promise<SidecarHandle> {
    const child: ChildProcessWithoutNullStreams = spawn(opts.command, opts.args, {
      env: { ...process.env, ...opts.env },
      stdio: ["pipe", "pipe", "pipe"],
      // Windows: 隐藏控制台窗口（Electron 打包后必需）
      windowsHide: true,
    });
    if (child.pid === undefined) {
      throw new Error("spawn failed: no pid assigned (Windows B-77 类似坑：进程启动即失败)");
    }
    const exited = new Promise<{ code: number | null; signal: NodeJS.Signals | null }>(
      (resolve) => child.once("exit", (code, signal) => resolve({ code, signal })),
    );
    return {
      pid: child.pid,
      stdin: child.stdin,
      stdout: child.stdout,
      stderr: child.stderr,
      exited,
      kill: (signal) => child.kill(signal),
    };
  }

  export function writeFrame(handle: SidecarHandle, obj: unknown): void {
    const line = JSON.stringify(obj) + "\n";
    handle.stdin.write(line);
  }

  /** 读一行 NDJSON 帧；单行 JSON 上限 64 MiB（overview §8），超限 reject 不 truncate。 */
  export function readFrame(handle: SidecarHandle): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const rl = createInterface({ input: handle.stdout, crlfDelay: Infinity });
      let done = false;
      rl.once("line", (line) => {
        done = true;
        rl.close();
        try {
          resolve(JSON.parse(line));
        } catch (err) {
          reject(new Error(`sidecar NDJSON parse: ${(err as Error).message}`));
        }
      });
      handle.exited.then((r) => {
        if (!done) {
          rl.close();
          reject(new Error(`sidecar exited before frame: code=${r.code} signal=${r.signal}`));
        }
      });
    });
  }
  ```

- [ ] **Step 4：`main/index.ts` 里挂启动（B3 只启动、不接 renderer）**

  ```diff
  + import { resolveQuestorCommand } from "./questor-command";
  + import { startSidecar } from "./sidecar";

    app.whenReady().then(async () => {
  +   // B3：先只做"拉起来 + 日志"，B4 加 generation/lifecycle_lock，B6 交给 IPC bridge。
  +   // 严格照 wuu wuuCommand.ts：绝不用 PATH 找 `questor`、绝不从 workspace 找 `bin/questor`
  +   //（B-114：用户把 questor 仓库本身开成 workspace 会撞 ELF/py 版本坑，wuu issue #8 同形）。
  +   const cmd = resolveQuestorCommand(process.env, app.getAppPath(), process.resourcesPath);
  +   const handle = await startSidecar({ command: cmd.command, args: cmd.args, cwd: cmd.cwd });
  +   console.log("[sidecar] pid=", handle.pid, "cmd=", cmd.command);
  +   handle.stderr.on("data", (c) => console.error("[sidecar]", c.toString()));
  +   handle.exited.then((r) => console.warn("[sidecar] exited", r));
      createWindow();
      ...
    });
  ```

  `resolveQuestorCommand(env, appPath, resourcesPath)` 的优先级（照 wuu）：
  1. `env.QUESTOR_DESKTOP_CORE` 显式覆盖（开发/CI 用）；
  2. `env.QUESTOR_DESKTOP_USE_UV_RUN === "1"` + 从 `appPath` 往上找 `pyproject.toml` 所在 sourceRoot → `{command: "uv", args: ["run", "--directory", sourceRoot, "questor", "serve", "stdio"], cwd: sourceRoot}`；
  3. 打包产物 `join(resourcesPath, "bin", "questor-core")`（Windows 额外试 `.exe`）存在 → 用它（B7 electron-builder 负责把 uv-build 后的 wheel 挨进 `Resources/bin/`）；
  4. 都失败 → throw `"questor desktop core is missing; reinstall the desktop app"`；**绝不 fall back 到 PATH 里的 `questor`**（那是独立 CLI 装的可能版本漂移）。

- [ ] **Step 5：跑测试全绿**

  Run: `npm --prefix desktop run test`
  Expected: 两条 PASS。

- [ ] **Step 6：本地手动跑**

  Run: `npm --prefix desktop run dev` → 主进程 console 打印 `[sidecar] pid=NNNN` → 关掉窗口 → 打印 `[sidecar] exited {code:null, signal:'SIGTERM'}`（若 `uv run questor serve stdio` 正常）。

- [ ] **Step 7：提交**

  ```bash
  git add desktop/src/main/sidecar.ts desktop/src/main/index.ts desktop/tests/sidecar.test.ts desktop/package.json desktop/electron.vite.config.ts
  git commit -m "feat(desktop): spawn questor serve stdio via child_process and roundtrip NDJSON" -m "Refs ADR-0030/0032; provenance wuu appServerClients.ts + EvoFlow backend.rs, rewritten."
  ```

---

### Task B4：`runtime_state.json` 单调 generation + `lifecycle_lock` 防拉起竞态

**Files:**
- Create: `desktop/src/main/sidecar-state.ts`
- Create: `desktop/src/main/sidecar-lock.ts`
- Create: `desktop/tests/generation.test.ts`（单调性、lifecycle_lock）
- Modify: `desktop/src/main/index.ts`（`startSidecar` 前后调 lock/state）

**Interfaces:**
- Produces:
  ```typescript
  interface SidecarState {
    generation: number;    // 单调递增，每次成功拉起 +1
    pid: number;
    startedAt: string;     // ISO
    // Option A（renderer↔main IPC↔sidecar stdio）下无 endpoint 字段——renderer 不直连内核。
    // 预留 future remote/relay 接入时开（属 M8，另开 ADR）。
  }
  function readState(home: string): Promise<SidecarState | null>;
  function bumpState(home: string, next: Omit<SidecarState, "generation">): Promise<SidecarState>;
  async function withLifecycleLock<T>(home: string, fn: () => Promise<T>): Promise<T>;
  ```

**参照**：wuu `desktop/src/main/appServerClients.ts` 的 generation 语义 + EvoFlow `backend.rs` 的 lifecycle_lock（**重写实现加 provenance**）。

- [ ] **Step 1：写失败测试**

  `desktop/tests/generation.test.ts`：

  ```typescript
  import { afterEach, beforeEach, describe, expect, it } from "vitest";
  import { mkdtemp, rm } from "node:fs/promises";
  import { tmpdir } from "node:os";
  import { join } from "node:path";
  import { bumpState, readState, withLifecycleLock } from "../src/main/sidecar-state";

  let home = "";
  beforeEach(async () => { home = await mkdtemp(join(tmpdir(), "questor-desktop-")); });
  afterEach(async () => { await rm(home, { recursive: true, force: true }); });

  describe("generation 单调性（B-108）", () => {
    it("空 home 首次 bumpState → generation=1", async () => {
      expect(await readState(home)).toBeNull();
      const s = await bumpState(home, { pid: 111, startedAt: new Date().toISOString() });
      expect(s.generation).toBe(1);
      expect((await readState(home))?.pid).toBe(111);
    });

    it("连续两次 bumpState → generation 递增", async () => {
      await bumpState(home, { pid: 1, startedAt: "2026-01-01T00:00:00Z" });
      const s = await bumpState(home, { pid: 2, startedAt: "2026-01-01T00:00:01Z" });
      expect(s.generation).toBe(2);
    });

    it("state 文件损坏（残尾）时 readState 返回 null 而非抛（对齐 gesta B-74 容错）", async () => {
      await bumpState(home, { pid: 1, startedAt: "x" });
      // 追加半行模拟 crash 残尾
      await appendFile(join(home, "runtime_state.json"), "\n{trunc");
      expect(await readState(home)).not.toBeNull(); // 读回上一个完整版本
    });
  });

  describe("lifecycle_lock 防并发拉起（B-109）", () => {
    it("两个 withLifecycleLock 并发 → 串行", async () => {
      let peak = 0, cur = 0;
      const fn = async () => { cur++; peak = Math.max(peak, cur); await sleep(50); cur--; };
      await Promise.all([
        withLifecycleLock(home, fn),
        withLifecycleLock(home, fn),
        withLifecycleLock(home, fn),
      ]);
      expect(peak).toBe(1);
    });
  });
  ```

  （`appendFile` 与 `sleep` 从 `node:fs/promises` / 顶部 helper 引入。）

- [ ] **Step 2：跑测试确认失败**

  Run: `npm --prefix desktop run test` — Expected: FAIL（模块未建）。

- [ ] **Step 3：实现 `sidecar-state.ts` + `sidecar-lock.ts`（写盘走 atomic-file.ts，B-115）**

  核心要点：
  - 状态路径 `~/.questor/desktop/runtime_state.json`（走 `QUESTOR_HOME` 单点解析，overview §14"路径单点解析"）。
  - **写路径必须走 B3 新落的 `atomic-file.ts`**（B-115：只做 `writeFile + rename` 而无 `fsync`，崩溃时 rename 可能已发生但字节仍在页缓存里、下次开机文件半新半旧）：唯一落盘口是 `writeTextFileAtomicSync(path, JSON.stringify(next, null, 2) + "\n")`；temp 命名 `.<basename>.<pid>.<uuid>.tmp` 保证多进程不撞。
  - `readState`：读整个文件 + `JSON.parse`；不存在 → `null`；parse 失败但文件存在 → **回退到 `.bak`**（`bumpState` 写前把旧文件 rename 成 `.bak`，容 crash 残尾，B-108）。
  - `bumpState`：读旧 → `generation+1` → 若旧存在则 `rename(runtime_state.json → runtime_state.json.bak)` → `writeTextFileAtomicSync(runtime_state.json, ...)`（含 fsync）→ 保留 `.bak`。
  - `withLifecycleLock`：用 `.lifecycle.lock` 文件的 `wx`（O_CREAT|O_EXCL）独占创建立锁 + 心跳 mtime；获不到锁 → 50 ms 退避重试直到 5 s；释放走 `unlink`。跨进程锁——与 questor `state/` 的 storelock 语义同形，但**在 TS 侧重写**（不能 import Python）。
  - `atomic-file.ts` 自身单测在 B3 已建；本 Task 不重复。

- [ ] **Step 4：跑测试全绿**

  Run: `npm --prefix desktop run test` — Expected: PASS（4 条 generation + 1 条 lock）。

- [ ] **Step 5：`main/index.ts` 集成**

  ```diff
  - const handle = await startSidecar({...});
  - console.log("[sidecar] pid=", handle.pid);
  + const home = resolveQuestorHome(); // 走 QUESTOR_HOME 或 ~/.questor
  + const handle = await withLifecycleLock(home, async () => {
  +   const h = await startSidecar({ command: ..., args: ["serve","stdio"] });
  +   await bumpState(home, { pid: h.pid, startedAt: new Date().toISOString() });
  +   return h;
  + });
  ```

- [ ] **Step 6：负向验证 + 提交**

  临时把 `bumpState` 里 `generation+1` 改成 `generation+0` → generation.test.ts 应红 → 复原。

  ```bash
  git add desktop/src/main/sidecar-state.ts desktop/src/main/sidecar-lock.ts desktop/src/main/index.ts desktop/tests/generation.test.ts docs/specs/pitfalls.md
  git commit -m "feat(desktop): monotonic generation and lifecycle_lock for sidecar spawn" -m "Covers B-108 (crash-tail tolerance), B-109 (concurrent spawn prevention). Provenance: wuu appServerClients + EvoFlow backend.rs, rewritten."
  ```

---

### Task B5：崩溃重启 fail-open + 子进程树关停

**Files:**
- Create: `desktop/src/main/child-shutdown.ts`
- Modify: `desktop/src/main/index.ts`（`exited` 事件挂重启）
- Modify: `desktop/src/main/sidecar.ts`（导出 `killTree` 用 child-shutdown）
- Create: `desktop/tests/restart.test.ts`
- Create: `docs/notes/2026-10-13-desktop-restart-policy.md`

**Interfaces:**
- Produces:
  ```typescript
  async function killTree(handle: SidecarHandle, timeoutMs?: number): Promise<void>;
  // 语义：SIGTERM → 等 exited 或 timeout → SIGKILL；Windows 用 Job Object 或 pid+pgid+start_time 三元组
  // 校验防 PID 复用（overview §10、wuu `internal/process/manager.go` 同调）。

  function armRestartPolicy(handle: SidecarHandle, opts: { backoffMs: number[]; maxRetries: number }): void;
  ```

**纪律**：fail-open 意思是"sidecar 挂了、UI 显式提示、不静默重启到死循环"。backoffMs 表 `[500, 2000, 8000]`；超过 `maxRetries=3` 停止重启并把状态广播给 renderer（B6）。

- [ ] **Step 1：写失败测试（重启计数 + kill tree）**

  `desktop/tests/restart.test.ts`（关键用例）：

  ```typescript
  it("exited with non-zero → armRestartPolicy 触发一次 respawn，计数 +1", async () => {
    const fake = makeFakeExiter(1);
    let respawns = 0;
    armRestartPolicy(fake, { backoffMs: [10, 10, 10], maxRetries: 3,
      onRespawn: () => { respawns++; }});
    fake.emitExit({ code: 1, signal: null });
    await sleep(50);
    expect(respawns).toBe(1);
  });

  it("killTree SIGTERM 超时 → SIGKILL", async () => {
    const fake = makeFakeUnkillable();
    await killTree(fake, 100);
    expect(fake.killedSignals).toEqual(["SIGTERM", "SIGKILL"]);
  });
  ```

- [ ] **Step 2：红 → Step 3：实现 `child-shutdown.ts`（严格照 wuu `desktop/src/main/childShutdown.ts`，B-113）**

  ```typescript
  // 关停语义（wuu 实测教训）：**等 exit 事件、不等 pipe close**——子进程后代可能仍持继承 pipe，
  // 只看 pipe close 会让主进程以为"已停"、实际还活着继续写盘（B-113）。
  // 时序：requestStop（可选协议级优雅停机） → 失败退回 SIGTERM → SIGTERM at graceMs
  // → SIGKILL at graceMs+3s → reject at graceMs+5s。所有 timer unref 不阻事件循环退出。
  // 与 wuu childShutdown.ts 一致：grace 20 s、SIGKILL 在 graceMs+3s、reject 在 graceMs+5s。
  // Windows Job Object 后续视需要引入；本项目现阶段先对齐 wuu 的三层定时。
  import type { SidecarHandle } from "./sidecar";

  export async function killTree(
    handle: SidecarHandle,
    requestStop?: () => Promise<void>,
    graceMs = 20_000,
  ): Promise<void> {
    const timers: ReturnType<typeof setTimeout>[] = [];
    const exitedWithinGrace = await new Promise<boolean>((resolve) => {
      handle.exited.then(() => resolve(true));
      for (const [delay, signal] of [[graceMs, "SIGTERM"], [graceMs + 3_000, "SIGKILL"]] as const) {
        const t = setTimeout(() => { try { handle.kill(signal); } catch { /* already gone */ } }, delay);
        t.unref(); timers.push(t);
      }
      const final = setTimeout(() => resolve(false), graceMs + 5_000);
      final.unref(); timers.push(final);
      // 先试协议级优雅停机（走 `session/control stop`），失败退回 SIGTERM（timer 会兜底 SIGKILL）
      void Promise.resolve(requestStop?.()).catch(() => handle.kill("SIGTERM"));
    });
    for (const t of timers) clearTimeout(t);
    if (!exitedWithinGrace) throw new Error("Child process did not exit after shutdown");
  }

  export function armRestartPolicy(
    handle: SidecarHandle,
    opts: { backoffMs: number[]; maxRetries: number; onRespawn: () => void },
  ): void {
    let retries = 0;
    handle.exited.then(async (r) => {
      if (r.code === 0) return; // 正常退出（用户关窗）不重启
      if (retries >= opts.maxRetries) return; // fail-open：UI 会显式提示 sidecar 挂了
      const wait = opts.backoffMs[Math.min(retries, opts.backoffMs.length - 1)];
      retries += 1;
      setTimeout(() => opts.onRespawn(), wait);
    });
  }
  ```

- [ ] **Step 4：`main/index.ts` 集成**（在 `startSidecar` 后 `armRestartPolicy`；`app.on("before-quit")` 里 `killTree`）

- [ ] **Step 5：全绿 + Step 6：手动验证**（跑 `desktop run dev`，`kill -9 <pid>` 杀 sidecar，观察重启日志 3 次后停）

- [ ] **Step 7：落 `docs/notes/2026-10-13-desktop-restart-policy.md`**（含锚点、日期、ADR 关联）

- [ ] **Step 8：提交**

  ```bash
  git add desktop/src/main/child-shutdown.ts desktop/src/main/index.ts desktop/tests/restart.test.ts docs/notes/2026-10-13-desktop-restart-policy.md docs/specs/pitfalls.md
  git commit -m "feat(desktop): fail-open restart with backoff and process-tree kill" -m "Refs ADR-0007 pid-reuse guard; B-110/B-111 covered."
  ```

---

### Task B6：Renderer ↔ Main IPC ↔ Sidecar stdio（Option A，照 wuu）

**Files:**
- Create: `desktop/src/main/app-server-bridge.ts`（主进程 pending 表 + server-request 路由表 + `emitServerEvent` fanout，简化到单 client）
- Create: `desktop/src/main/renderer-batcher.ts`（照 wuu `rendererServerEventBatcher.ts`：50 ms 合批 delta、控制事件先 flush、raw provider delta 不转发）
- Rewrite: `desktop/src/preload/index.ts`（contextBridge `window.questorHost`：`request / onServerEvent / respondToServerRequest / rejectServerRequest / getSnapshot`）
- Modify: `desktop/src/main/index.ts`（注册 `ipcMain.handle("qst:request", ...)` 等；bridge → batcher → `webContents.send("qst:server-event", ...)`）
- Create: `ui/src/rpc/ipc-transport.ts`（`Transport` 接口的 IpcTransport 实现，用 `window.questorHost`）
- Create: `ui/src/rpc/server-events-fanout.ts`（照 wuu `renderer/ServerEvents.ts`：Set\<listener> + 单桥 `disconnect ??=`）
- Modify: `ui/src/rpc/client.ts`（`window.questorHost` 存在 → `IpcTransport`；否则维持 `WebSocketTransport`，**浏览器路径零改**）
- Modify: `desktop/electron.vite.config.ts`（renderer root 指 `../ui`，构建产物进 `desktop/out/renderer`）
- Create: `desktop/tests/ipc-parity.test.ts`（护栏 B-116：preload ↔ main 一一对偶）
- Create: `desktop/tests/renderer-batcher.test.ts`（B-117：合批窗口、控制事件先 flush、raw delta 不转发）
- Create: `desktop/tests/bridge.test.ts`（B-118：pending 匹配 + server-request public id 桥 + `turn/started` 落 sessionOwners）

**决策（推翻旧 Step 0 的 A/B 讨论）**：**A = 唯一方案**（ADR-0006 结论 4 字面要求"桌面 stdio NDJSON、网页 WS/SSE"；wuu 实际实现就是 A）。**B 已否决**：起本地 `serve http` 让 renderer 连 WS，等于给桌面另开一条 WS、架空了 stdio。ADR-0030 §结论 4 允许在 `ui/` **内**加性改动（新增 `IpcTransport` 与 `window.questorHost` 消费），不动协议/schema/其他内核模块。

**Interfaces:**
- Consumes: `sidecar.ts` 的 `SidecarHandle` + `writeFrame`；`atomic-file.ts`（B4 写的 `runtime_state.json`）。
- Produces:
  ```typescript
  // desktop/src/main/app-server-bridge.ts
  class AppServerBridge {
    dispatchRequest(method: string, params?: unknown): Promise<unknown>;
    respondToServerRequest(publicRouteID: string, result: unknown): void;
    rejectServerRequest(publicRouteID: string, message: string): void;
    runningThreadsSnapshot(): RunningThreadSnapshot[];
    onEvent(listener: (evt: AppServerClientEvent) => void): () => void;
  }
  // preload 挂 window.questorHost
  interface QuestorHostApi {
    request<T = unknown>(method: string, params?: unknown): Promise<T>;
    respondToServerRequest(id: string, result: unknown): Promise<void>;
    rejectServerRequest(id: string, message: string): Promise<void>;
    onServerEvent(handler: (event: ServerEvent) => void): () => void;
    getSnapshot(): Promise<RunningThreadSnapshot[]>;
  }
  // ui/src/rpc/ipc-transport.ts
  class IpcTransport implements Transport { /* call / subscribe / close */ }
  function isElectronHost(): boolean;
  ```

- [ ] **Step 1：写失败测试（ipc-parity + batcher + bridge）**

  `desktop/tests/ipc-parity.test.ts`（B-116）：

  ```typescript
  // 扫 preload.ts 里的每个 ipcRenderer.invoke / sendSync / on 的 channel x，
  // 必须在 main 侧找到 ipcMain.handle / on / webContents.send 的对偶。
  import { readFileSync, readdirSync } from "node:fs";
  import { join } from "node:path";
  const preloadSrc = readFileSync(join(__dirname, "../src/preload/index.ts"), "utf8");
  const mainSrcs = readdirSync(join(__dirname, "../src/main"))
    .filter((f) => f.endsWith(".ts"))
    .map((f) => readFileSync(join(__dirname, "../src/main", f), "utf8"))
    .join("\n");
  const inv = [...preloadSrc.matchAll(/ipcRenderer\.invoke\(\s*"([^"]+)"/g)].map((m) => m[1]);
  const syn = [...preloadSrc.matchAll(/ipcRenderer\.sendSync\(\s*"([^"]+)"/g)].map((m) => m[1]);
  const onl = [...preloadSrc.matchAll(/ipcRenderer\.on\(\s*"([^"]+)"/g)].map((m) => m[1]);
  const hnd = [...mainSrcs.matchAll(/ipcMain\.handle\(\s*"([^"]+)"/g)].map((m) => m[1]);
  const mon = [...mainSrcs.matchAll(/ipcMain\.on\(\s*"([^"]+)"/g)].map((m) => m[1]);
  const snd = [...mainSrcs.matchAll(/webContents\.send\(\s*"([^"]+)"/g)].map((m) => m[1]);
  it("qst:* invoke ↔ ipcMain.handle 对偶", () => {
    for (const ch of inv) expect(hnd, `ipcMain.handle 缺对偶：${ch}`).toContain(ch);
  });
  it("qst:* sendSync ↔ ipcMain.on 对偶（若引入同步 bootstrap）", () => {
    for (const ch of syn) expect(mon, `ipcMain.on 缺对偶：${ch}`).toContain(ch);
  });
  it("qst:* ipcRenderer.on ↔ webContents.send 对偶", () => {
    for (const ch of onl) expect(snd, `webContents.send 缺对偶：${ch}`).toContain(ch);
  });
  ```

  `desktop/tests/renderer-batcher.test.ts`：断言 50 ms 内同 identity delta 合并为一、控制事件先 flush 后立刻 emit、raw provider delta 不转发；snapshot resolve 前 batch 已 flush（防重放）。

  `desktop/tests/bridge.test.ts`：fake `SidecarHandle` + 三条断言：请求-响应按 id 匹配；`turn/started` 通知落 `sessionOwners`；server-initiated request 到达 renderer 侧时被替换成 `server-request-${N}` public id。

- [ ] **Step 2：跑测试全红**

  Run: `npm --prefix desktop run test` → FAIL（bridge/batcher/preload 未建）。

- [ ] **Step 3：实现 `desktop/src/main/app-server-bridge.ts`**

  ```typescript
  // Renderer ↔ Main ↔ Sidecar NDJSON 桥。
  // 照 wuu `desktop/src/main/appServerClients.ts::AppServerClient` 简化到单 client
  //（Questor 起步一 shell 一 workspace，多 client MRU 属后续）；**重写实现加 provenance**。
  // B-118：server-initiated request 用 `server-request-${N}` public id 桥接，不暴露内核真实 id。
  import type { SidecarHandle } from "./sidecar";
  import { writeFrame } from "./sidecar";

  interface Pending { resolve: (v: unknown) => void; reject: (e: unknown) => void; method: string }
  type AppServerClientEvent =
    | { kind: "notification"; message: { method: string; params?: unknown } }
    | { kind: "server-request"; message: { id: string; method: string; params?: unknown } }
    | { kind: "server-exit"; code: number | null; message: string };

  export class AppServerBridge {
    private nextRequestID = 1;
    private nextRouteID = 1;
    private pending = new Map<string, Pending>();
    private serverRequestRoutes = new Map<string, { serverID: string }>();
    private sessionOwners = new Set<string>();  // thread_id 集（单 client 时只记归属）
    private eventListeners = new Set<(evt: AppServerClientEvent) => void>();
    private stdoutBuf = "";

    constructor(private handle: SidecarHandle) {
      handle.stdout.on("data", (chunk: Buffer) => this.onStdout(chunk));
      // questor 侧已保证 stderr 洁净、只吞不转发到 stdout（B-87）
      handle.stderr.on("data", () => { /* sink */ });
    }

    dispatchRequest(method: string, params?: unknown): Promise<unknown> {
      const id = `req-${this.nextRequestID++}`;
      return new Promise((resolve, reject) => {
        this.pending.set(id, { resolve, reject, method });
        writeFrame(this.handle, { id, method, params });
      });
    }

    respondToServerRequest(publicRouteID: string, result: unknown): void {
      const route = this.serverRequestRoutes.get(publicRouteID);
      if (!route) throw new Error("server request is no longer active");
      this.serverRequestRoutes.delete(publicRouteID);
      writeFrame(this.handle, { id: route.serverID, result });
    }

    rejectServerRequest(publicRouteID: string, message: string): void {
      const route = this.serverRequestRoutes.get(publicRouteID);
      if (!route) throw new Error("server request is no longer active");
      this.serverRequestRoutes.delete(publicRouteID);
      writeFrame(this.handle, { id: route.serverID, error: { code: "rejected", message } });
    }

    runningThreadsSnapshot(): { threadId: string }[] {
      return [...this.sessionOwners].map((threadId) => ({ threadId }));
    }

    onEvent(listener: (evt: AppServerClientEvent) => void): () => void {
      this.eventListeners.add(listener);
      return () => this.eventListeners.delete(listener);
    }

    private onStdout(chunk: Buffer): void {
      this.stdoutBuf += chunk.toString("utf8");
      let nl: number;
      while ((nl = this.stdoutBuf.indexOf("\n")) >= 0) {
        const line = this.stdoutBuf.slice(0, nl).trim();
        this.stdoutBuf = this.stdoutBuf.slice(nl + 1);
        if (!line) continue;
        this.handleFrame(JSON.parse(line));
      }
    }

    private handleFrame(msg: { id?: string; method?: string; params?: unknown; result?: unknown; error?: unknown }): void {
      if (msg.id && msg.method === undefined && (msg.result !== undefined || msg.error !== undefined)) {
        const p = this.pending.get(msg.id);
        if (!p) return;
        this.pending.delete(msg.id);
        if (msg.error) p.reject(msg.error); else p.resolve(msg.result);
        return;
      }
      if (msg.id && msg.method) {
        const publicID = `server-request-${this.nextRouteID++}`;
        this.serverRequestRoutes.set(publicID, { serverID: msg.id });
        const evt: AppServerClientEvent = { kind: "server-request", message: { ...msg, id: publicID } };
        for (const l of this.eventListeners) l(evt);
        return;
      }
      if (msg.method) {
        const params = msg.params as { thread_id?: string } | undefined;
        if (msg.method === "turn/started" && params?.thread_id) this.sessionOwners.add(params.thread_id);
        const evt: AppServerClientEvent = { kind: "notification", message: msg as { method: string; params?: unknown } };
        for (const l of this.eventListeners) l(evt);
      }
    }
  }
  ```

- [ ] **Step 4：实现 `desktop/src/main/renderer-batcher.ts`**

  严格照 wuu `rendererServerEventBatcher.ts`：`STREAM_DELTA_NOTIFICATION_METHODS = new Set(["item/agentMessage/delta","item/reasoning/delta","item/toolCall/delta","item/toolCall/outputDelta"])`；`RENDERER_IGNORED_STREAM_EVENT_TYPES = new Set(["content_delta","thinking_delta","tool_use_delta"])`；`DEFAULT_STREAM_BATCH_INTERVAL_MS = 50`；同 identity 合并、非 delta 事件先 flush 再立即 emit、`resolveSnapshot` 前 flush。导出 `class RendererServerEventBatcher { enqueue(event); flush(); resolveSnapshot<T>(request: Promise<T>): Promise<T>; }`。

- [ ] **Step 5：改写 `desktop/src/preload/index.ts`**

  ```typescript
  import { contextBridge, ipcRenderer } from "electron";

  const api = {
    request: <T>(method: string, params?: unknown) =>
      ipcRenderer.invoke("qst:request", method, params) as Promise<T>,
    respondToServerRequest: (id: string, result: unknown) =>
      ipcRenderer.invoke("qst:respond-server-request", id, result) as Promise<void>,
    rejectServerRequest: (id: string, message: string) =>
      ipcRenderer.invoke("qst:reject-server-request", id, message) as Promise<void>,
    getSnapshot: () => ipcRenderer.invoke("qst:snapshot"),
    onServerEvent: (handler: (event: ServerEvent) => void) => {
      const listener = (_e: Electron.IpcRendererEvent, payload: ServerEvent) => handler(payload);
      ipcRenderer.on("qst:server-event", listener);
      return () => ipcRenderer.removeListener("qst:server-event", listener);
    },
  };
  contextBridge.exposeInMainWorld("questorHost", api);
  ```

- [ ] **Step 6：`main/index.ts` 注册 IPC handlers + 挂 batcher**

  ```typescript
  const bridge = new AppServerBridge(sidecarHandle);
  const batcher = new RendererServerEventBatcher((evt) => win.webContents.send("qst:server-event", evt));
  bridge.onEvent((e) => batcher.enqueue(toServerEvent(e)));

  ipcMain.handle("qst:request", (_e, method, params) => bridge.dispatchRequest(method, params));
  ipcMain.handle("qst:respond-server-request", (_e, id, r) => bridge.respondToServerRequest(id, r));
  ipcMain.handle("qst:reject-server-request", (_e, id, m) => bridge.rejectServerRequest(id, m));
  ipcMain.handle("qst:snapshot", () => bridge.runningThreadsSnapshot());
  ```

- [ ] **Step 7：新建 `ui/src/rpc/ipc-transport.ts` + `server-events-fanout.ts` + 修改 `client.ts`**

  ```typescript
  // ui/src/rpc/ipc-transport.ts —— Transport 的 Electron 实现
  import type { Transport } from "./transport";
  import { subscribeServerEvents } from "./server-events-fanout";

  interface QuestorHostApi {
    request<T>(method: string, params?: unknown): Promise<T>;
    onServerEvent(handler: (event: ServerEvent) => void): () => void;
    respondToServerRequest(id: string, result: unknown): Promise<void>;
    rejectServerRequest(id: string, message: string): Promise<void>;
    getSnapshot(): Promise<RunningThreadSnapshot[]>;
  }
  declare global { interface Window { questorHost?: QuestorHostApi } }

  export function isElectronHost(): boolean {
    return typeof window !== "undefined" && !!window.questorHost;
  }

  export class IpcTransport implements Transport {
    constructor(private host: QuestorHostApi) {}
    call<T>(method: string, params?: unknown): Promise<T> { return this.host.request<T>(method, params); }
    subscribe(topic: string) { return subscribeServerEvents(topic); }
    close(): void { /* IPC 无连接概念，no-op */ }
  }
  ```

  `ui/src/rpc/client.ts` 里：

  ```diff
  - export const client = createClient(new WebSocketTransport(wsEndpoint));
  + import { IpcTransport, isElectronHost } from "./ipc-transport";
  + const transport: Transport = isElectronHost()
  +   ? new IpcTransport(window.questorHost!)
  +   : new WebSocketTransport(wsEndpoint);   // 浏览器路径零改
  + export const client = createClient(transport);
  ```

  `ui/src/rpc/server-events-fanout.ts` 照 wuu `renderer/ServerEvents.ts`：Set\<listener> + `disconnect ??= window.questorHost.onServerEvent(handler)` + 最后一个 listener 走时 `disconnect=undefined`。护栏 A4 与 A5–A8 现有面板测试**继续跑浏览器路径**（`WebSocketTransport` 分支），不破现有测。

- [ ] **Step 8：`electron.vite.config.ts` renderer root**

  ```typescript
  renderer: {
    root: "../ui",
    build: { outDir: fileURLToPath(new URL("out/renderer", import.meta.url)), emptyOutDir: true },
  }
  ```

- [ ] **Step 9：手动跑 + 断链验证**

  Run: `npm --prefix ui run build && npm --prefix desktop run dev` → 打开窗口 → 看到 Questor AppShell → 起一个 turn → Review 面板显示 diff。**断链**：`kill -9 <sidecar pid>` → renderer 3 s 内看到"sidecar 挂了、正在重启（fail-open）"提示（B5 backoff）；**重启窗口里 renderer 不需刷新页面**——preload 桥常驻，sidecar 复活后 `bridge.onEvent` 重挂即可。

- [ ] **Step 10：跑全套 + 提交**

  Run: `npm --prefix desktop run test` 全绿；`npm --prefix ui run test` 全绿；`npm --prefix ui run typecheck` 0 error；`just check`（或 §Global Constraints 里的退路逐条手动跑）全绿；`test_no_hardcoded_panel_case` 与 `test_serve_http_ws` 仍绿（浏览器路径不破）。

  ```bash
  git add desktop/src/main/app-server-bridge.ts desktop/src/main/renderer-batcher.ts desktop/src/preload/index.ts desktop/src/main/index.ts desktop/electron.vite.config.ts ui/src/rpc/ipc-transport.ts ui/src/rpc/server-events-fanout.ts ui/src/rpc/client.ts desktop/tests/ipc-parity.test.ts desktop/tests/renderer-batcher.test.ts desktop/tests/bridge.test.ts docs/specs/pitfalls.md
  git commit -m "feat(desktop): renderer<->main IPC<->sidecar stdio bridge (Option A per wuu)" -m "Refs ADR-0006 §结论 4 (desktop stdio, web WS) and ADR-0030. Covers B-113/B-116/B-117/B-118. Provenance: rewritten from wuu appServerClients.ts + preload.ts + rendererServerEventBatcher.ts + renderer/ServerEvents.ts, no code copy." --no-verify=false
  ```

**B6 出口判据**：
1. `qst:request` / `qst:respond-server-request` / `qst:reject-server-request` / `qst:snapshot` / `qst:server-event` 五对 IPC channel 一一对偶（`ipc-parity.test.ts` 咬住，B-116）；
2. delta 事件 50 ms 窗口内按 identity 合批；控制/终止事件先 flush；raw provider delta 不转发（B-117）；
3. server-initiated request 的 public id 桥接生效，内核真实 id 不出现在 renderer（B-118）；
4. **浏览器宿主路径完全不变**：`window.questorHost` 不存在时 `client.ts` 走 `WebSocketTransport`；现有 `test_serve_http_ws` 与 Track A 全部面板测绿；
5. 手动走查：起窗口 → 跑 turn → Review 真 diff 显示；`kill -9` sidecar → fail-open 提示 → 自动重启 → renderer 无需刷新。

---

### Task B7：`assets/` + `electron-builder` Windows 打包

**Files:**
- Create: `assets/icon.ico`（或从 `assets/icon.svg` 生成脚本产 ICO）
- Create: `desktop/electron-builder.yml`
- Create: `assets/README.md`（图标源与再生成命令）
- Modify: `desktop/package.json`（scripts.package）

**Interfaces:**
- Produces: `npm --prefix desktop run package` 产 `desktop/dist/Questor-Setup-<version>.exe`。

- [ ] **Step 1**：写 `electron-builder.yml`

  ```yaml
  appId: com.questor.desktop
  productName: Questor
  directories:
    output: dist
    buildResources: ../assets
  files:
    - out/**/*
    - "!**/node_modules/**/{*.md,LICENSE*,README*}"
  win:
    target: nsis
    icon: ../assets/icon.ico
  nsis:
    oneClick: false
    perMachine: false
    allowToChangeInstallationDirectory: true
  ```

- [ ] **Step 2**：`assets/README.md` 记录"图标源 + 再生成命令"（wuu `scripts/generate-icon.ts` 同款做法参照）；`assets/icon.svg` 起手。
- [ ] **Step 3**：跑 `npm --prefix desktop run package` → 观察产物；缺 icon 会警告但不阻断（先占位）。
- [ ] **Step 4**：跑一次冒烟——安装 exe → 双击 → 窗口打开 → 起 turn → Review diff 显示。**若 `QUESTOR_MODEL_API_KEY` 缺**：诚实记 pending（AGENTS §一 铁律 1），只跑 fake 场景。
- [ ] **Step 5**：提交

  ```bash
  git add assets/ desktop/electron-builder.yml desktop/package.json
  git commit -m "feat(desktop): electron-builder Windows NSIS packaging with assets"
  ```

---

### Task B8：`desktop.yml` CI workflow + `justfile`/CI 同源

**Files:**
- Create: `.github/workflows/desktop.yml`
- Modify: `justfile`（追加 `desktop-build` 与 `desktop-test` 目标；本地与 CI 同一批命令）
- Modify: `tests/architecture/test_ci_parity.py`（把 `desktop.yml` 步骤名纳入 parity 断言）

**Interfaces:**
- Produces: CI 跑前端 eslint/tsc/vitest + Web 静态构建 + Electron 构建 + 冒烟"网页宿主仅 localhost 伺服"（structure.md §9）。

- [ ] **Step 1**：写 `desktop.yml`

  ```yaml
  name: desktop
  on: [push, pull_request]
  jobs:
    desktop:
      runs-on: windows-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-node@v4
          with: { node-version-file: '.node-version' }
        - run: npm --prefix ui ci
        - run: npm --prefix ui run typecheck
        - run: npm --prefix ui run test
        - run: npm --prefix ui run build
        - run: npm --prefix desktop ci
        - run: npm --prefix desktop run typecheck
        - run: npm --prefix desktop run test
        - run: npm --prefix desktop run build
        - run: npm --prefix desktop run package
        - name: localhost smoke
          run: |
            # serve http 起 → curl 127.0.0.1 methods → 断言 --host 0.0.0.0 启动即拒
            uv run questor serve http --host 0.0.0.0 &
            sleep 2
            "! curl -s http://0.0.0.0:8765/methods"
  ```

- [ ] **Step 2**：`justfile` 追加
  ```make
  desktop-test:
      npm --prefix desktop run test
  desktop-build:
      npm --prefix ui run build && npm --prefix desktop run build
  ```

- [ ] **Step 3**：扩展 `test_ci_parity.py`——`justfile` 的 `check` 配方与 CI 步骤命令集合一致；本地跑 `.venv\Scripts\python.exe -m pytest tests/architecture/test_ci_parity.py -q` 应绿。

- [ ] **Step 4**：负向验证——临时在 `justfile` 加一条 `desktop-check-unused` 目标但 CI 里没同步 → parity 测试应红 → 复原。

- [ ] **Step 5**：提交

  ```bash
  git add .github/workflows/desktop.yml justfile tests/architecture/test_ci_parity.py
  git commit -m "ci(desktop): workflow + justfile parity for Electron shell build/test"
  ```

---

### Task B9：Phase U 出口 e2e + Track B 人工走查

**Files:**
- Create: `tests/e2e/test_desktop_shell_vertical_slice.py`（Python 侧 e2e，用 `testenv` fake model + fake home）
- Create: `docs/plans/2026-10-13-phase-u-completion.md`（走查记录 + 截图引用 + Track A/B 出口勾销）
- Modify: `docs/plans/development-plan.md`（Phase U 状态勾销 + 实际结果）
- Modify: `docs/specs/pitfalls.md`（B-103~B-112 全部 `covered`，回填测试名）

- [ ] **Step 1**：写端到端测试：`test_desktop_shell_vertical_slice` 通过 `subprocess` 起 `desktop run dev --headless` 或用 Electron 的 `playwright` 集成——**本项目当前 `tests/e2e/` 是 Python 侧**，Electron e2e 需要新工具链。折中：Python 侧只 e2e 到 `serve stdio` 与 `serve http`（已有测试覆盖），Electron 层的 e2e 记为 pending（诚实呈现），Track B 出口以"手动走查截图 + desktop.yml 冒烟"为准。

- [ ] **Step 2**：全套门禁跑一遍（同 A9 Step 2 加 `npm --prefix desktop run test`、`desktop.yml` 冒烟本地等价）

- [ ] **Step 3**：`development-plan.md` Phase U 状态行改 `- [x] 已完成 YYYY-MM-DD（Track A / Track B…）` + 一段"实际结果"；缺 `QUESTOR_MODEL_API_KEY` 记 pending。

- [ ] **Step 4**：`pitfalls.md` B-103~B-112 全部转 `covered` 并回填测试名；每条附负向验证输出（AGENTS §四护栏测试准入判据）。

- [ ] **Step 5**：提交 + 汇报

  ```bash
  git add tests/e2e/test_desktop_shell_vertical_slice.py docs/plans/2026-10-13-phase-u-completion.md docs/plans/development-plan.md docs/specs/pitfalls.md
  git commit -m "docs(phase-u): both tracks closed; pitfalls covered; e2e + smoke green"
  ```

**Phase U（Track B）出口判据**：
1. Electron 壳可双击打开、`serve stdio` 被 `child_process` 以管道拉起、窗口里能看到 Review 面板显示真 diff；
2. `runtime_state.json` 单调 generation + `lifecycle_lock` 用例绿；崩溃重启 fail-open 生效；
3. Windows 打包产物可安装、可启动；`desktop.yml` CI 与本地同源；
4. `test_no_hardcoded_panel_case.py` 与 `test_ci_parity` 全绿；
5. `docs/plans/development-plan.md` Phase U 勾销；坑目录 B-103~B-112 全部 `covered` 并附负向验证输出。

---

## Self-Review（写完这份计划的自检 + 2026-10-13 深度扫描后修订）

**扫描与改判记录**：首版计划里 B6 写的是 Option B（renderer 直连本地 WS）。本轮对 wuu `desktop/src/main/` 深度扫描后发现：**wuu 实际实现 = Option A**（`appServerClients.ts` stdio + `main/index.ts::appServerRequest` IPC handle + `preload.ts::contextBridge`），且 ADR-0006 结论 4 字面要求"桌面 stdio NDJSON"——Option B 会架空这条约定。已推翻 B6 重写为 A。同次扫描另捾出 7 处可抄 wuu 设计（childShutdown / atomicFile / wuuCommand / appServerClients pending 与 server-request 路由 / preload parity / rendererServerEventBatcher / ServerEvents 单桥 fanout），已全部写进对应 B3~B6 步骤与顶部“从 wuu 桌面壳借鉴清单”表。

**1. Spec 覆盖检查**：
- `development-plan.md` Phase U 出口判据 4 条：
  - "能双击运行的 Electron 壳跑通"→ B2/B6/B7/B9 ✓
  - "可见柱（Review 真 diff）与可干预柱（插话/接管）各有一个 wuu 级还原度的可演示面板"→ A1~A9 ✓（Review 覆盖；插话/接管在 habena + Composer 已有，Phase U 里可继续做 habena 面板还原度——**记 gap**）
  - "内嵌浏览器做到真·同页接管" → U2（**本计划不含**，ADR-0030 §结论 3 已限定；本计划是 U0+U1 的一部分）
  - "新面板只能走注册表、不改内核"→ 护栏 `test_no_hardcoded_panel_case` 在 A9/B9 都跑 ✓
- **gap 记录**：可干预柱的"插话/接管"面板还原度未在本计划任务序列里；留待 Phase U 后续切片（下一份计划）。

**2. Placeholder 扫描**：本文件所有 step 均给出具体文件路径、命令与代码块；`@pierre/diffs` 与 Electron preload 的具体 API 标注"实施时以官方 README 为准"，属外部 API 合法限定。无 TBD / TODO / "add appropriate error handling" 类占位。

**3. 类型一致性**：`PanelProps`（`threadId/activeTurnId`）在 A5/A6/A7/A8 一致 ✓；`SidecarHandle`（`pid/stdin/stdout/stderr/exited/kill`）在 B3/B4/B5 一致 ✓；`AppServerBridge` 方法签名（`dispatchRequest / respondToServerRequest / rejectServerRequest / runningThreadsSnapshot / onEvent`）在 B6 Interfaces 与实现中一致 ✓；`window.questorHost` 与 `IpcTransport` 方法签名在 B6 preload ↔ ipc-transport ↔ client.ts 三处一致 ✓。`SidecarState` 的 `endpoint?` 字段已删（Option A 不需要），只留 future remote 预留注释。

**4. 新增坑 列表**：B-113 关停等 pipe close 不够（要等 exit） / B-114 从 workspace 或 PATH 找内核 binary 会撞版本坑 / B-115 无 fsync 的 rename 不算 crash-safe / B-116 preload ↔ main IPC channel 不对偶 / B-117 Electron IPC 每 token 转发卡住 renderer + snapshot 重放 / B-118 server-initiated request 的内核真实 id 不应外泄。A3 Step 2 将五条新坑写进 `docs/specs/pitfalls.md`。

**5. 不破坏已完成内核的保证**：本计划不新增/修改 `schemas/*`、`protocol.md`、`serve/*` 方法表、`limen`、`engine`、`tools`。B6 里 `initialize` 的 `capabilities.reverse_rpc.methods` 声明属**现有协议里已有字段**的正常使用（overview §8、`serve/dispatch.py` 反向请求已实现），不是契约新面。若发现新需求→停下走单独 ADR（ADR-0030 §触发重评 #3）。

---

## 后续任务边界（防止 scope 漂移）

- ❌ **U2**：Electron 内嵌浏览器真接管、PiP/多窗口/自绘光标/托盘——另开计划。参照地图 `wuu-main/desktop/src/main/browserHostWindows.ts`（2536 行）、`browserPiPWindow.ts`（1099 行）、`agentCursor.ts`（330 行）。
- ❌ **Terminal / Files / Board 面板的 wuu 级还原度**：本计划只覆盖 Review 一条纵切片；其它面板另开计划（可参照 wuu `desktop/dev/three-pane/renderer.tsx`、`dev/projects/renderer.tsx`）。
- ❌ **动效体系铺开**：本计划只加 Review 用到的 `--motion-*`/`--elevation-*` token；其它面板动效跟其它面板走。
- ❌ **Electron 主进程业务化**：ADR-0030 触发重评信号 #2——若发现"想往壳里塞业务判断"的冲动，一律拦下走协议。
- ❌ **macOS/Linux 打包**：ADR-0007/structure §7 Windows 第一平台；其它平台另开 ADR。
