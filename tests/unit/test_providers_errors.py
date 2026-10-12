"""错误分类：状态码优先于 body 的 type/code（2026-10-12 实测形态的回归）。

实测来源 `docs/notes/2026-10-12-m23-wire-probe.md`：某 Anthropic 兼容端点对欠费账户
返回 402，body 里却写 `type=unknown_error` / `code=invalid_request_error`；404 是
`content-length: 0` 的空 body。这两条形态是"照 body 归类"会翻车的地方。
"""

from __future__ import annotations

import pytest

from questor.providers.errors import (
    AuthenticationError,
    EndpointNotFoundError,
    LLMError,
    LLMTimeoutError,
    ProtocolError,
    QuotaExceededError,
    RateLimitError,
    RequestError,
    ServerError,
    UnexpectedStatusError,
    classify_status,
    error_message_from_body,
    parse_retry_after,
)

_MEASURED_402_BODY = (
    b'{"error":{"message":"Insufficient Balance (request_id: 2627d406)",'
    b'"type":"unknown_error","param":null,"code":"invalid_request_error"}}'
)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (402, QuotaExceededError),
        (404, EndpointNotFoundError),
        (400, RequestError),
        (422, RequestError),
        (408, LLMTimeoutError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServerError),
        (302, ProtocolError),
        (418, UnexpectedStatusError),
    ],
)
def test_status_code_decides_the_class(status: int, expected: type[LLMError]) -> None:
    assert isinstance(classify_status(status), expected)


@pytest.mark.parametrize("status", [401, 402, 403, 404, 400, 422, 302, 418])
def test_configuration_and_request_errors_are_not_retryable(status: int) -> None:
    """不可重试是判据不是偏好：欠费/鉴权/路径不存在重试多少次都是同一个答案。"""
    assert classify_status(status).retryable is False


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_transient_errors_are_retryable(status: int) -> None:
    assert classify_status(status).retryable is True


def test_measured_402_body_does_not_override_the_status_class() -> None:
    """body 说 `invalid_request_error`，状态码说 402——分类必须跟状态码，
    否则会得出"参数写错"的错误结论并丢掉"账户欠费"这个真原因。"""
    message = error_message_from_body(_MEASURED_402_BODY)
    error = classify_status(402, message=message)
    assert isinstance(error, QuotaExceededError)
    assert error.retryable is False
    assert "Insufficient Balance" in str(error)


def test_empty_body_404_still_yields_a_readable_reason() -> None:
    """实测 404 的空 body（content-length: 0）不能导致"读错误也报错"。"""
    assert error_message_from_body(b"") == ""
    error = classify_status(404, message=error_message_from_body(b""))
    assert isinstance(error, EndpointNotFoundError)
    assert "404" in str(error)  # 没原因时至少留下状态码，不写空话


def test_non_json_body_is_passed_through_truncated() -> None:
    error = error_message_from_body("<html>502 Bad Gateway</html>")
    assert error.startswith("<html>502")


def test_retry_after_parses_seconds_and_rejects_junk() -> None:
    assert parse_retry_after("30") == 30.0
    assert parse_retry_after("0") == 0.0
    # 实测：错误响应里没有 retry-after，也没有 x-ratelimit-* —— None 是正常路径
    assert parse_retry_after(None) is None
    assert parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert parse_retry_after("-5") is None


def test_rate_limit_carries_retry_after() -> None:
    error = classify_status(429, message="slow down", retry_after_s=12.5)
    assert isinstance(error, RateLimitError)
    assert error.retry_after_s == 12.5


def test_base_class_is_not_retryable_by_default() -> None:
    """默认不可重试：新加的错误类忘了表态时，宁可少重试也不要重放流（B-84）。"""
    assert LLMError.retryable is False
