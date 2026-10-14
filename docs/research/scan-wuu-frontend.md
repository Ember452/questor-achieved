# wuu 前端 × app-server 协议可移植性扫描报告

> 只读扫描 `d:\DEVELOP\My-project\wuu-main`，聚焦 `clients/`、`packages/`、`desktop/`、
> `internal/appserver`、`cmd/wuu-server`。核心问题：**wuu 前端能否「纯靠 app-server 协议」驱动，
> 从而挂在 Python 重写的后端上？以及能否在 Windows 起来？**

> ⚠️ **深度修订（第二轮取证）**：首版为快速成文在若干处停于表面甚至说反。
> 已用证据补正并新增 **§8 补深与勘误**，关键更正：
> ① server→client **通知词汇约 40 条**（首版误判「0」）；② 反向 RPC 精确为 **browser 家族 8 方法**；
> ③ **内嵌终端 PTY 由 Electron 主进程 `node-pty` 持有**（`terminalSessions.ts`），**不是后端**（首版说反）；
> ④ `app-server` 子命令与 `--workdir/--workspace-id` 已核实落 `cmd/wuu/main.go:117/2105` → `rt.Serve(stdin,stdout)`；
> ⑤ 最硬证据：**渲染层直接按 `method=="turn/event"` 消费 app-server 通知、并复用 `@wuu/protocol` 类型；
> mobile-web 用相对路径直接 import `desktop/src/renderer` 源码跑在同一渲染层**——前端本就是传输无关、协议驱动。

## 结论速览

- **可复用度：高（本地桌面路径）。** 前端与后端之间是**纯 JSON 消息契约（app-server 协议）**，
  本地走 **stdio JSONL**、远程走 **relay + E2E 封装帧**，两者承载同一套消息词汇。
  只要 Python 后端**忠实复刻 `wuu-core app-server` 的 stdio JSONL 契约**，Electron 前端可原样复用。
- **接缝位置非常干净**：协议是唯一跨语言边界。前端主进程通过
  `resolveWuuCommand` 决定拉起哪个可执行文件，且已内建 `WUU_DESKTOP_CORE` 环境变量覆盖钩子
  ——把 `wuu-core` 换成 Python 可执行文件即可对接，无需改协议消费代码。
- **Windows：官方支持的目标**（有 `build:core:win` / `pack:win` / `dist:win`、`.exe` 解析、NSIS 打包）。
  唯一 mac 专属的是可选的 **CUA（computer-use agent）helper**，非 darwin 平台自动跳过，不影响主链路。
- **最大雷区不是「前端依赖 Go 行为」，而是「协议契约没有代码生成、靠人工双份维护」**，
  以及**反向 RPC + plugin 子进程 helper**这两处隐藏契约面。逐条见下。

---

## 0) 冷启动：没看过 wuu 也能读懂（先建立心智模型）

> 本节为「第一次接触该仓库」的读者准备；已熟悉者可跳到 §1。

### 0.1 wuu 是什么（一句话）

wuu 是一个**可自托管的 AI 编程 Agent**：用户在桌面 GUI 里用自然语言下任务，Agent 会读写文件、跑
命令、开子代理、操作浏览器来完成，并把每一步产出的 diff 交给用户审阅/批准。本仓库 = **Go 后端（agent 引擎）
+ 多前端壳（Electron 桌面 / Web / Android）**。本报告只回答一个问题：**这套前端能否换成 Python 后端。**

### 0.2 必懂术语（域模型 + 架构）

