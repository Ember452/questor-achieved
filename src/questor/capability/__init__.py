"""capability —— feature flag 与能力开关（L4 渐进启用的机制，overview §6）。

三柱归属：**可见**的开关面——哪些能力开着对用户必须可见（协议 initialize 回显），
绝不静默启用。

依赖裁决（ADR-0012）：本模块不 import config——只定义旗标注册表与查询接口；
配置值由上层组装时注入。默认全关：L4 能力（MCP/skills/hooks/插件/网页宿主等）
显式 enable 才存在，与协议侧"能力 opt-in 声明"（B-61）同源。
"""

from __future__ import annotations

from enum import StrEnum


class FeatureFlag(StrEnum):
    """L4 能力旗标：默认全关，显式启用才存在；新旗标加入必须保持默认关。"""

    MCP = "mcp"
    SKILLS = "skills"
    HOOKS = "hooks"
    PLUGINS = "plugins"
    WEB_HOST = "web_host"
    IM_CHANNELS = "im_channels"
    CONTAINERS = "containers"
    BROWSER_PANEL = "browser_panel"

    @classmethod
    def by_name(cls, name: str) -> FeatureFlag:
        """按字符串名取旗标；未知名字显式报错（组装层解析配置时消费）。"""
        try:
            return cls(name)
        except ValueError as exc:
            raise ValueError(f"未知的 feature flag：{name!r}") from exc


class FeatureFlags:
    """旗标注册表：默认全关、显式开关、组装层注入覆盖。

    非线程安全——M2.1 的组装发生在启动期单线程；引入并发需求时按 ADR 再升级。
    """

    def __init__(self) -> None:
        self._enabled: set[FeatureFlag] = set()

    def is_enabled(self, flag: FeatureFlag) -> bool:
        """该能力当前是否启用（默认 False——opt-in 语义）。"""
        return flag in self._enabled

    def enable(self, flag: FeatureFlag) -> None:
        """启用能力；幂等。"""
        self._enabled.add(flag)

    def disable(self, flag: FeatureFlag) -> None:
        """停用能力；停用即停全部相关产品行为（M7 出口语义的基础）。"""
        self._enabled.discard(flag)

    def enable_only(self, flags: frozenset[FeatureFlag] | set[FeatureFlag]) -> None:
        """以组装层给定的集合覆盖当前开关状态（快照式注入，不叠加）。"""
        self._enabled = set(flags)

    def enabled_names(self) -> tuple[str, ...]:
        """已启用旗标的名字（排序稳定，供协议 initialize 回显与测试断言）。"""
        return tuple(sorted(f.value for f in self._enabled))
