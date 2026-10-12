"""serve —— 网关与协议服务（overview §6：最上层组装点，矩阵上不得 import `cli`）。

三柱归属：**可见**与**可干预**的通道。GUI 能力必须经协议可达——不存在"只有桌面壳
能调"的私有端点（overview §14），所以本包是能力的**唯一对外形状**，M3 的 WS/SSE
宿主与桌面 sidecar 共用同一张方法表（`protocol.md` §8 的硬约定）。

本期是 M2.3 雏形：NDJSON over stdio + 会话层五个方法。名称合法性由
`tests/architecture/test_serve_names_are_contracted.py` 对着 `protocol.md` 判定；
`HandlerCtx`（含 `principal` 传递位）由 ADR-0020 定形。
"""

from __future__ import annotations

from questor.serve.app_server import PROTOCOL_NAME, AppServer, build_dispatcher
from questor.serve.dispatch import Dispatcher, Handler, HandlerCtx
from questor.serve.envelope import (
    MAX_LINE_BYTES,
    Notification,
    ProtocolFrameError,
    Request,
    error_payload,
    parse_line,
    response_line,
)
from questor.serve.notifications import PROTOCOL_NOTIFICATIONS, notification_of
from questor.serve.stdio import run_stdio, write_line

__all__ = [
    "MAX_LINE_BYTES",
    "PROTOCOL_NAME",
    "PROTOCOL_NOTIFICATIONS",
    "AppServer",
    "Dispatcher",
    "Handler",
    "HandlerCtx",
    "Notification",
    "ProtocolFrameError",
    "Request",
    "build_dispatcher",
    "error_payload",
    "notification_of",
    "parse_line",
    "response_line",
    "run_stdio",
    "write_line",
]