| 术语 | 含义 |
|---|---|
| **thread（会话/线程）** | 一次持续对话的容器，对应一个项目工作区；可分叉/归档。 |
| **turn（回合）** | 用户发一句→Agent 干一轮（可能多次调模型+工具）的最小执行单元。 |
| **run / session / workspace** | run=一次执行；session=持久化会话；workspace=一个项目目录(worktree)。 |
| **app-server / core / wuu-core** | 同义：Go 写的后端服务进程，内嵌 agent 引擎，对前端说 app-server 协议。 |
| **plugin helper** | core 再拉起的子进程二进制（memory/todo/automation/ask-user…），提供扩展能力。 |
| **反向 RPC** | 后端反过来调前端的调用（如让前端截图/控制浏览器）；方向 client←server。 |
| **CUA** | computer-use agent，macOS 专属的「图形化操控电脑」能力（可选）。 |
| **PTY / node-pty** | 伪终端；桌面主进程用它跑内嵌终端，与后端无关。 |
| **relay / E2E** | 远程控制的中继服务器与端到端加密通道（手机↔电脑），与本地桌面路径并存。 |

### 0.3 一张图看懂「接缝」（Python 就从这里插进去）

```
╔══════════ Electron 桌面壳（前端・TypeScript/React・本报告主角）══════════╗
║  渲染层 renderer            ←  Electron IPC（173 通道，≈透传）  →  主进程 main  ║
║  （会话侧栏/对话流/Review-diff/ │           │                       ║
║   编辑器/终端node-pty/浏览器）  │    持有 app-server 客户端 + 反向RPC应答   ║
╚═══════════════════════════════╪════════════════════════════════╝
                                │  spawn 子进程 + stdio JSONL（一行一个 JSON）
             ◀══ 跨语言接缝(SEAM)：只靠这套 JSON 消息，无任何 Go 类型依赖 ══▶
                                ▼
        wuu-core  app-server（后端・Go）：agent 引擎/工具执行/持久化/调模型
        契约面：112 请求方法 · ~40 通知 · 8 反向 browser 方法 · initialize 握手
              │  再 spawn（stdio）
              ▼
        wuu-*-plugin helpers（Go 插件二进制：memory/todo/automation/ask-user…）

  ‼ 移植动作：把上面整个「Go 盒子」（core + 它的 plugin helpers）换成一个
     说完全相同 JSONL 契约的 Python 进程；下面三层结构不变，前端不改。
```

### 0.4 一段具体消息流（让人体感「JSON-RPC over stdio」）

前端主进程往子进程 stdin 逐行写 JSON、从 stdout 逐行读 JSON；字段以 snake_case 为主（示意）：
```jsonc
// ① 前端→后端：初始化握手（每次拉起都发）
{"id":"1","method":"initialize","params":{"protocol_version":"wuu-app-server/v0.1",
  "capabilities":{"reverse_rpc":{"methods":["browser/cdp","browser/screenshot","»»"]}}}}
// ② 后端→前端：握手回应（带一大块能力/配置快照）
{"id":"1","result":{"status":"ready","protocol_version":"wuu-app-server/v0.1",
  "provider":"openai","model":"…","features":{"browser":true,"safe_mode":false},"»»":"…"}}
// ③ 前端→后端：发一个回合
{"id":"2","method":"turn/start","params":{"thread_id":"t-1","input":"…"}}
// ④ 后端→前端：流式推送（无 id，单向通知；打字机效果就靠这些）
{"method":"item/agentMessage/delta","params":{"thread_id":"t-1","turn_id":"x","text":"…"}}
{"method":"turn/completed","params":{"thread_id":"t-1","turn_id":"x"}}
```
> 要点：请求带 `id`、响应回填同 `id`；通知无 `id`（服务端→客户端方向服务端用 `srv-` 前缀）。整个
> 协议就是这套 `{method, params}` / `{result, error}` 的 JSON 对象集——**语言中立**，这就是能换后端的根本原因。

---

## 1) 前端形态

### 形态：Electron（非纯 web），且是多客户端仓库

| 客户端 | 目录 | 技术 | 用途 |
|---|---|---|---|
| **desktop** | `desktop/` | Electron 44 + React 19 + electron-vite 5 | 主桌面工作台 |
| mobile-web | `clients/mobile-web/` | Vite + TS | 「共享 desktop renderer over 加密远程 bridge」的 Web 壳 |
| mobile | `clients/mobile/` | TS | 移动客户端逻辑 |
| native | `clients/native/android/` | Kotlin（Jetpack Compose） | Android 原生壳，独立实现同一协议 |
| core | `clients/core/` | TS 库 | 共享 app-server 客户端（RPC/wire/secure/compression） |

