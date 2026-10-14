"""initialize 握手契约（protocol.md §2）。

# Reimplements wuu@wuu-main internal/appserver/protocol.go#L264-325（InitializeParams/Result）
#   + config_handlers.go#L45-97（handleInitialize 装配与版本校验）。
# pitfalls: B-60（版本严格相等不降级）B-61（deferred/reverse 皆 opt-in）

插件/二开面字段（extension_trust/extension_inventory）按 protocol.md §2 裁剪，不在 questor 契约
（ADR-0044 不做插件宿主）。若干大 summary（permissions/providers/model_profile/tool_surface/
model_roles/model_aliases/advanced_settings/general_settings）的**完整字段属 config 面**，本 Phase 1
未实测、以 `dict[str, Any]` 不透明透传占位（不凭猜编字段表，§1.5 机制 1），随 Phase 2 config 面
移植逐字段收紧——此为 port-ledger 登记过的后置，非静默遗漏。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from questor.schemas.app_server.names import PROTOCOL_VERSION

__all__ = [
    "ClientCapabilities",
    "ClientInfo",
    "CoreBuildInfo",
    "FeatureFlags",
    "InitializeParams",
    "InitializeResult",
    "ReverseRPCCapabilities",
    "RuntimeIssue",
    "RuntimeHostSummary",
]


class _Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class ClientInfo(_Wire):
    name: str | None = None
    version: str | None = None


class ReverseRPCCapabilities(_Wire):
    methods: list[str] | None = None


class ClientCapabilities(_Wire):
    """能力声明全 opt-in（B-61）：省略的能力核心绝不发对应请求。"""

    reverse_rpc: ReverseRPCCapabilities | None = None
    deferred_notification_content: bool = False


class InitializeParams(_Wire):
    protocol_version: str | None = None
    client: ClientInfo | None = None
    capabilities: ClientCapabilities | None = None

    def version_error(self) -> str | None:
        """版本校验（config_handlers.go#L50-51）。

        非空且 ≠ 服务端串即返错误消息（严格相等、不降级，B-60）。
        """
        given = self.protocol_version
        if given and given != PROTOCOL_VERSION:
            return f"unsupported protocol version {given!r} (server uses {PROTOCOL_VERSION!r})"
        return None


class CoreBuildInfo(_Wire):
    version: str | None = None
    commit: str | None = None
    date: str | None = None
    dirty: bool = False


class RuntimeHostSummary(_Wire):
    kind: str
    instance_id: str | None = None


class RuntimeIssue(_Wire):
    code: str
    provider: str | None = None
    message: str | None = None


class FeatureFlags(_Wire):
    project_agent: bool = False
    browser: bool = False
    safe_mode: bool = False


class InitializeResult(_Wire):
    """握手结果（装配 config_handlers.go#L65-97）。

    `provider`/`model` 是**当前活动选择串**（非凭据）；凭据类字段永不经本契约上线（P1-4）。
    """

    status: str
    issues: list[RuntimeIssue] | None = None
    protocol_version: str
    core: CoreBuildInfo
    provider: str
    model: str
    max_parallel: int
    runtime_host: RuntimeHostSummary
    workspace_root: str
    features: FeatureFlags
    effort: str | None = None
    variant: str | None = None
    # 以下 summary 完整字段属 config 面，Phase 2 收紧（见模块 docstring）。
    permissions: dict[str, Any] | None = None
    model_profile: dict[str, Any] | None = None
    tool_surface: dict[str, Any] | None = None
    model_roles: list[dict[str, Any]] | None = None
    model_aliases: dict[str, Any] | None = None
    providers: list[dict[str, Any]] | None = None
    advanced_settings: dict[str, Any] | None = None
    general_settings: dict[str, Any] | None = None
