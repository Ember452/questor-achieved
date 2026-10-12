"""协议信封：NDJSON 行 ↔ 请求/响应/通知（protocol.md §1）。

刻意薄：只做"字节 ↔ 结构"的转换，不碰语义。字符串错误码（不假装 JSON-RPC 数值码）
的合法取值来自 `schemas/app_server/v0-1.json` 的枚举——由
`tests/architecture/test_serve_names_are_contracted.py` 机械核对，方法名与通知族同。

行缓冲有上限（protocol §1）：超限即拒该帧并保留连接，不无限缓冲。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "MAX_LINE_BYTES",
    "Notification",
    "ProtocolFrameError",
    "Request",
    "encode_line",
    "error_line",
    "error_payload",
    "notification_line",
    "parse_line",
    "response_line",
]

#: 单行 JSON 上限 64 MiB（protocol.md §1）；超限的命令输出走全量日志引用
MAX_LINE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Request:
    """一条客户端请求。``id`` 用于关联响应，``method`` 是协议方法名。"""

    id: str
    method: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Notification:
    """服务端 → 客户端通知（无 id，客户端不得拿它当响应）。"""

    method: str
    params: dict[str, Any] = field(default_factory=dict)


class ProtocolFrameError(ValueError):
    """帧不合法（非 JSON / 缺字段 / 超限）。调用方回 `invalid_params` 或忽略该行。"""


def encode_line(payload: dict[str, Any]) -> str:
    """结构 → 单行 JSON（NDJSON：一行一帧，行尾由调用方补换行）。"""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode("utf-8")) > MAX_LINE_BYTES:
        raise ProtocolFrameError(f"单帧超过 {MAX_LINE_BYTES} 字节上限，应改走 deferred content")
    return text


def parse_line(text: str) -> Request:
    """解析请求帧；缺 id/method 或非法 JSON 一律抛 :class:`ProtocolFrameError`。"""
    if not text.strip():
        raise ProtocolFrameError("空行不是请求帧")
    if len(text.encode("utf-8")) > MAX_LINE_BYTES:
        raise ProtocolFrameError("请求帧超过单行上限")
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ProtocolFrameError(f"不是合法 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise ProtocolFrameError("帧顶层必须是对象")
    request_id = payload.get("id")
    method = payload.get("method")
    if not isinstance(request_id, str) or not isinstance(method, str):
        raise ProtocolFrameError("请求帧必须含字符串 id 与 method")
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise ProtocolFrameError("params 给定则必须是对象")
    return Request(id=request_id, method=method, params=dict(params))


def response_line(request_id: str, result: dict[str, Any]) -> str:
    """成功响应（回显 id，客户端按 id 关联）。"""
    return encode_line({"id": request_id, "result": result})


def error_payload(
    code: str, message: str, *, model_next_action: str | None = None
) -> dict[str, Any]:
    """错误载荷：码是字符串；`model_next_action` 是 limen 方言的可选字段。"""
    payload: dict[str, Any] = {"code": code, "message": message}
    if model_next_action:
        payload["model_next_action"] = model_next_action
    return payload


def error_line(request_id: str, payload: dict[str, Any]) -> str:
    return encode_line({"id": request_id, "error": payload})


def notification_line(notification: Notification) -> str:
    return encode_line({"method": notification.method, "params": notification.params})
