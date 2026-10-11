"""prompts 单元行为：资产加载、占位符替换、缺资产显式爆炸、资产结构守卫。"""

from __future__ import annotations

import pytest

from questor import prompts
from questor.prompts import PromptNotFoundError


def test_available_lists_all_assets() -> None:
    names = prompts.available()
    # M2.2 当期消费的四件；新增资产时此清单随之更新（防"放了资产没人用"）
    assert names == (
        "converge_message",
        "max_tokens_escalation",
        "max_tokens_recovery",
        "system_core",
    )


def test_render_substitutes_placeholders() -> None:
    text = prompts.render("converge_message", reason="token budget exceeded")
    assert "token budget exceeded" in text
    assert "$reason" not in text


def test_render_missing_value_raises() -> None:
    with pytest.raises(KeyError):
        prompts.render("converge_message")  # $reason 缺值


def test_missing_asset_raises_prompt_not_found() -> None:
    with pytest.raises(PromptNotFoundError, match="no-such-prompt"):
        prompts.raw("no-such-prompt")


def test_assets_are_structurally_valid() -> None:
    """护栏：assets/ 下每个 .toml 都必须有非空 description 与 body——防止半成品资产混进发布包。"""
    import tomllib
    from importlib import resources

    files = resources.files("questor.prompts.assets")
    toml_files = [p for p in files.iterdir() if p.name.endswith(".toml")]
    assert toml_files, "资产目录不应为空"
    for entry in toml_files:
        data = tomllib.loads(entry.read_text(encoding="utf-8"))
        assert isinstance(data.get("description"), str) and data["description"], entry.name
        assert isinstance(data.get("body"), str) and data["body"], entry.name


def test_render_without_placeholders_returns_body_unchanged() -> None:
    """无占位符的资产渲染即原文；选型依据见 render docstring（Template 不吃大括号）。"""
    assert prompts.render("system_core") == prompts.raw("system_core")
