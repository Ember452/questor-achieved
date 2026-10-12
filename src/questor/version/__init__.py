"""版本单点：根目录 ``VERSION`` 是唯一真相源（structure §10），本模块只做解析与回落。

参照 wuu 根 ``VERSION`` + ``internal/version`` 的同一设计决定（构建时读文件而非散布
硬编码），不复制其代码。构建标识（M2.3 定形）见 :func:`build_commit`。
"""

from __future__ import annotations

import importlib.metadata
import pathlib

_VERSION_FILE_NAME = "VERSION"


def _read_version_file() -> str:
    """开发态（包未安装）从包位置向上定位仓库根的 ``VERSION`` 并读出。

    ``src/questor/version/__init__.py`` 的祖先链是 version → questor → src → 仓库根，
    逐级上查即可覆盖 src 布局与未来的扁平布局。
    """
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _VERSION_FILE_NAME
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip()
    raise RuntimeError(f"无法定位 {_VERSION_FILE_NAME}：包未安装，且仓库根不在 {here} 的祖先目录中")


def questor_version() -> str:
    """返回当前包版本（CalVer，如 ``2026.10.11``）。

    优先读已安装分发的元数据（pyproject 经 hatchling dynamic 版本从 ``VERSION`` 生成，
    两处天然同值）；未安装时回落读仓库根的 ``VERSION``。两个来源都不可用就抛
    ``RuntimeError``，绝不猜默认值——版本号的诚实呈现优先于可用性。
    """
    try:
        return importlib.metadata.version("questor")
    except importlib.metadata.PackageNotFoundError:
        return _read_version_file()


def build_commit() -> str:
    """构建标识：短 hash，拿不到就写 `source`，**绝不编一个看起来像 hash 的字符串**。

    只读 `.git/HEAD` 与 ref（或 `packed-refs`），不起 `git` 子进程：本函数可能在
    事件循环里被调用（`serve.initialize`），subprocess 就是阻塞调用（AGENTS §五）。
    因此只能拿到"当前 checkout 的局部 hash"，不追求与发布产物逐字一致；
    `initialize` 回显与日志用它就够，真要精确到 commit 走发布流程写进元数据。
    """
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        head = parent / ".git" / "HEAD"
        if not head.is_file():
            continue
        try:
            text = head.read_text(encoding="utf-8").strip()
        except OSError:
            return "source"
        if text.startswith("ref:"):
            ref = text.split(":", 1)[1].strip()
            return _resolve_ref(parent / ".git", ref)
        return text[:7] if text else "source"
    return "source"


def _resolve_ref(git_dir: pathlib.Path, ref: str) -> str:
    """松散 ref 优先，其次 `packed-refs`；都找不到就写 `source`（不猜 hash）。"""
    loose = git_dir / ref
    if loose.is_file():
        try:
            return loose.read_text(encoding="utf-8").strip()[:7] or "source"
        except OSError:
            return "source"
    packed = git_dir / "packed-refs"
    if packed.is_file():
        try:
            for line in packed.read_text(encoding="utf-8").splitlines():
                if line.startswith("^") or not line or line.startswith("#"):
                    continue
                digest, _, name = line.partition(" ")
                if name.strip() == ref:
                    return digest[:7]
        except OSError:
            return "source"
    return "source"
