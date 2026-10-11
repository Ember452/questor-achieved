# ADR-0009 — 门禁入口用 `just`，以及本机装不上时的退路

状态: accepted
日期: 2026-10-11 | 关联: `AGENTS.md` §四、`structure.md` §2.2、`justfile`、`ADR-0008`

## 结论

1. 门禁的**唯一入口是 `justfile`**（`just check` / `just test` / `just gen` / `just build`），
   CI 调用其中同一批命令（`ADR-0008` 已把范围与内容对齐）。
2. **本机没有 `just` 时的退路**：按 `justfile` 里 `check` 配方列出的命令**逐条手动执行**——
   命令清单的唯一真相是 `justfile` 本身，**不再另写一份 ps1/py 包装**（两份定义必然漂移，
   这正是本项目最反对的"同一事实两套真相"）。
3. 换 `noxfile.py` 或 `Makefile` 的门槛：只有当 `just` 在**多数开发环境都拿不到**时才换，
   换时须记一条新 ADR 并同步 `AGENTS.md` §四、`structure.md` §2.2 与 CI。

## 为什么是 just（而不是"随便跑几条命令"）

| 理由 | 说明 |
| --- | --- |
| **消灭参数漂移** | 四条门禁各有参数（`--check`、`-q`、目录范围）。没有单一入口时，本地跑的和 CI 跑的会悄悄不同——本项目已经因为"CI 少跑 pyright、钩子版本与 CI 不一致"各踩过一次 |
| **门禁可被引用** | 文档与 commit 里能写"跑 `just check`"，比贴四行命令更不易过时；`AGENTS.md` §四 才有一句可核查的 DoD |
| **跨平台单文件** | Windows 上 `make` 需要额外兼容层，`just` 是单个原生二进制、语法上就是"命令别名表"，不承担构建依赖图这类我们不需要的问题 |
| **零依赖侵入** | 不进 `pyproject`、不装 Python 依赖、不污染 venv；`nox` 则会给仓库再加一层 Python 工具链与其依赖 |
| **够用就停** | 我们没有"依赖图/增量构建"需求（任务都是全量快跑），所以不需要 make/just 之外的构建系统 |

## 当前实况（诚实记录）

**这台机器上 `just` 仍不可用**：`winget install Casey.Just` 能找到包（1.58.0）但下载
GitHub Release 被网络拦截（`InternetOpenUrl() failed. 0x80072f19`）；`cargo`/`choco`/`scoop`
均未安装；PyPI 上名为 `just` 的包**无法核实是同一软件**（查询时 TLS 超时），因此**不装未知来源**。

后果与处置：`just check` 这条出口判据（"本地与 CI 同源"）目前只能由 **CI 侧**证明——
`ci.yml` 的 `lint` job 已按同一批命令逐条执行，并额外跑 `pre-commit run --all-files`。
本机恢复 `just` 的方法（任一）：浏览器下载 `just` 的 Windows zip 解压入 PATH，
或给 `winget`/终端配置可达 GitHub 的代理后重试 `winget install --id Casey.Just -e`。

## 被否决的选项

- **现在换 nox**：为一个"本机暂时装不上"的问题给仓库加一层 Python 工具链与依赖，
  代价大于收益；且 `justfile` 已是可读的纯命令清单，退路成本极低。
- **写 `scripts/ci/check.ps1` 复刻 just 任务**：会出现两份门禁定义，改一处忘另一处——
  正是本项目反复修的那类缺陷。
- **让 `just setup` 继续引用不存在的 pre-commit**：上一轮已修（依赖已补），此处仅记录因果。

## 适用条件与失效条件

**适用**：单人开发 + CI 为 GitHub Actions；任务数量在十条以内、无需依赖图。

**触发重新评审**：① 需要在任务间表达依赖关系（如"先 build 前端再 package 桌面"）→ 评估
`just` 的 dependencies 语法是否够用，或转 nox；② 团队里多数人环境拿不到 `just`；
③ 出现需要跨 OS 的复杂打包脚本链 → 那属于 `desktop/` 工程脚本，不是门禁入口。
