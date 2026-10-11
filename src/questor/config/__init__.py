"""config —— 类型化配置加载与作用域合并（overview §6）。

三柱归属：**可见**——配置问题摊开给用户（protocol initialize 的 needs_setup/issues），
本模块负责把分层后的真相当作唯一事实交给上层。公开入口见 :mod:`questor.config.loader`。
"""

from __future__ import annotations

from questor.config.loader import (
    USER_ONLY_FIELDS,
    ConfigError,
    ConfigSnapshot,
    load_config,
)

__all__ = [
    "USER_ONLY_FIELDS",
    "ConfigError",
    "ConfigSnapshot",
    "load_config",
]
