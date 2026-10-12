"""文档链接核查：`docs/**/*.md` 里的相对链接必须能解析到仓库内真实文件。

为什么要有机器检查：文档最容易"看着对、链接早废"——`AGENTS.md` §四 要求文档与事实
一致；ADR-0008 把"引用可核查"定为一条纪律。本脚本只查**相对链接的存在性**
（外链 http(s) 与纯锚点不查），不看措辞、不做语义判断。

判定顺序（减少跨目录书写导致的误报）：
1. 相对当前 md 文件解析；
2. 仍找不到时，相对仓库根解析（仓库里允许写 `docs/x/y.md` 这种根相对路径）。
两个位置都不存在 → 记为问题。

用法：python scripts/ci/check_docs.py
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
#: Markdown 内联链接 `[text](target)`；只取 target
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _target_paths(md_file: pathlib.Path, target: str) -> list[pathlib.Path]:
    candidate = target.split("#", 1)[0].strip()
    if not candidate or candidate.startswith(("http://", "https://", "mailto:")):
        return []
    return [md_file.parent / candidate, REPO / candidate]


def main() -> int:
    problems: list[str] = []
    checked = 0
    for md_file in sorted(DOCS.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        for raw in _LINK.findall(text):
            candidates = _target_paths(md_file, raw)
            if not candidates:
                continue
            checked += 1
            if not any(path.is_file() or path.is_dir() for path in candidates):
                problems.append(f"{md_file.relative_to(REPO)}: 链接失效 → {raw}")
    if problems:
        print("check_docs FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"check_docs OK: {checked} 条文档相对链接均可解析")
    return 0


if __name__ == "__main__":
    sys.exit(main())