**desktop 是 Electron**：入口 `desktop/src/main` (主进程) + `desktop/src/renderer` (渲染层) +
`desktop/src/shared`；`electron.vite.config.ts` 三段式构建；`main: "out/main/index.js"`。

### 窗口 / 面板（renderer 侧观察）

- **会话/线程侧栏**：`ThreadSidebar.tsx`(46KB)、`ThreadItemView.tsx`(39KB)、会话归档/搜索/固定/文件夹。
- **对话流**：`TurnView.tsx`、`TurnNotice.tsx`、`ToolActivity.tsx`/`ToolActivityHelpers.ts`(49KB)、
  `UserQuestionCard.tsx`、`MessageImage`/`VideoAttachment`/`pdfjs` 附件渲染。
- **Review / diff 面板**：`WorkspaceReviewPanels.tsx`(23KB)、`TurnFileDiffPanel.tsx`、
  `ToolDiffPreview.tsx`、`WorkspaceMonacoDiffEditor.tsx`。
- **内嵌编辑器 / 文件树**：`WorkspaceFiles.tsx`(36KB)、`WorkspaceMonacoEditor.tsx`(22KB)、
  `@pierre/trees` 文件树、`WorkspaceCodeHighlight`。
- **内嵌终端**：`WorkspaceTerminalPanel.tsx`(36KB) + `@xterm/xterm` + `node-pty`。
- **浏览器视图**：主进程 `browserHostWindows.ts`(103KB!)、`browserPiPWindow.ts`(44KB)、 picture-in-picture。
- **worktree / workspace 视图**：`WorkspacePanels.tsx`(57KB)、`WorktreeNotice.tsx`、多 workspace 池。
- **吉祥物 / 宠物窗**：`WuuMascot.tsx`、`codexPetWindow.ts`(73KB)、`cuaActivityWindows.ts`（mac CUA）。

### 技术栈与规模

- 框架 **React 19**；构建 **electron-vite 5 + Vite 7 + TS 7**；测试 **Vitest**（+ 大量 Electron e2e 脚本）。
- 富组件：**Monaco 0.53**（编辑器/diff）、**xterm 6**（终端）、**mermaid**、**react-markdown + remark-gfm + rehype-raw**、
  **highlight.js**、**pdfjs-dist**、**@dnd-kit**（拖拽）、**lucide-react**（图标）、**qrcode**。
- 状态管理：**未见 Redux/Zustand 等外部状态库** → 以 React hooks + Context 为主
  （如 `WorkbenchConnectionContext.tsx`、`TurnTelemetryStore.ts`、`ViewSwitchState.ts`）。
- **规模**：renderer ≈ **648 文件**（`.tsx` 324 / `.ts` 245 / `*.test.*` 231）；main ≈ **97 文件**；
  preload 暴露 ≈ **173 个 IPC 通道**。属大型前端。

---

## 2) 前端 ↔ 后端通信

### 两条传输，同一套消息词汇

1. **本地（desktop main ↔ core）**：**stdio JSONL**。主进程用子进程管道，一行一个 JSON。
   - 拉起：`appServerClients.ts` → `spawn(command, ["app-server","--workdir",dir,"--workspace-id",id], {stdio:["pipe","pipe","pipe"]})`。
   - 写：`child.stdin.write(JSON.stringify(payload) + "\n")`；帧上限 **64 MiB**（`MAX_APP_SERVER_FRAME_BYTES`，
     对齐后端 `internal/appserver/stdio.go` 的 `appServerMaxStdioRequestBytes = 64*1024*1024`）。
   - 附件以 **base64 内嵌**到单条 JSONL 请求（20MB PDF ≈ 27MB base64）。
