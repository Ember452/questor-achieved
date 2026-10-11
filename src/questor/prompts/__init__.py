"""prompts —— 运行时提示词与指令资产（overview §6；随包发布，禁止内联在代码里）。

三柱归属：**可验证**的辅路——提示词是 agent 行为的一部分，作为资产随包发布才能
被审计与 diff，而不是散落在循环代码的字符串字面量里。

形态：``assets/*.toml``，每个文件 ``description``（中文一句话用途）+ ``body``
（提示词正文，``$placeholder`` 占位经 :func:`render` 替换）。M2.2 只落 engine
当期消费的四件；plan 模式提醒随 M4 orchestration、摘要协议随 M2.3 context 落盘
（文档视距：不预置未消费的资产）。
"""

from __future__ import annotations

import string
import tomllib
from importlib import resources
from typing import Any

_ASSETS_PACKAGE = "questor.prompts.assets"


class PromptNotFoundError(KeyError):
    """资产名不存在——调用方拼写错误或资产未随包发布，显式爆炸不猜。"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"提示词资产不存在：{name!r}（available() 见清单）")


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
