# behavior-review-fidelity-wuu —— Review 面板 wuu 级还原度行为规格

来源：wuu `desktop/dev/review/renderer.tsx`（127 行 fixture）与 `dev/design-system`、`dev/elevation`、
`dev/motion`、`dev/three-pane`；evopanel `src/zcode-ui/styles.css`（2053 行、Tailwind v4 `@theme`
所在）。扫描日期 2026-10-13。Questor 模块归属：`ui/panels/review.tsx` 与 `ui/src/design/*`。

---

## 0. 与 wuu 的语义差异（诚实标注）

- **wuu 的 Review 面板是工作区级**：`WorkspaceReviewPanel gitStatus={GitStatusResult}` +
  `GitChangeFile[]` 列全 workspace 未提交改动，按路径排序、header 显示总 additions/deletions
  （wuu `dev/review/renderer.tsx:80-91`）。
- **Questor 是 per-turn 级**：`review/turn_diff` 拿"该 turn 覆盖的写工具真 diff"（`FileDiff[]`），
  语义根基是 overview §1 的"可审计"——审计对象是**一轮 Agent 循环的产出**，不是工作区快照。
- **本规格只借用 wuu 的视觉与动效**，不借工作区语义。Questor 保留 per-turn 模型；
  `fingerprint` / `byte_size` / 写时刻 diff 语义不动（B-66/B-93）。

## 1. 文件卡片（可见柱）

- **行为**：每个 `FileDiff` 一张卡片；卡片头含 `path`（mono）、状态徽标（`new` / `modified`）、
  `byte_size`、`hunks.length` 或 `100+ hunks`、`content_fingerprint` 前 7 位；卡片体默认展开，
  `hunks.length > 100` 时默认折叠。
- **参照**：wuu `dev/review/renderer.tsx:28-74`（`add(file, original, modified)` 造样本 + 排序）；
  wuu 生产组件 `WorkspaceReviewPanels.tsx` 视觉即 fixture 呈现的那套。
- **边界行为**：`diffs.length === 0` 显式占位"该 turn 无写工具调用"，不显示卡片列表（B-107）；
  `unified === ""` 显示 "(no changes)"。
- **坑**：B-105（fingerprint 短哈希字体粗细一致性）、B-107（空态可见性）。

### Questor 采纳决定

`ui/src/panels/review.tsx` 按上述重写；`hunks.length > 100` 折叠阈值是本计划定的默认值，
未来视需要开 config 项，不在代码里散落魔法数（AGENTS §四）。

## 2. 双栏 diff 渲染（`@pierre/diffs`）

- **行为**：卡片体走 `@pierre/diffs`，add/del 色对来自 `--color-diff-add-*` / `--color-diff-del-*`
  token，禁 hex 字面量（护栏 `ui/tests/design.tokens.test.ts`）。
- **参照**：evopanel 与 wuu 皆实测选型（`structure.md` §7"技术栈与现成件"）；封装文件是
  `ui/src/panels/review.diff-view.tsx`。
- **边界行为**：unified 字符串含 hunk header `@@` 与至少一段 hunk；头行不被 wrap 截断（B-103）；
  长行 wrap 显式开启。
- **坑**：B-103（头尾截断）、B-106（暗色色对反相）。

### Questor 采纳决定

`FileDiffView` 为唯一 diff 入口；`@pierre/diffs` 上游 API 变化只改这一文件。主题模式从
`useTheme` hook 取，避免亮/暗硬编码。

## 3. 已阅态与折叠动效

- **行为**：卡片头右侧一枚 4 px 圆点 `--color-read-state-dot`；点开卡片头后进入"已阅"态
  （`data-read="true"`），圆点淡出；未阅态圆点隐藏。折叠/展开走 `max-height` 过渡
  `--motion-normal` 180 ms、曲线 `--motion-ease-standard`；`prefers-reduced-motion: reduce`
  下 `transition: none`。
- **参照**：wuu `dev/motion/fixture.css:36-38`（`@container style(--motion-reduced: 1)` 里
  `animation: none`）—— 本项目走 `@media (prefers-reduced-motion: reduce)` 语义等价；两者都
  要求"动效可关"。
- **边界行为**：折叠态卡片体 `max-height: 0`；展开态 `max-height: 800px`；`overflow: hidden`。
- **坑**：B-104（reduced-motion 断言）。

### Questor 采纳决定

在 `ui/src/design/base.css` 里给 `.qst-review-card-body` 与 `.qst-review-read-dot` 加
`@media (prefers-reduced-motion: reduce) { transition: none !important; }`（Task A4 落 token、
A6 落组件、A8 落护栏测）。

## 4. 主题与 token 单点

- **行为**：所有 add/del 色、elevation 阴影、motion 时长/曲线**必须**通过
  `ui/src/design/tokens.css` 的 `@theme` 定义；`themes.css` 只做 `.dark` 覆盖；组件不得出现
  `#hex` 字面量。
- **参照**：evopanel `styles.css` 的**架构**（Tailwind v4 `@theme` 单点派生 14 px 驱动的
  `--text-ui-*` calc 族）——本项目沿用其单点机制但**只提取本项目用得上的族**
  （elevation 4 级、motion 3 时长 + 2 曲线、diff 色对 4 组），不照搬 evopanel 51 个分散 css。
- **边界行为**：`--elevation-0..4`、`--motion-fast/normal/slow`、`--motion-ease-standard/out`、
  `--color-diff-{add,del}-{bg,fg}` 齐；缺任一由 A4 护栏测红。
- **坑**：B-106（暗色色对反相）。

### Questor 采纳决定

Task A4 落 token 族与护栏；Track A 组件仅通过 Tailwind 类映射到 token 或用 `var(--...)`；
`ui/tests/design.tokens.test.ts` 用正则扫组件源码里的 `#[0-9a-fA-F]{3,8}` 字面量、命中即红。
