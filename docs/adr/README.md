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
| 0002 | 全量重写策略与 provenance 纪律 | planned（已由 `overview.md` §3 承载内容） |
| 0003 | 仓库边界与依赖拓扑（不依赖参照项目代码） | planned |
| 0004 | 语义唯一来源与 adapter 位置 | planned |
| 0005 | 工作区修订号与 turn↔revision 绑定 | planned |
| [0006](0006-desktop-shell-and-browser-panel.md) | 桌面壳选型与浏览器面板边界（Tauri 优先，镜像而非同页） | accepted |
| [0007](0007-windows-sandbox.md) | Windows 沙箱策略：诚实降级 + 进程树管理，强隔离走可选执行环境 | accepted |
| [0008](0008-gate-scope-and-citation-checks.md) | 门禁范围与内容一致性、引用核查工具规范 | accepted |
| [0009](0009-gate-entry-just.md) | 门禁入口用 just，及本机装不上时的退路 | accepted |
