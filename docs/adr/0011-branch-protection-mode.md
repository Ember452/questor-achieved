# ADR-0011 — 分支保护形态：required checks，但不强制 PR

状态: accepted
日期: 2026-10-11 | 关联: `AGENTS.md` §六、`ADR-0008`、`docs/plans/development-plan.md`

## 结论

1. `main` 的保护形态取 **B 方案**：
   - ☑ `Require status checks to pass before merging`（**只在经 PR 合并时生效**）
   - ☑ `Require branches to be up to date before merging`
   - ☐ **不勾** `Require a pull request before merging` —— 保留直接 `git push origin main` 的能力，
     红了我们也能推上去再修。这是单人阶段的自觉取舍：**用点击次数换一点纪律余量**。
2. required 名单（**逐字照抄，不要凭印象加 OS 后缀**）：

   | check 名 | 来自 | 是否矩阵 |
   | --- | --- | --- |
   | `lint` | `ci.yml` job `lint` | 否 → **不带后缀** |
   | `test (ubuntu-latest)` | `ci.yml` job `test` | 是 |
   | `test (windows-latest)` | `ci.yml` job `test` | 是 |
   | `arch` | `contracts.yml` job `arch` | 否 |
   | `gen-check` | `contracts.yml` job `gen-check` | 否 |
   | `audit` | `security.yml` job `audit` | 否（该 workflow 也 `on: pull_request`，故能 report） |

3. 填错名字的后果写在这里供复查：**一个永不 report 的 required 名字会让所有 PR 永久卡在
   "Expected — Waiting for status to be reported"**。本项目 2026-10-11 就因把非矩阵 job 写成
   `lint (ubuntu-latest)` 这类名字而误判过一次"dependabot 的 PR 没绿"。

## 理由与取舍

A 方案（PR-only）更严格，但每次改动都要开分支、建 PR、点合并；单人开发阶段这个成本主要付在
"想快速推进"的时刻，容易反过来诱发绕过保护的行为（直接改保护规则），那比 B 更糟。
B 保留了 required checks 对**外部改动（Dependabot、将来的贡献者）**的约束力，同时不打断本地节奏；
代价很明确：**我们自己的推送不受 CI 结果阻拦**，所以"推之前本地跑全套"从建议升为硬要求
（`AGENTS.md` §四 的四件套 + `just check` 展开式）。

## 被否决的选项

- **A｜PR-only**：多一层点击，且单人自审 PR 的形式意义大于实质；将来有第二个人或开始对外收 PR 时再升。
- **不设 required checks**：等于门禁只靠自觉，而本阶段已经证明"只靠自觉的约束会漏"
  （CI 少跑 pyright、钩子版本与 CI 不一致两次都是这么发生的）。
- **把 `build`/`code-review` 之类不存在的名字填进去**：会永久拦住合并，已在 §3 记录为事故预防。

## 适用条件与失效条件

**适用**：单人维护、当前无外部贡献者、变更以本地节奏推进。

**触发重新评审**：① 出现第二个协作者或开始对外收 PR → 升 A 方案（强制 PR + 至少一人审查）；
② 首次发布/打 tag 前 → 应改为保护 `release` 相关分支并要求 PR；③ 新增 workflow 或 job 改名 →
本表与 GitHub 设置必须同时更新（本表是 required 名单的唯一真相）。
