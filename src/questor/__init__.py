"""Questor —— 可审计的个人 AI Agent 工作站。

预-alpha 阶段：包根只做最小聚合，不放业务逻辑。版本经 :mod:`questor.version`
单点解析（根 ``VERSION`` 是唯一真相源），用 PEP 562 惰性求值——import 本包不触发
版本解析，安装损坏只在真正取 ``__version__`` 时报错。
工程约束见 AGENTS.md（复用三分法与语义唯一来源表），决策记录见 docs/adr/。
"""

from __future__ import annotations

_DEFERRED_ATTRS = frozenset({"__version__"})


def __getattr__(name: str) -> str:
    if name == "__version__":
        from questor.version import questor_version

        return questor_version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals()) + list(_DEFERRED_ATTRS))
