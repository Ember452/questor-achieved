"""护栏：``VERSION`` 文件是版本唯一真相源（structure §10），三处引用必须同源。

护栏判据：让本测试可以失败的是"版本真相源被绕开"这类真实设计改动（恢复静态 version、
VERSION 文件换格式、hatch 配置漂移），而不是随手改个值。

负向验证记录（2026-10-11，均已复原）：
1. 把 ``VERSION`` 内容临时改成 ``2026.10.11-rc1`` → ``test_version_file_is_calver`` 与
   ``test_questor_version_matches_version_file`` 双双 FAILED（CalVer 正则与元数据同值断言）。
2. 把 pyproject 临时加回 ``version = "0.1.0"`` → ``test_pyproject_reads_version_dynamically``
   FAILED（"静态 version 会与 VERSION 文件形成两套真相"）。
"""

from __future__ import annotations

import importlib.metadata
import pathlib
import re
import tomllib

import pytest

from questor.version import questor_version

REPO = pathlib.Path(__file__).resolve().parents[2]

CALVER = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}$")


def _version_file_text() -> str:
    return (REPO / "VERSION").read_text(encoding="utf-8").strip()


def test_version_file_is_calver() -> None:
    assert CALVER.match(_version_file_text()), _version_file_text()


def test_pyproject_reads_version_dynamically() -> None:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert "version" not in project, "静态 version 会与 VERSION 文件形成两套真相"
    assert project["dynamic"] == ["version"]
    assert data["tool"]["hatch"]["version"]["path"] == "VERSION"


def test_questor_version_matches_version_file() -> None:
    # uv sync 安装的是本仓库（hatchling dynamic 版本 = VERSION），元数据与文件必须同值
    assert questor_version() == _version_file_text()


def test_falls_back_to_version_file_when_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", _raise)
    assert questor_version() == _version_file_text()


def test_fails_loudly_when_no_source_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """元数据不可用且仓库根不可定位时必须抛错，绝不猜默认值。"""

    def _raise(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", _raise)
    monkeypatch.setattr(
        "questor.version.pathlib.Path",  # 定位失败路径：所有祖先目录都无 VERSION
        lambda p: tmp_path / "nowhere",
    )
    with pytest.raises(RuntimeError, match="无法定位 VERSION"):
        questor_version()
