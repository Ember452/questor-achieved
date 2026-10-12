"""Layer1 工具结果预算的行为（B-24/25/26/27 的对应测试）。

先枚举它能怎么坏，再对着写：幂等性、聚合降序的顺序、原始历史不被改写、
陈旧裁剪边界的可复现性——这四条是 FlowCoder 交过学费的地方。
"""

from __future__ import annotations

import pytest

from questor.context import budget
from questor.context.replacements import ReplacementState, state_from_records
from questor.context.tool_results import BudgetOutcome, apply_tool_result_budget
from questor.schemas.context import PERSISTED_TAG, SNIPPED_TAG
from questor.schemas.llm import Message, ToolResultBlock
from questor.testenv.fake_home import fake_home


def _results(*pairs: tuple[str, str]) -> list[Message]:
    return [
        Message(
            role="assistant",
            content="",
            tool_calls=[],
        ),
        Message(
            role="user",
            content="",
            tool_results=[
                ToolResultBlock(tool_use_id=tool_use_id, content=content)
                for tool_use_id, content in pairs
            ],
        ),
    ]


def _view(messages: list[Message]) -> list[str]:
    return [r.content for m in messages for r in m.tool_results]


def _big() -> str:
    """默认超 SINGLE_RESULT_CHAR_LIMIT 的内容。"""
    return "x" * (budget.SINGLE_RESULT_CHAR_LIMIT + 1_000)


def test_single_over_limit_becomes_persisted_preview(tmp_path) -> None:
    _ = tmp_path
    with fake_home():
        state = ReplacementState()
        content = _big()
        outcome = apply_tool_result_budget(
            _results(("t1", content)), thread_id="thread-ctx01", state=state
        )

    view = _view(outcome.messages)[0]
    assert view.startswith(PERSISTED_TAG)
    assert content[: budget.PREVIEW_CHARS] in view
    assert state.representations["t1"] == view
    assert [r.tool_use_id for r in outcome.records] == ["t1"]
    assert outcome.records[0].spilled_file  # 回链进决策记录，事后可对账


def test_under_both_limits_stays_verbatim(tmp_path) -> None:
    _ = tmp_path
    with fake_home():
        outcome = apply_tool_result_budget(
            _results(("t1", "短结果")), thread_id="thread-ctx01", state=ReplacementState()
        )
    assert _view(outcome.messages) == ["短结果"]
    assert outcome.records == ()


def test_inline_tier_truncates_without_spilling(tmp_path) -> None:
    """10K~50K 这一档只做内联截断：全文进盘对这条尺寸没收益，只多一份字节。"""
    _ = tmp_path
    content = "y" * (budget.INLINE_RESULT_CHAR_LIMIT + 500)
    with fake_home():
        outcome = apply_tool_result_budget(
            _results(("t1", content)), thread_id="thread-ctx01", state=ReplacementState()
        )
    view = _view(outcome.messages)[0]
    assert not view.startswith(PERSISTED_TAG)
    assert len(view) == budget.INLINE_RESULT_CHAR_LIMIT


def test_second_pass_is_idempotent_and_does_not_reprocess(tmp_path) -> None:
    """B-24/25 的幂等面：同一历史第二次进来不得再落盘、不得把预览再加工一遍。"""
    _ = tmp_path
    content = _big()
    with fake_home():
        state = ReplacementState()
        first = apply_tool_result_budget(
            _results(("t1", content)), thread_id="thread-ctx01", state=state
        )
        pending_after_first = len(state.representations)
        second = apply_tool_result_budget(first.messages, thread_id="thread-ctx01", state=state)
    assert second.records == ()  # 无新决策就不该再落一条记录
    assert _view(second.messages) == _view(first.messages)
    assert len(state.representations) == pending_after_first


def test_original_history_objects_are_untouched(tmp_path) -> None:
    """B-25：绝不 mutate 原始对话——原 Message/ToolResultBlock 的字段必须一字未变。"""
    _ = tmp_path
    content = _big()
    messages = _results(("t1", content))
    original_block = messages[1].tool_results[0]
    with fake_home():
        apply_tool_result_budget(messages, thread_id="thread-ctx01", state=ReplacementState())

    assert original_block.content == content
    assert messages[1].tool_results[0] is original_block


