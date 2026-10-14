# ADR-0033 — 引擎契约提取列为 M6 准入条件（不再追认"随 M2 物化"）

状态: proposed（待用户裁决）
日期: 2026-10-13 | 关联: `docs/plans/development-plan.md` Phase M6、`tests/contract/README.md`、
`AGENTS.md` §五 出口判据、structure §11 M6 行、overview §11

## 结论

1. 撤销 M1 复审当时那句"用例随 M2 引擎物化首批落地"的口头承诺，把
   **`engine/contract/` + `tests/contract/` 参数化套件**正式定为 **M6 的第一个任务**，
   并且是 M6 的**准入门禁**：契约测试对内建引擎未跑绿，不许开始写任何外部适配器。
2. 契约的最小面按计划已有的边界定义取（RunTurn / Interrupt / Close + 线程绑定 +
   resume），实现体在 `engine/loop.py`，声明体在 `engine/contract/`。
3. M5 收口至 M6 开工之间**不做**"先把 Protocol 类骨架摆出来"的中间态。

## 理由与取舍

- **实测现状**（本 ADR 落笔前复核）：`src/questor/engine/` 只有 constants / conversation /
  events / loop / model / output_recovery / `__init__` 七个文件，**没有 `contract/`**；
  `tests/contract/` 只有一个 README.md、0 条用例；`pytest tests/contract` 收集 0 条。
  而 M1 的勾销记录写的是"✅ 已按 §11 占位例外建立"——**建了目录不等于落了套件**，
  洞正是这样过掉门禁的。
- **为什么不提前做骨架**：`tests/contract/README.md` 自己写了判据——"先写这套测试，
  再写第二个引擎，否则契约会退化成'内置引擎私有行为的复述'"。在第二个引擎存在之前，
  任何参数化套件都只能拿内建引擎自己当被测对象，绿了也不证明契约可用；只会造出一个
  看似有契约、实则锁死内建形状的假门。代价是承认：M2–M5 期间契约面一直在裸奔。
- **为什么必须是准入条件而非并行任务**：`engine/loop.py`（778 行）已直接
  `from questor.gesta import load_thread`、`from questor.gesta.writer import ThreadWriter`、
  `from questor.prompts import render, summary_assembly, system_assembly`。每多一个里程碑，
  "从 loop 里逆向出契约"的成本单调上升。把它排在 M6 内部、适配器之后，等于把逆向
  成本推到最高点。
- **牺牲了什么**：M6 的可见交付（引擎选择 UI、四态目录）要晚一个身位；换来的是
  "换引擎 = 替换实现而非改上层"这条本项目主门真正被机械验证过。

## 被否决的选项

- **现在就抽契约**：没有第二实现者当考官，抽出来的只会是内建引擎的私有形状复述，
  与本 ADR 想防的病同源（见上）。
- **推到 M6 之后（等真需要外部引擎时再说）**：那时 `engine/loop.py` 已再长三个里程碑，
  逆向成本最高，且大概率触发"为省事直接在适配器里绕过契约"的退路。
- **只做 Protocol 类型声明、不写测试**：`Protocol` 是结构 typing，pyright 只能证明
  形状相容，证明不了 turn 生命周期、事件顺序、插话只在步前边界消费（B-67）、
  stop/resume/fork 的可观察语义——而这些正是契约的内容，缺一半就是假门。
- **把 `tests/contract/README.md` 直接删掉当没承诺过**：承诺消失、洞还在，
  且失去唯一记录着"为什么它是主门"的文字。

## 适用条件与失效条件

**适用**：M6 全程。落地形式 = `engine/contract/` 声明 + `tests/contract/` 参数化
（参数对象 = 内建引擎 + 各外部适配器），并按 AGENTS §四 附每条护栏的负向验证输出。

**触发重新评审**：
1. 若决定引入任何外部引擎适配器而契约套件尚未对内建引擎跑绿 → 停下，本 ADR 的
   准入条件优先于适配器；
2. 若 M6 被整体延后（`development-plan.md` 横切规则 5 的砍单预案：M6 受阻整体延后），
   则本条件随之后移，但**不得静默撤销**——需在计划里显式记一行；
3. 若 `engine/loop.py` 与 gesta/prompts 的耦合面继续增长（新增直接 import），
   提取成本判据需重估。
