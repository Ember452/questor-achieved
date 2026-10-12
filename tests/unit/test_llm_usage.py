"""用量与锚点的算术（B-28 的底层：窗口占了多少，谁说了算）。

`Conversation` 的阈值判断全靠这两个函数，算错的后果不是崩溃而是"该压时不压"，
所以单独钉住：缓存分量占窗口、锚点之后才走字符估算、压缩换视图后锚点必须清零。
"""

from __future__ import annotations

from questor.engine.conversation import Conversation, estimate_tokens
from questor.schemas.llm import LLMUsage, Message


def test_total_input_counts_cache() -> None:
    """缓存命中与缓存新建都占上下文：只算 input_tokens 会让阈值永远晚于真实压力。"""
    usage = LLMUsage(input_tokens=100, cache_read=8_000, cache_creation=2_000, output_tokens=50)
    assert usage.total_input() == 10_100
    assert usage.total_input() + usage.output_tokens == 10_150


def test_anchor_makes_history_before_it_trust_api_and_tail_use_estimate() -> None:
    conv = Conversation()
    conv.add_user("u" * 3_500)  # 锚点前：1000 token 由 API 说了算
    conv.record_usage_anchor(LLMUsage(input_tokens=7, cache_read=1_000, output_tokens=3))
    assert conv.current_tokens() == 1_010

    conv.add_assistant("a" * 3_500, [])  # 锚点后：按字符估算
    assert conv.current_tokens() == 1_010 + estimate_tokens(conv.history[1:])


def test_replace_history_clears_the_anchor() -> None:
    """压缩后不清零锚点就是拿旧消息数算新历史——B-28 的另一半。"""
    conv = Conversation([Message(role="user", content="u" * 3_500)])
    conv.record_usage_anchor(LLMUsage(input_tokens=50_000))
    assert conv.baseline_tokens == 50_000

    conv.replace_history([Message(role="user", content="摘要")])
    assert conv.baseline_tokens == 0 and conv.anchor_count == 0
    assert conv.current_tokens() == estimate_tokens(conv.history)
