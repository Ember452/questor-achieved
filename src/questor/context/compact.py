"""Layer2 自动压缩：阈值、保留窗口、前缀退化、熔断与摘要编排（B-20/21/22/23/28/29/11）。

与 FlowCoder `context/manager.py` 的三处刻意不同：

1. **纯函数 + 注入摘要器**：`auto_compact` 不收模型客户端，只收
   ``summarize: Callable[[list[Message]], Awaitable[str]]``——模型调用归 engine（矩阵上
   context 不得 import engine，反过来让 context 持有 port 就更糟）。
2. **不做"压完再清理会话目录"**（FlowCoder `cleanup_tool_results` 的 rmtree 重建）：
   落盘全文是可审计证据与回读目标，删掉等于自毁逃生门（B-20 要的就是那条路径可达）。
3. **失败与熔断分开表态**：熔断 open 时返回 `breaker_open` 而不是抛异常——循环要能把
   "自动压缩已停手"这件事如实告诉用户（`notice/compact`），而不是让一轮 run 莫名失败。

压缩只重写内存里的会话视图；**被摘要的原文仍在正文 Item 里**（append-only），
`context.boundary` 记录则让"模型当时看到什么"可回放（ADR-0017）。
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from questor.context import budget
from questor.schemas.context import PERSISTED_TAG, SNIPPED_TAG
from questor.schemas.llm import Message, estimate_tokens

__all__ = [
    "CompactOutcome",
    "auto_compact",
    "compute_compact_threshold",
    "keep_start_index",
    "recovery_attachment",
    "should_auto_compact",
    "strip_analysis_block",
]

Summarizer = Callable[[Sequence[Message]], Awaitable[str]]

_SUMMARY_TAG = re.compile(r"<summary>(.*?)</summary>", re.DOTALL)
_ANALYSIS_TAG = re.compile(r"<analysis>.*?</analysis>", re.DOTALL)


@dataclass(frozen=True)
class CompactOutcome:
    """一次压缩裁决的结果。``kind`` 是 `notice/compact` 事件的载荷第一段。"""

    kind: str  # noop | compacted | breaker_open | failed
    messages: list[Message] = field(default_factory=list)
    summary: str = ""
    kept: tuple[Message, ...] = ()
    before_tokens: int = 0
    after_tokens: int = 0
    reason: str = ""


class CompactBreaker:
    """连续失败熔断（B-23）：open 后自动压缩拒绝再试，直到有一次成功。"""

    def __init__(self, max_failures: int = budget.COMPACT_BREAKER_FAILURES) -> None:
        self.max_failures = max_failures
        self.consecutive_failures = 0

    @property
    def is_open(self) -> bool:
        return self.consecutive_failures >= self.max_failures

    def record_failure(self) -> None:
        self.consecutive_failures += 1

    def record_success(self) -> None:
        self.consecutive_failures = 0


def compute_compact_threshold(context_window: int, *, manual: bool = False) -> int:
    """触发阈值 = 窗口 - 摘要输出预留 - 触发冗余（手动档冗余更小）。"""
    margin = budget.MANUAL_COMPACT_SAFETY_MARGIN if manual else budget.AUTO_COMPACT_SAFETY_MARGIN
    return context_window - budget.SUMMARY_OUTPUT_RESERVE - margin


def should_auto_compact(current_tokens: int, context_window: int) -> bool:
    return current_tokens >= compute_compact_threshold(context_window)


def strip_analysis_block(text: str) -> str:
    """取 ``<summary>`` 正文；标签缺失时原样返回（模型不总守格式，丢内容比丢格式更糟）。"""
    match = _SUMMARY_TAG.search(text)
    body = match.group(1) if match else text
    return _ANALYSIS_TAG.sub("", body).strip()


def _is_dangling_tool_result(messages: Sequence[Message], index: int) -> bool:
    """index 处是"承载 tool_result 的 user 消息"，而其前一条是发起调用的 assistant。"""
    if index <= 0:
        return False
    message = messages[index]
    previous = messages[index - 1]
    return bool(message.tool_results) and bool(previous.tool_calls)


def keep_start_index(messages: Sequence[Message]) -> int:
    """决定尾部原样保留的起点（B-21：绝不留下悬空 tool_result）。

    从尾向前累加，token 达下限**或**条数达下限即停（先到先停）；纳入下一条会超硬上限
    时停止（但绝不拒绝保留最后一条）。最后把起点回退到不成对拆开的位置。
    """
    total = len(messages)
    if total == 0:
        return 0
    kept_tokens = 0
    start = total
    for index in range(total - 1, -1, -1):
        tokens = estimate_tokens([messages[index]])
        kept_count = total - index - 1  # 纳入本条**之前**已保留几条
        if kept_count > 0 and kept_tokens + tokens > budget.KEEP_MAX_TOKENS:
            break
        kept_tokens += tokens
        start = index
        if (
            kept_tokens >= budget.KEEP_RECENT_TOKENS
            or kept_count + 1 >= budget.KEEP_RECENT_MESSAGES
        ):
            break
    while _is_dangling_tool_result(messages, start):
        start -= 1
    return start


def recovery_attachment(spilled: Sequence[tuple[str, str]], tool_inventory: str = "") -> str:
    """压缩后的工作集重注入（B-11）：落盘回链清单 + 可用工具清单。

    只重注入**能自证来源**的东西：哪些结果的全文在盘上（id + 文件名），以及还能调哪些工具。
    记忆与技能索引段随 memory/M7 模块加入——那两格现在是空的，空就不写，
    不放"占位提示词"（AGENTS §二：不做无消费者的形状）。
    """
    sections: list[str] = []
    if spilled:
        lines = [
            "## 已落盘的工具结果",
            "以下结果的全文在盘上，需要精确内容时用 read 工具读，不要凭预览猜测：",
        ]
        for tool_use_id, name in spilled[: budget.RECOVERY_FILE_LIMIT]:
            lines.append(f"- {tool_use_id} → {name}")
        sections.append("\n".join(lines))
    if tool_inventory:
        sections.append("## 可用工具\n" + tool_inventory)
    return "\n\n".join(sections)


def _rebuild(
    summary: str, keep: Sequence[Message], attachment: str, transcript_ref: str
) -> list[Message]:
    content = (
        "本次会话延续自更早的对话，因窗口压力做过一次压缩。以下是被摘要部分的正文：\n\n" + summary
    )
    if keep:
        content += "\n\n近期消息已原样保留在下方。"
    if transcript_ref:
        # B-20 逃生门：摘要有损，用户原话/报错/代码片段都必预先指回完整正文
        content += "\n\n需要压缩前的原文（代码、报错、用户原话）时，读完整会话记录："
        content += transcript_ref
    if attachment:
        content += "\n\n---\n\n" + attachment
    return [Message(role="user", content=content), *keep]


async def auto_compact(
    messages: Sequence[Message],
    *,
    summarize: Summarizer,
    context_window: int,
    current_tokens: int,
    transcript_ref: str = "",
    attachment: str = "",
    manual: bool = False,
    breaker: CompactBreaker | None = None,
) -> CompactOutcome:
    """执行一次压缩裁决；四种返回都算正常（noop/compacted/breaker_open/failed）。"""
    threshold = compute_compact_threshold(context_window, manual=manual)
    if not manual and current_tokens < threshold:
        return CompactOutcome(kind="noop", messages=list(messages), reason="below threshold")
    if not manual and breaker is not None and breaker.is_open:
        return CompactOutcome(
            kind="breaker_open",
            messages=list(messages),
            reason=(
                f"连续 {breaker.consecutive_failures} 次摘要失败，自动压缩已停手；"
                "请人工整理或用 compact 手动触发"
            ),
        )

    start = keep_start_index(messages)
    prefix = list(messages[:start])
    keep = tuple(messages[start:])
    if start <= 0 or estimate_tokens(prefix) < budget.MIN_SUMMARIZE_PREFIX_TOKENS:
        # B-22：可摘要的前缀太小就别压——摘要自身要占的往返比回收的空间还多
        return CompactOutcome(kind="noop", messages=list(messages), reason="prefix too small")

    try:
        raw = await summarize(prefix)
    except Exception as exc:  # noqa: BLE001 - 摘要器包住的是外部模型调用，失败形态不可枚举
        if breaker is not None:
            breaker.record_failure()
        return CompactOutcome(kind="failed", messages=list(messages), reason=f"摘要生成失败：{exc}")

    summary = strip_analysis_block(raw)
    if not summary.strip():
        if breaker is not None:
            breaker.record_failure()
        return CompactOutcome(
            kind="failed", messages=list(messages), reason="摘要为空（不拿空历史继续跑）"
        )
    if breaker is not None:
        breaker.record_success()

    rebuilt = _rebuild(summary, keep, attachment, transcript_ref)
    return CompactOutcome(
        kind="compacted",
        messages=rebuilt,
        summary=summary,
        kept=keep,
        before_tokens=current_tokens,
        after_tokens=estimate_tokens(rebuilt),
    )


def spilled_representations(messages: Sequence[Message]) -> list[tuple[str, str]]:
    """从会话历史里读出"哪些结果的全文在盘上"（供 :func:`recovery_attachment` 用）。

    读的是表示本身的前缀与回链行，不另开一份状态——状态与历史必须同源。
    """
    found: list[tuple[str, str]] = []
    for message in messages:
        for result in message.tool_results:
            text = result.content
            if not text.startswith((PERSISTED_TAG, SNIPPED_TAG)):
                continue
            name = next(
                (line for line in text.splitlines() if "全文已落盘：" in line),
                result.tool_use_id,
            )
            found.append((result.tool_use_id, name.split("：")[-1].strip()))
    return found
