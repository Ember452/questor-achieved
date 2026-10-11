# ADR-0014 — 运行状态机补充 queued → cancelled 迁移

状态: accepted
日期: 2026-10-11 | 关联: `data-model.md` §3.1（v1.0 → v1.1）、`gesta/transitions.py`、M2.2 engine

## 结论

data-model §3.1 的运行状态机原图只有 `queued → running → (终态|旁态)`。补充一条迁移：
**`queued → cancelled`**——尚未起跑的运行可以取消，不必也不得伪造一个 `running` 起点。
`data-model.md` 递增到 v1.1；`gesta/transitions.py` 的白名单表与本图逐字对齐。

## 理由与取舍

- 排队中的 turn 被用户撤回/取消是真实操作流。若白名单禁止 queued → cancelled，
  engine 只能让 run 先迁到 running 再迁 cancelled——那是**对状态机撒谎**：
  进程从未起跑，却留下 running 历史，审计面出现假事实（违反铁律 1）。
- 代价：白名单多一条边；终态不可变、旁态必经 running 的既有约束全部不变。

## 被否决的选项

- **保持 v1.0 白名单，M2.2 用 running→cancelled 绕行**：两套真相——图上没有的迁移
  出现在代码里，架构断言失去意义。
- **queued → failed**：取消不是失败，失败是引擎执行后的结果语义。

## 适用条件与失效条件

**适用**：gesta 状态机白名单与未来 engine 的取消传播（M2.2 起长期有效）。

**触发重新评审**：若出现"queued 运行必须先起跑才能定序"的语义需求（如审批占用 run），
重新审视该迁移。
