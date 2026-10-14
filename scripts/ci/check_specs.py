"""specs 资产核查：M1a 出口判据的机械检查（CI 与本地同源）。

检查 docs/specs/pitfalls.md：
- **有效**条目数 >= 下限（默认 50；状态为 moot 的不计入，但**仍占编号**，不回收）；
- 编号 B-01 起连续递增，无跳号、无重复；
- 每条有归属模块与证据列（不允许"某处"）；状态列只能取 open / covered / moot；
- 状态 covered 必须给出对应测试列（不允许空），否则算未回填。
- 证据列必须含一个可定位的文件路径；能本地解析到参照仓时，**核实该文件真的存在**。
  行号不在断言之列：行号会随参照仓的新提交漂移，且核查工具本身会读数出错
  （PowerShell 5.1 的 `Get-Content` 实测把 1076 行的文件读成 1004 行）——
  行号核查一律用 Python `read_text().splitlines()`，不用 shell 数行。见 ADR-0008。

用法：python scripts/ci/check_specs.py [--min 50]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PITFALLS = REPO / "docs" / "specs" / "pitfalls.md"
NON_LOCATABLE = ("某处", "那个文件", "某文件")

# 参照仓的本地根。不写死某台机器的路径：用环境变量指定，未设或不可达时只校形式、
# 不断言文件存在（CI 机器上就是这种情况）。
REF_ROOTS = {
    "wuu": Path(os.environ.get("QUESTOR_REF_WUU", REPO.parent / "wuu-main")),
    "EvoFlow": Path(os.environ.get("QUESTOR_REF_EVOFLOW", REPO.parent / "EvoFlow-main")),
    "FlowCoder": Path(os.environ["QUESTOR_REF_FLOWCODER"])
    if "QUESTOR_REF_FLOWCODER" in os.environ
    else None,
}
BACKTICK = re.compile(r"`([^`]+)`")
VALID_STATUS = ("open", "covered", "moot")
SPECS_DIR = REPO / "docs" / "specs"
_BID = re.compile(r"B-\d+")
_ROW_ID = re.compile(r"^\| (B-\d+) \|")


def _check_evidence(cells: list[str]) -> str | None:
    """校核单条的“证据”列；返回问题描述，None 表示无问题。"""
    paths = [t.split("#")[0] for t in BACKTICK.findall(cells[4]) if ("/" in t or "." in t)]
    if not paths:
        return "证据列没给出可定位的文件路径"
    project = cells[3].split()[0] if cells[3].split() else ""
    root = REF_ROOTS.get(project)
    if root is None or not root.is_dir():
        return None  # 仓根未配置或不可达：只校形式，不断言存在
    for rel in paths:
        if not (root / rel).is_file() and not (root / rel).is_dir():
            return f"引用文件不存在：{project} {rel}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min", type=int, default=50)
    args = parser.parse_args()

    rows: list[tuple[str, str, str]] = []
    entries: dict[str, list[str]] = {}
    for line in PITFALLS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| (B-\d+) \| ([^|]+) \| ([^|]+) \|", line)
        if m:
            rows.append((m.group(1), m.group(2).strip(), m.group(3).strip()))
            entries[m.group(1)] = [c.strip() for c in line.strip().strip("|").split("|")]

    problems: list[str] = []
    numbers = [int(r[0][2:]) for r in rows]
    active = [n for n, c in entries.items() if len(c) < 7 or c[6] != "moot"]
    if len(active) < args.min:
        problems.append(f"有效条目数 {len(active)}（不计 moot）< {args.min}")
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append("编号不连续或有跳号（moot 条目仍应占号，不回收）")
    if len(set(numbers)) != len(numbers):
        problems.append("pitfalls.md 存在重复编号（全局须唯一）")
    for num, module, desc in rows:
        if not module or module.startswith("-"):
            problems.append(f"{num}: 缺归属模块")
        for word in NON_LOCATABLE:
            if word in desc:
                problems.append(f"{num}: 含不可定位表述 {word!r}")
        cells = entries.get(num, [])
        if len(cells) >= 5:
            bad = _check_evidence(cells)
            if bad:
                problems.append(f"{num}: {bad}")
        if len(cells) >= 7:
            if cells[6] not in VALID_STATUS:
                problems.append(f"{num}: 状态列非法 {cells[6]!r}（只允许 open/covered/moot）")
            if cells[6] == "covered" and cells[5] in ("", "待落"):
                problems.append(f"{num}: 状态 covered 但未回填对应测试")

    # 跨文档一致性：behavior-*.md 只能引用 pitfalls.md 已存在的坑号；
    # 其“本区域坑条目”表内编号不得重复（防 limen 九条塌成 B-50、sandbox 撞 B-32 那类）。
    # 语义归属正确性由 port-ledger 人工对账保证，本机械断言只拦“引用不存在”与“表内重复”。
    valid_ids = {r[0] for r in rows}
    for spec in sorted(SPECS_DIR.glob("behavior-*.md")):
        text = spec.read_text(encoding="utf-8")
        for ref in sorted(set(_BID.findall(text))):
            if ref not in valid_ids:
                problems.append(f"{spec.name}: 引用了 pitfalls.md 不存在的坑号 {ref}")
        tail_ids = [m.group(1) for m in (_ROW_ID.match(line) for line in text.splitlines()) if m]
        dups = sorted({x for x in tail_ids if tail_ids.count(x) > 1})
        if dups:
            problems.append(f"{spec.name}: 本区域坑表内编号重复 {dups}（每条须唯一，勿塌成同号）")

    if problems:
        print("check_specs FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"check_specs OK: 有效 {len(active)}/{len(rows)} 条，编号连续，证据可定位")
    return 0


if __name__ == "__main__":
    sys.exit(main())
