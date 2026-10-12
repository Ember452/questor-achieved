"""prompts —— 运行时提示词与指令资产（overview §6；随包发布，禁止内联在代码里）。

三柱归属：**可验证**的辅路——提示词是 agent 行为的一部分，作为资产随包发布才能
被审计与 diff，而不是散落在循环代码的字符串字面量里。

形态：``assets/*.toml``，每个文件 ``description``（中文一句话用途）+ ``body``
（提示词正文，``$placeholder`` 占位经 :func:`render` 替换）。M2.2 只落 engine
当期消费的四件；plan 模式提醒随 M4 orchestration、摘要协议随 M2.3 context 落盘
（文档视距：不预置未消费的资产）。

分块装配（ADR-0018）：system 不再是一串混装文本，而是**类型化块 + 缓存边界**：
稳定块（身份/规则/项目指令/工具约定）排在边界之前，易变块（环境事实）排在之后。
稳定性由 kind 推导、边界归 prompts 侧判定，provider 只消费结果（不得自己猜哪段可缓存）。
"""

from __future__ import annotations

import string
import tomllib
from collections.abc import Sequence
from importlib import resources
from typing import Any

from questor.schemas.llm import (
    STABLE_PROMPT_BLOCK_ORDER,
    PromptAssembly,
    PromptBlock,
    PromptBlockKind,
)

__all__ = [
    "PromptAssembly",
    "PromptAssemblyError",
    "PromptBlock",
    "PromptBlockKind",
    "PromptNotFoundError",
    "assemble",
    "available",
    "raw",
    "render",
    "summary_assembly",
    "system_assembly",
]

_ASSETS_PACKAGE = "questor.prompts.assets"


class PromptNotFoundError(KeyError):
    """资产名不存在——调用方拼写错误或资产未随包发布，显式爆炸不猜。"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"提示词资产不存在：{name!r}（available() 见清单）")


class PromptAssemblyError(ValueError):
    """装配违反"稳定在前"不变量——不是格式问题，而是会让缓存前缀永不命中的设计错（B-81）。"""


def assemble(blocks: Sequence[PromptBlock]) -> PromptAssembly:
    """按"稳定在前"不变量装配；违反即抛 :class:`PromptAssemblyError`（B-81）。

    空文本块直接丢弃（没配 project_rules 不应在 system 里留下空段落）。边界 = 首个
    易变块的下标；没有易变块时边界就是块数。
    """
    kept = [block for block in blocks if block.text.strip()]
    volatile_at = [index for index, block in enumerate(kept) if not block.stable]
    boundary = volatile_at[0] if volatile_at else len(kept)
    misplaced = [block for block in kept[boundary:] if block.stable]
    if misplaced:
        raise PromptAssemblyError(
            f"稳定块 {misplaced[0].kind.value!r} 排在易变块 {kept[boundary].kind.value!r} 之后，"
            "会让缓存前缀永不命中（B-81）"
        )
    return PromptAssembly(tuple(kept), boundary)


def system_assembly(
    *,
    project_rules: str | None = None,
    tool_inventory: str | None = None,
    environment: str | None = None,
) -> PromptAssembly:
    """M2.3 的真实装配：随包资产 + 调用方提供的项目指令、工具清单与环境事实。

    ``project_rules`` 来自目标仓库的指令文件（会话内不变，算稳定）；``tool_inventory``
    是可用工具清单摘要（压缩后重注入需要，B-11）；``environment`` 是 cwd/日期一类
    事实（易变，**不进缓存前缀**）。三者由装配点（cli/serve）与压缩重注入（context）传入——
    本模块不做文件与网络 IO。块序按 :data:`STABLE_PROMPT_BLOCK_ORDER`，同义不同序在此关掉。
    """
    supplied: dict[PromptBlockKind, str] = {
        PromptBlockKind.AGENT_IDENTITY: raw(PromptBlockKind.AGENT_IDENTITY.value),
        PromptBlockKind.QUESTOR_RULES: raw(PromptBlockKind.QUESTOR_RULES.value),
        PromptBlockKind.PROJECT_RULES: project_rules or "",
        PromptBlockKind.TOOL_POLICY: raw(PromptBlockKind.TOOL_POLICY.value),
        PromptBlockKind.TOOL_INVENTORY: tool_inventory or "",
    }
    stable = [
        PromptBlock(kind, supplied[kind]) for kind in STABLE_PROMPT_BLOCK_ORDER if kind in supplied
    ]
    volatile = [PromptBlock(PromptBlockKind.ENVIRONMENT, environment or "")]
    return assemble([*stable, *volatile])


def summary_assembly() -> PromptAssembly:
    """摘要那一趟模型调用的 system（B-29）。

    它是独立的 pass，不拿主 system——主提示词里有"用工具去验证"的指令，
    而摘要 pass 必须只输出文本（资产里写死了不得调工具）。
    """
    return assemble(
        [PromptBlock(PromptBlockKind.SUMMARY_PROTOCOL, raw(PromptBlockKind.SUMMARY_PROTOCOL.value))]
    )


def available() -> tuple[str, ...]:
    """全部资产名（不含 .toml 后缀，排序稳定）。"""
    files = resources.files(_ASSETS_PACKAGE)
    return tuple(
        sorted(p.name.removesuffix(".toml") for p in files.iterdir() if p.name.endswith(".toml"))
    )


def raw(name: str) -> str:
    """读资产的 ``body`` 原文（不做占位符替换）；缺资产抛 :class:`PromptNotFoundError`。"""
    files = resources.files(_ASSETS_PACKAGE)
    entry = files.joinpath(f"{name}.toml")
    if not entry.is_file():
        raise PromptNotFoundError(name)
    data: dict[str, Any] = tomllib.loads(entry.read_text(encoding="utf-8"))
    body = data.get("body")
    if not isinstance(body, str) or not body:
        raise ValueError(f"提示词资产 {name!r} 缺少非空 body 字段")
    return body


def render(name: str, **values: str) -> str:
    """读资产并替换 ``$placeholder`` 占位符；缺占位符值显式抛 KeyError。

    用 :class:`string.Template` 而非 ``str.format``——提示词正文里的大括号
    （JSON 示例等）不会被误当占位符。
    """
    return string.Template(raw(name)).substitute(**values)
