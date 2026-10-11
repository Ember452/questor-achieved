"""specs 资产核查：M1a 出口判据的机械检查（CI 与本地同源）。

检查 docs/specs/pitfalls.md：
- 条目数 >= 下限（默认 50）；
- 编号 B-01 起连续递增，无跳号、无重复；
- 每条有归属模块与证据列（不允许"某处"）。

用法：python scripts/ci/check_specs.py [--min 50]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PITFALLS = REPO / "docs" / "specs" / "pitfalls.md"
NON_LOCATABLE = ("某处", "那个文件", "某文件")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min", type=int, default=50)
    args = parser.parse_args()

    rows: list[tuple[str, str, str]] = []
    for line in PITFALLS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| (B-\d+) \| ([^|]+) \| ([^|]+) \|", line)
        if m:
            rows.append((m.group(1), m.group(2).strip(), m.group(3).strip()))

    problems: list[str] = []
    numbers = [int(r[0][2:]) for r in rows]
    if len(rows) < args.min:
        problems.append(f"条目数 {len(rows)} < {args.min}")
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append("编号不连续或有跳号")
    for num, module, desc in rows:
        if not module or module.startswith("-"):
            problems.append(f"{num}: 缺归属模块")
        for word in NON_LOCATABLE:
            if word in desc:
                problems.append(f"{num}: 含不可定位表述 {word!r}")

    if problems:
        print("check_specs FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"check_specs OK: {len(rows)} 条坑，编号连续，归属与证据完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
