# ADR-0032 — Electron 桌面壳工具链依赖引入

状态: accepted
日期: 2026-10-13 | 关联: ADR-0030（Electron 改判与 Phase U）、ADR-0006（一套前端两宿主，桌面 stdio）、
`structure.md` §2/§7/§9、`docs/plans/2026-10-13-phase-u-ui-and-electron-shell.md` Track B

## 结论

1. `desktop/` 引入 `electron`（当前 stable，实施时以 `npm view electron version` 结果钉），
   `electron-vite`（main / preload / renderer 三段构建），`electron-builder`（Windows NSIS 目标）。
2. sidecar 拉起走 Node 内置 `child_process.spawn`；**不**引入 `@tauri-apps/*`、`nativefier`、
   `node-stream-registrar` 等壳侧库；也不引 Electron 的 IPC 高层框架（`electron-store` 等）——
   主进程的 pending 表与 server-request 路由自己写（照 wuu `appServerClients.ts` 的形状）。
3. renderer **不复制** `ui/` 源码：`desktop/electron.vite.config.ts` 的 `renderer` 段 root 指 `../ui`，
   构建产物入 `desktop/out/renderer/`；`ui/` 单点、`desktop/` 只包壳（ADR-0006 结论 2/4）。
4. `desktop/package.json` 独立于 `ui/package.json`——两个 lockfile 各自 npm 管理（**违背 structure §7
   "lockfile 只允许一个"的现成约定，见下"取舍"），因为 Electron 主进程与 renderer 的构建链、依赖面
   与 `ui/` 完全不同栈；两份 `package.json` 各自独立、不共享依赖树，硬塞成一份会引 npm workspace
   复杂度而买不到东西（当前无第二使用者）。**这是一条本 ADR 显式批准的偏离**，`structure.md` §7
   的"lockfile 只允许一个"约束回写为"`ui/` 与 `desktop/` 各自一份、彼此不共享依赖树"。

## 理由与取舍

- **为什么 Electron**：ADR-0030 已定；wuu `desktop/src/main/appServerClients.ts` 用 `child_process`
  + stdio 拉 Go sidecar，同款形态搬到 Python 零障碍；Electron 自带 Chromium，Browser 面板可
  做真·同页接管（ADR-0030 §结论 2）。
- **为什么 `electron-vite`**：与 `ui/` 现有 Vite 6 配置心智一致（同一份 `defineConfig` 语法），
  main / preload / renderer 三段一键跑，比手写 esbuild + tsc 分三份维护成本低。
- **为什么 `electron-builder`**：Windows NSIS 打包事实标准；wuu 与 EvoFlow 的 evopanel 皆实测（后者用 Tauri
  bundler 但同层抽象）。
- **代价（诚实）**：安装包 +约 200 MB、自带 Node/Chromium 升级维护面、`electron-builder` 的 CI 缓存
  与代码签名（本轮**不做签名**，用户本机安装 Windows 会弹 SmartScreen 提示，README 明写）。
  ADR-0030 已记，不在此重复。
- **两份 lockfile 的代价（本 ADR 显式接受的偏离）**：`structure.md` §7 原写"lockfile 只允许一个"，
  依据是 wuu 的 `desktop/` 同时存在 `bun.lock` 与 `package-lock.json` 是双锁源漂移。本项目 `ui/` 与
  `desktop/` 各一份 `package-lock.json` 属**不同根、不同依赖树**，不是同一份 package 的双锁；
  dependabot 用 `directory: /ui` 与 `directory: /desktop` 两条分别覆盖即可，无漂移面。硬合到
  单一 workspace 会引入 npm workspaces + 交叉构建路径的复杂度，与本项目"边界清晰、单点解析"的
  留门纪律相冲突（overview §14）。

## 被否决的选项

- **`electron-forge`**：偏插件式脚手架，与本项目"壳薄、纯 hand-rolled"路线相左；且 wuu 与 evopanel
  均实测用 `electron-builder`（前者）与 tauri-bundler（后者），同层参照。
- **`pkg` / `nexe` 把 Python 内核单文件打包塞进 Electron 资源**：Python 侧走 PyInstaller 会引一条
  完全独立的大依赖链、启动慢、杀软误报多；本项目保持 `uv run questor serve stdio` 拉起路径，
  与内核开发流同源。
- **`@tauri-apps/plugin-shell` 或 Tauri 全家**：ADR-0030 已改判 Electron 出局 Tauri。
- **`electron-store` / `electron-window-state`**：壳层偏好存储与窗口状态属业务面，进 Python 侧
  `config` 模块或走 `~/.questor/desktop/` 单点；壳里不含业务判断（overview §14）。
- **npm workspaces 合并 `ui/` 与 `desktop/`**：见"取舍"末段——增加交叉构建路径与 hoisting 意外，
  不买到任何实际收益，且违反"边界清晰"的留门纪律。

## 适用条件与失效条件

**适用**：Track B 全程（B2~B9）；后续 macOS/Linux 打包（另开 ADR）与代码签名（另开 ADR）沿用同一
`electron-builder` 底座。

**触发重新评审**：
1. Electron 上游出现阻断性 Windows 缺陷（ADR-0030 §失效条件 1）→ 回到 Tauri 或 Web 宿主评估；
2. `electron-vite` 停维或与 Vite 主版本脱节 → 换 `electron-forge` 或手写 vite 三段配置，另开 ADR；
3. 安装包超过 500 MB（含 Chromium）→ 评估 asar 拆包、`files` 白名单更严；
4. 出现第三个"Electron 主进程需要独立 lockfile 之外的 npm 依赖树"（如某个 native module）→
   重走本 ADR 决定是否合并到 workspaces。
