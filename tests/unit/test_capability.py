"""capability 单元行为：默认全关、显式开关、覆盖注入、未知旗标报错。"""

from __future__ import annotations

import pytest

from questor.capability import FeatureFlag, FeatureFlags


def test_default_all_off() -> None:
    flags = FeatureFlags()
    assert flags.enabled_names() == ()
    for flag in FeatureFlag:
        assert flags.is_enabled(flag) is False


def test_enable_disable_is_idempotent() -> None:
    flags = FeatureFlags()
    flags.enable(FeatureFlag.MCP)
    flags.enable(FeatureFlag.MCP)
    assert flags.enabled_names() == ("mcp",)
    flags.disable(FeatureFlag.MCP)
    flags.disable(FeatureFlag.MCP)  # 幂等
    assert flags.enabled_names() == ()


def test_enable_only_replaces_whole_state() -> None:
    flags = FeatureFlags()
    flags.enable(FeatureFlag.CONTAINERS)
    flags.enable_only({FeatureFlag.WEB_HOST, FeatureFlag.IM_CHANNELS})
    assert flags.enabled_names() == ("im_channels", "web_host")


def test_by_name_and_unknown_rejected() -> None:
    assert FeatureFlag.by_name("mcp") is FeatureFlag.MCP
    with pytest.raises(ValueError, match="未知的 feature flag"):
        FeatureFlag.by_name("not-a-flag")
