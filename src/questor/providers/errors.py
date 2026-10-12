"""LLM 错误分类：**HTTP 状态码优先**，其次 body 的 type/code，最后 message 关键字。

为什么状态码优先（2026-10-12 实测，见 `docs/notes/2026-10-12-m23-wire-probe.md`）：
某 Anthropic 兼容端点对欠费账户返回 `402`，但 body 里写的是
`{"type":"unknown_error","code":"invalid_request_error"}`——照 body 归类会把"账户欠费、
重试无用"误判成"参数写错"，既丢了正确的原因，也给错的重试结论。同理 `404` 的空 body
（`content-length: 0`）代表"该端点不讲这个协议"，不是"资源不存在可重试"。

`asyncio.CancelledError` 不在本模块的分类里：它是取消语义，必须放行（AGENTS §五）。

# Reimplements FlowCoder@flowcoder client/errors.py + error_mapping.py 的语义 — B-84
"""

from __future__ import annotations

import json

__all__ = [
    "AuthenticationError",
    "EndpointNotFoundError",
    "LLMError",
    "LLMTimeoutError",
    "NetworkError",
    "ProtocolError",
    "QuotaExceededError",
    "RateLimitError",
    "RequestError",
    "ServerError",
    "UnexpectedStatusError",
    "classify_status",
    "error_message_from_body",
    "parse_retry_after",
]


class LLMError(Exception):
    """LLM 调用失败的基类；``retryable`` 是**唯一**的重试判据入口。"""

    retryable = False

    def __init__(
        self, message: str, *, status: int | None = None, body_type: str | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body_type = body_type


class AuthenticationError(LLMError):
    """401/403：凭据缺失或无权限。重试无意义，必须让人去修配置。"""


class QuotaExceededError(LLMError):
    """402：配额/余额不足。实测会以 4xx 业务错误的样子出现，故需单独一档。"""


class RequestError(LLMError):
    """400/422：请求体不被端点接受（含字段缺失、类型不符）。"""


class EndpointNotFoundError(LLMError):
    """404：该端点不提供这个协议路径（空 body 是它的典型形态）。"""


class RateLimitError(LLMError):
    """429：限流。``retry_after_s`` 可能为 None（实测有响应不带该头）。"""

    retryable = True

    def __init__(
        self, message: str, *, retry_after_s: float | None = None, status: int | None = 429
    ) -> None:
        super().__init__(message, status=status)
        self.retry_after_s = retry_after_s


class ServerError(LLMError):
    """5xx：端点侧故障。可在零交付时重试。"""

    retryable = True


class NetworkError(LLMError):
    """连接失败/读写中断（未收到响应）。可在零交付时重试。"""

    retryable = True


class LLMTimeoutError(LLMError):
    """超时：连接成功但没等到结果（含"连上了却永不出首事件"）。"""

    retryable = True


class ProtocolError(LLMError):
    """流里的内容讲不通：JSON 解析失败、未知事件、协议版本对不上。"""


#: 状态码 → 错误类（显式表驱动，不做散落 if；B-33 同族的"档位表驱动"纪律）
_STATUS_TABLE: dict[int, type[LLMError]] = {
    400: RequestError,
    401: AuthenticationError,
    402: QuotaExceededError,
    403: AuthenticationError,
    404: EndpointNotFoundError,
    408: LLMTimeoutError,
    422: RequestError,
    429: RateLimitError,
}


def classify_status(
    status: int, *, message: str = "", retry_after_s: float | None = None
) -> LLMError:
    """按状态码归类；5xx 归 ServerError，其余未知 4xx/3xx 归 UnexpectedStatusError。"""
    cls = _STATUS_TABLE.get(status)
    if cls is None:
        if 500 <= status < 600:
            cls = ServerError
        elif 300 <= status < 400:
            cls = ProtocolError  # 重定向意味着 base_url 配错了，不该静默跟跳
        else:
            cls = UnexpectedStatusError
    text = message or f"模型端点返回 HTTP {status}"
    if cls is RateLimitError:
        return RateLimitError(text, retry_after_s=retry_after_s, status=status)
    return cls(text, status=status)


def parse_retry_after(value: str | None) -> float | None:
    """解析 ``retry-after``：支持秒数与 HTTP-date；无法解析返回 None（不猜）。"""
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


class UnexpectedStatusError(LLMError):
    """未预期的状态码：不重试，并把状态原样带出以便回写坑目录。"""


def error_message_from_body(body: bytes | str) -> str:
    """从错误体里取人类可读的 message；空 body / 非 JSON / 缺字段都返回空串。

    不抛异常：错误体本身就坏掉（实测 404 的 `content-length: 0`）时，调用方仍要
    能拿到状态码维度的错——不能因为"读错误也错"而丢原因。
    """
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    if not text.strip():
        return ""
    try:
        parsed = json.loads(text)
    except ValueError:
        return text.strip()[:400]
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message[:400]
        message = parsed.get("message")
        if isinstance(message, str) and message:
            return message[:400]
    return text.strip()[:400]
