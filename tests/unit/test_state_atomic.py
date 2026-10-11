"""state.atomic 单元行为：原子写、幂等写、安全建目录。

崩溃注入类对抗用例在 tests/adversarial/test_state_atomic_failure.py。
"""

from __future__ import annotations

import os
import pathlib
import stat

from questor.state.atomic import mkdir_secure, write_atomic, write_excl
from questor.testenv.fake_home import fake_home


def test_write_atomic_creates_parents_and_content(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "deep" / "nested" / "file.toml"
    write_atomic(target, b"alpha")
    assert target.read_bytes() == b"alpha"


def test_write_atomic_replaces_existing(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "file.bin"
    write_atomic(target, b"old")
    write_atomic(target, b"new-much-longer")
    assert target.read_bytes() == b"new-much-longer"
    assert not [p for p in tmp_path.iterdir() if p.name != "file.bin"], "不留临时残件"


def test_write_excl_first_true_second_false(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "toolu_01.txt"
    assert write_excl(target, b"first") is True
    assert write_excl(target, b"second") is False  # B-24：重复落盘静默跳过
    assert target.read_bytes() == b"first"


def test_write_excl_creates_parents(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "x" / "y" / "result.txt"
    assert write_excl(target, b"data") is True


def test_mkdir_secure_idempotent(tmp_path: pathlib.Path) -> None:
    created = mkdir_secure(tmp_path / "a" / "b")
    assert created.is_dir()
    assert mkdir_secure(tmp_path / "a" / "b") == created


def test_written_files_are_owner_private_posix(
    tmp_path: pathlib.Path,
) -> None:
    """POSIX 上凭据级文件收紧 0600；Windows mode 位不作为安全保证，跳过。"""
    if os.name == "nt":
        import pytest

        pytest.skip("Windows 的 chmod 只影响只读位，mode 语义不作断言")
    target = tmp_path / "secret.bin"
    write_atomic(target, b"x")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    subdir = mkdir_secure(tmp_path / "sub")
    assert stat.S_IMODE(subdir.stat().st_mode) == 0o700


def test_atomic_roundtrip_in_fake_home() -> None:
    """在隔离 home 下写 config 类文件，路径解析与原子写协同工作。"""
    from questor.state.paths import config_path

    with fake_home():
        target = config_path()
        write_atomic(target, b"[model]\n")
        assert target.read_bytes() == b"[model]\n"
