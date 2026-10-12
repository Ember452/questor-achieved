"""Layer1 工具结果预算（超预算结果落盘与回读，overview §6 context 职责）。

三档处理 + 聚合降序 + 陈旧裁剪，全部**只产生新 Message**：`Message` 是 frozen 的，
"绝不 mutate 原始对话"（B-25）由类型兼管而不是靠自觉。

与 FlowCoder 的一处收紧：陈旧裁剪的边界写进状态并落盘（B-27）——FlowCoder 的
`_snip_stale_messages` 在无状态的情况下对新 history 重算，docstring 自认"边界 drift 是
已知 trade-off"；那样恢复出来的会话表示会与模型上一轮看到的不一致。

IO 说明：本模块**同步**写盘（经 `gesta.spill_tool_result` 的 O_EXCL 幂等写，B-24），
调用方在事件循环里要 `asyncio.to_thread` 包一层（`engine` 已这么做）。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from questor.context import budget
from questor.context.replacements import ReplacementState
from questor.gesta.store import spill_tool_result
from questor.schemas.context import PERSISTED_TAG, SNIPPED_TAG, ReplacementRecord
from questor.schemas.llm import Message, ToolResultBlock

__all__ = ["BudgetOutcome", "apply_tool_result_budget", "persisted_preview"]


@dataclass(frozen=True)
class BudgetOutcome:
    """一轮预算裁决的结果：新的会话表示 + 待落盘的决策增量。"""

    messages: list[Message]
    records: tuple[ReplacementRecord, ...] = field(default_factory=tuple)
    #: 本轮算出的陈旧边界（None=还没到需要裁剪的时候）
    stale_boundary_turn: int | None = None
    #: 本轮相对原文省下的字符数（`notice/compact` 与可观测面用）
    reclaimed_chars: int = 0


def persisted_preview(content: str, spill_file: str) -> str:
    """落盘后的会话内表示：说明 + 文件回链 + 预览（模型据此知道去哪读全文）。"""
    size_kb = len(content.encode("utf-8")) // budget.BYTES_PER_KIB
    return (
        f"{PERSISTED_TAG}\n"
        f"输出过大（{size_kb}KB），全文已落盘：{spill_file}\n"
        f"需要精确内容时用 read 工具读该文件，不要凭预览猜测。\n"
        f"预览（前 {budget.PREVIEW_CHARS} 字符）：\n{content[: budget.PREVIEW_CHARS]}\n"
        f"</persisted-output>"
    )


def _snipped_preview(content: str) -> str:
    return (
        f"{SNIPPED_TAG}\n(旧结果已裁剪，原始长度 {len(content)} 字符)"
        f"\n{content[: budget.SNIPPED_HEAD_CHARS]}\n… (snipped)"
    )


def apply_tool_result_budget(
    messages: list[Message], *, thread_id: str, state: ReplacementState
) -> BudgetOutcome:
    """对会话历史应用 Layer1 预算，返回新的消息列表与本轮决策增量。

    ``messages`` 不被修改（返回的列表里，未受影响的消息是同一对象；被替换的消息是
    :func:`dataclasses.replace` 出来的新对象）。幂等：同一 ``tool_use_id`` 第二次进来
    会命中 ``state.representations``，不会再次落盘或改判。
    """
    originals = {r.tool_use_id: r.content for m in messages for r in m.tool_results}
    fresh: list[ToolResultBlock] = []
    for message in messages:
        for result in message.tool_results:
            tool_use_id = result.tool_use_id
            if tool_use_id in state.representations or tool_use_id in state.seen_ids:
                continue
            if result.content.startswith((PERSISTED_TAG, SNIPPED_TAG)):
                # 已经是某种"处理过的表示"：钉住它，别二次加工
                state.decide(tool_use_id, result.content, None)
                continue
            if len(result.content) > budget.SINGLE_RESULT_CHAR_LIMIT:
                _spill_and_decide(thread_id, tool_use_id, result.content, state)
            elif len(result.content) > budget.INLINE_RESULT_CHAR_LIMIT:
                state.decide(tool_use_id, result.content[: budget.INLINE_RESULT_CHAR_LIMIT], None)
            else:
                fresh.append(result)

    stale_boundary = _stale_boundary(messages, state)
    _enforce_aggregate(thread_id, fresh, state)
    new_messages = _render(messages, state)
    records = tuple(state.clear_pending())
    reclaimed = _reclaimed(originals, new_messages)
    return BudgetOutcome(
        messages=new_messages,
        records=records,
        stale_boundary_turn=stale_boundary,
        reclaimed_chars=reclaimed,
    )


def _spill_and_decide(
    thread_id: str, tool_use_id: str, content: str, state: ReplacementState
) -> None:
    spill = spill_tool_result(thread_id, tool_use_id, content)
    state.decide(tool_use_id, persisted_preview(content, spill.file), spill.file)


def _enforce_aggregate(
    thread_id: str, fresh: list[ToolResultBlock], state: ReplacementState
) -> None:
    """聚合超限：按单条长度**降序**逐条落盘，直到总量达标或候选耗尽（B-26）。

    只对本轮 fresh 动手：已钉住的表示不得回溯修改（否则模型会看到同一结果的两套表示）。
    ``fresh`` 里带着原文，所以下面的长度计算无需查盘。
    """
    by_id = {result.tool_use_id: result for result in fresh}
    total = sum(len(value) for value in state.representations.values()) + sum(
        len(result.content) for result in fresh
    )
    while total > budget.AGGREGATE_CHAR_LIMIT:
        candidates = [i for i in by_id if i not in state.representations]
        if not candidates:
            return
        biggest = max(candidates, key=lambda tool_use_id: len(by_id[tool_use_id].content))
        content = by_id[biggest].content
        _spill_and_decide(thread_id, biggest, content, state)
        total += len(state.representations[biggest]) - len(content)


def _stale_boundary(messages: list[Message], state: ReplacementState) -> int | None:
    """按轮数算陈旧边界；边界一旦算出就写入状态（B-27），恢复时沿用不重算。"""
    total_turns = sum(1 for m in messages if m.role == "assistant" and not m.tool_calls)
    boundary = total_turns - budget.KEEP_RECENT_TURNS
    if boundary <= 0:
        return state.stale_boundary_turn
    if state.stale_boundary_turn is None or boundary > state.stale_boundary_turn:
        state.stale_boundary_turn = boundary
    return state.stale_boundary_turn


def _render(messages: list[Message], state: ReplacementState) -> list[Message]:
    """把决策套到历史上；被替换的消息产生新对象（B-25）。"""
    rendered: list[Message] = []
    turn_seen = 0
    boundary = state.stale_boundary_turn
    for message in messages:
        if message.role == "assistant" and not message.tool_calls:
            turn_seen += 1
        if not message.tool_results:
            rendered.append(message)
            continue
        results: list[ToolResultBlock] = []
        changed = False
        for result in message.tool_results:
            representation = state.representations.get(result.tool_use_id)
            if representation is None:
                representation = result.content
            stale = boundary is not None and turn_seen <= boundary
            if (
                stale
                and not representation.startswith((PERSISTED_TAG, SNIPPED_TAG))
                and (len(representation) > budget.OLD_RESULT_SNIP_CHARS)
            ):
                representation = _snipped_preview(representation)
            if representation != result.content:
                changed = True
                results.append(replace(result, content=representation))
            else:
                results.append(result)
        rendered.append(replace(message, tool_results=results) if changed else message)
    return rendered


def _reclaimed(originals: dict[str, str], messages: list[Message]) -> int:
    after = {
        result.tool_use_id: len(result.content)
        for message in messages
        for result in message.tool_results
    }
    return sum(max(0, len(text) - after.get(key, len(text))) for key, text in originals.items())
