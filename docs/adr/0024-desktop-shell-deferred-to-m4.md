# ADR-0024 — 桌面壳 `desktop/src-tauri/` 从 M3 交付里摘出，落 M4/M5 交界

状态: accepted
日期: 2026-10-12 | 关联: M3 / `overview.md` §4 §12 §14、`structure.md` §7 §11、ADR-0006、
`development-plan.md` M3 交付段、`ui/README.md`

## 结论

`structure.md` §11 与 `overview.md` §12 把 `desktop/src-tauri/`、`assets/`、`desktop.yml`
三条列进 M3 交付。本 ADR 将其**整体推迟到 M4/M5 交界**，与"看板 UI + 桌面壳"一起做。

M3 交付范围收敛为：
- 后端四模块（`review` / `habena` / `sessiontrace` / `worktree`）+ WS 传输 + `serve http` 子命令；
- 前端从 mock 迁到 generated 类型驱动 + 视图注册表骨架 + `Review` / `Files` 两面板；
- 双宿主同契约的验证走"**stdio + WS**"两条传输，浏览器 localhost 承担桌面壳原本要做的
  协议验证角色。

## 理由与取舍

**为什么推**（用 overview §14 三问判据）：
1. **桌面壳是产品化外壳，不是扩展接缝**：Rust 侧 sidecar 生命周期、capabilities 声明、
   图标打包——都是"发布一个能双击运行的东西"要付的账，与协议形状、事件流、修订号绑定
   等 M3 关键扩展接缝无耦合。M4/M5 加看板与验收卡时一起做，成本相同、收益更集中。
2. **验证面不减**：`overview.md` §12 M3 出口判据明写"面板显示真实 diff / 插话下一个工具
   边界被消费 / 接管即停 / 网页只绑 127.0.0.1 且无第二套契约"——四条中只有第三条与桌面壳
   略相关，但接管走 `session/control` 是内核侧 CAS，浏览器已能验；四条全绿不依赖 Tauri。
3. **工程量对比悬殊**：ADR-0006 记录里 wuu `desktop/` 是 241k 行、95 个脚本——那是 Electron
   路线的价，Tauri 版仍需要 Rust 侧 sidecar 拉起 / generation / lifecycle_lock / 崩溃重启 /
   capabilities 全套；同期落 backend `review`/`habena` 的接口价值更高。

**代价（如实承认）**：
- M3 交付物里"能双击打开的桌面 app"这一格空着；README/文档不能写"支持桌面"。
- `runtime_state.json` 单调 generation + `lifecycle_lock`（EvoFlow `backend.rs` 的设计决定
  沿用，plan 中 M3b-3 桌面侧）随本 ADR 一起推后；M4/M5 落桌面壳时同批改。
- `desktop.yml` workflow 一起推；`.github/workflows/` 只保 `ci.yml` / `contracts.yml`
  升级到方法族匹配 / `security.yml`；`evals.yml` 在 M3d 建。

## 被否决的选项

- **照 structure §11 原样落 M3**：桌面壳与后端四模块并行做，两条学习曲线同时爬坡；
  Windows 上 Rust + Python 双工具链联调会吞 2–3 周（对应 overview §15 风险表"面板工程量
  误判"）。
- **只做 sidecar 生命周期不做 capabilities**：capabilities 与 Rust 打包链绑得紧，"半个桌面壳"
  无法运行，等于交付一个不完整的目录树。
- **推到 M6**：M6 是外部引擎适配器，与桌面壳无耦合；推到 M4/M5 交界与"看板 + 验收卡"同期是
  最紧凑的排布。
- **完全不做桌面壳**（放弃 Tauri）：违反 ADR-0006 已定的"桌面 = Tauri"；Windows 第一平台
  有一个原生壳是"可见"柱的一部分。

## 适用条件与失效条件

**适用**：M3 交付范围；`structure.md` §11 M3 行回写为"`review` `habena` `sessiontrace`
`worktree`、`ui/` panels、WS 传输、`serve http` 子命令（桌面壳推 M4/M5）"；
`overview.md` §12 M3 行同步。
**触发重新评审**：① 用户反馈里有强"本地双击运行"诉求（非浏览器 localhost 可满足）→ 提前
落 Tauri；② M4 结束时看板与验收卡的 UI 面板未成型、无法与桌面壳同期做 → 桌面壳另开一段
（M5 收口前）；③ Tauri 上游出现阻断性的 Windows 缺陷 → 按 ADR-0006 的失效条件重评 Electron。
