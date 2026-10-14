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

# ui/ 与 desktop/ 已随 ADR-0040/0044 废弃并从工作树物理移出（快照在 reference-only-archive 分支）。
# 前端类型检查 / 壳侧测 / gen 链的门禁配方在 Phase 2b 照 wuu renderer 重建时一并重建
# （届时与 desktop.yml / contracts.yml 同批恢复，CI parity 测自动重新咬合）。

# schema → 前端类型生成链（R4）已随 ui/ 退役暂停；真相源 src/questor/schemas 保留，
# scripts/gen/types.mjs 输出目标（ui/src/rpc/generated）不存在即无从校验。Phase 2b 重建。

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
# npm audit 行随 ui/ 退役暂停；Phase 2b 新前端落地时恢复。
audit:
    uv run pip-audit --skip-editable

build:
    uv build

# 本地钩子全量跑（CI 同一条）
hooks:
    uv run pre-commit run --all-files --color=never

# gen-check/types-check/desktop-test 随 ui/+desktop/ 移出门禁（Phase 0 归档，见上注）；
# Phase 2b 重建前端时逐项加回，CI parity 测（tests/architecture/test_ci_parity.py）双向盯。
check: lint types test arch specs
    @echo "just check: all green"

ci: check build
