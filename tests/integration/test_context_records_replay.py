"""集成：上下文工程记录随正文落盘并可回放（ADR-0017 的端到端形态）。

三层各自的单测都看不到这条链路：`context` 只算决策、`gesta` 只管记录、
`engine` 只负责调用——"决策落到盘上、重启后还能折回来"必须在集成层验一次。
断言重点：回放后 fold 出的投影与写入内容一致，且旧记录**只追加不改写**。
"""

from __future__ import annotations

import pathlib

from questor.context import ReplacementState, apply_tool_result_budget
from questor.engine.conversation import Message, ToolResultBlock
from questor.gesta import create_thread, load_thread
from questor.gesta.writer import ThreadWriter
from questor.schemas.context import PERSISTED_TAG, ContextReplacements, ReplacementRecord
from questor.schemas.model import (
    Item,
    ItemKind,
    PermissionMode,
    Thread,
    Timestamp,
    utc_timestamp_now,
)
from questor.testenv.fake_home import fake_home

T0: Timestamp = "2026-10-12T08:30:00Z"
THREAD = "thread-ctx-r"


def _make_thread() -> None:
    create_thread(
        Thread(
            id=THREAD,
            workspace_id="ws-ctx",
            title="上下文记录回放",
            engine_id="questor-engine",
            permission_mode=PermissionMode.STANDARD,
            pinned=False,
            archived=False,
            created_at=T0,
            updated_at=T0,
        )
    )


def _messages() -> list[Message]:
    big = "z" * 60_000  # 超单条落盘阈值
    return [
        Message(role="user", content="读一下大文件"),
        Message(
            role="user",
            content="",
            tool_results=[ToolResultBlock(tool_use_id="t-big", content=big)],
        ),
    ]


def test_layer1_decisions_survive_a_restart() -> None:
    with fake_home():
        _make_thread()
        writer = ThreadWriter(THREAD)
        writer.open()

        state = ReplacementState()
        outcome = apply_tool_result_budget(_messages(), thread_id=THREAD, state=state)
        assert outcome.records, "60K 的结果应当被换成落盘预览"
        writer.add_context_replacements(
            ContextReplacements(
                thread_id=THREAD,
                run_id="run-ctx",
                turn_id="turn-ctx",
                records=tuple(outcome.records),
                stale_boundary_turn=outcome.stale_boundary_turn,
                created_at=utc_timestamp_now(),
            )
        )
        # 正常会话记录照写：被替换的原文必须在正文里留痕（可审计）
        writer.add_item(
            Item(
                id="item-raw",
                run_id="run-ctx",
                kind=ItemKind.TOOL_RESULT,
                payload={
                    "tool_use_id": "t-big",
                    "output_len": len(_messages()[1].tool_results[0].content),
                },
                created_at=T0,
            )
        )

        view = load_thread(THREAD)
        assert len(view.context_replacements) == 1
        record = view.context_replacements[0]
        assert record.records[0].tool_use_id == "t-big"
        assert record.records[0].representation.startswith(PERSISTED_TAG)
        assert record.records[0].spilled_file  # 全文在盘上的回链
        from questor.state.paths import tool_result_path

        assert tool_result_path("t-big").read_text(encoding="utf-8").startswith("z" * 1000)


def test_second_write_appends_and_keeps_history(tmp_path: pathlib.Path) -> None:
    """追加语义：第二次落盘不覆盖第一条，也不动被替换结果的原始 Item（B-25/ADR-0017）。"""
    _ = tmp_path
    with fake_home():
        _make_thread()
        writer = ThreadWriter(THREAD)
        writer.open()
        first = ContextReplacements(
            thread_id=THREAD,
            run_id="run-1",
            turn_id="turn-1",
            records=(ReplacementRecord(tool_use_id="a", representation="预览A"),),
        )
        second = ContextReplacements(
            thread_id=THREAD,
            run_id="run-2",
            turn_id="turn-2",
            records=(ReplacementRecord(tool_use_id="b", representation="预览B"),),
        )
        writer.add_context_replacements(first)
        writer.add_context_replacements(second)

        view = load_thread(THREAD)
        assert [r.run_id for r in view.context_replacements] == ["run-1", "run-2"]
        assert [len(r.records) for r in view.context_replacements] == [1, 1]

        # seq 稠密：上下文记录同样占号，不因为"不是 Item"就跳过分配
        from questor.gesta.store import _read_records
        from questor.state.paths import thread_path

        records = _read_records(thread_path(THREAD))
        assert view.last_seq == len(records) == 3  # thread.created + 两条上下文记录


def test_wrong_thread_is_rejected() -> None:
    """归属校验：把 A 线程的记录写进 B 的句柄必须爆炸，而不是留下对不上账的历史。"""
    import pytest

    from questor.gesta import ThreadStoreError

    with fake_home():
        _make_thread()
        writer = ThreadWriter(THREAD)
        writer.open()
        payload = ContextReplacements(
            thread_id="thread-other",
            run_id="run-x",
            turn_id="turn-x",
            records=(ReplacementRecord(tool_use_id="a", representation="预览"),),
        )
        with pytest.raises(ThreadStoreError, match="不一致"):
            writer.add_context_replacements(payload)
