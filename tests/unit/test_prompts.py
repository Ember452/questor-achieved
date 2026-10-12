"""prompts 单元行为：资产加载、占位符替换、缺资产显式爆炸、资产结构守卫、
分块装配与缓存边界（ADR-0018）。"""

from __future__ import annotations

import pytest

from questor import prompts
from questor.prompts import (
    PromptAssemblyError,
    PromptBlock,
    PromptBlockKind,
    PromptNotFoundError,
    assemble,
    system_assembly,
)


def test_available_lists_all_assets() -> None:
    names = prompts.available()
    # M2.2 的临时三件 + M2.3 的分块三件 + M4 编排三件（plan/task/goal）；
    # 原 system_core 已拆进 agent_identity/questor_rules（ADR-0018：同一内容不留两份）。
    # 新增资产时此清单随之更新（防"放了资产没人用"）
    assert names == (
        "agent_identity",
        "converge_message",
        "goal_loop",
        "max_tokens_escalation",
        "max_tokens_recovery",
        "plan_protocol",
        "questor_rules",
        "summary_protocol",
        "summary_request",
        "task_protocol",
        "tool_policy",
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
    assert prompts.render("agent_identity") == prompts.raw("agent_identity")


# ---- 分块装配与缓存边界（ADR-0018；B-81 的形状断言） ----


def test_stability_is_derived_from_kind() -> None:
    """stable 归属由 kind 推导，调用方不能自报——防止把易变内容谎标成稳定以套缓存。"""
    assert PromptBlock(PromptBlockKind.ENVIRONMENT, "cwd").stable is False
    assert PromptBlock(PromptBlockKind.QUESTOR_RULES, "rules").stable is True
    assert PromptBlock(PromptBlockKind.PROJECT_RULES, "AGENTS.md").stable is True
    assert PromptBlock(PromptBlockKind.TOOL_POLICY, "tools").stable is True


def test_assemble_rejects_volatile_before_stable() -> None:
    """B-81：动态内容排在稳定前缀之前会让缓存前缀永不命中——装配层直接拒。"""
    with pytest.raises(PromptAssemblyError, match="environment"):
        assemble(
            [
                PromptBlock(PromptBlockKind.ENVIRONMENT, "cwd=D:/x"),
                PromptBlock(PromptBlockKind.QUESTOR_RULES, "rules"),
            ]
        )


def test_assemble_computes_boundary_and_drops_empty_blocks() -> None:
    """空块不产出（没配 project_rules 不应产生空段落）；边界=首个 volatile 的下标。"""
    assembly = assemble(
        [
            PromptBlock(PromptBlockKind.AGENT_IDENTITY, "identity"),
            PromptBlock(PromptBlockKind.PROJECT_RULES, ""),
            PromptBlock(PromptBlockKind.TOOL_POLICY, "tool policy"),
            PromptBlock(PromptBlockKind.ENVIRONMENT, "cwd"),
        ]
    )
    assert [b.kind.value for b in assembly.blocks] == [
        "agent_identity",
        "tool_policy",
        "environment",
    ]
    assert assembly.cache_boundary == 2
    assert all(b.stable for b in assembly.cacheable)
    assert assembly.text == "identity\n\ntool policy\n\ncwd"


def test_system_assembly_keeps_environment_out_of_the_cached_prefix() -> None:
    """M2.3 的真实装配：环境事实进不了缓存前缀（B-81 的可检形状断言）。"""
    assembly = system_assembly(project_rules="AGENTS.md 内容", environment="cwd=D:/p")
    assert assembly.cache_boundary == len(assembly.cacheable)
    assert [b.kind for b in assembly.cacheable] == [
        PromptBlockKind.AGENT_IDENTITY,
        PromptBlockKind.QUESTOR_RULES,
        PromptBlockKind.PROJECT_RULES,
        PromptBlockKind.TOOL_POLICY,
    ]
    tail = assembly.blocks[assembly.cache_boundary :]
    assert [b.kind for b in tail] == [PromptBlockKind.ENVIRONMENT]


def test_every_stable_kind_has_an_asset() -> None:
    """护栏：登记了 stable kind 就必须有随包发布的资产——防"加了枚举没人填内容"。"""
    asset_backed = {
        PromptBlockKind.AGENT_IDENTITY,
        PromptBlockKind.QUESTOR_RULES,
        PromptBlockKind.TOOL_POLICY,
        PromptBlockKind.SUMMARY_PROTOCOL,
    }
    for kind in asset_backed:
        assert prompts.raw(kind.value), kind
    # project_rules 来自目标仓库的 AGENTS.md，不由本包提供资产
    assert PromptBlockKind.PROJECT_RULES not in asset_backed
