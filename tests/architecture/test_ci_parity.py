"""跨文件一致性契约：CI 的 `run:` 必须与 justfile 配方逐字相同。

为什么这是契约而不是配置复述：`justfile` 是门禁命令的唯一真相（AGENTS §四、ADR-0009），
而 CI 一旦自带 justfile 里没有的 flag，就会出现"本地绿、CI 红"或"CI 红、本地查不出"——
本仓库已因此翻车两次：把不存在的 `--full-path` 写进 CI（双 OS 全红），
以及 pre-commit 钩子排在 `npm ci` 之前（依赖缺失）。

两个方向都查：
- justfile 配方里的每条门禁命令，必须在某个 workflow 中出现（防漏跑）；
- workflow 里每条门禁形状的 `run:`，必须来自 justfile（防 CI 私加参数）。

负向验证方法（新增/修改本测试后必须实跑一次再复原）：把 ci.yml 任一
`uv run ...` 行改成不存在的 flag，本测试必须失败。
"""

from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]

# 需要与 CI 对齐的配方；setup/fmt/coverage 是本地便利用，check/ci 是聚合入口，不参与比对
# desktop-build 不列入 GATE_RECIPES：它 = ui build + desktop build 两步、本测不拆行
# 无对应的单一 CI 命令；desktop.yml 里两行分分列入 (npm --prefix ui run build
# 已在 types-check 里不写、但 build 配方里已含 uv build；ui/desktop 两行 build 已在
# 下面 workflow_commands 里直接命中。
GATE_RECIPES = (
    "lint",
    "types",
    "test",
    "arch",
    "specs",
    "gen-check",
    "types-check",
    "desktop-test",
    "build",
    "hooks",
)
# 环境准备类步骤：不属于门禁命令，允许只存在于 CI
CI_ONLY_ALLOWED = frozenset(
    {
        "uv sync",
        "uv sync --frozen",
        "npm ci --prefix ui",
        "npm ci --prefix desktop",
    }
)
# 判定"这是门禁命令"的前缀（ADR-0019 后生成链入口从 npm 搬到 node scripts/gen/，前缀同补；
# B8 把 desktop 一侧一并拉进扫描，R-11）。
GATE_PREFIXES = (
    "uv run ",
    "npm --prefix ui run ",
    "npm --prefix desktop run ",
    "node scripts/gen/",
    "uv build",
)


def _justfile_commands() -> dict[str, list[str]]:
    """解析 justfile：配方名 → 其命令行列表。"""
    recipes: dict[str, list[str]] = {}
    current = ""  # 空串表示不在任何配方内；避开 Optional 带来的类型空洞
    for line in (REPO / "justfile").read_text(encoding="utf-8").splitlines():
        head = re.match(r"^([A-Za-z][\w-]*):\s*$", line)
        if head:
            name: str = head[1]
            current = name
            recipes.setdefault(current, [])
            continue
        if current and re.match(r"^\s{4}\S", line):
            cmd = line.strip()
            if not cmd.startswith("@"):  # @ 前缀只是回显控制，不是命令本体
                recipes[current].append(cmd)
        elif current and line and not line.startswith((" ", "#")):
            current = ""
    return recipes


def _workflow_commands() -> list[str]:
    """收集门禁 workflow 里所有 `run:` 的首行命令（本仓库的 run 均为单行门禁命令）。"""
    out: list[str] = []
    for name in (
        "ci.yml",
        "contracts.yml",
        "security.yml",
        "docs.yml",
        "desktop.yml",
    ):
        path = REPO / ".github" / "workflows" / name
        if not path.is_file():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in (doc.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                run = step.get("run") if isinstance(step, dict) else None
                if run:
                    out.append(run.strip())
    return out


def test_every_gate_recipe_command_runs_in_ci() -> None:
    commands = set(_workflow_commands())
    missing = [
        f"{recipe}: {cmd}"
        for recipe, cmds in _justfile_commands().items()
        if recipe in GATE_RECIPES
        for cmd in cmds
        if cmd not in commands
    ]
    assert not missing, "以下 justfile 门禁命令没有任何 CI 步骤执行：\n" + "\n".join(missing)


def test_ci_invents_no_gate_commands_of_its_own() -> None:
    declared = {c for cmds in _justfile_commands().values() for c in cmds}
    orphans = [
        run
        for run in _workflow_commands()
        if run.startswith(GATE_PREFIXES) and run not in declared and run not in CI_ONLY_ALLOWED
    ]
    detail = "\n".join(orphans)
    msg = "CI 里有 justfile 未声明的门禁命令（会造成本地绿、CI 红）：\n" + detail
    assert not orphans, msg
