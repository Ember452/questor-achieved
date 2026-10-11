"""版本单点：根目录 ``VERSION`` 是唯一真相源（structure §10），本模块只做解析与回落。

参照 wuu 根 ``VERSION`` + ``internal/version`` 的同一设计决定（构建时读文件而非散布
硬编码），不复制其代码。构建标识（git hash 等）随 M2.3 CLI 收口再定形态，本模块不预置。
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
