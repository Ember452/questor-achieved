"""笔记核查：`docs/notes/*.md` 的锚点必须存在，代码类锚点还不得比笔记更旧。

规则来源 `docs/adr/0010-notes-anchored-and-expiring.md`。为什么必须有机器检查：
笔记是唯一会"过期后仍然看起来可信"的文档，比没笔记更危险（本仓库已因不可复核的
引用翻过一次车）。

三件可机械判定的事：

1. 每条笔记的 `锚点:` 路径必须存在于仓库（否则等于指向不存在的代码）；
2. **代码/配置类锚点**（`docs/` 之外）的最后提交日期若晚于笔记的"复核日期"，判为过期，
   必须重新读过并更新 `复核于:`，或者删掉这条笔记。`docs/**` 里的文字修订不参与新鲜度
   判定——改一句说明不构成"机制变了"（否则每次编辑文档都要全体笔记陪跑，制造假工）。
3. **浅克隆下拒绝判定**：`git log -1 -- <路径>` 在 depth=1 的仓库里只能看到 tip，
   会把所有锚点都算成"今天改过"而全体误报过期（B-80，CI 已实际发生）。

"复核日期"取 `复核于:`，没有该字段时回退到 `日期:`。

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
REVIEW = re.compile(r"复核于:\s*(\d{4}-\d{2}-\d{2})")
PATH_IN_ANCHOR = re.compile(r"[\w./-]+\.[A-Za-z]{1,5}")
# 这些前缀下的锚点是文字产物，只做存在性核查，不参与新鲜度判定
PROSE_PREFIXES = ("docs/",)


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
        if not line.strip() or line.startswith(("#", "日期:", "复核于:")):
            grabbing = False
            continue
        collected.append(line.strip())
    return "\n".join(collected)


def _is_shallow() -> bool:
    out = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip() == "true"


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
    shallow = _is_shallow()
    if shallow:
        problems.append(
            "仓库是浅克隆，锚点的提交日期不可信（`git log -1 -- 路径` 只能看到 tip）。"
            "CI 需要 actions/checkout 的 fetch-depth: 0；本地请 git fetch --unshallow 后重跑"
        )

    for note in notes:
        text = note.read_text(encoding="utf-8")
        rel_note = note.relative_to(REPO).as_posix()

        review = REVIEW.search(text) or DATE.search(text)
        if not review:
            problems.append(f"{rel_note}: 缺 `日期:` 或 `复核于:` 头")
            continue
        since = dt.date.fromisoformat(review.group(1))

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
            if rel.startswith(PROSE_PREFIXES) or shallow:
                continue
            last = _last_commit_date(rel)
            if last and last > since:
                problems.append(
                    f"{rel_note}: 已过期——代码锚点 {rel} 最后改于 {last}，晚于复核日期 {since}；"
                    "请重读本条并更新 复核于: 或删除它（不留过期笔记）"
                )

    if problems:
        print("check_notes FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    tail = "（浅克隆：仅核查存在性）" if shallow else ""
    print(f"check_notes OK: {len(notes)} 条笔记，锚点均可核且未过期{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
