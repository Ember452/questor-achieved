"""线信封契约模型：Request / Response / ResponseError / Notification（protocol.md §1）。

# Reimplements wuu@wuu-main internal/appserver/protocol.go#L223-337（Request/Response/
#   ResponseError/Notification/clientResponse）——以 Go json tag 为准。
# pitfalls: B-59（反向响应路由）B-60（版本严格相等）

`Request.ID` 是 `int | str`（port-ledger P1-2）：wuu 用 `json.RawMessage` 承 id，其自身测试
以数字 id 生成（rpc_fixture_test.go:30 `fmt.Sprintf("%d", nextID)`），响应须逐字节回显请求 id。
旧 questor `serve/envelope.py` 强制字符串 id 是漂移，本契约模型纠正。

信封是"形状"定义（供 fixture 回放与校验）；运行时逐字节编解码在 `serve/envelope.py`（codec），
二者职责不同、不重复定义字段字面量。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = ["Notification", "Request", "Response", "ResponseError", "ReverseResponse"]


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResponseError(_Envelope):
    """字符串错误码（非 JSON-RPC 数值码）。`model_next_action` 是 limen 方言可选扩展（B-52）。"""

    code: str
    message: str
    model_next_action: str | None = None


class Request(_Envelope):
    """客户端上行请求。`params` 给定则为对象；`id` 数字或字符串（P1-2）。"""

    id: int | str
    method: str
    params: dict[str, Any] | None = None


class Response(_Envelope):
    """对请求的响应：回显 id，`result` 与 `error` 二选一。"""

    id: int | str
    result: Any | None = None
    error: ResponseError | None = None


class Notification(_Envelope):
    """服务端 → 客户端通知（无 id）。"""

    method: str
    params: dict[str, Any] | None = None


class ReverseResponse(_Envelope):
    """客户端对 server-initiated 反向请求的响应（`clientResponse` #L333-337）。

    与 :class:`Response` 分开的理由同 wuu：反向投递路径要把 result 当 raw JSON 重解码不丢，
    且判据是"有 id、无 method、含 result|error"（handleLine 先路由给 pending 等待者，B-59）。
    """

    id: int | str
    result: Any | None = None
    error: ResponseError | None = None