2. **远程（mobile/remote ↔ host）**：**relay WebSocket + E2E 封装帧**，app-server JSON 行作为
   `E2EMsg.rpc` 的 `line`（或 `line_gzip`）承载。见 `clients/core/src/wire.ts`（镜像自 `internal/remote/wire`）。
   - `cmd/wuu-server` 是**自托管账号/中继(relay)服务**，**不是**桌面直连的后端。

### 消息形状来源：`packages/protocol` 是**手写单一真相源**，非生成

- `packages/protocol/package.json` 自称：*"Wuu app-server protocol types — single source of truth for all clients"*。
- `packages/protocol/src/index.ts`（**3010 行**）定义 `AppServerRequest/Response/Notification/Error`、
  `APP_SERVER_PROTOCOL_VERSION = "wuu-app-server/v0.1"` 及全部方法请求/结果类型。所有 TS 客户端都 `import` 它。
- 后端 Go 侧**另有一份手写契约** `internal/appserver/protocol.go`（**2770 行**，**112 个 `Method*` 常量**，
  `ProtocolVersion = "wuu-app-server/v0.1"`）。
- **关键事实**：全仓无 `Code generated / DO NOT EDIT / go:generate` 标记指向协议 →
  **TS 与 Go 两份定义靠约定 + 测试同步，不是从一个 schema 代码生成。** 这就是移植的第一雷区：
  Python 后端必须逐字段对齐 **Go 实际序列化的 JSON 形状**（而非 TS 类型），否则前端解析断裂。

### 握手 / 初始化流程

- 每次 spawn（含预热/重启）后，主进程立即发 `initialize`（`ensureStarted()` 里 `this.request("initialize", getInitializeParams())`）。
- 后端 `handleInitialize`（`config_handlers.go:45`）：
  - 校验 `params.ProtocolVersion`（不匹配则报错）；
  - 读取 `params.Capabilities.ReverseRPC.Methods` → `setClientMethods(...)`（**协商客户端支持哪些反向方法**）；
  - 返回**极丰富的 `InitializeResult`**：status/issues、core build info、provider/model/effort/variant、
    runtime host、workspace root、permissions、extension trust/inventory、model profile/roles/aliases、
    providers、advanced/general settings、features(Browser/SafeMode/ProjectAgent) 等。
- 请求/响应/通知/反向请求**复用同一 stdio 通道**（`id` 关联；服务端发起的 id 前缀 `srv-`）。

### 前端是否有逻辑直接依赖 Go 后端特有行为（移植雷区，逐条）

> 前端本身不 import Go；但以下「行为契约」需 Python 后端逐条复刻，否则功能静默劣化：

1. **协议版本字符串**：必须回 `wuu-app-server/v0.1`，否则 `initialize` 被前端/后端互斥拒绝。
2. **反向 RPC（server → client）**：`client_calls.go` 表明后端会**回调前端**执行 **browser 家族 8 方法**
   （`browser/cdp`、`screenshot`、`open_tab`、`close_tab`、`set_visibility`、`list_tabs`、`turn_ended`、`finalize`，详见 §8.3）；
   其中前 **6 个齐备**才置 `features.Browser=true`。前端主进程用
   `serverRequestRoutes`/`respondToServerRequest`/`rejectServerRequest` 路由这些反向请求。
   → **Python 后端必须实现同样的反向调用编排 + 依赖 initialize 里的 capabilities 协商**（30s 超时、单 stdin scanner 串行交付）。
3. **通知流词汇**：如 `activity/stopped`（含 `params.id`）等，前端 `updateStoppedActivityIDs` 依赖具体字段名。
4. **plugin 子进程 helper**：`APP_SERVER_HELPERS` 列出 `wuu-peers/automation/memory/dream/todo/ask-user-plugin`
   等 **Go 插件二进制**，通过环境变量 `<NAME>_PLUGIN_HELPER` 注入 core。core 再 spawn 它们。
   → `plugin/*`、`user-question/*` 等方法的后端语义依赖这些 helper；Python 后端需**自带等价实现或替换 helper 契约**。
