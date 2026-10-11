# tests/architecture

架构套件：依赖方向（R1）、append-only 不可改写、状态迁移唯一入口
（`docs/architecture/overview.md` §4 §11）。

按 `AGENTS.md` §四，依赖方向与不可变性改动加跑本套件。第一个用例应是最先落地的
R1 依赖方向检查；用例建立前收集 0 条属预期，不作为门禁依据。
