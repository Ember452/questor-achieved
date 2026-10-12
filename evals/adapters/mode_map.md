# 档位映射表（Questor ↔ FlowCoder 对照评测用）

ADR-0021 明写"adapter 必须走显式档位映射表并声明'映射不承诺等价保护'"。本表就是那份
映射：Questor `PermissionMode` 三档 vs FlowCoder 六档模式。

| Questor | FlowCoder 非交互 | 语义对齐？ | 已知不保护 |
| --- | --- | --- | --- |
| `read_only` | `--mode dontAsk`（或 `default` + 拒所有 edit） | 部分 | FlowCoder 没有"读只限注册根"的边界，`dontAsk` 只关弹窗；Questor 的 `read_only` 是 limen 硬闸（B-50） |
| `standard` | `--mode default` | 部分 | Questor `standard` = limen 路径门 + 危险命令守卫 + 敏感路径恒开；FlowCoder `default` 只是"每次问"的弹窗模式，路径门不在同一层 |
| `unconfined` | `--mode bypassPermissions` | 部分 | Questor 敏感路径守卫在 `unconfined` 仍在（B-54 写恒拒），FlowCoder `bypassPermissions` 是全放开 |
| — | `--mode acceptEdits` | 不映射 | Questor 没有"自动接编辑但仍问命令"这一档 |
| — | `--mode plan` | 不映射 | 计划模式属 M4 orchestration，Questor 三档里没有 |
| — | `--mode custom` | 不映射 | 自定义规则组属 M7 extensions |

**2026-10-12 实测**：`flowcoder --mode read_only` 直接报参数错——FlowCoder 不认这个
字面。上表的"Questor→FlowCoder"列是**语义近似**，不是命令行参数。跑评测时 adapter
按上表把 Questor 档翻成 FlowCoder 参数组合。

**不承诺等价保护**：三档 × 任务的通过矩阵只在"Questor 侧的行为契约成立"意义上可比；
FlowCoder 的六档实际语义（尤其弹窗、`plan` 模式的路径门细节）与 Questor 的 limen 单门
不同。**跑失败也发布**（`evals/README.md` 纪律 2），失败原因按 `failure_tax.py` 四分类。

## M3d 首跑状态（诚实标注）

- **时间**：2026-10-12
- **状态**：**未跑**（本机 `QUESTOR_MODEL_API_KEY` 未配 & 未确认 FlowCoder 侧凭据可用）
- **出口判据 5** 因此记为 **pending**：ADR-0021 明写"基线跑批不阻塞合入只阻塞 M3
  出口"；本仓库把 M3 出口 5 的达成推到"凭据可用后跑一次 `just evals-baseline`"
  之时（`evals/results/YYYY-MM-DD/` 落 `result.json`，五要件齐）。
- **不做**的事：为凑数用假端点跑一遍并写"通过"——违反 evals README 纪律 1 与
  overview §11 的"用基准对比代替'代码看起来一样'作为可信证据"。
