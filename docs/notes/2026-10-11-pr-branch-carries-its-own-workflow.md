# 改了 main 上的 workflow，为什么已开出的 PR 还是红的

日期: 2026-10-11
复核于: 2026-10-12
锚点: .github/workflows/ci.yml, docs/adr/0011-branch-protection-mode.md, docs/adr/0009-gate-entry-just.md

## 我的预测

我把 `.github/workflows/ci.yml` 里的两个 bug（不存在的 pytest 选项、pre-commit 排在 `npm ci` 之前）
修好并推上 main，于是预期：那个 Dependabot 的 `ui-minor` PR 下一次跑 checks 就会变绿。
它还红着，我接着猜是"required check 名字填错了所以永远 Expected"。两个预测都错。

## 实测到的机制

用 SSH 把 PR 分支取下来看它自己那份 workflow，结论一目了然：

```
git fetch origin dependabot/npm_and_yarn/ui/ui-minor-<hash>
git log --oneline -3 FETCH_HEAD          → 基点是 ec6dce6（修 CI 之前的 main）
git show FETCH_HEAD:.github/workflows/ci.yml → 里面仍然是 --full-path 那一行，
                                                pre-commit 仍然排在 npm ci 之前
```

**Actions 执行的是"事件所在 ref"里的 workflow 文件**。PR 分支创建时从 main 切出，那份
workflow 就成了分支里的一个普通文件副本；此后 main 上的修复不会追过去。GitHub 读的是
分支里那一份，所以它跑的仍然是有 bug 的旧命令，报错与我修复前一模一样。

## 差异在哪、为什么

我下意识把 workflow 当成了"服务器上的配置"，其实它是**仓库内容**（version-as-code）。
凡属"配置即代码"的东西都有这个滞后：`.github/workflows/*`、`.pre-commit-config.yaml`、
`pyproject.toml` 里的门禁范围——修 main 只影响**之后**新建的分支与事件。

同一个机制在另一处表现相反：`dependabot.yml` 改成分组 + 屏蔽 major 之后，旧的 7 个 PR
**确实**被关掉了（Dependabot 会按新配置重新评估并放弃不再符合条件的 PR）。所以
"新配置什么时候生效"不能一概而论：**跑 checks 用的是分支里的旧副本，而"要不要开这个 PR"
用的是默认分支上的新配置**。

## 可迁移的结论

看 PR 红的时候，先问一句"它跑的到底是哪一份 workflow"：
`git show <pr-ref>:.github/workflows/<file>` 十秒钟就能确证，比读日志猜原因快得多。
修法也只有一个：**让 PR 分支同步默认分支**（GitHub 的 Update branch，或把 main 并进去），
不要手改 Dependabot 分支——它下次重建会覆盖掉。
