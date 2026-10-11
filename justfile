# Questor 门禁单一入口——CI 必须调用同一批命令（AGENTS.md §四；本地与 CI 不一致视为缺陷）
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
    uv run ruff format --check src tests evals scripts

types:
    uv run pyright

# 前端类型检查（无 desktop.yml 之前，先把 tsc --noEmit 接进门禁）
types-check:
    npm --prefix ui run typecheck

# schema → 前端类型（R4 生成链；真相源 src/questor/schemas）
gen:
    npm --prefix ui run gen

# 生成后 git diff --exit-code 必须为空（R4 的可检查形式）
gen-check:
    npm --prefix ui run gen:check

# 依赖方向与三条硬断言（R1；import-linter + AST allow-list 双层）
arch:
    uv run pytest tests/architecture -q

test:
    uv run pytest -q

coverage:
    uv run pytest --cov=src/questor --cov-report=term-missing -q

# 坑目录核查（scripts/ci 的工具）：条目数、编号连续性、锚点存在性
specs:
    uv run python scripts/ci/check_specs.py

build:
    uv build

check: lint types test arch specs gen-check types-check
    @echo "just check: all green"

ci: check build