5. **engine/authenticate（Codex 外部主机）**：`engine/list` 后端会向外部 Codex 主机查询模型列表（异步、耗时），
   前端在模型选择器打开时刷新。行为语义需复刻。
6. **错误形状**：`AppServerError = {code, message}`；`writeResponse` 的 result/error 结构、以及 oversized reverse-RPC 结果处理。
7. **帧大小上限（64 MiB）**：两端必须一致，否则大附件在一侧被裁剪、另一侧等待。
8. **transport-agnostic 假设**：TS 类型层不含 OS 假设；但 `WorkspaceRoot`、`ConfigPath`、`SessionDir` 等返回值
   是**后端产生的路径字符串**，Python 后端要按目标 OS 产生**原生路径**（见第 3 节）。

**正面结论**：以上都是「协议行为」而非「Go 语言绑定」。前端代码里没有 `import` Go、没有反射 Go 结构体，
只有 JSON 字段名约定 → 可移植性主要取决于**契约复刻的完整度**，而非前端改造。

---

## 3) 平台耦合（macOS-only 假设 / Windows 障碍）

### 打包与构建脚本（`desktop/package.json`）

- **macOS 链路**：`pack:mac` / `dist:mac`（dmg+zip）、`build:cua-mac`、`sign-mac.cjs`、`icon.icns`、dmg 背景、
  `@electron/osx-sign`、`NSScreenCaptureUsageDescription`（computer-use 截屏权限）。
- **Windows 链路（已存在）**：`build:core:win`（`--platform=win32`）、`pack:win`（dir）、`dist:win`（nsis+zip）、
  `"win": { icon: build/icon.ico, target: [nsis, zip] }`、NSIS 安装器配置（可改安装目录）。
- 结论：**Windows 是一等公民构建目标**，非事后补丁。

### 运行期平台判定（已跨平台化）

- `resolveWuuCommand`：打包后优先找 `Resources/bin/wuu-core`，**同时探测 `wuu-core.exe`**（Windows）。
- `appServerHelperEnvironment(..., platform)`：`platform === "win32"` 时给 helper 名追加 `.exe`；
  plugin helper 通用，仅 `wuu-cua-mac` 标 `platform: "darwin"` → **非 mac 自动跳过**。
- `configurePackagedCUA`：`if (platform !== "darwin" || !resourcesPath) return;` —— **CUA（图形化电脑操作）是唯一 mac 专属能力**，
  Windows/Linux 下整块禁用，不影响会话/对话/Review/终端/浏览器主链路。
- 历史坑（`wuuCommand.ts` 注释）：桌面 core **绝不**复用 workspace 里的 `bin/wuu`（曾因 macOS 上捡到 Linux ELF 报 `spawn ENOEXEC`）
  → 移植时 Python 打包同样要保证「自带可执行、架构/OS 匹配」。

### node-pty / 原生模块

- `node-pty@1.1` 为内嵌终端提供 PTY，`asarUnpack: node-pty/**`。属**需按平台重建的原生模块**，
  本身跨平台（Win 用 ConPTY），但 Windows 上需保证 prebuild/gyp 正常；与后端语言无关（在主进程侧）。

### Windows 已知障碍评估

- 协议/传输（stdio JSONL）跨平台无碍。
- 打包链路齐备。
- **主要风险点**：① 后端产生的**路径分隔符/家目录/config 路径**需按 Win 语义（后端职责，Python 需正确处理）；
  ② CUA 在 Windows 缺失（若产品需要「电脑操作」，Win 无对应实现）；③ node-pty 原生重建；
  ④ stdio 子进程在 Windows 的信号/优雅关闭（主进程已有 `childShutdown.ts`，但需实测）。

---

## 4) 接缝判定：换成 Python 后端，前端能否直接复用？

### 判定：**能直接复用（高可复用度），前提是忠实复刻 app-server stdio JSONL 契约**

