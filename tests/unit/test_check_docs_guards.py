"""B-123 的配对护栏：文档类收口项的"存在性复核"必须有机械牙齿。

坑的形状：`check_docs.py` 旧版只校 `[text](target)` 相对链接，于是两种真实缺陷
它一概看不见——① 必读表用**反引号**写路径（不是链接）；② 必读位指向的文档首行
挂着"已被取代 / 不得作实现依据"横幅。本仓实测踩过：`AGENTS.md` §七 必读表长期
写着 `development-plan.md`，而 `port-ledger` TL-2 早已记"必读已 redirect"。

断言策略：不起第二份实现（那会造出"测的是测试自己"的双真相），而是**直接跑那个
脚本**：真仓必须退 0；合成仓里注入三类偏离必须各自退 1 并给出可定位的消息。
每条负向都注真偏离，验证护栏会咬人。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci" / "check_docs.py"


def _run(script: Path, cwd: Path) -> tuple[int, str]:
    """跑脚本，返回退出码与合并输出。

    两个平台细节都是实测钉下的，不是洁癖：
    - `-B`：避免在临时仓里落 `__pycache__`。
    - `PYTHONIOENCODING=utf-8`：子进程 stdout 默认跟随控制台代码页（本机 cp936），
      父进程按 UTF-8 解码会 `UnicodeDecodeError`，报错发生在断言之前——判红用例
      会退化成"测不出原因的红"（B-124）。
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _build_repo(tmp_path: Path) -> Path:
    """搭一个最小仓：AGENTS.md 作入口文档，docs/ 下放一篇现役档与一篇作废档。"""
    repo = tmp_path / "repo"
    (repo / "scripts" / "ci").mkdir(parents=True)
    (repo / "docs" / "plans").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "ci" / "check_docs.py")
    (repo / "docs" / "plans" / "live-plan.md").write_text(
        "# 现役计划\n\n正文。\n", encoding="utf-8"
    )
    (repo / "docs" / "plans" / "old-plan.md").write_text(
        "# 旧计划\n\n> ⚠️ **历史文档 / 已被取代（2026-10-14）**：本文不再作实现依据。\n",
        encoding="utf-8",
    )
    return repo


def _set_entry(repo: Path, body: str) -> None:
    (repo / "AGENTS.md").write_text(body, encoding="utf-8")


@pytest.mark.parametrize("reference", ["docs/plans/不存在.md", "不存在.md"])
def test_missing_doc_reference_in_entry_is_red(tmp_path: Path, reference: str) -> None:
    """负向①：必读位引用不存在的文档——根相对写法与裸文件名写法都必须判红。"""
    repo = _build_repo(tmp_path)
    _set_entry(repo, f"# 规范\n\n| 要做的事 | 必读 |\n|---|---|\n| 开工前 | `{reference}` |\n")
    code, out = _run(repo / "scripts" / "ci" / "check_docs.py", repo)
    assert code == 1, f"引用不存在的文档必须判红，实际输出：{out}"
    assert "不存在" in out and reference in out


def test_deprecated_doc_as_required_reading_is_red(tmp_path: Path) -> None:
    """负向②：必读位指向挂着作废横幅的文档，且同句没说明它作废 → 判红。

    这正是本仓漏掉过的那一类：台账说"已 redirect"，文件里那行仍把作废档当必读。
    """
    repo = _build_repo(tmp_path)
    _set_entry(
        repo,
        "# 规范\n\n| 要做的事 | 必读 |\n|---|---|\n"
        "| 想知道阶段怎么做 | `docs/plans/old-plan.md` |\n",
    )
    code, out = _run(repo / "scripts" / "ci" / "check_docs.py", repo)
    assert code == 1, f"必读位指向作废档必须判红，实际输出：{out}"
    assert "作废" in out


def test_deprecated_doc_mention_with_caveat_is_allowed(tmp_path: Path) -> None:
    """正向：同句显式标注"已作废，不得作实现依据"时允许提及（否则没法写历史横幅）。"""
    repo = _build_repo(tmp_path)
    _set_entry(
        repo,
        "# 规范\n\n| 要做的事 | 必读 |\n|---|---|\n"
        "| 想知道阶段怎么做 | `docs/plans/live-plan.md`；旧 `docs/plans/old-plan.md` 已作废 |\n",
    )
    code, out = _run(repo / "scripts" / "ci" / "check_docs.py", repo)
    assert code == 0, f"标明作废的提及不该判红，实际输出：{out}"


def test_head_marker_only_counts_in_head(tmp_path: Path) -> None:
    """负向③：作废横幅只认文档开头；正文深处出现标记不该把现役档打成废档。

    不加这条限定会误伤：母计划 §11 里就写着“给旧文档加历史头「不得再作实现依据」”，
    那是在说别的文档，不是在声明自己作废。
    """
    repo = _build_repo(tmp_path)
    body = "\n".join(
        ["# 母计划", "", "> 本文是计划态快照，不含执行进度。", ""]
        + [f"第 {n} 行正文。" for n in range(1, 10)]
        + ["执行步骤里有一句：给旧文档加历史头「不得再作实现依据」。", ""]
    )
    (repo / "docs" / "plans" / "old-plan.md").write_text(body + "\n", encoding="utf-8")
    _set_entry(
        repo,
        "# 规范\n\n| 要做的事 | 必读 |\n|---|---|\n| 开工前 | `docs/plans/old-plan.md` |\n",
    )
    code, out = _run(repo / "scripts" / "ci" / "check_docs.py", repo)
    assert code == 0, f"标记出现在正文深处不该被判为作废档，实际输出：{out}"


def test_real_repository_passes() -> None:
    """真仓必须绿——本条同时是"必读地图指向的都是活档"的持续回归钉。"""
    code, out = _run(SCRIPT, REPO)
    assert code == 0, f"仓库根 check_docs 应绿，实际输出：{out}"
