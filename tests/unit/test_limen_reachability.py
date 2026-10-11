"""limen 可达性推导单元行为：B-30 二段 resolve、Windows 大小写折叠、分隔符边界。"""

from __future__ import annotations

import os
import pathlib

import pytest

from questor.limen.reachability import check_path, is_within

WIN = os.path.normcase("A") == "a"


def test_inside_root_allowed(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "src").mkdir()
    assert is_within(str(root / "src" / "main.py"), [str(root)]) is True


def test_outside_root_rejected(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    assert is_within(str(tmp_path / "elsewhere.txt"), [str(root)]) is False


def test_separator_boundary(tmp_path: pathlib.Path) -> None:
    """/root-evil 不是 /root 内部——前缀比较必须带分隔符边界。"""
    root = tmp_path / "ws"
    root.mkdir()
    evil = tmp_path / "ws-evil"
    evil.mkdir()
    assert is_within(str(evil / "x.py"), [str(root)]) is False


def test_case_insensitive_on_windows(tmp_path: pathlib.Path) -> None:
    if not WIN:
        pytest.skip("POSIX 路径大小写敏感，无此语义")
    root = tmp_path / "ws"
    root.mkdir()
    assert is_within(str(tmp_path / "WS" / "x.py"), [str(root)]) is True


def test_b30_double_resolve_rejects_dotdot_tail(tmp_path: pathlib.Path) -> None:
    """B-30：不存在的路径带 ".." 尾段——二段 resolve 后必须落在根外。"""
    root = tmp_path / "ws"
    root.mkdir()
    # 祖先（root/missing-dir）不存在；尾部含 ".." 想逃到 root 之外
    sneaky = root / "missing-dir" / ".." / ".." / "outside.txt"
    assert is_within(str(sneaky), [str(root)]) is False
    # 正常的不存在路径（尾部无 ..）仍在界内
    assert is_within(str(root / "not-yet.py"), [str(root)]) is True


def test_b30_dotdot_tail_into_sibling(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    sneaky = root / "a" / ".." / ".." / "sibling" / "secret.txt"
    assert is_within(str(sneaky), [str(root)]) is False


def test_symlink_alias_resolves_same(tmp_path: pathlib.Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    try:
        link = tmp_path / "link"
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("当前环境无符号链接权限")
    assert is_within(str(link / "x.py"), [str(real)]) is True


def test_check_path_missing_param_denied() -> None:
    """B-31：触路径工具缺路径参数视为 deny 而非跳过。"""
    allowed, reason = check_path(None, ["/tmp"], expects_path=True)
    assert allowed is False
    assert reason is not None and "缺少必需的路径参数" in reason


def test_check_path_non_path_tools_pass() -> None:
    allowed, reason = check_path(None, [], expects_path=False)
    assert allowed is True and reason is None
