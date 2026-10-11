# tests/integration

集成套件：协议往返、会话恢复、diff 与修订号绑定、审批收紧不可提权
（`docs/architecture/overview.md` §11）。

按 `AGENTS.md` §四，契约/数据模型改动加跑本套件。目录随 M1 契约文档落盘建立用例；
本目录尚无用例时 `pytest tests/integration` 收集 0 条属预期，不作为门禁依据。
