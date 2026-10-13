# Questor 前端（`ui/`）

**唯一前端代码源**：一套代码两个宿主——Electron 桌面壳与浏览器。内核能力的可见性与可干预性
全部落在这里；内核做完而这里没入口，等于第一柱没做到（`AGENTS.md` §一）。

## 目录职责

| 路径 | 职责 |
| --- | --- |
| `src/app-shell/` | 三栏骨架（侧栏 / 会话 / 工作区面板）；M3 起接真实数据 |
| `src/design/` | `tokens.css`（语义 token）、`themes.css`（主题覆盖）、`base.css`、`useTheme` |
| `src/rpc/generated/` | **由 schema 生成，禁止手改**（`just gen` 覆盖；CI 断言重新生成后无 diff） |
| `src/rpc/mock.ts` | mock 协议服务，**只服务于 M1–M2 的 UI 开发**；M3 真接后降级为测试替身 |
| `src/state/` | 工作台状态（面板可见性、主题等 UI-local 状态；会话状态的归属见下） |
| `noop.js` | `scripts/gen/types.mjs` 里 `createRequire` 的路径锚点（ADR-0019），不参与运行时逻辑 |

## 命令

```bash
npm --prefix ui ci
npm --prefix ui run dev          # 浏览器开发（vite）
just gen                          # 重新生成类型（定义点：scripts/gen/types.mjs）
just gen-check                    # 生成后 git diff 必须为空
npm --prefix ui run typecheck    # tsc --noEmit
npm --prefix ui run build        # 产出 dist/（不入库）
```

`just check` 已包含 `gen-check` 与 `typecheck`，与 CI 同一批命令（`ADR-0008`）。

## 状态归属的边界（M3 前必须守住）

- **会话/运行/权限的真相永远在 Python 侧**，前端只做呈现与操作发起；
  `src/state/` 只允许存 UI-local 状态（哪个面板开着、主题、草稿），
  一旦在这里镜像会话历史，就会出现"刷新前看到的和落盘记录不一致"——三柱之可见即失效。
- 引用/批注/选中定位必须携带**工作区修订号**（`overview.md` §7）；前端不得自行推断"当前文件内容"。

## 选型与现成件

React 19 + TS + Vite 6 + Tailwind 4 + zustand **v5** + SWR；`@xterm/xterm`（Terminal）、
`@pierre/diffs`（Review）、`@xyflow/react`（DAG 看板）、`streamdown`/`shiki`（流式 Markdown 与高亮）
在对应里程碑引入（`structure.md` §7 有取舍依据）。**lockfile 只允许一个**（本目录 `package-lock.json` + npm）。

## 尚未做（避免误读现有骨架）

已交付并真接：`Review` / `Files`（M3）、`Board` 看板（M4/M5）；协议真连接（stdio + WS + `serve http`）自 M3 起可用。
尚未建面板：**Terminal** 与 **Browser**——随 Phase U（ADR-0030）进入交付；Electron 下 Browser 可做真·同页接管
（面板 tab 即 Agent 操作页、一点即暂停），不再以“镜像”形式存在，也不适用原 ADR-0006 “不得称同一页面”限制。