理由：
- 前端↔后端**唯一边界就是 JSON 消息**；前端不 import Go、不依赖 Go 类型系统。
- 拉起点对称且已参数化：`WUU_DESKTOP_CORE` 可把 `wuu-core` 换成任意可执行文件（含 Python 打包产物），
  CLI 契约是 `<exe> app-server --workdir <dir> [--workspace-id <id>]` + 64MiB stdio JSONL。
- 传输、握手、能力协商均在协议层，跨语言中立。

### Python 后端必须复刻的契约面（工作量清单）

1. **`initialize` 全流程**：版本校验、`capabilities.reverse_rpc.methods` 协商、返回完整 `InitializeResult`（字段极多）。
2. **112 个请求方法**（`thread/*`、`turn/*`、`run/*`、`session*`、`sideThread/*`、`config/*`、`engine/*`、
   `plugin/*`、`user-question/*`、`workspace/*`、`process/*`、`mcp/*`、`activity/*`、`git/*`、`auth/*`、`browser/*` 等）
   的**入参/结果 JSON 形状**（逐字段对齐 Go 实际序列化，注意 snake_case 为主）。
3. **反向 RPC**：后端主动调用前端 **browser 家族 8 方法**（id 前缀 `srv-`、30s 超时、串行交付；清单见 §8.3）。
4. **通知流（约 40 条，流式 UI 的真契约）**：`item/agentMessage|reasoning|toolCall/*` 增量、`turn/event`、
   `turn/usage`（后端节流、前端折算 tokens/s）、`activity/*`、`config/changed`、`user-question/requested|resolved` 等（全集见 §8.2）。
5. **plugin helper 语义**：`plugin/*`、`user-question/*` 背后的插件子进程模型（Go 侧是 `wuu-*-plugin` 二进制）
   —— Python 需自带等价实现或重定义 helper 契约。
6. **64 MiB stdio 帧限制 + base64 附件**、错误 `{code,message}` 形状。

### 需要改的前端点清单

- **几乎不需要改协议消费代码**；改动集中在「装配 / 平台 / 可选能力」：
  1. `desktop/src/main/wuuCommand.ts`：让 Python 产物在打包/开发两态被正确解析
     （可沿用 `WUU_DESKTOP_CORE`，或把 `Resources/bin/wuu-core(.exe)` 换成 Python 冻结可执行名）。
  2. spawn 参数：确认 Python 入口接受 `app-server --workdir [--workspace-id]` 子命令；若不同需改 `ensureStarted()` 的 `appServerArgs`。
  3. `appServerHelperEnvironment` / `APP_SERVER_HELPERS`：把 Go plugin helper 环境变量替换为 Python 等价可执行；
     非 darwin 保持 CUA 跳过即可。
  4. 若 Python 后端**不实现浏览器反向 RPC**：前端 `supportsBrowserClient` 相关能力会自然降级（initialize features.Browser=false），
     属可接受退化而非必改；反之若实现，须与前端反向请求路由对齐。
  5. 可选：若消息词汇有增删，同步更新 `packages/protocol/src/index.ts`（手写，非生成）——**建议为 Python 后端补一个契约一致性测试**，
     用 JSON fixtures 比对 Go 与 Python 的输出，弥补「无代码生成」带来的漂移风险。

### 协议契约的生成链说明

- **不存在跨语言代码生成链。** TS 契约（`packages/protocol`）与 Go 契约（`internal/appserver/protocol.go`）
  是**两份人工并行维护**的定义，靠共享常量 `wuu-app-server/v0.1` + 测试约定对齐。
  远程 `wire.ts` 则「mirrored from `internal/remote/wire`」（同样是人工镜像，非 codegen）。
- 移植含义：Python 后端是**第三份并行实现**，没有任何 schema 能保证三者的字段一致 →
  **必须显式引入契约测试 / fixture 回放**作为移植期的安全带。

---

## 关键文件索引

