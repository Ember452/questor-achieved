# phase0-wuu-renderer-assembly —— wuu 渲染层装配实测 + Questor renderer 重搭建议

> 本表原为 Phase 0 前置扫描产物（曾 0 字节空文件，2026-10-14 Phase 1 回填）。是 ADR-0040/0020 落笔前必测项。
> 实测来源：`wuu@wuu-main desktop/src/{main,renderer,shared}`（renderer **648 文件**、扁平布局）、
> `desktop/src/renderer/AppState.ts`（事件 reducer）、`desktop/src/main/preload.ts`（IPC 桥）。
> 每行带 wuu 文件锚，可复核。诚实边界：本机跑不了 wuu（无构建），结论取自源码阅读，非运行时抓取。

## 1. 顶层布局（三段式）

`desktop/src/` 三目录：
- **`main/`** — Electron 主进程（Node 侧）：拉起/附着 app-server、shell 能力、窗口。
- **`renderer/`** — React UI（Chromium 侧）：**648 文件、扁平为主**（大量组件 `.tsx` 直接落顶层，
  按前缀分组如 `Workspace*`/`App*`；子目录仅 `assets/`(19) `background/`(11) `i18n/`(7) `plugins/`(47)
  `styles/`(48) `test/`(2) `ui/`(2)）。**不是**按面板建嵌套目录——靠命名前缀 + 中央 reducer 组织。
- **`shared/`** — 主↔渲染共享契约：`workbench.ts`(**1209 行**，工作台类型契约)、`protocol.ts`(5 行，薄再导出)、
  `themeContract.generated.ts`(173，Tailwind `@theme` 派生)、`iconArtwork.ts`(233)、`DesktopPageZoom.ts` 等。

## 2. 事件消费：中央 reducer `AppState.ts`（非按面板各自订阅）

app-server 通知到达后，**统一进 `AppState.ts` 的 `switch(method)` 归约**（同文件命中 54 处方法串），
再由组件订阅派生态。真实分支样例（`desktop/src/renderer/AppState.ts`）：
- `case "thread/resumed":`（:368）、`case "thread/started":`（:700）——线程快照落地。
- `case "item/agentMessage/delta":`（:379）/`replace`（:387）——正文增量 vs 整体替换两态。
- `case "item/reasoning/delta":`（:395）/`replace`（:403）——推理增量/替换。
- `case "item/toolCall/delta":`（:411）/`outputDelta`（:419）——工具入参流 / 输出流。
- `case "turn/event":`（:427）、`case "turn/usage":`（:429，注释见 :148 "pushed by appserver turn/usage … samples"）、
  `case "item/started|completed|removed":`（:431-438）。
- `event.message.method === "turn/completed" || "turn/error"`（:483-484）——回合终态判定。
- `case "config/error":`（:663）/`config/changed`（:667）。

**装配含义**：增量语义（delta 追加 / replace 覆盖，Phase 1 契约 P1-8）在前端由这一个 reducer 落地，
组件不重复解析协议——这是"协议驱动 UI"的接缝收口点。Questor 重搭须保留该单点 reducer 形态。

## 3. 状态管理：无 zustand，手写 store 模块

未发现 zustand 依赖；状态经**专用模块 + React**承载：`AppState.ts`（协议态归约）、
`AppLayoutState.ts`（面板布局）、`ViewSwitchState.ts`（视图切换）、`WorkspaceToolState.ts`（工具态）、
`ExternalAgentActivityStore.ts`（activity）。→ 印证旧 `ui/` 的 zustand 选型被撤销（§1.6），对齐 wuu 手写态。

## 4. 面板组成（工作台 = 会话侧栏 + 对话流 + 多视图面板）

顶层组件按前缀归组（锚 `desktop/src/renderer/`）：
- **Review**：`WorkspaceReviewPanels.tsx`（工作区级 diff，消费 shell 侧 `gitService` 盘态真相——ADR-0045/C0）、
  `WorkspaceReviewHelpers.ts`。
- **Files**：`WorkspaceFiles.tsx`、`WorkspacePaths.ts`、`WorkspaceCodeHighlight.ts`、`WorkspacePdfPreview.tsx`。
- **Terminal**：`WorkspaceTerminalPanel.tsx`（+ 主进程 `terminalSessions.ts`，node-pty/ConPTY）。
- **Browser**：`WorkspaceBrowserPanel.tsx`、`WorkspaceBrowserOpen/Navigation.ts`（+ 主进程 `browserView/browserPiPWindow`）。
- **编辑器/diff**：`WorkspaceMonacoEditor.tsx` / `WorkspaceMonacoDiffEditor.tsx`（Monaco 接入点）。
- **多视图容器**：`WorkspaceViewTabs.tsx`、`WorkspacePanels.tsx`、`WorkspacePreviewBoundary.tsx`。
- **对话流**：`ThreadItemView.tsx`、`TurnViewHelpers.ts`、`UserQuestionCard.tsx`（HITL）、`InternalUserNotification.ts`。
- **侧栏/品牌/吉祥物**：`SidebarBrand.tsx`、`WuuMascot.tsx` 等（宠物/吉祥物 = **不采纳**，§不采纳清单）。

