# Questor 文档

| 阶段 | 读什么 | 作用 |
| --- | --- | --- |
| 想知道这是什么 | [`../README.md`](../README.md) | 对外定位与三柱 |
| **动手前必读** | [`architecture/overview.md`](architecture/overview.md) | **唯一架构入口**：定位、参照边界、分层与依赖规则、功能地图、数据契约、权限模型、恢复语义、测试与出口判据、里程碑、未决项 |
| 想知道目录怎么摆 | [`architecture/structure.md`](architecture/structure.md) | 物理布局地图：总体结构与各部分结构（目录/职责块级），随里程碑物化 |
| 想知道前端怎么摆 | [`architecture/structure.md`](architecture/structure.md) | 渲染层目标态住 `desktop/src/renderer`（ADR-0040，照 wuu 重搭）；旧 `ui/`、`desktop/` 已废弃并移出工作树，快照在 `reference-only-archive` 分支 |
| 想知道某模块怎么设计 | [`architecture/modules/`](architecture/modules/) | 模块内部设计篇（随模块开工落盘；契约仍以 overview §7 §8 与 data-model/protocol 为准） |
| 想知道当前阶段怎么做 | [`plans/phase-a-mvp.md`](plans/phase-a-mvp.md) | A 阶段纵向切片计划（Phase 1–4）；旧 M 系列 `development-plan.md` 已标历史，不得作实现依据 |
| 想知道总计划与阶段提示词原文 | [`plans/2026-10-13-wuu-alignment-master-plan.md`](plans/2026-10-13-wuu-alignment-master-plan.md) | 母计划（自计划缓存区归档入库）：全局不变量 §0、复刻五机制 §1.5、exe 三门槛 §1.6、扩展缝 §1.7、缺陷台账 §9、已否方案 §10、各阶段提示词；**计划态快照，进度以 `phase-a-mvp.md` + `research/port-ledger.md` 为准** |
| 想搞清一条链路实际怎么跑通 | [`notes/`](notes/README.md) | 机制解释笔记：预测→验证写法，每条带锚点；锚点过期会被 `check_notes` 判红 |
| 想知道为什么这么定 | [`adr/`](adr/README.md) | 决策记录（编号索引与模板在此） |
| 想知道工程纪律 | [`../AGENTS.md`](../AGENTS.md) | 复用优先的母本移植纪律、语义唯一来源表、注释与语言标准、护栏测试准入、质量门禁、Git 规矩 |
| 开工边界层任务前 | [`specs/`](specs/README.md) | 行为规格表 `behavior-*.md`、坑目录 `B-NN`（`cases-*.md` 用例清单已按 ADR-0037 取消） |

## 写作规矩

- **契约唯一来源**：数据模型、状态机、协议以 `architecture/overview.md` §7 §8 及其后续
  展开篇为准，其他文档只引用不复述。
- **先文档后代码**：改契约先改文档并递增版本号，代码跟随；顺序不可反。
- **文档视距冻结**：非当期里程碑的模块内部设计篇不新增、不修订，只能在对应模块开工时改，
  防止用写文档代替交付。
- 每个"已决定"必须能追溯到 ADR 或 overview 条目；每个"没决定"显式写在 overview §13，
  **不许默默替用户选**。