| 主题 | 路径 |
|---|---|
| TS 协议单一真相源（手写 3010 行） | `packages/protocol/src/index.ts`、`packages/protocol/package.json` |
| Go 协议常量/类型（手写 2770 行、112 方法） | `internal/appserver/protocol.go` |
| stdio 帧上限 64MiB | `internal/appserver/stdio.go` |
| 请求分发 / initialize 落地 | `internal/appserver/server.go`（`case MethodInitialize`）、`internal/appserver/config_handlers.go:45`（`handleInitialize`） |
| 反向 RPC（server→client） | `internal/appserver/client_calls.go` |
| 桌面拉起 core + stdio JSONL + 反向路由 | `desktop/src/main/appServerClients.ts`（`ensureStarted`、`write`、`serverRequestRoutes`、`APP_SERVER_HELPERS`、`appServerHelperEnvironment`、`configurePackagedCUA`） |
| core 可执行解析（跨平台/覆盖钩子） | `desktop/src/main/wuuCommand.ts`（`WUU_DESKTOP_CORE`、`wuu-core(.exe)`） |
| renderer↔main IPC 边界 | `desktop/src/main/preload.ts`（173 通道） |
| 远程/中继 wire（app-server 行封装） | `clients/core/src/wire.ts`、`clients/core/src/client.ts` |
| 中继服务入口（非桌面直连） | `cmd/wuu-server/main.go` |
| 打包脚本（mac/win） | `desktop/package.json`（`build:core:win`、`pack:win`、`dist:win`、`build:cua-mac`） |
| 面板样例 | `ThreadSidebar.tsx`、`WorkspacePanels.tsx`、`WorkspaceReviewPanels.tsx`、`WorkspaceTerminalPanel.tsx`、`browserHostWindows.ts` |

## 8. 补深与勘误（第二轮取证，逐条落文件/行号）

### 8.1 勘误：内嵌终端 PTY 归属（首版说反）

- 首版称「main/renderer grep node-pty 为空 → PTY 可能在后端」，**错**。
- 实据：`desktop/src/main/terminalSessions.ts:10 import * as pty from "node-pty"`，`TerminalSessionManager`
  在 **Electron 主进程** spawn PTY，会话带 `ownerWindowID`（绑定 BrowserWindow），事件经 `TerminalSessionEvent` 回推渲染层。
- 结论：**内嵌终端是纯前端能力（主进程 node-pty），与后端语言无关** → 换 Python 后端不影响终端面板。
- 区分：协议里的 `process/list|read|write|resize|stop` 是**后端侧的 worker/进程**（agent 跑的后台命令），
  与前端 node-pty 终端是两套东西。→ Python 后端仍需实现 `process/*`（PTY 派生，**平台相关：Win 用 ConPTY**）。

### 8.2 补全：server→client 通知词汇（首版误判「0」）

实据 `internal/appserver/protocol.go:155-200`，共约 **40 条 `Notification*`**，这是**流式 UI 的真正契约**：
- 线程/回合生命周期：`thread/started|resumed|updated`、`turn/started|queued|dequeued|steered|unsteered|held|completed|error`、`run/started|updated`。
- **增量流式（最关键）**：`turn/event`、`item/started|completed|removed`、
  `item/agentMessage/delta|replace`、`item/reasoning/delta|replace`、`item/toolCall/delta|outputDelta`。
- 实时用量：`turn/usage`（注释明确：后端按每秒少量次节流推送，**渲染层自行用 delta 折算 tokens/s**）。
- 活动/侧线程：`activity/started|updated|control_changed|stopped`、`sideThread/event`。
- 配置/插件/MCP：`config/changed|error`、`plugin/inventory/changed`、`mcp/status/updated`、`agent/updated|mailbox`。
- HITL：`user-question/requested|resolved`。
→ Python 后端要驱动完整对话流，**必须逐条 emit 这些通知**，且 `item/*` 增量与 `turn/usage` 节流语义要对齐（否则打字机/耗时表失效）。

### 8.3 精确化：反向 RPC 面（首版只列 6 个）

- browser 家族共 **8 个 server→client 方法**（`protocol.go:146-153`）：`browser/cdp`、`browser/screenshot`、
  `browser/open_tab`、`browser/close_tab`、`browser/set_visibility`、`browser/list_tabs`、`browser/turn_ended`、`browser/finalize`。
