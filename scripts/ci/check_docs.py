"""文档链接与必读指向核查：`docs/**/*.md` 的引用必须能解析，且必读位不得指向作废档。

为什么要有机器检查：文档最容易"看着对、链接早废"——`AGENTS.md` §四 要求文档与事实
一致；ADR-0008 把"引用可核查"定为一条纪律。本脚本查三类事实，不看措辞、不做语义判断：

1. **相对链接存在性**：`docs/**/*.md` 里 `[text](target)` 的 target（外链与纯锚点不查）。
2. **入口文档的反引号路径存在性**（B-123 补的盲区）：`AGENTS.md` 与 `docs/README.md`
   是"开工必读地图"，其中的反引号 `.md` 路径若是仓库内文档就必须真实存在。
   旧版只查 ①，实测漏过两处：必读表用反引号写路径、指向的文档首行挂着作废横幅——
   两种形状都不是 `[..](..)`，机器一概看不见。
3. **必读位不得指向作废档**（B-123）：首 8 行含"已被取代 / 历史文档 / 历史执行记录 /
   作实现依据"任一标记的文档记为作废档；入口文档里凡引用它、且**同一行没有**"作废 /
   不得 / 历史 / superseded / 已被取代"这类明确贬义措辞，就判红。理由：AGENTS §七
   必读表长期写着 `development-plan.md`，而该文件首行就声明"均作废，不再作实现依据"——
   台账上记的"已 redirect"与文件实况两张皮，靠人眼复核抓不住。

判定顺序（减少跨目录书写导致的误报）：
1. 相对当前 md 文件解析；
2. 仍找不到时，相对仓库根解析（仓库里允许写 `docs/x/y.md` 这种根相对路径）。
两个位置都不存在 → 记为问题。

行号不在断言之列：行号会随文档修订漂移。见 ADR-0008。

用法：python scripts/ci/check_docs.py
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
#: 入口文档＝开工必读地图；它们的引用面就是新窗口的实际阅读面
ENTRY_DOCS = (REPO / "AGENTS.md", DOCS / "README.md")
#: Markdown 内联链接 `[text](target)`；只取 target
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
#: 反引号内“像一篇仓库文档”的引用：以 .md 结尾、不含空白与反引号。允许非 ASCII
#: 文件名（否则中文档名就是新盲区），通配与锁点后缀另处处理。
_BACKTICK_DOC = re.compile(r"`([^`\s]+\.md)(?:#[^`]*)?`")
#: 文档头部（前 8 行）出现任一标记 ⇒ 该文档不得作实现依据
_DEPRECATED_MARKERS = ("已被取代", "历史文档", "历史执行记录", "作实现依据")
#: 入口文档同句里出现任一措辞 ⇒ 允许提到作废档（是在"标注它作废"，不是在指它必读）
_SUPERSESSION_WORDS = ("作废", "不得", "历史", "superseded", "已被取代")
_HEAD_LINES = 8


def _target_candidates(md_file: pathlib.Path, target: str) -> list[pathlib.Path]:
    """把链接/路径串解析成候选文件位置；外链与纯锚点返回空表（不查）。"""
    candidate = target.split("#", 1)[0].strip()
    if not candidate or candidate.startswith(("http://", "https://", "mailto:")):
        return []
    return [md_file.parent / candidate, REPO / candidate]


def _lines(md_file: pathlib.Path) -> list[str]:
    return md_file.read_text(encoding="utf-8").splitlines()


def find_dead_links(docs_dir: pathlib.Path = DOCS) -> list[str]:
    """① 相对链接存在性。"""
    problems: list[str] = []
    for md_file in sorted(docs_dir.rglob("*.md")):
        for raw in _LINK.findall(md_file.read_text(encoding="utf-8")):
            candidates = _target_candidates(md_file, raw)
            if candidates and not any(p.is_file() or p.is_dir() for p in candidates):
                problems.append(f"{md_file.relative_to(REPO)}: 链接失效 → {raw}")
    return problems


def find_deprecated_docs(docs_dir: pathlib.Path = DOCS) -> set[str]:
    """③ 的输入：首 8 行挂作废横幅的文档（相对 posix 路径集合）。"""
    deprecated: set[str] = set()
    for md_file in sorted(docs_dir.rglob("*.md")):
        head = "\n".join(_lines(md_file)[:_HEAD_LINES])
        if any(marker in head for marker in _DEPRECATED_MARKERS):
            deprecated.add(md_file.relative_to(REPO).as_posix())
    return deprecated


def _resolve_doc(md_file: pathlib.Path, ref: str) -> pathlib.Path | None | bool:
    """把入口文档里的 `.md` 引用解析到真实文件。

    返回：命中的 Path；`None` 表示仓内查无此文档（判红）；`True` 表示同名多篇
    （写法不够精确但不算断链，不判红）。仓库里惯用裸文件名（`overview.md`）指
    `docs/architecture/overview.md`，所以路径解析不中时按 basename 兜底。
    """
    for candidate in (md_file.parent / ref, REPO / ref, DOCS / ref):
        if candidate.is_file():
            return candidate
    name = pathlib.Path(ref).name
    matches = [p for p in DOCS.rglob(name) if p.is_file()]
    matches += [p for p in REPO.glob(name) if p.is_file()]
    if len(matches) == 1:
        return matches[0]
    return True if len(matches) > 1 else None


def check_entry_docs(
    entry_docs: tuple[pathlib.Path, ...] = ENTRY_DOCS,
    deprecated: set[str] | None = None,
) -> list[str]:
    """② + ③ 入口文档里的反引号 `.md` 路径：必须存在；指作废档必须同句标明。"""
    if deprecated is None:
        deprecated = find_deprecated_docs()
    problems: list[str] = []
    for md_file in entry_docs:
        if not md_file.is_file():
            continue
        for lineno, line in enumerate(_lines(md_file), start=1):
            for ref in _BACKTICK_DOC.findall(line):
                if any(ch in ref for ch in ("*", "?", "<", ">", "{")) or "NNNN" in ref:
                    continue  # 命名模板/占位写法（behavior-<pkg>.md、NNNN-标题.md）
                hit = _resolve_doc(md_file, ref)
                if hit is None:
                    problems.append(
                        f"{md_file.relative_to(REPO)}:{lineno}: 必读引用的文档不存在 → {ref}"
                    )
                    continue
                if hit is True:  # 同名多篇，写法不精确不断链
                    continue
                posix = hit.relative_to(REPO).as_posix()
                if posix in deprecated and not any(word in line for word in _SUPERSESSION_WORDS):
                    problems.append(
                        f"{md_file.relative_to(REPO)}:{lineno}: 必读位指向已标作废的文档，"
                        f"且同句未注明其作废 → {ref}"
                    )
    return problems


def main() -> int:
    problems = find_dead_links() + check_entry_docs()
    if problems:
        print("check_docs FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        f"check_docs OK: 文档相对链接均可解析；"
        f"入口必读的反引号路径全部存在（作废档指向已标 {len(find_deprecated_docs())} 篇在册）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
