"""对抗：原子写的崩溃注入（B-72 的两个面）。

- 写入中途任何一步失败：目标文件不半写、临时文件必被清理；
- 临时文件与目标**同目录**——跨目录 rename 不原子（B-72）。
"""

from __future__ import annotations

import os
import pathlib
import tempfile
from typing import Any

import pytest

from questor.state.atomic import write_atomic


def test_failure_leaves_no_partial_target_and_no_temp(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "data.json"
    target.write_bytes(b"original")
    (tmp_path / "unrelated.txt").write_bytes(b"keep")

    def _boom(src: os.PathLike[str] | str, dst: os.PathLike[str] | str) -> None:
        raise OSError("injected rename failure")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError, match="injected rename failure"):
        write_atomic(target, b"new-content")
    monkeypatch.undo()

    assert target.read_bytes() == b"original", "rename 失败后目标必须保持旧内容"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == [], "临时文件必被清理"


def test_failure_on_first_write_cleans_temp_too(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "fresh.json"

    def _boom(fd: int) -> None:
        raise OSError("injected fsync failure")

    monkeypatch.setattr(os, "fsync", _boom)
    with pytest.raises(OSError, match="injected fsync failure"):
        write_atomic(target, b"data")
    monkeypatch.undo()

    assert not target.exists()
    assert list(tmp_path.iterdir()) == [], "目录里只允许目标文件，不留 .tmp"


def test_temp_file_lives_in_target_directory(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-72：mkstemp 的 dir 必须是目标父目录——跨卷 rename 不原子。"""
    seen_dirs: list[object] = []
    original_mkstemp = tempfile.mkstemp

    def _recording_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
        seen_dirs.append(kwargs["dir"])
        return original_mkstemp(*args, **kwargs)

    monkeypatch.setattr("questor.state.atomic.tempfile.mkstemp", _recording_mkstemp)
    target = tmp_path / "sub" / "file.bin"
    write_atomic(target, b"data")
    assert seen_dirs == [target.parent]
