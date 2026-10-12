# Changelog

本项目所有值得注意的改动都记在此。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [CalVer `YYYY.M.D`](https://calver.org/)（与 `VERSION` 单点一致，见 ADR-0001）。

**纪律**：每次里程碑收口时把 `Unreleased` 段落到具体的日期版本；条目按 `Added` / `Changed` /
`Removed` / `Fixed` 分门；每条附对应的 commit 或 ADR/B-NN 引用——**不写"优化 / 提升 /
改进"这种无锚表述**（AGENTS §五 与 development-plan 的"每阶段收尾四件事"同源）。

## [未发布]

### Added
- **M3 工作台数据面**（overview §12 M3 行；详见 `docs/plans/development-plan.md` Phase M3）：
  - `src/questor/review/` — 工作区修订号单点、写工具算 diff、turn↔revision 聚合（ADR-0005、B-66/B-93）；
  - `src/questor/habena/` — 插话收件箱、接管栅栏（CAS + revision）、`habena.held_work` 记录 kind 落正文（B-63/64/65/67）；
  - `src/questor/sessiontrace/` — 会话轨迹投影回放，不重跑工具不联系模型（overview §6）；
  - `src/questor/worktree/` — Git worktree 生命周期（`thread/fork mode=worktree`）；
  - `serve` — `files/*` / `review/turn_diff` / `content/read` / `workspace/*` / `sessiontrace/get` /
    `thread/{rename,archive,delete,show,fork}` / `turn/{steer,queue,dequeue}` / `session/control` 方法族；
  - `serve/fanout.py` — 多宿主通知扇出（B-96，每订阅者一个 `asyncio.Queue`）；
  - `serve/ws.py` + `serve/http.py` — WS 传输与本地 http 宿主（ADR-0022/0023，硬 assert 127.0.0.1）；
  - `cli serve http` — 起本地 http + WS 宿主；`--host 0.0.0.0` 启动即拒；
  - `ui/src/rpc/` — `Transport` 抽象 + `WebSocketTransport` + 强类型 `client.ts`（R4：类型全部从
    `rpc/generated/` 引，无手写 DTO）；
  - `ui/src/panels/` — 视图注册表骨架（`PANELS` + `resolvePanel` + `PanelHost` 单分发点，ADR-0020）
    与 `Review` / `Files` 两块真接面板；`MessageStream` 从 Notification union 分派渲染；Composer 解禁。
- `src/questor/schemas/app_server/v0-1.json` — 扩到方法族形状（15 方法 + 6 通知族 + 内嵌
  `ThreadDTO` / `WorkspaceDTO` / `FileDiff` / `DiffHunk`）；`scripts/gen/types.mjs`（新，从 `ui/scripts/`
  搬来，兑现 ADR-0019 归属）打开 `declareExternallyReferenced` 让 `$defs` 全部 export。
- `docs/adr/0022-serve-ws-starlette-uvicorn.md` / `0023-m3-transport-ws-only.md` /
  `0024-desktop-shell-deferred-to-m4.md` — M3 期新增决策；`0005-workspace-revision.md` 从 planned
  归档 accepted。
- 坑目录 `docs/specs/pitfalls.md` 追加 B-89..B-93（M2.2 复审遗留修复与 M3 期新坑）；
  B-60/63/64/65/66/67 从 open 转 covered（回填具体测试名）。

### Changed
- `Workspace.revision` 由 write / edit 工具通过 `bump_revision` 单点递增（B-92）；
  `ToolContext.workspace_id` 新增字段；`serve/assembly.build_engine` 缺省时经
  `ensure_workspace_for_root` 归一化 workspace id（B-91）。
- `serve/dispatch.py`：加 `ProtocolError`（业务错自持 code）与 `request_client` 反向请求路由；
  pending 表优先于 method switch（B-59）；`_run` 里 ProtocolError 分支在 ValueError 之前。
- `Engine._loop`：iteration 起点前调 `_consume_inbox_iteration`（B-67/94），
  `Engine.__init__` 加 `inbox: InboxPort | None = None` 参数与 `attach_inbox()` setter。

### Fixed
- `tools/executor.py::_as_outcome`：`asyncio.CancelledError` 不再被降级为 error 结果，
  改重传（AGENTS §五 异步纪律；B-89；M2.2 复审遗留 M3 修）。
- `tools/impl/{read,write,edit,search,list}.py`：async execute 里的同步文件 IO 全部沉入
  同步 helper + `asyncio.to_thread`（B-90；M2.2 复审遗留 M3 修）。
- `cli/__init__.py`：不再自己算 `sha256` 当 workspace_id；改走 `serve.assembly.ensure_workspace_for_root`
  （B-91）。
- `engine/loop.py` 与 `tests/unit/test_engine_shape.py` 里的"单函数 ≤60 行"文案与
  `MAX_FUNCTION_LINES = 80` 常量对齐。
- `limen/gate.py` docstring：判定顺序补"参数提权"（B-55 门内侧）与"缺路径"（B-31）两层。

### Removed
- `ui/scripts/gen-types.mjs`（搬到 `scripts/gen/types.mjs`，避免两处定义，ADR-0019 归属兑现）；
  `ui/package.json` 里 `gen` / `gen:check` 脚本移除。

## [M3 骨架] - 2026-10-12（本 CHANGELOG 起始条目，对应 `91bbd78` 之后的 M3 提交序列）

见上方 `[未发布]`。M3 出口判据 1–4 全部经测试钉住；判据 5（evals N=12 首跑）
诚实标注"未跑"（本机无凭据），见 `evals/README.md` §M3d。
