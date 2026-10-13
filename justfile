# Questor 门禁单一入口——CI 必须调用同一批命令（AGENTS.md §四；本地与 CI 不一致视为缺陷）

# just 在 Windows 上默认用 sh 当 shell，而本机没有 sh（实测报
# "could not find the shell `sh`: program not found"）。just 1.58.0 不支持
# 在 set shell 里做条件：`if(...)` 函数式与顶层 `if` 块都报语法错（均实测）。
# 所以这里写死 PowerShell。非 Windows 贡献者把本行改成 ["sh", "-cu"] 即可；
# CI 不调用 just（保留六个独立 required check 的粒度），故不受影响。
set shell := ["powershell.exe", "-NoProfile", "-Command"]

default:
    @just --list

setup:
    uv sync
    uv run pre-commit install

fmt:
    uv run ruff check --fix src tests evals scripts
    uv run ruff format src tests evals scripts

# 范围必须覆盖全部 Python 产出：src（生产码）、tests（测试）、evals（跑批器）、scripts（CI 工具）。
# 只 lint src tests 会让 evals/scripts 里的违规静默存在而 CI 仍绿——M1 复审实测踩过。
lint:
    uv run ruff check src tests evals scripts
    uv run ruff format --check --diff src tests evals scripts
    uv run lint-imports

types:
    uv run pyright

# 前端类型检查（ui + desktop 两侧都入 check；B8 把 desktop typecheck 拉进来，与 desktop.yml 同源）
types-check:
    npm --prefix ui run typecheck
    npm --prefix desktop run typecheck

# Desktop 壳侧测（vitest node env）；不启 GUI，沙箱/CI 可同命。本地与 CI 同一命令。
desktop-test:
    npm --prefix desktop run test

# 一套前端两宿主：ui 先 build 产 dist、desktop 后 build 把 dist 塑进 out/renderer。
# 不进 `check`：build 不验新行为、只多一倍时长；也不入 `desktop.yml` CI（推 future release workflow）。
desktop-build:
    npm --prefix ui run build
    npm --prefix desktop run build

# schema → 前端类型（R4 生成链；真相源 src/questor/schemas，定义点在 scripts/gen/）
gen:
    node scripts/gen/types.mjs

# 生成后 git diff --exit-code 必须为空（R4 的可检查形式）
gen-check:
    node scripts/gen/types.mjs --check

# 依赖方向与三条硬断言（R1；import-linter + AST allow-list 双层）
arch:
    uv run pytest tests/architecture -q

# -rfE 在末尾汇总全部 failed/error；--color=no 保证 CI 日志无 ANSI 噪声。
# 选项改动必须先本地跑过：曾把不存在的 --full-path 写进 CI，双 OS 全红（B-69）。
test:
    uv run pytest -q -rfE --color=no

coverage:
    uv run pytest --cov=src/questor --cov-report=term-missing -q

# 坑目录与笔记核查（scripts/ci 的工具）：条目数、编号连续性、锚点存在性、文档链接
specs:
    uv run python scripts/ci/check_specs.py
    uv run python scripts/ci/check_notes.py
    uv run python scripts/ci/check_docs.py

# 依赖审计（security.yml 同一条；不放进 check 是因为它要联网、不适合每次提交跑）
audit:
    uv run pip-audit --skip-editable
    npm --prefix ui audit --omit=dev

build:
    uv build

# 本地钩子全量跑（CI 同一条）：需先 `just setup` 且 ui 依赖已装（gen-check 钩子依赖它）
hooks:
    uv run pre-commit run --all-files --color=never

check: lint types test arch specs gen-check types-check desktop-test
    @echo "just check: all green"

ci: check build