## 5. 主进程能力（renderer 只读消费，能力住 main）

`desktop/src/main/`（锚）：
- `appServerClients.ts` — 拉起/附着 app-server（sidecar）。
- **`gitService.ts`** — 工作区 `git diff`（含 untracked）盘态真相，供 Review 面板。**Questor 照此：内核不出工作区 diff（ADR-0045）**。
- `atomicFile.ts` / `childShutdown.ts` / `wuuCommand.ts` — 原子写 / sidecar 关停（等 exit 不等 pipe，B-113）/ 被管进程绝不 PATH 兜底。
- `terminalSessions.ts` — PTY 会话；`browserView/browserHostWindows/browserPiPWindow.ts` — 浏览器宿主。
- `rendererServerEventBatcher.ts` — 服务端事件批处理再送渲染（节流，对应 `turn/usage`/`run/updated`）。
- `preload.ts` — contextBridge 暴露 IPC。
- `remote*`（12 个文件）/`phoneAccess` — **remote/relay 不做**（A 阶段）；`codexPet*`/`cua*` — 宠物/CUA **不采纳**。

## 6. preload IPC 通道分布（共 **189** 个 `wuu:` 通道，contextBridge）

按域计数（`preload.ts`）：`thread`16、`browser`15、`plugin`12、`project`10、`git`9、`turn`8、`window`8、
`remote`8、`mcp`8、`config`8、`codex`7、`session`7、`file`7、`side(thread)`6、`terminal`6、`language`5、
`theme`5、`onboarding`5、`managed`4、`user`4、`account`4、`activity`4、`auth`3、`message`3、`pop(over)`3、
`engine(s)`5、`running`3、`server`2、`artifact`2、`extension`2、`desktop`2、`skill`2，余 build/text/settings/cua/system/build/reveal/usage/instructions/reject/respond/open 各 1。

> **Questor A 阶段 IPC 面裁剪**：`plugin`/`mcp`/`codex`(xai)/`remote`/`project`/`side`/`extension`/`skill`/`cua`/宠物 等
> 随"不做/后置"族裁掉；保留 thread/turn/run/item/activity/session/config/file/terminal/browser/git/window/theme/message/user-question。

## 7. Questor renderer 重搭目录/装配建议（照 wuu，落 ADR-0040）

- **住** `desktop/src/renderer/`（新壳），主进程 `desktop/src/main/`、共享 `desktop/src/shared/`。
- **单一事件 reducer**（对应 `AppState.ts`）消费 app-server 通知（`method==` switch，delta/replace 两态），
  组件订阅派生态——协议解析只在一点。
- **协议类型**来自 `packages/protocol` 手抄契约（对齐 Phase 1 `schemas/app_server/`；wuu 无代码生成，TS/Py 并行须同批改 + parity 测）。
- **状态**用轻量模块（非 zustand），布局/视图/工具态分文件。
- **面板**：会话侧栏 / 对话流（ThreadItemView）/ Review（消费 shell `gitService`）/ Files / Terminal / Browser / Monaco 编辑器·diff / 多视图 Tabs——按 wuu 前缀组织，非深嵌套。
- **shell 能力**（主进程）：sidecar 生命周期（childShutdown/wuuCommand）、gitService、terminalSessions、browserView、atomicFile——移植时按记忆坑项处理。
- **动效/主题**：Tailwind v4 `@theme` 派生（wuu `themeContract.generated.ts` + `styles/` 48 文件），亮/暗双套 + `prefers-reduced-motion`（照 behavior-review-fidelity-wuu）。

## 8. 不采纳清单（防 scope 漂移）
多 client MRU 池化、宠物/吉祥物窗（`codexPet*`/`WuuMascot`）、PiP、remote/relay 桥、plugin/mcp/skill 宿主、
subagent/sideThread/participant——均随 §1.6/§0"不做"排除，重搭不引入。

## 9. 诚实标注
wuu renderer 648 文件、打磨极重（§1.6 已知）。本装配给出的是**结构与接缝**，非逐组件复刻；Phase 2 界面保真度
沿 Phase 2→3→4 逐波向 wuu 贴近，不承诺第一版吃平全部 648 文件细节。运行时行为（真实 IPC 时序）本机不可抓，属盲区。
