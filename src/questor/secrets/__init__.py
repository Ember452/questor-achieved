"""secrets —— 凭据存储（OS keyring 优先）与守卫（overview §6）。

三柱归属：**可验证**的辅路——凭据永不进会话记录与日志（红线 ①），
"验证用了什么凭据"只能以键名出现在记录里，值永远遮蔽。

存储次序：OS keyring（Windows 凭据管理器等，ADR-0013）优先；keyring 不可用时
回落 ``<home>/secrets/<key>`` 文件（0600，明文落盘带一次性告警——诚实呈现，
绝不伪装"已加密"）。值一律以 ``SecretStr`` 出入（红线 ①：repr/日志不泄漏）。
"""

from __future__ import annotations

from questor.secrets.store import SERVICE_NAME, delete_secret, get_secret, set_secret

__all__ = [
    "SERVICE_NAME",
    "delete_secret",
    "get_secret",
    "set_secret",
]
