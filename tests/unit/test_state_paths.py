"""state.paths 单元行为：home 重定向、id 校验、slug 与 workspace 目录名。

fake_home 隔离 ``~/.questor``，防测试污染真实会话记录。
"""

from __future__ import annotations

import os
import pathlib

import pytest

from questor.state.paths import (
    config_path,
    files_dir,
    index_dir,
    questor_home,
    sanitize_slug,
    sessions_dir,
    thread_path,
    tool_result_path,
    validate_entity_id,
    validate_filename_component,
    workspace_dir_name,
    workspaces_dir,
)
from questor.testenv.fake_home import fake_home


def test_home_honors_questor_home_env() -> None:
    with fake_home() as tmp:
        assert questor_home() == (tmp / ".questor").resolve()


def test_home_env_read_at_call_time(tmp_path: pathlib.Path) -> None:
    """B-73：env 覆盖必须每次调用时求值——中途改环境立即生效，无缓存。"""
    with fake_home() as tmp:
        first = questor_home()
        relocated = tmp / "relocated"
        os.environ["QUESTOR_HOME"] = str(relocated)
        try:
            second = questor_home()
        finally:
            os.environ["QUESTOR_HOME"] = str(tmp / ".questor")
    assert first != second
    assert os.path.normcase(str(second)) == os.path.normcase(str(relocated))


def test_standard_dirs_live_under_home() -> None:
    with fake_home() as tmp:
        home = tmp / ".questor"
        assert sessions_dir() == home / "sessions"
        assert index_dir() == home / "index"
        assert files_dir() == home / "files"
        assert workspaces_dir() == home / "workspaces"
        assert config_path() == home / "config.toml"


@pytest.mark.parametrize(
    "bad",
    ["", ".", "..", "ABC", "-abc", "a_b", "a/b", "a\\b", "a b"],
)
def test_entity_id_rejects_bad_shapes(bad: str) -> None:
    # 空串/点项/大写/连字符开头/下划线/分隔符/空格均不符合 data-model §1 的 id 形状
    with pytest.raises(ValueError):
        validate_entity_id(bad)


def test_entity_id_accepts_canonical_shape() -> None:
    assert validate_entity_id("abc-123") == "abc-123"


def test_thread_path_is_sessions_jsonl() -> None:
    with fake_home():
        assert thread_path("abc-123") == sessions_dir() / "abc-123.jsonl"


def test_thread_path_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        thread_path("../escape")


@pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b", "a:b", "a b"])
def test_filename_component_rejects_unsafe(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_filename_component(bad)


def test_filename_component_allows_provider_ids() -> None:
    # provider 的 tool_use_id 可能带大写/下划线/点，落盘只要求路径组件安全
    assert tool_result_path("toolu_01ABC.def") == sessions_dir() / "toolu_01ABC.def.txt"


def test_sanitize_slug_folds_and_trims() -> None:
    assert sanitize_slug("My.Project_v2") == "My.Project_v2"
    assert sanitize_slug("我的项目") == "workspace"  # 全非法 → 回落
    assert sanitize_slug("a//b??c") == "a-b-c"
    assert len(sanitize_slug("x" * 100)) <= 48


def test_workspace_dir_name_stable_and_hashed() -> None:
    with fake_home() as tmp:
        root = tmp / "proj"
        root.mkdir()
        name_one = workspace_dir_name(root)
        name_two = workspace_dir_name(root)
        assert name_one == name_two
        slug, _, digest = name_one.rpartition("-")
        assert slug == "proj"
        assert len(digest) == 16 and all(c in "0123456789abcdef" for c in digest)
        assert workspace_dir_name(tmp / "other") != name_one


def test_workspace_dir_name_canonicalizes_symlinks(tmp_path: pathlib.Path) -> None:
    """符号链接路径与真实路径必须映射同一目录（wuu EvalSymlinks 语义）。"""
    real = tmp_path / "real-proj"
    real.mkdir()
    try:
        link = tmp_path / "link-proj"
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("当前环境无符号链接权限（Windows 未开开发者模式等）")
    assert workspace_dir_name(link) == workspace_dir_name(real)
