"""跨 turn 恢复：从会话正文重建模型将看到的会话历史（M2.3 出口判据"压缩后 resume 可恢复"）。

重建顺序就是真相顺序，不能反：

1. 从 Item 流折出历史（message 项 + 工具结果项聚成一条 user 消息）；
2. 套上 `context.replacements` 的决策（模型当时看到的是预览，恢复后也得是同一份预览，
   否则前缀变了、缓存与审计两头都对不上）；
3. 按时间依次应用 `context.boundary`：每次压缩都把历史换成"摘要 + 保留尾部"。
   后一次摘要的输入里已含前一次摘要，所以"覆盖式"重建与实时发生的顺序一致。

已知边界（如实写在这，不藏在代码里）：边界记录按 `created_at` 排序，秒级粒度下同秒内的
两次压缩顺序不确定——M2.3 的循环不会在同一秒内压两次（压缩后 token 数骤降），
真要密集压缩的场景出现时改按记录 seq 排序（需要 Item/记录带 seq 出来，属契约增量）。
"""

from __future__ import annotations

from collections.abc import Sequence

from questor.context.replacements import ReplacementState, state_from_records
from questor.gesta.store import ThreadView
from questor.schemas.llm import Message, ToolCall, ToolResultBlock

__all__ = ["rebuild_history", "state_from_view", "tool_use_ids_in_view"]


def tool_use_ids_in_view(view: ThreadView) -> list[str]:
    return [
        str(result.get("tool_use_id", ""))
        for item in view.items
        if item.kind.value == "tool_result"
        for result in [item.payload]
    ]


def state_from_view(view: ThreadView) -> ReplacementState:
    """从正文记录重建替换决策状态（只采纳仍在线的 id，见 `state_from_records`）。"""
    return state_from_records(view.context_replacements, tool_use_ids_in_view(view))


def _tool_calls_from(payload_calls: object) -> list[ToolCall]:
    calls: list[ToolCall] = []
    if not isinstance(payload_calls, list):
        return calls
    for entry in payload_calls:
        if not isinstance(entry, dict):
            continue
        arguments = entry.get("arguments")
        calls.append(
            ToolCall(
                id=str(entry.get("id", "")),
                name=str(entry.get("name", "")),
                arguments=dict(arguments) if isinstance(arguments, dict) else {},
            )
        )
    return calls


def _message_from_item(item_kind: str, payload: dict[str, object]) -> Message | None:
    if item_kind != "message":
        return None
    role = str(payload.get("role", "user"))
    text = str(payload.get("text", ""))
    calls = _tool_calls_from(payload.get("tool_calls"))
    if role == "assistant":
        return Message(role="assistant", content=text, tool_calls=calls)
    return Message(role="user", content=text)


def _result_text(item_payload: dict[str, object]) -> str:
    """取工具结果的盘上全文：新记录带 ``output``，旧记录只有 ``preview`` 与 ``spilled``。

    回退顺序就是真相优先级：全文 > 落盘文件旁的全量预览 > 2K 预览。历史上写下的
    "只存 preview"记录（B-86 之前的形式）不可事后补全，只能标为降级。
    """
    for key in ("output", "preview"):
        value = item_payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def rebuild_history(view: ThreadView, state: ReplacementState | None = None) -> list[Message]:
    """按记录顺序重建会话历史；``state`` 缺省时从视图自身重建。"""
    decisions = (state or state_from_view(view)).representations
    history: list[Message] = []
    by_item: dict[str, Message] = {}
    pending: list[ToolResultBlock] = []

    def flush_results() -> None:
        if not pending:
            return
        message = Message(role="user", content="", tool_results=list(pending))
        by_item[f"results-{len(by_item)}"] = message
        history.append(message)
        pending.clear()

    for item in view.items:
        if item.kind.value == "tool_result":
            pending.append(
                ToolResultBlock(
                    tool_use_id=str(item.payload.get("tool_use_id", "")),
                    content=decisions.get(
                        str(item.payload.get("tool_use_id", "")), _result_text(item.payload)
                    ),
                    is_error=bool(item.payload.get("is_error", False)),
                )
            )
            continue
        if item.kind.value == "tool_call":
            continue  # 调用意图已记在 assistant message 的 tool_calls 里，不重复合成
        message = _message_from_item(item.kind.value, item.payload)
        if message is None:
            continue
        flush_results()
        by_item[item.id] = message
        history.append(message)
    flush_results()

    for boundary in sorted(view.context_boundaries, key=lambda b: b.created_at):
        kept: Sequence[Message] = [
            by_item[item_id] for item_id in boundary.kept_item_ids if item_id in by_item
        ]
        from questor.context.compact import _rebuild  # noqa: PLC0415 - 仅此函数需要，避免环状导入

        rebuilt = _rebuild(boundary.summary, kept, "", boundary.transcript_ref)
        history = rebuilt
        for item_id, message in zip(boundary.kept_item_ids, kept, strict=False):
            by_item[item_id] = message
    return history
