"""架构守卫：R1 依赖方向的 AST allow-list 检查（tests/architecture 首个可执行门禁）。

机制参照 FlowCoder `tests/architecture/test_dependency_direction.py`（ast.parse 收集
顶层 questor.* 导入，对 allow-list 求违规交集）。与 import-linter 的分工：

- 本测试：逐模块 allow-list 矩阵（structure.md §5 表直译），对**已存在**的模块生效，
  模块随里程碑物化后自动纳入检查——新仓库 0 违规起步，不设 baseline；
- import-linter（layers/forbidden 声明式契约）：M2 随首批真实模块引入
  （structure.md §5 预案："受阻则自写 AST 遍历"——当前模块未物化，声明式契约
  无检查对象）。

规则即现状：本表锁定 structure.md §5 的依赖矩阵；矩阵改动必须先改 structure.md
再改这里的 ALLOWED_IMPORTS（AGENTS §七：先文档后代码）。

三条硬断言（append-only 不可改写、状态迁移唯一写入入口、权限判定无绕过路径）随
gesta/engine/limen 模块物化（M2）落为本目录独立测试。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "questor"

# structure.md §5 依赖矩阵直译。stdlib 不在检查范围。
ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "limen": frozenset({"schemas"}),
    "state": frozenset({"schemas"}),
    "version": frozenset({"schemas"}),
    "capability": frozenset({"schemas"}),
    "config": frozenset({"schemas", "state"}),
    "secrets": frozenset({"schemas", "state"}),
    "tools": frozenset({"limen", "state", "config", "schemas", "prompts", "review", "workspaces"}),
    "review": frozenset({"limen", "state", "schemas", "gesta"}),
    "worktree": frozenset({"limen", "state", "schemas"}),
    "workspaces": frozenset({"limen", "state", "schemas"}),
    "gesta": frozenset({"schemas", "state", "config"}),
    "context": frozenset({"schemas", "gesta", "providers"}),
    "providers": frozenset({"schemas", "state"}),
    "engine": frozenset(
        {"tools", "limen", "context", "gesta", "providers", "schemas", "prompts", "state"}
    ),
    "habena": frozenset({"engine", "gesta", "schemas"}),
    "vigilia": frozenset({"engine", "gesta", "schemas", "state"}),
    "evidence": frozenset({"review", "tools", "gesta", "schemas"}),
    "sessiontrace": frozenset({"gesta", "schemas"}),
    "orchestration": frozenset(
        {"engine", "vigilia", "gesta", "context", "schemas", "prompts", "state"}
    ),
    "skills": frozenset({"schemas"}),
    "mcp": frozenset({"schemas"}),
    "hooks": frozenset({"schemas"}),
    "extensions": frozenset({"schemas"}),
    "serve": frozenset(
        {
            "orchestration",
            "habena",
            "sessiontrace",
            "vigilia",
            "evidence",
            "engine",
            "tools",
            "review",
            "context",
            "gesta",
            "limen",
            "providers",
            "worktree",
            "workspaces",
            "config",
            "state",
            "secrets",
            "capability",
            "version",
            "schemas",
            "prompts",
            "skills",
            "mcp",
            "hooks",
            "extensions",
        }
    ),
    # version 是叶模块（只读 VERSION），cli 的 `questor version` 需要它；structure §5 已同步
    "cli": frozenset({"serve", "engine", "providers", "config", "schemas", "version"}),
    "testenv": frozenset({"*"}),  # 仅测试基建；生产代码禁止 import（反向由评审保证）
    "schemas": frozenset(),
    # prompts 只取 schemas 的 wire 类型（PromptBlock/PromptAssembly 等，ADR-0018）：
    # 类型住无依赖层，装配行为住 prompts，避开 providers 反向 import prompts。
    "prompts": frozenset({"schemas"}),
}


def _top_level_questor_imports(path: Path) -> set[str]:
    """收集一个 .py 文件里 questor.* 的顶层模块名。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:  # pragma: no cover - 语法错误由 lint 层先行拦截
        raise AssertionError(f"无法解析 {path}: {e}") from e
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "questor" and len(parts) > 1:
                    found.add(parts[1])
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if node.level == 0 and parts[0] == "questor" and len(parts) > 1:
                found.add(parts[1])
    return found


