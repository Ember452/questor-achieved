"""config.loader 单元行为：分层合并、strip 用户专属字段（B-57/B-75）、错误呈现。"""

from __future__ import annotations

import logging
import pathlib

import pytest

from questor.config import ConfigError, load_config
from questor.config.loader import _deep_merge
from questor.testenv.fake_home import fake_home

USER_TOML = """
[providers.anthropic]
api_key = "user-key-in-user-layer-is-kept"

[ui]
theme = "dark"
refresh = 5
tags = ["a", "b"]

[tools]
timeout_s = 30
"""

SHARED_TOML = """
[providers.anthropic]
api_key = "LEAKED-SHARED-KEY"       # B-57：项目层带凭据 → strip
API_Key = "LEAKED-CASE-VARIANT"     # B-75：大小写变体 → 全拼写删除
base_url = "https://example.invalid"

[permission_mode]
mode = "unconfined"                 # 键名为 permission_mode 的表 → 整键删除

[permission_mode_override]
note = "my_api_key 不是全拼匹配，必须保留"

[ui]
theme = "light"                     # 标量覆盖
tags = ["c"]                        # 列表整体替换

[tools]
timeout_s = 60
"""

LOCAL_TOML = """
[ui]
refresh = 10

[providers]
auth_token = "LEAKED-LOCAL-TOKEN"   # 本地层同样 strip（凭据不进任何项目层）
"""


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _project(home: pathlib.Path, shared: str = "", local: str = "") -> pathlib.Path:
    """项目根放在 fake home 之下的子目录——不得与 QUESTOR_HOME 本身重合。"""
    root = home / "project"
    if shared:
        _write(root / ".questor" / "config.toml", shared)
    if local:
        _write(root / ".questor" / "config.local.toml", local)
    return root


def test_user_layer_only() -> None:
    with fake_home() as tmp:
        _write(tmp / ".questor" / "config.toml", USER_TOML)
        snap = load_config()
        assert snap.layers_applied == ("user",)
        assert snap.data["providers"]["anthropic"]["api_key"] == "user-key-in-user-layer-is-kept"
        assert snap.data["ui"]["theme"] == "dark"


def test_layers_merge_deep_and_override() -> None:
    with fake_home() as tmp:
        _write(tmp / ".questor" / "config.toml", USER_TOML)
        root = _project(tmp, shared=SHARED_TOML, local=LOCAL_TOML)
        snap = load_config(root)
        assert snap.layers_applied == ("user", "project-shared", "project-local")
        # 深合并：shared 只覆盖 theme，refresh 留待 local，tags 整体替换
        assert snap.data["ui"]["theme"] == "light"
        assert snap.data["ui"]["refresh"] == 10
        assert snap.data["ui"]["tags"] == ["c"]
        assert snap.data["tools"]["timeout_s"] == 60


def test_user_only_fields_stripped_from_project_layers(caplog: pytest.LogCaptureFixture) -> None:
    with fake_home() as tmp:
        _write(tmp / ".questor" / "config.toml", USER_TOML)
        root = _project(tmp, shared=SHARED_TOML, local=LOCAL_TOML)
        with caplog.at_level(logging.WARNING, logger="questor.config.loader"):
            snap = load_config(root)
    # 共享层凭据剥离：用户层的合法 api_key 保留，泄漏值没有进来
    assert snap.data["providers"]["anthropic"]["api_key"] == "user-key-in-user-layer-is-kept"
    assert "API_Key" not in snap.data["providers"]["anthropic"]
    assert "permission_mode" not in snap.data
    # 非全拼匹配的键保留（B-75 的另一半：不做子串误伤）
    assert snap.data["permission_mode_override"]["note"] == "my_api_key 不是全拼匹配，必须保留"
    # 本地层的 auth_token 也被剥离（用户层没有此键 → 合并后不存在）
    assert "auth_token" not in snap.data["providers"]
    # strip 都有一次性警告
    assert len(snap.stripped) == 4
    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 4
    assert any("api_key" in w for w in warnings)
    assert any("permission_mode" in w for w in warnings)


def test_strip_warning_deduped_within_process(caplog: pytest.LogCaptureFixture) -> None:
    with fake_home() as tmp:
        root = _project(tmp, shared=SHARED_TOML)
        with caplog.at_level(logging.WARNING, logger="questor.config.loader"):
            load_config(root)
            first = len(caplog.records)
            load_config(root)
            assert len(caplog.records) == first, "同一层同一字段的警告只发一次"


def test_missing_layers_are_skipped() -> None:
    with fake_home():
        snap = load_config()
        assert snap.layers_applied == ()
        assert snap.data == {}


def test_malformed_toml_raises_with_path(tmp_path: pathlib.Path) -> None:
    with fake_home() as tmp:
        broken = tmp / ".questor" / "config.toml"
        _write(broken, "[ui\nbroken =")
        with pytest.raises(ConfigError, match="config.toml"):
            load_config()


def test_deep_merge_does_not_mutate_inputs() -> None:
    base = {"a": {"x": 1, "y": 2}, "keep": True}
    overlay = {"a": {"x": 9, "z": 3}}
    merged = _deep_merge(base, overlay)
    assert merged == {"a": {"x": 9, "y": 2, "z": 3}, "keep": True}
    assert base == {"a": {"x": 1, "y": 2}, "keep": True}, "输入不得被改写"
    assert overlay == {"a": {"x": 9, "z": 3}}
