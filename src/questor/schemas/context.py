"""上下文工程的事实形状（`data-model.md` §5 v1.2；进程内共享，非跨进程契约）。

住 `schemas` 的理由与 `llm.py` 同源：写方是 `context`、读方是 `context.rehydrate`、
落盘与回放方是 `gesta`——三个模块必须看同一份定义，而不是各自复刻一份字段。
用 pydantic 而非裸 dataclass：它要经 JSON 往返（写进记录流再 fold 回来），
校验必须在入口处爆炸（AGENTS §四"跨边界数据一律 pydantic v2"）。

两类事实都是**追加**语义：被替换的原文仍在会话正文里，压缩不变成改写（ADR-0017）。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = [
    "PERSISTED_TAG",
    "SNIPPED_TAG",
    "ContextBoundary",
    "ContextReplacements",
    "ReplacementRecord",
]

#: 会话内表示的两种前缀标记：模型看到它就懂得"全文在盘上/已裁剪"，
#: 也是恢复时判定"这条结果已被处理过"的幂等依据（重放不会二次决策）。
PERSISTED_TAG = "<persisted-output>"
SNIPPED_TAG = "<snipped>"


class _Frozen(BaseModel):
    """冻结 + 禁额外字段：与 `schemas/model.py` 的实体同一套纪律。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ReplacementRecord(_Frozen):
    """一个 tool_use_id 的最终会话内表示。

    ``representation`` 是**实际回喂模型的文本**（预览或截断后的片段），不是被丢弃的原文；
    ``spilled_file`` 指向盘上全文（O_EXCL 幂等写的文件名，data-model §5）。
    """

    tool_use_id: str
    representation: str
    spilled_file: str | None = None


class ContextReplacements(_Frozen):
    """一轮模型步之前落盘的替换决策增量（`context.replacements` 记录的载荷）。

    ``stale_boundary_turn`` 记录"陈旧裁剪从哪一轮起生效"（B-27：FlowCoder 的裁剪是无状态
    跑的，docstring 自认边界会 drift；这里把边界写进状态，恢复后才能复现同一表示）。
    """

    thread_id: str
    run_id: str
    turn_id: str
    records: tuple[ReplacementRecord, ...] = ()
    seen_ids: tuple[str, ...] = ()
    stale_boundary_turn: int | None = None
    created_at: str = ""


class ContextBoundary(_Frozen):
    """一次压缩的边界记录（`context.boundary` 载荷，ADR-0017）。

    为什么存 `kept_item_ids` 而不是字节偏移：resume 时要从**同一批 Item**重建保留尾部，
    偏移会随任何追加失效，id 不会。``summary`` 是模型生成的摘要正文（有损），
    ``transcript_ref`` 是逃生门——摘要不够用时指回完整正文（B-20）。
    """

    thread_id: str
    run_id: str
    turn_id: str
    summary: str
    kept_item_ids: tuple[str, ...] = ()
    before_tokens: int = 0
    after_tokens: int = 0
    reinjected: tuple[str, ...] = ()
    transcript_ref: str = ""
    created_at: str = ""
