"""笔记核查：`docs/notes/*.md` 的锚点必须存在，且不得比锚点更旧。

规则来源 `docs/adr/0010-notes-anchored-and-expiring.md`。为什么必须有机器检查：
笔记是唯一会"过期后仍然看起来可信"的文档，比没笔记更危险（本仓库已因不可复核的
引用翻过一次车）。所以本核查只做两件可机械判定的事：

1. 每条笔记的 `锚点:` 路径必须存在于仓库（否则等于指向不存在的代码）；
2. 锚点文件的最后提交**日期**若晚于笔记 `日期:`，本条判为过期，必须更新或删除。

用法：python scripts/ci/check_notes.py
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
NOTES = REPO / "docs" / "notes"
DATE = re.compile(r"日期:\s*(\d{4}-\d{2}-\d{2})")
PATH_IN_ANCHOR = re.compile(r"[\w./-]+\.[A-Za-z]{1,5}")


def _anchor_blob(text: str) -> str:
    """取 `锚点:` 那一行及其后续缩进行（允许列表换行书写）。"""
    collected: list[str] = []
    grabbing = False
    for line in text.splitlines():
        if line.startswith("锚点:"):
            grabbing = True
            collected.append(line.split("锚点:", 1)[1])
            continue
        if not grabbing:
            continue
        if not line.strip() or line.startswith(("#", "日期:")):
            grabbing = False
            continue
        collected.append(line.strip())
    return "\n".join(collected)


def _last_commit_date(rel: str) -> dt.date | None:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%cd", "--date=short", "--", rel],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    value = out.stdout.strip()
    if not value:
        return None
    return dt.date.fromisoformat(value)


def main() -> int:
    problems: list[str] = []
    notes = sorted(p for p in NOTES.glob("*.md")) if NOTES.is_dir() else []
    notes = [p for p in notes if p.name != "README.md"]

    for note in notes:
        text = note.read_text(encoding="utf-8")
        rel_note = note.relative_to(REPO).as_posix()

        date_match = DATE.search(text)
        if not date_match:
            problems.append(f"{rel_note}: 缺 `日期: YYYY-MM-DD` 头")
            continue
        note_date = dt.date.fromisoformat(date_match.group(1))

        anchors = PATH_IN_ANCHOR.findall(_anchor_blob(text))
        if not anchors:
            problems.append(f"{rel_note}: 无 `锚点:`，无法核查（宁缺毋空）")
            continue

        for raw in dict.fromkeys(anchors):
            # 只去掉显式的 `./` 前缀；不得用 lstrip("./")——它会吃掉 `.github/...`
            # 与 `.pre-commit-config.yaml` 的前导点，把存在的文件误判成不存在。
            rel = raw[2:] if raw.startswith("./") else raw
            if not (REPO / rel).is_file():
                problems.append(f"{rel_note}: 锚点文件不存在 → {rel}")
                continue
            last = _last_commit_date(rel)
            if last and last > note_date:
                problems.append(
                    f"{rel_note}: 已过期——锚点 {rel} 最后改于 {last}，晚于笔记 {note_date}；"
                    "请更新该条或删除它（不留过期笔记）"
                )

    if problems:
        print("check_notes FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"check_notes OK: {len(notes)} 条笔记，锚点均可核且未过期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
