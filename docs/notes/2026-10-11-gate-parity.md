# 门禁是怎么从"看着一致"变成"真的一致"的

日期: 2026-10-11
复核于: 2026-10-12
锚点: justfile, .github/workflows/ci.yml, tests/architecture/test_ci_parity.py,
      scripts/ci/check_specs.py, .pre-commit-config.yaml

## 我原来的预测

我以为"把 CI 和 `just check` 写成同一批命令"这件事，靠**注释里写一句'与 justfile 同源'**
就成立了；而且我以为给 CI 加几个更好用的 flag（`--output-format=github`、`--full-path`）
不算破坏一致性——"只是让报错更清楚"。

## 实际发生了什么

两条都被推翻，而且都是我自己写的：

1. `--full-path` 在 pytest 9.1.1 **不存在**。我把它写进 CI 时没有本地跑过这条命令。
   结果 ubuntu 与 windows 两个 leg 同时红，报错内容还是一句 usage——
   看起来像环境问题，实际是我造的参数。
2. `pre-commit run --all-files` 我排在 `npm ci --prefix ui` **之前**。而我上一轮刚加的
   gen-check 钩子是 `language: system`、依赖 `ui/node_modules` → 钩子必然在 CI 里炸在
   `ERR_MODULE_NOT_FOUND`。也就是说：我为了"把漂移挡在提交时"加的钩子，
   自己成了 CI 红灯的原因。
3. 更本质的：我给的"修复"（把 pyright、check_specs 加进 CI）本身又是**在 CI 里独造命令**，
   和 AGENTS §四 那句"CI 必须调用同一批命令"互相打脸——那句话只活在注释里。

## 差异在哪、为什么

一致性的定义不能是"两条命令看起来差不多"。我原来允许 CI 带"额外 flag"，
这个口子正是漏掉 `--full-path` 的地方：**任何只存在于 CI 的参数，都不会被本地任何一次运行验证过。**

于是改成两条硬规则：

- **逐字一致**：CI 每个 `run:` 必须等于 justfile 里某条配方命令；反向也查
  （CI 出现 justfile 没有的门禁命令就红）。为此我放弃了 ruff 的 GitHub annotations——
  那是"CI 独有 flag"，而精准报错已经有别的办法拿到（失败时把真实 diff 写进 step summary）。
- **一致性别靠承诺，靠测试**：`tests/architecture/test_ci_parity.py` 解析 justfile 与 workflow，
  两个方向都断言。它属于"跨文件一致性契约"，不是复述字面量。

## 可迁移的结论

写进 CI/钩子/脚本里的任何命令，**必须先原样本地跑一次**；把 CI 当第一次执行环境，
等于把验证成本换成一次全红 + 一次误诊（我第一次就误诊成"行尾问题"）。
凡"两边必须一致"的约束，只有被机器断言时才算存在——这条本仓库已经付过三次学费：
`overview §6 ↔ structure §3` 的模块表、生成物跨平台复现（B-68）、以及这次的 justfile ↔ CI。