- 加 2 条反向通知：`browser/request_cancelled`、`browser/turn_started`（`protocol.go:155-156`）。
- 全部经 `browser_handlers.go:112 callClient(ctx, method, scoped)` 单一桥发出，受 30s 超时 + 单 stdin scanner 串行交付约束。
- `supportsBrowserClient()` 用其中 6 个齐备与否，决定 `initialize.features.Browser` 开关 → **前端不实现则浏览器能力自动降级**。

### 8.4 坐实：`app-server` CLI 契约（首版仅有前端假设）

- `desktop/scripts/build-core.cjs:76` → `wuu-core` = `go build ./cmd/wuu`。
- `cmd/wuu/main.go:117 case "app-server": runAppServer`；`runAppServer`(L2105) 用 `flag.FlagSet("app-server")` 解析：
  `--workdir`、`--workspace-id`、`--provider`、`--model`、`--config`、`--host`(local/cloud)、`--instance-id`、`--no-tools`、`--safe-mode`；
  再 `wuusdk.New(Options{...})` → `rt.Serve(ctx, os.Stdin, os.Stdout)`。
- ⚠️ **Windows 侧后端隐患**：`runAppServer` 里 `HomeDir: os.Getenv("HOME")`（L2135）——Go 端用 `HOME`，
  而 Windows 传统上是 `USERPROFILE`；Python 重写时家目录/配置发现要按 Win 语义取（属后端职责，但移植须知）。

### 8.5 最硬证据：前端确为「传输无关 + 协议驱动」（直接决定可复用度=高）

- `desktop/src/shared/protocol.ts` 仅 5 行：`export * from "../../../packages/protocol/src/index"` →
  桌面所有 `shared/protocol` 引用 = `@wuu/protocol` 真相源。
- 渲染层**直接按协议方法名分支**：如 `renderer/plugins/*` 里 `host.publishHostEvent({kind:"notification", message:{method:"turn/event"}})`、
  `if (method === "automation.list")`、`request.method === "create_goal"` → **main→IPC 基本是 app-server 通知对象的透传**，
  渲染层看到的仍是原始 `method` 字符串。→ 换后端只要通知形状对，渲染逻辑不改。
- **跨宿主复用同一渲染层的铁证**：`clients/mobile-web/src/lib/language.ts` 直接
  `import type ... from "../../../../desktop/src/renderer/i18n"` 与 `"../../../../desktop/src/shared/protocol"`；
  `threads.ts/store.ts/pluginAssets.ts` 均 `from "@wuu/protocol"`。
  mobile-web 用**另一套传输（desktopBridge → 加密远程 app-server 桥）**跑**同一 React 渲染层源码**。
  → 前端与后端之间**唯一耦合就是协议消息**，传输层本就被抽象掉；这是对「可移植性=高」的最强实证，也修正了首版仅凭 package.json 描述的含糊判断。

## 一句话答复

**可以。** wuu 的 Electron 前端与后端之间只有「app-server JSON 协议」这一道跨语言边界，
且已被实证为**传输无关 + 协议驱动**：渲染层直接消费 `@wuu/protocol` 类型并按 `method` 分支，
同一渲染层源码在桌面（stdio JSONL）与 mobile-web（relay 桥）上复用；拉起点对 Python 可执行开放（`WUU_DESKTOP_CORE`）；
内嵌终端由主进程 node-pty 自持、与后端无关；Windows 亦是官方构建目标，唯一 mac 专属的 CUA 属可选降级能力。
真正的风险不在前端改造，而在于**协议契约无代码生成、需人工逐字段复刻**——完整契约面是
**112 请求方法 + 8 反向 browser 方法 + 约 40 条通知（含 `item/*` 增量与 `turn/usage` 节流）+ 富 `initialize` 结果 + plugin helper 语义**；
务必用契约/fixture 测试把 Python 实现钉死在 Go 的实际 JSON 输出上。