def test_aggregate_overflow_spills_largest_first(tmp_path) -> None:
    """B-26：聚合超限按单条长度降序落盘——先砍最大的，而不是先砍最先遇到的。"""
    _ = tmp_path
    # 聚合上限只在单条不超两档时才有意义：取 25 条低于内联上限的结果，合计 225K > 200K
    lengths = list(range(9_000, 9_000 - 25, -1))
    assert max(lengths) < budget.INLINE_RESULT_CHAR_LIMIT
    assert sum(lengths) > budget.AGGREGATE_CHAR_LIMIT
    names = [f"t{index}" for index in range(len(lengths))]
    messages = _results(*list(zip(names, ["x" * n for n in lengths], strict=True)))
    with fake_home():
        outcome = apply_tool_result_budget(
            messages, thread_id="thread-ctx01", state=ReplacementState()
        )

    spilled = [record.tool_use_id for record in outcome.records]
    assert spilled, "合计已超聚合上限，必须动手"
    assert spilled[0] == "t0", f"最长的一条应最先被落盘，实际顺序：{spilled[:3]}"
    # 降序：被落盘的顺序长度不递增
    by_name = dict(zip(names, lengths, strict=True))
    assert [by_name[i] for i in spilled] == sorted((by_name[i] for i in spilled), reverse=True)
    rendered = dict(zip(names, _view(outcome.messages), strict=True))
    for tool_use_id in spilled:
        assert rendered[tool_use_id].startswith(PERSISTED_TAG)


def test_stale_boundary_is_recorded_in_state(tmp_path) -> None:
    """B-27：陈旧边界进状态并可复现——FlowCoder 的无状态重算正是它自认的 trade-off。"""
    _ = tmp_path
    turn_count = budget.KEEP_RECENT_TURNS + 3
    ids = [f"t{index}" for index in range(turn_count)]
    messages: list[Message] = []
    for index in ids:
        old = "o" * (budget.OLD_RESULT_SNIP_CHARS + 100)
        messages.append(Message(role="assistant", content=f"第 {index} 轮结论"))
        messages.append(
            Message(role="user", content="", tool_results=[ToolResultBlock(index, old)])
        )
    with fake_home():
        state = ReplacementState()
        outcome = apply_tool_result_budget(messages, thread_id="thread-ctx01", state=state)
        assert outcome.stale_boundary_turn == 3
        # 恢复面：边界与决策从记录重建后，渲染结果与本轮一致
        rebuilt = state_from_records([_record(outcome)], ids)
        replay = apply_tool_result_budget(messages, thread_id="thread-ctx01", state=rebuilt)

    assert _view(replay.messages) == _view(outcome.messages)
    assert any(text.startswith(SNIPPED_TAG) for text in _view(outcome.messages))


def _record(outcome: BudgetOutcome) -> object:
    """把本轮决策包成一条 `ContextReplacements`（与 writer 落盘的载荷同形）。"""
    from questor.schemas.context import ContextReplacements

    return ContextReplacements(
        thread_id="thread-ctx01",
        run_id="run-1",
        turn_id="turn-1",
        records=tuple(outcome.records),
        stale_boundary_turn=outcome.stale_boundary_turn,
        created_at="2026-10-12T08:30:00Z",
    )


def test_state_from_records_ignores_ids_absent_from_history() -> None:
    """重建只采纳仍在线的 id：已随压缩离场的结果不该继续占状态（否则长跑无界增长）。"""
    from questor.schemas.context import ContextReplacements, ReplacementRecord

    record = ContextReplacements(
        thread_id="thread-ctx01",
        run_id="run-1",
        turn_id="turn-1",
        records=(
            ReplacementRecord(tool_use_id="alive", representation="预览"),
            ReplacementRecord(tool_use_id="gone", representation="旧预览"),
        ),
        seen_ids=("alive", "gone"),
        stale_boundary_turn=7,
    )
    state = state_from_records([record], ["alive"])
    assert set(state.representations) == {"alive"}
    assert state.seen_ids == {"alive"}
    assert state.stale_boundary_turn == 7


def test_budget_thresholds_live_in_one_table() -> None:
    """护栏（B-05 同源）：context 的阈值只许住 budget.py，别在实现里散布魔法数。"""
    import ast
    import pathlib

    root = pathlib.Path("src/questor/context")
    offenders: list[str] = []
    for path in sorted(root.glob("*.py")):
        if path.name == "budget.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int)
                and node.value >= 1000
            ):
                offenders.append(f"{path.name}:{node.lineno}={node.value}")
    assert not offenders, "阈值散落在 budget.py 之外：" + ", ".join(offenders)


@pytest.mark.parametrize("threshold", [budget.SINGLE_RESULT_CHAR_LIMIT])
def test_single_threshold_is_above_inline(threshold: int) -> None:
    """两档必须有序，否则内联截断会先于落盘吞掉内容、预览回链永远拿不到。"""
    assert threshold > budget.INLINE_RESULT_CHAR_LIMIT > budget.OLD_RESULT_SNIP_CHARS
