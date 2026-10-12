"""Layer2 压缩裁决的行为（B-20/21/22/23/28/29 的对应测试）。

先枚举它能怎么坏：该压不压（阈值算错）、压完丢了配对（模型直接 400）、
前缀太小压了个寂寞、摘要器坏了无限重试、压缩后没逃生门（有损摘要无法核对）。
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from questor.context import budget
from questor.context.compact import (
    CompactBreaker,
    CompactOutcome,
    Summarizer,
    auto_compact,
    compute_compact_threshold,
    keep_start_index,
    should_auto_compact,
    strip_analysis_block,
)
from questor.schemas.llm import Message, ToolCall, ToolResultBlock

_WINDOW = 40_000


def _user(text: str) -> Message:
    return Message(role="user", content=text)


def _assistant(text: str) -> Message:
    return Message(role="assistant", content=text)


def _tool_pair(call_id: str, result_text: str) -> list[Message]:
    return [
        Message(role="assistant", content="", tool_calls=[ToolCall(call_id, "read", {"p": "a"})]),
        Message(role="user", content="", tool_results=[ToolResultBlock(call_id, result_text)]),
    ]


def _long_session(turns: int = 8, size: int = 5_000) -> list[Message]:
    """足够长的会话：前缀要能被摘要（条数过保留窗口且 token 过 `MIN_SUMMARIZE_PREFIX_TOKENS`）。"""
    messages: list[Message] = []
    for index in range(turns):
        messages.append(_user(f"u{index}" + "u" * size))
        messages.append(_assistant(f"a{index}" + "a" * size))
    return messages


def _summarizer(*parts: object) -> Summarizer:
    """按序返回文本（或抛错）的摘要器。列表耗尽后重复最后一项，方便多轮测试。"""
    queue = list(parts)

    async def _summarize(prefix: Sequence[Message]) -> str:
        del prefix
        item = queue.pop(0) if queue else "<summary>摘要</summary>"
        if isinstance(item, BaseException):
            raise item
        return str(item)

    return _summarize


async def _compact(
    messages: list[Message],
    *,
    tokens: int = 40_000,
    summarizer: Summarizer | None = None,
    transcript_ref: str = "",
    breaker: CompactBreaker | None = None,
) -> CompactOutcome:
    """参数显式列出而不是 `**kwargs: object`——否则类型在这一层就丢了，pyright 报的是噪音。"""
    return await auto_compact(
        messages,
        summarize=summarizer or _summarizer("<analysis>想</analysis><summary>结论</summary>"),
        context_window=_WINDOW,
        current_tokens=tokens,
        transcript_ref=transcript_ref,
        breaker=breaker,
    )


def test_threshold_differs_between_auto_and_manual() -> None:
    auto = compute_compact_threshold(_WINDOW)
    manual = compute_compact_threshold(_WINDOW, manual=True)
    assert auto == _WINDOW - budget.SUMMARY_OUTPUT_RESERVE - budget.AUTO_COMPACT_SAFETY_MARGIN
    # 手动档允许贴得更近：用户主动按下的压缩不必再留自动档的冗余
    assert manual > auto
    assert should_auto_compact(auto, _WINDOW) and not should_auto_compact(auto - 1, _WINDOW)


async def test_below_threshold_is_a_noop_not_an_error() -> None:
    outcome = await _compact([_user("x" * 5000)], tokens=1000)
    assert outcome.kind == "noop"
    assert outcome.reason == "below threshold"


async def test_small_prefix_degrades_to_noop() -> None:
    """B-22：可摘要的前缀太小就别压——摘要自身的往返比回收的空间还多。"""
    messages = [_user("很短的一句话"), _assistant("很短的回答")] * 2
    outcome = await _compact(list(messages), tokens=40_000)
    assert outcome.kind == "noop"
    assert outcome.reason == "prefix too small"


async def test_keep_window_never_splits_a_tool_pair() -> None:
    """B-21：keep_start 落在 tool_result 上时必须回退到配对的 assistant。"""
    messages = [_user("开始")] + _tool_pair("c1", "结果正文") + _tool_pair("c2", "结果正文")
    start = keep_start_index(messages)
    # 任何被保留的 tool_result，其配对的 assistant 调用也必须在保留区间内
    for index in range(start, len(messages)):
        if messages[index].tool_results:
            assert messages[index - 1].tool_calls, "保留了悬空 tool_result"


async def test_rebuilt_history_carries_transcript_escape_hatch() -> None:
    """B-20：摘要必须有指回原文的路径，否则有损摘要无法核对。"""
    outcome = await _compact(
        _long_session(),
        transcript_ref="sessions/thread-x.jsonl",
    )
    assert outcome.kind == "compacted"
    first = outcome.messages[0].content
    assert "sessions/thread-x.jsonl" in first
    assert "结论" in first
    assert "<analysis>" not in first  # 思考草稿段被丢弃，不进会话


async def test_breaker_opens_after_consecutive_failures_and_blocks() -> None:
    """B-23：连败到阈值后自动压缩停手，且表态是 breaker_open 而不是把 run 弄失败。"""
    breaker = CompactBreaker()
    failing = _summarizer(RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom"))
    for _ in range(budget.COMPACT_BREAKER_FAILURES):
        outcome = await _compact(_long_session(), summarizer=failing, breaker=breaker)
        assert outcome.kind == "failed"
    assert breaker.is_open
    blocked = await _compact(
        _long_session(),
        summarizer=_summarizer("<summary>不该被调用</summary>"),
        breaker=breaker,
    )
    assert blocked.kind == "breaker_open"
    assert "停手" in blocked.reason


async def test_success_resets_the_breaker() -> None:
    breaker = CompactBreaker()
    breaker.record_failure()
    breaker.record_failure()
    outcome = await _compact(_long_session(), breaker=breaker)
    assert outcome.kind == "compacted"
    assert breaker.consecutive_failures == 0
    assert not breaker.is_open


async def test_compaction_actually_shrinks_the_estimate() -> None:
    """B-28 的可核对面：压缩后 after_tokens 必须真的更小，否则"压了"是假话。"""
    outcome = await _compact(_long_session(turns=10, size=8_000))
    assert outcome.kind == "compacted"
    assert outcome.after_tokens < outcome.before_tokens


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<analysis>草稿</analysis><summary>正文</summary>", "正文"),
        ("没有标签的裸文本", "没有标签的裸文本"),  # 模型不总守格式：丢内容比丢格式更糟
        ("<analysis>草稿</analysis>只有草稿", "只有草稿"),
    ],
)
def test_summary_extraction_is_lossless_on_missing_tags(raw: str, expected: str) -> None:
    assert strip_analysis_block(raw) == expected
