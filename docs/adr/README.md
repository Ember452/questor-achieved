# ADR 索引

决策记录。改动数据契约 / 状态机 / 消息协议 / 依赖选型 / 范围砍单前，
先在此处加一条记录，再动代码（规则见 `../../AGENTS.md` §二 §七）。

## 模板

```
# ADR-NNNN — <一句话标题>

状态: proposed | accepted | superseded by ADR-XXXX | deprecated
日期: YYYY-MM-DD | 关联: T-x.x / B-NN / 文档路径

## 结论
一件什么事，选定了什么。

## 理由与取舍
为什么这么定；牺牲了什么换来了什么。

## 被否决的选项
逐条列出，各写一句"为什么不行"，不要写"不合适"。

## 适用条件与失效条件
在什么前提下成立；出现什么信号（依赖变更、平台扩展、上游改动）
必须重新评审本决策。
```

## 编号索引

| 编号 | 标题 | 状态 |
| --- | --- | --- |
| [0001](0001-naming-and-availability.md) | 项目命名、拼写裁决与占用核查 | accepted |
| 0002 | 全量重写策略与 provenance 纪律 | **superseded by [0037]**（转向复用优先；provenance 纪律并入 0037） |
| 0003 | 仓库边界与依赖拓扑（不依赖参照项目代码） | planned |
| 0004 | 语义唯一来源与 adapter 位置 | planned |
| [0005](0005-workspace-revision.md) | 工作区修订号与 turn↔revision 绑定 | accepted（M3d 归档） |
| [0006](0006-desktop-shell-and-browser-panel.md) | 桌面壳选型与浏览器面板边界（Tauri 优先，镜像而非同页） | accepted；壳选型与浏览器面板边界 **superseded by 0030** |
| [0007](0007-windows-sandbox.md) | Windows 沙箱策略：诚实降级 + 进程树管理，强隔离走可选执行环境 | accepted |
| [0008](0008-gate-scope-and-citation-checks.md) | 门禁范围与内容一致性、引用核查工具规范 | accepted |
| [0009](0009-gate-entry-just.md) | 门禁入口用 just，及本机装不上时的退路 | accepted |
| [0010](0010-notes-anchored-and-expiring.md) | 学习笔记：锚点化 + 过期即删 | accepted |
| [0011](0011-branch-protection-mode.md) | 分支保护形态：required checks，但不强制 PR（附 required 名单真相表） | accepted |
| [0012](0012-module-dependency-rulings.md) | gesta 与 capability 的依赖方向裁决（以矩阵为准，回写 overview §6） | accepted |
| [0013](0013-m2-foundation-dependencies.md) | M2.1 地基依赖引入（pydantic v2 / keyring / import-linter） | accepted |
| [0014](0014-run-status-queued-cancelled.md) | 运行状态机补充 queued → cancelled 迁移（data-model v1.1） | accepted |
| [0015](0015-pywin32-job-object.md) | Windows 进程树管理引入 pywin32（平台标记依赖） | accepted |
| [0016](0016-providers-wire-layer.md) | providers 传输层：自建 wire 层 over httpx，不接厂商 SDK | accepted |
| [0017](0017-context-records-in-transcript.md) | 上下文工程事实作为 append-only 记录进会话正文（data-model v1.2） | accepted |
| [0018](0018-prompt-blocks-and-cache-prefix.md) | 提示词类型化分块与缓存前缀（稳定在前） | accepted |
| [0019](0019-generated-artifacts-mechanical-check.md) | 生成链定义点归位与第三方声明生成（含对初稿错话的前提修正） | accepted |
| [0020](0020-interface-surfaces-moved-earlier.md) | 接口面提前：UI 视图注册表骨架与 handler 上下文位（M3） | accepted |
| [0021](0021-m2-exit-split-evals-deferred.md) | M2 出口拆分：evals 对照基线移出 M2.3 + 判据可执行性口径 | accepted |
| [0022](0022-serve-ws-starlette-uvicorn.md) | serve 传输层引入 starlette + uvicorn（仅本地 127.0.0.1） | accepted |
| [0023](0023-m3-transport-ws-only.md) | M3 传输层只落 WS，SSE 推到 M8 | accepted |
| [0024](0024-desktop-shell-deferred-to-m4.md) | 桌面壳 `desktop/src-tauri/` 从 M3 摘出，落 M4/M5 交界（M4 收口再明确为 M5） | accepted；壳选型与排期 **改判 by 0030**（Electron + 提前为 Phase U） |
| [0025](0025-orchestration-domain-and-store.md) | 编排域：Task/Plan/Goal 实体、状态机与独立 append-only store | accepted |
| [0026](0026-vigilia-scheduling-and-sweep.md) | vigilia 调度与清扫语义：声明式触发器 + tick 游标幂等 + 唤醒检查点 | accepted |
| [0027](0027-evidence-minimal-and-export-interface.md) | evidence 最小版：声称 vs 录得的并排核对，export 形状先定死为接口 | accepted |
| [0028](0028-protocol-additive-evolution.md) | 协议演进规则：加性方法/通知不升版本，破坏性改动才升 | accepted |
| [0029](0029-acceptance-loop-evidence-writepoint.md) | 验收闭环：状态机强制、evidence 生产写入点、声称显式绑定 tool_use_id | accepted |
| [0030](0030-desktop-shell-electron-and-ui-track.md) | 桌面壳改判 Electron；界面/桌面壳主线提前为 Phase U（取代 0006 壳选型/浏览器面板边界、改判 0024 排期） | accepted |
| [0031](0031-ui-diff-renderer-and-vitest.md) | Review 面板 diff 渲染器与前端测试面依赖引入（@pierre/diffs + vitest + happy-dom） | accepted |
| [0032](0032-electron-shell-and-toolchain.md) | Electron 桌面壳工具链依赖引入（electron + electron-vite + electron-builder；`desktop/` 与 `ui/` 各自一份 lockfile） | accepted |
| [0033](0033-engine-contract-as-m6-entry-gate.md) | 引擎契约提取：原定“列为 M6 准入”→现改判为随 Phase 2a 落薄契约 | accepted（2026-10-14 改判；参数化套件仍等第二实现者） |
| [0034](0034-longrun-driver-host-ownership.md) | 长跑驱动的宿主归属 | accepted（A/B/C 因长任务面后置 by [0043] 作废；“降级必须握手可见”转为 Phase 2a 硬约束） |
| [0035](0035-review-diff-authoritative-source.md) | Review 的 diff 权威源 | **superseded by [0045]**（照 wuu 双源，采集点在壳侧） |
| [0036](0036-app-server-split-timing.md) | AppServer 拆分时机 | **withdrawn by [0037]**（重写时按域分文件 + 方法表单一来源） |
| [0037](0037-reuse-first-over-rewrite.md) | 复用优先取代全量重写（母本 wuu 逐文件移植 + MIT 署名） | accepted |
| [0038](0038-wuu-single-anchor.md) | wuu 单锚；EvoFlow 降后期规格；FlowCoder 退出 | accepted |
| [0039](0039-appcontainer-windows-upgrade.md) | AppContainer 列为 Windows 写隔离后期升级路径（改判 0007） | accepted |
| [0040](0040-frontend-in-desktop-renderer.md) | 前端归属改判：渲染层回归 desktop/src/renderer，废弃 ui/ | accepted |
| [0041](0041-session-sqlite-authority.md) | 会话存储权威源 = SQLite 库（改判 JSONL 唯一真相源） | accepted |
| [0042](0042-protocol-vocabulary-align-wuu.md) | 协议词表取齐 wuu app-server | accepted |
| [0043](0043-longtask-layer-deferred.md) | 长任务/编排/验收层后置为 Phase 6 | accepted |
| [0044](0044-disposition-map-and-adversarial-rule.md) | 现有实现处置地图 + 对抗套件与代码废弃相容规则 | accepted |
| [0045](0045-review-diff-dual-source.md) | Review/diff 双源归属：盘态真相归壳侧 GitService | accepted |
