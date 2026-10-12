# evals —— Questor 对照评测

本目录是**公开证据库**：任何 README、release note、产品页不得引用没有
`results/` 支撑记录的结果。纪律移植自 wuu `evals/README.md`（2026-10-11 实测摘录）。

## 纪律（不可协商）

1. **公开结果五要件**：符合 `result.schema.json` 的 `result.json`、精确 prompt 或
   case 定义、原始机器可读报告、grader 输出与复现脚本、每个 artifact 的 sha256。
2. **失败也要发布**（"Publish failures and errors, not only successful runs"）；单次
   运行只能是 case study，性能/成本结论需重复运行。
3. **比较规则**：所有被测者用同一 case、同一 prompt、同一 fixture commit、同一
   timeout、同一 grader；记录模型设置、重试、工具权限、硬件、版本/commit、token、
   时长、成本来源。
4. **`results/` 不可变**：目录按 `YYYY-MM-DD/<run-id>/` 组织，被公开引用后不可修改，
   重跑发新目录；**不放示例分数**（模板容易被误当证据）。
5. **禁发**：API key、凭据、个人数据、私有仓库内容、隐藏模型推理；redaction 必须记录。
6. **基线**：FlowCoder 为主（同语言、可插拔），EvoFlow 按任务类型可选；wuu 不作基线
   （Go 工具链与引擎依赖使评测脚手架成本高于收益，见 structure.md §8）。

## 对照评测的 N

**N = 12**（4 可见 + 4 干预 + 4 验证），2026-10-11 钉死于 `tasks/tasks.json`。
development-plan 中所有"与参照实现同 N 个真实任务"一律指这 12 个。任务定义变更
须在本 README 变更记录处留痕，且**基线必须用新任务集重跑**。

## 布局

```
evals/
├── tasks/tasks.json        # 12 个任务定义（pillar 覆盖三柱；M1 只定义不实现）
├── runner/                  # 被测者插拔协议：Solver/Executor/Grader + 失败四分类
│   ├── protocol.py
│   └── failure_tax.py
├── results/                 # YYYY-MM-DD/<run-id>/，不可变（results/README.md）
└── result.schema.json       # 结果记录 schema（wuu 12 顶层字段 + case.pillar）
```

对照跑法：runner 只做 `Setup → session.ask(prompt) → Executor/Grader → record`；
Questor agent 与 FlowCoder agent 各写一个满足 `Solver` 协议的 adapter；同任务喂
两个 solver，各产出一份 result.json（失败也发布），共用 failure_tax 四分类对齐
失败率语义，对比报告给逐任务通过矩阵。

## 可比性口径（ADR-0021：2026-10-12 定）

"失败率不高于参照"只在这些条件下才是可执行的判据，否则它会退化成无法验证的口号：

1. **可比集**：双方都能以纯文件 + 路径门档跑通的任务（Questor `standard` 档 vs
   FlowCoder 非交互模式），逐任务同 prompt、同 fixture commit、同 timeout、同 grader。
2. **`not_in_baseline`**：需要 Docker/沙箱才能安全执行的任务显式标注不参与基线对比
   （Questor 侧沙箱属 M8）——**标注而非剔除**，不让它从判据里悄悄消失。
3. **`not_comparable`**：干预柱任务（插话/接管）——FlowCoder 的 `-p` 非交互模式没有
   插话通道，只发 Questor 侧结果并标此注，不猜分。
4. **档位映射表**：FlowCoder 的权限档是六档
   （`default|acceptEdits|plan|bypassPermissions|custom|dontAsk`），Questor 是三档；
   adapter 必须走显式映射表并声明"映射不承诺等价保护"（与 M6 引擎权限映射同一口径，
   2026-10-12 实测：`flowcoder --mode read_only` 直接报参数错）。
5. **跑批时点**：对照基线首跑不卡 M2.3 出口，挂在 M3 出口前（ADR-0021）。

## 变更记录

- 2026-10-11：骨架建立；N=12 钉死；任务主题定稿（tasks/tasks.json）。
- 2026-10-12：新增"可比性口径"（ADR-0021）；对照基线首跑移出 M2.3 出口。
