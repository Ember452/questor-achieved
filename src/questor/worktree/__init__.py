"""worktree —— Git worktree 生命周期与隔离（overview §6）。

M3b-2 最小落地：`thread/fork(mode=worktree)` 调 `git worktree add`；新 worktree
路径落在 `<QUESTOR_HOME>/worktrees/<thread-id>/<repo-slug>`，thread 删除时调
`git worktree remove`。**不引 pygit2**（保持极简，subprocess 足够），依赖不变。

诚实边界：
- worktree 里的代码变更**不自动回主分支**——用户自行 `git merge`；Questor 只管
  创建与清理，不猜"什么时候合"。
- 非 git 仓库、目标路径已存在、上游 worktree 被外部删掉等情况一律 raise WorktreeError；
  调用方（serve handler）转 ProtocolError。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from questor.state.paths import questor_home


class WorktreeError(Exception):
    """worktree 生命周期失败（非 git 仓库 / 路径冲突 / git CLI 报错）。"""


_SLUG_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def worktree_root(thread_id: str, repo_root: Path) -> Path:
    """新 worktree 的建议路径：`<QUESTOR_HOME>/worktrees/<thread-id>/<repo-slug>`。"""
    slug = _SLUG_SAFE.sub("-", repo_root.name).strip("-") or "repo"
    return questor_home() / "worktrees" / thread_id / slug


def add_worktree(repo_root: Path, *, branch: str, path: Path) -> Path:
    """`git worktree add -b <branch> <path>`；成功返回 path，失败 raise WorktreeError。"""
    if not (repo_root / ".git").exists():
        raise WorktreeError(f"{repo_root} 不是 git 仓库根（未找到 .git）")
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(  # noqa: S603 —— 固定 argv，无用户输入拼接
        ["git", "-C", str(repo_root), "worktree", "add", "-b", branch, str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise WorktreeError(
            f"git worktree add 失败（exit={result.returncode}）：{result.stderr.strip()}"
        )
    return path


def remove_worktree(repo_root: Path, path: Path) -> None:
    """`git worktree remove <path>`；不存在时幂等通过。"""
    if not path.exists():
        return
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_root), "worktree", "remove", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise WorktreeError(
            f"git worktree remove 失败（exit={result.returncode}）：{result.stderr.strip()}"
        )


def list_worktrees(repo_root: Path) -> list[str]:
    """`git worktree list --porcelain` 抽 path 行；本模块用于诊断与 thread 删除前校验。"""
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return [
        line[len("worktree ") :]
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    ]
