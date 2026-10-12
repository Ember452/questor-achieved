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
    "ProtocolError",
    "ProtocolFrameError",
    "Request",
    "encode_line",
    "error_line",
    "error_payload",
    "notification_line",
    "parse_line",
    "response_line",
    "reverse_request_line",
    "try_parse_reverse_response",
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


class ProtocolError(ValueError):
    """业务错误的载体：handler raise 本异常 = 用 `code` 而非默认 `invalid_params`。

    与 ValueError 的分工：ValueError = 参数校验失败（信封层）；ProtocolError =
    “请求合法但业务上拒”（stale_revision / boundary_denied 等）。Dispatcher
    先接 ProtocolError、后接 ValueError，确保 code 不被吞。model_next_action 可选，
    给模型时带上下一步动作（与 limen 方言同源）。
    """

    def __init__(self, code: str, message: str, *, model_next_action: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.model_next_action = model_next_action


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


def reverse_request_line(request_id: str, method: str, params: dict[str, Any]) -> str:
    """服务端反向请求帧：带 `id` + `method` + `params`，形式与客户端 Request 同。

    与通知不同：通知无 id 且客户端不得当响应；反向请求的 `id` 是服务端生成的
    correlation_id，客户端回同一 id 的响应，Dispatcher._resolve_pending 按它路由（B-59）。
    """
    return encode_line({"id": request_id, "method": method, "params": params})


def try_parse_reverse_response(
    text: str,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None] | None:
    """尝试将一行解析为“客户端对反向请求的响应”；不是则 None。

    判据：顶层对象且包含 `id`、不包含 `method`、且至少含 `result` 或 `error`。
    与 `parse_line` 的分工：parse_line 处理客户端上行 Request（必有 method），
    本函数处理下行 Response（method 不存在）。handle_line 先看本函数、后看
    parse_line，避免 B-59 描述的“响应被 unknown_method 吞”回环。
    """
    import json as _json

    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = _json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    rid = payload.get("id")
    if not isinstance(rid, str):
        return None
    if "method" in payload:
        return None
    if "result" not in payload and "error" not in payload:
        return None
    result = payload.get("result") if isinstance(payload.get("result"), dict) else None
    error = payload.get("error") if isinstance(payload.get("error"), dict) else None
    return rid, result, error
