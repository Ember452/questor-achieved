# ADR-0031 — Review 面板 diff 渲染器与前端测试面依赖引入

状态: accepted
日期: 2026-10-13 | 关联: `AGENTS.md` §四 依赖纪律、`structure.md` §7 现成件清单、
ADR-0030（Phase U 提前与桌面壳改判）、`docs/plans/2026-10-13-phase-u-ui-and-electron-shell.md` Track A

## 结论

1. `ui/` 引入 `@pierre/diffs` 作为 Review 面板的双栏/行内 diff 渲染器；沿用 evopanel
   实测选型（`structure.md` §7"技术栈与现成件"）。
2. `ui/` 引入 `vitest` 作为前端测试 runner；`happy-dom` 作为 DOM 环境；配套
   `@testing-library/react` 与 `@testing-library/jest-dom`；与 vite 配置共享，不引 jest。
3. 上述均为**前端 npm 依赖**，不进 Python 侧；不新增 pytest 依赖、不动 `just gen-check`
   的 schema 生成链。

## 理由与取舍

- **为什么是 `@pierre/diffs`**：evopanel 实测在用（`structure.md` §7 已列）——复用可省
  M3 重新选型；相较 `react-diff-viewer` 支持语法高亮 token 与虚拟化，符合本项目
  "可见柱要吃到真实 diff"的判据（overview §1）。
- **为什么是 `vitest`**：与 Vite 配置同构，无需再维护 jest 那套 transform 边界；`happy-dom`
  相较 `jsdom` 快、体量小，够覆盖面板组件渲染与事件冒泡。`@testing-library/react` +
  `jest-dom` 提供 `getByRole`/`toBeInTheDocument` 等断言，AGENTS §四"测试先枚举失败方式"
  在 UI 层的落地工具。
- **代价（诚实）**：`@pierre/diffs` 引入约 30 KB gzip（未 minify），`vitest` + `happy-dom`
  增 CI 时长约 30–60 s。Track A 的"高还原度"必须付出这些账；不接受则退回 `<pre>` 版本、
  Phase U 目标即失效。

## 被否决的选项

- **`react-diff-viewer` / `diff2html`**：无 evopanel 实测背书，且缺语法高亮 token 一体化——
  `structure.md` §7 已把 `@pierre/diffs` 定为本项目现成件；引入别的等价件会让 M3/M4 已用
  的选型逻辑漂移。
- **`jest` + `ts-jest`**：与 Vite 配置分离、transform 边界要单维护；与 `ui/` 走 Vite 6 的
  单源原则冲突，两份构建配置必然漂移（AGENTS §四 门禁同源）。
- **不装测试 runner（只做人工走查）**：违反 AGENTS §四 "测试先枚举失败方式再实现"——
  还原度断言无锚，"面板好看与否"就变回主观印象；三柱里"可见"就退化为"看着差不多"。
- **Python 侧 pytest + playwright 走 e2e 覆盖 UI**：跨语言栈重、启动慢，`ui/` 组件级细节
  （折叠、已阅态、token 无 hex）用 pytest 测不经济。

## 适用条件与失效条件

**适用**：Track A 全程（Task A2~A9），以及 Track B 起 Electron 壳后 renderer 侧组件测；
后续 Terminal / Browser 面板沿用同测试面（Phase U 后续切片）。

**触发重新评审**：
1. `@pierre/diffs` 上游断维或体积失控（>100 KB gzip）→ 换 `react-diff-viewer` + `shiki` 组合，
   另开 ADR；
2. `vitest` 与 `vite` 大版本升级造成配置漂移 → 记 ADR 版本号钉，保持本地与 CI 同源；
3. 前端测试时长超过 CI 预算（>3 分钟）→ 拆 job 或换 `@vitest/browser`，但"CI 必须跑前端测"
   这条不变（AGENTS §四 门禁同源）。
