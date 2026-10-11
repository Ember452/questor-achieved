# ADR-0008 — 门禁范围、内容一致性与引用核查工具

状态: accepted
日期: 2026-10-11 | 关联: `AGENTS.md` §四、`structure.md` §2.2 §5、`scripts/ci/check_specs.py`、`tests/architecture/`

## 结论

1. **门禁范围 = 全部 Python 产出**：`src tests evals scripts` 四个目录一起进 `just lint` 与 CI。
   范围只写 `src tests` 会让 `evals/`、`scripts/` 里的违规静默存在而 CI 仍绿（本次实测已发生：
   4 个 ruff 错 + 1 个未格式化文件全在 `evals/runner/`，而 CI 与 `just check` 双绿）。
2. **`just check` 必须逐项兑现 AGENTS §四 的四件套**：现定义为
   `lint + types(pyright) + test(pytest) + arch + specs + gen-check + types-check(前端 tsc)`。
   CI 调同一批命令（拆成 job 可以，命令集合不可以不同）。
3. **出口判据要进 CI，不能只在本地自述**：`scripts/ci/check_specs.py` 与前端 `typecheck` 纳入 CI。
   "CI 与本地同源"是 `AGENTS.md` §四 的硬要求，此前只写在注释里、没有兑现。
4. **依赖补齐**：dev 组加入 `pre-commit`（`.pre-commit-config.yaml` 已提交，但 `just setup` 因缺依赖必失败）。
5. **引用核查的工具规范**：核查参照项目的行号/行数一律用 Python `read_text().splitlines()` 或
   .NET `[System.IO.File]::ReadAllLines()`；**禁止用 PowerShell 5.1 的 `Get-Content` 数行或按行号取内容**。
   `check_specs.py` 只断言**文件存在性**与形式可定位性，不断言行号内容——行号会随参照仓新提交漂移。
   参照仓根通过环境变量（`QUESTOR_REF_WUU` / `QUESTOR_REF_EVOFLOW` / `QUESTOR_REF_FLOWCODER`）提供；
   未配置或不可达时只校形式、不误报（CI 机器即此情形）。

## 理由与取舍

范围与内容一致性的代价是 CI 与本地命令变多、偶发失败面变大；换来的是"CI 绿"重新等价于
"仓库合规"——否则门禁给出**假的安全感**，比没有门禁更糟。选择把行号核查交给 Python 而不是
shell，是因为本次实测：同一文件 `Get-Content` 读作 1004 行、`ReadAllLines` 与 LF 计数均为 1076，
差异导致**误判参照项目的引用错位**（后已复验：B-01/B-02/B-03/B-05/B-10 与 `_run_loop` 起点
L289 逐条精确命中）。工具选错会污染资产可信度，而扫描三资产正是全计划的地基。

## 被否决的选项

- **只扩 just、不改 CI**：本地与 CI 会立刻分叉，违反 §四 同源要求。
- **让 `check_specs.py` 断言行号内容**：行号随参照仓演进必然漂移，会把核查变成"定期假失败"。
- **把 pre-commit 从 setup 里删掉以消除失败**：绕过了问题而非修正，且 §四 要求钩子与 CI 同源。
- **为 `just` 缺失静默改用 nox**：属于工具选型变更，须用户裁决（见失效条件）。

## 适用条件与失效条件

**适用**：仓库当前形态（`evals/`、`scripts/` 已存在 Python；CI 为 GitHub Actions；参照仓在本地可寻址）。

**触发重新评审的信号**：
1. 新增任何 Python 顶层目录（如 `plugins/`、`packages/`）→ 必须同步扩门禁范围，否则同类漏洞复现；
2. M2 引入 import-linter 声明式契约后，若与 AST 矩阵重复 → 保留其一并删除另一，避免"两个守卫互相掩盖"；
3. 决定安装 `just` 或改用 `nox` → 记 ADR 并同步 `AGENTS.md` §四 与本 ADR；
4. 参照仓在 CI 不可达成为常态 → 考虑把引用核查降级为"仅存在性抽查 + 本地全量"。
