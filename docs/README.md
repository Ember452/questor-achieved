# Questor 文档

| 阶段 | 读什么 | 作用 |
| --- | --- | --- |
| 想知道这是什么 | [`../README.md`](../README.md) | 对外定位与三柱 |
| **动手前必读** | [`architecture/overview.md`](architecture/overview.md) | **唯一架构入口**：定位、参照边界、分层与依赖规则、功能地图、数据契约、权限模型、恢复语义、测试与出口判据、里程碑、未决项 |
| 想知道目录怎么摆 | [`architecture/structure.md`](architecture/structure.md) | 物理布局地图：总体结构与各部分结构（目录/职责块级），随里程碑物化 |
| 想知道前端怎么摆 | [`../ui/README.md`](../ui/README.md) | 前端地图：目录职责、mock 与生成物边界、命令、状态归属约束 |
| 想知道某模块怎么设计 | [`architecture/modules/`](architecture/modules/) | 模块内部设计篇（随模块开工落盘；契约仍以 overview §7 §8 与 data-model/protocol 为准） |
| 想知道当前阶段怎么做 | [`plans/development-plan.md`](plans/development-plan.md) | 阶段级开发计划：顺序、阅读地图（去参照项目读什么区域）、各阶段文档产出时点 |
| 想搞清一条链路实际怎么跑通 | [`notes/`](notes/README.md) | 机制解释笔记：预测→验证写法，每条带锚点；锚点过期会被 `check_notes` 判红 |
| 想知道为什么这么定 | [`adr/`](adr/README.md) | 决策记录（编号索引与模板在此） |
| 想知道工程纪律 | [`../AGENTS.md`](../AGENTS.md) | 复用三分法、语义唯一来源、注释与语言标准、护栏测试准入、质量门禁、Git 规矩 |
| 开工边界层任务前 | `specs/`（M1 落盘） | 行为规格表、坑目录 `B-NN`、用例清单 |

## 写作规矩

- **契约唯一来源**：数据模型、状态机、协议以 `architecture/overview.md` §7 §8 及其后续
  展开篇为准，其他文档只引用不复述。
- **先文档后代码**：改契约先改文档并递增版本号，代码跟随；顺序不可反。
- **文档视距冻结**：非当期里程碑的模块内部设计篇不新增、不修订，只能在对应模块开工时改，
  防止用写文档代替交付。
- 每个"已决定"必须能追溯到 ADR 或 overview 条目；每个"没决定"显式写在 overview §13，
  **不许默默替用户选**。