def test_module_imports_stay_within_allow_list() -> None:
    """每个已物化模块的 questor.* 顶层导入必须落在 allow-list 内（R1 可执行形式）。"""
    violations: list[str] = []
    checked: list[str] = []
    for module_dir in sorted(SRC.iterdir()):
        if not module_dir.is_dir():
            continue
        # 只把"真实含 .py 的目录"当模块：__pycache__ 之类字节码噪声目录
        # （import questor 即会产生）不是顶层包，不参与登记检查
        if not any(module_dir.rglob("*.py")):
            continue
        module = module_dir.name
        if module not in ALLOWED_IMPORTS:
            violations.append(f"{module}: 新顶层包未登记——先在 structure.md §5 与 overview §6 登记")
            continue
        allowed = ALLOWED_IMPORTS[module]
        for py in module_dir.rglob("*.py"):
            # 自引用（包内 __init__ 导入自己的子模块）恒允许；"*" 只对 testenv 基建生效
            found = _top_level_questor_imports(py) - {module}
            if "*" in allowed:
                bad: set[str] = set()
            else:
                bad = found - allowed
            if bad:
                rel = py.relative_to(REPO_ROOT)
                violations.append(f"{rel} -> {sorted(bad)}（允许: {sorted(allowed)}）")
            if found:
                checked.append(f"{module}:{py.name}")
    # 守卫测试自身的负向性说明：本测试在"存在 questor 导入"时才有约束力；
    # 若 SRC 下没有任何 questor.* 交叉导入，测试仍通过——这是 0 违规起步的预期状态。
    # 因此本测试只在 ALLOWED_IMPORTS 与被测模块同时存在时才有意义，
    # 它的真负向证明由下方 test_reverse_guards_have_teeth 提供。
    assert not violations, "依赖方向违规（R1）:\n" + "\n".join(violations)


def _prod_files() -> list[Path]:
    """src/questor 下的生产文件；排除 testenv 自身（它正是被守卫的对象）。"""
    return [p for p in SRC.rglob("*.py") if p.parts[-2] != "testenv"]


def test_production_code_never_imports_testenv() -> None:
    """反向守卫：`questor.testenv` 只允许被测试 import（fake_home 模块文档声称的那条）。

    这条本身可负向：在 src/questor 下临时写一行 `from questor.testenv import fake_home`
    即会失败——不依赖"是否已有交叉导入"这种前提。
    """
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _prod_files()
        if "testenv" in _top_level_questor_imports(p)
    ]
    assert not offenders, "生产代码 import 了测试基建: " + ", ".join(offenders)


def test_matrix_has_no_bidirectional_edges() -> None:
    """禁环：矩阵不得存在双向允许（A↔B 互为可依赖即构成环）。

    M1 复审实测：`serve` 曾允许 import `cli` 而 `cli` 允许 import `serve`，
    两张允许表都不报违规，但代码可以形成环。本断言把"禁环"从口头规则
    变成对矩阵自身的检查（不依赖实现代码是否存在）。
    """
    cycles: list[str] = []
    for module, allowed in ALLOWED_IMPORTS.items():
        if "*" in allowed:
            continue
        for target in allowed - {"schemas"}:
            back = ALLOWED_IMPORTS.get(target)
            if back is not None and module in back:
                cycles.append(f"{module} -> {target} -> {module}")
    assert not cycles, "依赖矩阵存在双向允许（环）:\n" + "\n".join(sorted(set(cycles)))


def test_reverse_guards_have_teeth() -> None:
    """确认反向守卫确实能咬人：它必须正在检查至少一个生产文件，而不是空转。"""
    checked = _prod_files()
    assert checked, "src/questor 下没有可检查的 .py 文件，反向守卫为空转"
    # ALLOWED_IMPORTS 必须覆盖全部已物化模块，否则新模块会绕过矩阵（静默放行）
    materialized = {p.name for p in SRC.iterdir() if p.is_dir() and not p.name.startswith("__")}
    assert materialized <= set(ALLOWED_IMPORTS), (
        f"未登记的模块: {sorted(materialized - set(ALLOWED_IMPORTS))}"
    )
