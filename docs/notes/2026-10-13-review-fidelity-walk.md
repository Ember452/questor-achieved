# Review 面板 diff 渲染链路：从 `review/turn_diff` 到 `@pierre/diffs`

日期: 2026-10-13 | 复核于: 2026-10-13
锚点: `ui/src/panels/review.tsx`、`ui/src/panels/review.diff-view.tsx`、`ui/src/rpc/client.ts`、
`src/questor/review/diff.py`（写时算 unified）、`src/questor/serve/app_server.py`（`review/turn_diff` 路由）、
`docs/specs/behavior-review-fidelity-wuu.md` §2

## 预测

写 A7 前我猜的链路是 `client.call("review/turn_diff")` → `FileDiff[]` → 组件里塞给
`@pierre/diffs` 的 `<DiffView file={{ contents: unified }} />` 就完事。

## 验证与差异

跑起来三处和猜的不一样：

1. **API 形状**：`@pierre/diffs` 顶层不导出 `<DiffView>`。React 入口在 `@pierre/diffs/react`
   子路径（`package.json` exports），组件是 `<FileDiff fileDiff={FileDiffMetadata} options={...} />`。
   元数据不是 unified 字符串本身，需要转换。
2. **转换入口选择**：包内两个候选——`parseDiffFromFile(oldFile, newFile)` 面向"给两份完整文件、
   现场重算 diff"；`processFile(patchText, options)` 面向"已有 patch 串、解析成元数据"。
   本项目 `turn_diff` 返回的是**写工具执行时刻算好的 unified 片段**（B-66/B-93 的"写时算"），
   不是两份完整文件——所以选 `processFile`。这个选择是"不重算、尊重写时算的真相"的必然结果。
3. **`unified` 缺 git header**：`turn_diff` 里的 `unified` 是**纯 hunk 片段**（`@@ ... @@` 起头），
   没有 `diff --git a/... b/...` 头部。直接喂 `processFile` 会因为 `name` 空而没法按扩展名推断
   语言、行内容不渲染。修法是 `buildFileDiff` 用 `path` 合成一个最小 git header 再喂：
   ```ts
   const patch = `diff --git a/${path} b/${path}\n--- a/${path}\n+++ b/${path}\n${unified}`;
   ```
   只补 header，不改内容、不重算——保留原 hunk 结构与行号，B-103 断言的正是这个"完整性"。

## 测试环境的两个反直觉

`ui/tests/review.fidelity.test.tsx` 顶部注释也记了：

- `<FileDiff/>` 挂一个 `<diffs-container>` 自定义元素，happy-dom 会升级它并把结构渲染进
  **shadowRoot**——`testing-library` 不穿透 shadow、`container.textContent` 是空的。所以
  **不断言"渲染后有没有 `@@` 字样"**，改在封装契约层断言 `buildFileDiff(...)` 返回的元数据
  里首尾两个 hunk 的行内容都在。这才是 B-103 的真实回归面（截断 bug 丢的是元数据里的尾 hunk，
  不是渲染后的像素）。
- `@pierre/diffs` 的行文本要 shiki **异步**高亮后才落进 shadow；测试环境里不可靠。所以
  **测里靠 `disableWorkerPool={IS_TEST}` 走主线程高亮**（`IS_TEST = import.meta.env.MODE === "test"`），
  且断言只到 `color-scheme: dark` 这种**同步落**的 :host style，不去等 shiki。

## 一句话结论

`review/turn_diff` → `FileDiff[]` → `buildFileDiff`（合成 git header + `processFile`）→
`FileDiffMetadata` → `<FileDiff themeType overflow="wrap" hunkSeparators="metadata">` →
`@pierre/diffs` 内置主题 + tokens.css 的 `--color-diff-*` 共同上色。护栏与还原度断言**不进
shadow DOM**，全部在**封装契约层**与 **CSSOM 静态层**——这样测得准、也不被上游渲染时机绑住。
