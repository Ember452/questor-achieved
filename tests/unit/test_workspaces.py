"""workspaces 单元行为：注册幂等与同源身份、登记增删、可见性判定边界。"""

from __future__ import annotations

import os
import pathlib

import pytest

from questor.schemas.model import Workspace
from questor.testenv.fake_home import fake_home
from questor.workspaces import (
    WorkspaceError,
    get_workspace,
    is_within_workspace,
    list_workspaces,
    register,
    unregister,
)


def test_register_is_idempotent_and_stable() -> None:
    with fake_home() as tmp:
        root = tmp / "my-proj"
        root.mkdir()
        first = register(root)
        second = register(root)
        assert first == second
        assert len(first.id) == 16 and all(c in "0123456789abcdef" for c in first.id)
        assert first.root_paths == [str(root.resolve())]
        assert first.revision == 0


def test_register_case_insensitive_on_windows() -> None:
    """Windows 大小写不同的路径必须映射同一 id；POSIX 大小写敏感则跳过。"""
    if os.path.normcase("A") != "a":
        pytest.skip("POSIX 路径大小写敏感，无此语义")
    with fake_home() as tmp:
        (tmp / "my-proj").mkdir()
        lower = register(tmp / "my-proj")
        upper = register(tmp / "MY-PROJ")
        assert lower.id == upper.id


def test_register_canonicalizes_symlinks(tmp_path: pathlib.Path) -> None:
    """符号链接路径与真实路径注册出同一 id（wuu EvalSymlinks 语义）。"""
    real = tmp_path / "real-proj"
    real.mkdir()
    try:
        link = tmp_path / "link-proj"
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("当前环境无符号链接权限")
    with fake_home():
        a = register(real)
        b = register(link)
    assert a.id == b.id


def test_rename_updates_display_name() -> None:
    with fake_home() as tmp:
        root = tmp / "proj"
        root.mkdir()
        created = register(root, name="显示名")
        updated = register(root, name="改名")
        assert updated.name == "改名"
        assert updated.id == created.id
        assert get_workspace(created.id) == updated


def test_list_get_unregister() -> None:
    with fake_home() as tmp:
        (tmp / "proj-one").mkdir()
        (tmp / "proj-two").mkdir()
        one = register(tmp / "proj-one", name="one")
        two = register(tmp / "proj-two", name="two")
        assert {w.id for w in list_workspaces()} == {one.id, two.id}
        assert get_workspace(one.id) is not None
        unregister(one.id)
        assert get_workspace(one.id) is None
        assert {w.id for w in list_workspaces()} == {two.id}
        with pytest.raises(WorkspaceError, match="未注册"):
            unregister(one.id)


def test_is_within_workspace_boundaries(tmp_path: pathlib.Path) -> None:
    with fake_home() as tmp:
        root = tmp / "my-proj"
        root.mkdir()
        ws = register(root)
        inside = root / "src" / "main.py"
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.touch()
        assert is_within_workspace(inside, ws) is True
        assert is_within_workspace(root, ws) is True  # 根本身在界内
        # 分隔符边界：my-proj-evil 不是 my-proj 内部
        evil = tmp / "my-proj-evil"
        evil.mkdir()
        assert is_within_workspace(evil, ws) is False
        # 工作区外的路径
        assert is_within_workspace(tmp / "outside.txt", ws) is False
        # .. 逃逸：resolve 消化后不在界内
        escape = root / ".." / "elsewhere"
        assert is_within_workspace(escape, ws) is False
        # 未存在路径同样可判（可达性推导不要求文件已存在）
        assert is_within_workspace(root / "not-yet-created.py", ws) is True


def test_is_within_multiple_roots() -> None:
    with fake_home() as tmp:
        a = tmp / "proj-a"
        a.mkdir()
        extra = tmp / "proj-b"
        extra.mkdir()
        ws: Workspace = register(a)
        ws = ws.model_copy(update={"root_paths": [str(a.resolve()), str(extra.resolve())]})
        assert is_within_workspace(extra / "x.py", ws) is True
        assert is_within_workspace(a / "y.py", ws) is True
