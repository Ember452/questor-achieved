# Questor 门禁单一入口——CI 必须调用同一批命令（AGENTS.md §四；本地与 CI 不一致视为缺陷）
default:
    @just --list

setup:
    uv sync
    uv run pre-commit install

fmt:
    uv run ruff check --fix src tests
    uv run ruff format src tests

lint:
    uv run ruff check src tests
    uv run ruff format --check src tests

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

build:
    uv build

check: lint arch gen-check
    @echo "just check: all green"

ci: check coverage build
