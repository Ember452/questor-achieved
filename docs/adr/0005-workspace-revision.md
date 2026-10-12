# ADR-0005 — 工作区修订号与 turn↔revision 绑定

状态: accepted（M3a-2 落地时从 planned 转正式；本文件由 M3d 归档）
日期: 2026-10-12 | 关联: `overview.md` §7 §12 / `data-model.md` §4 / M3a-2 / B-66 B-92
`src/questor/review/`、`src/questor/workspaces/`、`src/questor/tools/impl/{write,edit}.py`

## 结论

工作区修订号（`Workspace.revision`）与 `Turn`/`Run`/`Item` 的绑定按以下方式落地：

1. **单点递增**：`workspaces.bump_revision(workspace_id) -> int` 是 revision +1 的唯一入口；
   write / edit 工具在 execute 完成后若 `ctx.workspace_id` 非 None 就 bump 一次。
   `run/stop` 不 bump（它不改盘）。**跨进程一致性**：`store_lock(workspaces_dir())`
   与 `register` 同一把锁。
2. **写时算 diff**：`review.compute_diff(path, old_text, new_text)` 由 write / edit 工具
   在 execute 里调用，unified 文本 + hunks + `content_fingerprint` + `byte_size` 塞
   `ToolResult.data["diff"]`，engine 随 `item.appended` 记录落正文（B-66）。
3. **turn ↔ revision 绑定**：`Run.workspace_revision_start` / `_end` 是 model.py 已就位
   字段；本 ADR 的 M3a-2 只落 `aggregate_turn_diff(view, turn_id)`——从该 turn 覆盖的
   run 里的 `tool_result` Item 聚合 diff。`Run` 的 revision 字段填充由 engine 侧未来
   接入（M4 长跑/编排时一并做，本期不半套）。
4. **files/read 绑定**：`expected_revision` 非空且不等于当前 `Workspace.revision` 时
   抛 `stale_revision` 错误方言（protocol.md §7 + `serve.envelope.ProtocolError`），
   附带新 revision 与 `model_next_action="re-read the file at revision N"`。

## 理由与取舍

- **为什么"单点递增"而不是"每次工具各自决定"**：多写入点必然漂移；把 revision 归一
  到 workspaces 让 files/read / selection / Review 面板 / M5 evidence 都能对账。
- **为什么不"事后重扫文件生成 diff"**：写工具落完 Item 之后，若外部（用户手改、别的
  Agent）改了盘，重扫得到的 diff 就不是"当时那一次"的变更——违反 overview §1"可验证"
  柱与 data-model §1"任何字段一旦写入不得改写"。B-66 是 wuu 已定死的选择。
- **代价**：`ctx.workspace_id` 是新增字段，无工作区场景（如单测直接构造 ToolContext）
  走 None，`data` 里不落 revision——诚实边界，不造"看起来总是 0"的假数据。
- **UI 层锁死**：`ReviewPanel` 只能通过 `review/turn_diff` 拿结构化 diff，不得拉
  `files/read` 重算——护栏在 `test_no_hardcoded_panel_case.py`（B-93）与
  `test_review_turn_diff.py`（B-66）两处钉住。

## 被否决的选项

- **让工具直接改 `Workspace.revision` 字段**：多写入点 + 无锁 = 跳进程下必漂；
  而且写"当前值"而不是"+1"会让并发写覆盖。
- **文件级 revision 而非工作区级**：粒度更细但复杂度爆升（每文件都要单点写入口）；
  M3 只保证"整体快照可对账"，M5 evidence 若需要更细粒度另开 ADR。
- **每次读文件都算 diff 与 HEAD 比较**（走 `git diff` 或类似）：违反"diff 属写时事实"，
  与 M5 evidence 复跑核验的语义撞车；且要引 pygit2 或多调外部 git CLI，属"重新发明
  边界层"（AGENTS §二 (a)）。
- **不做 CAS 直接放行旧 revision**（"用户体验优先"）：M3 出口判据"接管即停 + 无第二
  套契约"要求"任何数据形状只有一个真相"；stale_revision 拒是"给用户看盘上事实"的
  一部分，不能因"多一步刷新"就静默放行。

## 适用条件与失效条件

**适用**：M3a-2 起 `Workspace.revision` / 写工具 diff / files/read / review/turn_diff /
selection 与 M5 evidence 的所有绑定；本 ADR 是"工作区修订号"的**唯一契约文档**。
**触发重新评审**：① M5 evidence 若需要"文件级 fingerprint"（跨多次写做局部对账）→
扩 `Workspace` 与 `files/read` 形状走新 ADR；② M6 外部引擎适配器若不接受 Questor
的 revision 语义 → 权限映射表里显式声明"外部引擎的 diff 与 revision 独立"，不静默
合并；③ 若引入 Git 集成（`Review` 面板显示"与 HEAD 的 diff"），走 `review` 之外的
独立模块并另开 ADR——本 ADR 只管"Agent 视角的写时 diff"。
