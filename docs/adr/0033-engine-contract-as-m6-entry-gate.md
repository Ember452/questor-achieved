# ADR-0033 — 引擎契约提取：原定“列为 M6 准入”，现改判为随 Phase 2a 落薄契约

状态: accepted（2026-10-14 改判；原状态 proposed 待用户裁决）
日期: 2026-10-13 | 改判: 2026-10-14 | 关联: 母计划 `docs/plans/2026-10-13-wuu-alignment-master-plan.md`
§1.7 缝 1、`docs/plans/phase-a-mvp.md` Phase 2a、`tests/contract/README.md`、
`AGENTS.md` §五 出口判据、`structure.md` §3（原写的 development-plan M6 / structure §11 M6 行已随
M 系列作废，引用换成现行文档）

## 改判记录（2026-10-14，母本对齐转向后）

**本 ADR 的“后移到 M6”结论作废**，改为：引擎薄契约（`EngineID/TurnInput/EventSink/`
`ApprovalHandler/TurnResult/Session/Descriptor`）**随 Phase 2a 一起落地**，位置
`src/questor/engine/contract.py`。

为何改：原结论依据的两条前提在转向后都不成立——
1. 原怕的是“在第二个引擎存在前抽契约只会复述内建私有形状”。母计划 §1.7 缝 1 要的**不是多引擎**，
   而是“将来接外部引擎宿主（codex/claude CLI）时无冲突接入”的那条**命名缝**；保住它=不删符号，
   成本近于零，而“删了再补”是重写。
2. 原理由里“从 loop 逆向出契约的成本单调上升”恰好指向相反的做法：Phase 2a 正是循环**推倒重建**
   的唯一时刻，此时先定契约比事后逆向便宜一个数量级。本 ADR 用来否定“先摆 Protocol 骨架再说”
   这种中间态，而该风险在重建场景下不存在（新旧不同批，并行不会发生）。

**仍然保留的本 ADR 结论**（未被改判推翻）：
- `tests/contract/` 的参数化套件（拿两个实现当被测对象）仍不得在无第二实现者时假绿——Phase 2a
  只交“薄契约 + 内建引擎的单实现回放”；参数化套件等第二个引擎宿主出现时再开，否则契约会退化成
  内置引擎私有行为的复述（那句判据原样有效）。
- “建了目录不等于落了套件”这条教训有效：本 ADR 因此要求契约声明与配套测试**同批落地**，
  不得先建空目录再在台账上打勾。

**当时引用的“实测现状”已过期，就地订正（不删原文、只标日期）**：本 ADR 落笔时写的
`engine/` 只有七文件无 contract、`tests/contract/` 只有一个 README.md 且收集 0 条，属 2026-10-13 状态；
2026-10-14 Phase 1 已落 `tests/contract/{test_replay_wuu_frames,test_replay_control_plane}.py` +
两份 wuu 真实 golden（该套件现绿）。engine 侧七文件仍在，契约声明由本改判补上。

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
