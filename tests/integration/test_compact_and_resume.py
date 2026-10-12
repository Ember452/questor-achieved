"""集成：压缩后 resume 可恢复（M2.3 出口判据）+ 工具结果全文入正文（B-86）。

这条链路必须端到端验：`context` 只算决策、`engine` 只调用、`gesta` 只落盘——
"压完写进正文、重启后按正文重建出同一个视图"跨三个模块，任何一环单测都看不到。
"""

from __future__ import annotations

import pytest

from questor.engine import Engine
from questor.engine.events import CompactNotice, LoopCompleted
from questor.engine.loop import TurnRequest
from questor.engine.model import ToolCall
from questor.gesta import create_thread, load_thread
from questor.schemas.model import PermissionMode, Thread, Timestamp
from questor.testenv.fake_home import fake_home
from questor.testenv.fake_model import FakeModel, ScriptedTurn
from questor.tools.base import ToolContext
from questor.tools.filestate import FileStateCache
from questor.tools.impl.registry_default import build_default_registry
from questor.tools.impl.todo import TodoStore
from questor.tools.processmgr import ProcessManager

T0: Timestamp = "2026-10-12T08:30:00Z"
THREAD = "thread-rsm01"
# 阈值 = 34000 - 20000 - 13000 = 1000 token；一次 60K 字符的工具结果就够越过它
WINDOW = 34_000
BIG = "x" * 60_000


def _make_thread() -> None:
    create_thread(
        Thread(
            id=THREAD,
            workspace_id="ws-rsm",
            title="压缩后恢复",
            engine_id="questor-engine",
            permission_mode=PermissionMode.STANDARD,
            pinned=False,
            archived=False,
            created_at=T0,
            updated_at=T0,
        )
    )


def _engine(model: FakeModel, cwd: str) -> Engine:
    return Engine(
        model=model,
        registry=build_default_registry(),
        ctx=ToolContext(
            cwd=cwd, file_state=FileStateCache(), processes=ProcessManager(), todos=TodoStore()
        ),
        mode=PermissionMode.STANDARD,
        roots=[cwd],
        context_window=WINDOW,
    )


async def _collect(engine: Engine, request: TurnRequest) -> list[object]:
    return [event async for event in engine.run_turn(request)]


def _read_call(path: str) -> ScriptedTurn:
    return ScriptedTurn(
        text="我读一下",
        tool_calls=(ToolCall(id="c1", name="read", arguments={"path": path}),),
        stop_reason="tool_use",
    )


@pytest.mark.asyncio
async def test_compaction_then_resume_rebuilds_from_disk(tmp_path) -> None:
    """多轮跑出一个真的能压的历史（keep 窗口要吃到 5 条、前缀要过 2000 token），
    然后全新引擎实例只靠盘上记录恢复。"""
    with fake_home():
        _make_thread()
        notices: list[CompactNotice] = []
        for run in range(6):
            model = FakeModel(
                [
                    # 第一位：若本轮触发压缩，它就是摘要 pass 的回应；没压则当普通回答用掉
                    ScriptedTurn(text=f"<summary>第 {run} 次压缩的摘要</summary>"),
                    ScriptedTurn(
                        text=f"第 {run} 轮的长回答" + "a" * 5_000,
                        # 阈值锚点优先信 API 用量（B-28）：报小值就是告诉引擎"窗口还空"
                        input_tokens=17_000,
                    ),
                ]
            )
            events = await _collect(
                _engine(model, str(tmp_path)),
                TurnRequest(
                    thread_id=THREAD,
                    user_text=f"第 {run} 个问题" + "u" * 5_000,
                    resume=run > 0,
                ),
            )
            notices += [e for e in events if isinstance(e, CompactNotice)]

        assert any(n.kind == "compacted" for n in notices), (
            f"没触发压缩：{[n.kind for n in notices]}"
        )

        view = load_thread(THREAD)
        assert view.context_boundaries, "压缩没留下边界记录"
        boundary = view.context_boundaries[-1]
        assert boundary.summary
        assert boundary.transcript_ref.endswith(f"{THREAD}.jsonl")  # B-20 逃生门
        assert boundary.before_tokens > boundary.after_tokens  # B-28 可核对面

        # 最后一轮：全新引擎实例，只从盘上恢复，不碰之前的内存对象
        last = FakeModel(
            [
                ScriptedTurn(text="<summary>又一次摘要</summary>"),
                ScriptedTurn(text="继续，接着上文做。"),
            ]
        )
        await _collect(
            _engine(last, str(tmp_path)),
            TurnRequest(thread_id=THREAD, user_text="再继续", resume=True),
        )
        joined = "\n".join(message.content for message in last.requests[-1].messages)
        assert boundary.summary[:80] in joined, "resume 没带上压缩摘要，等于把历史丢了"
        assert "再继续" in joined, "本轮用户输入没进历史"


@pytest.mark.asyncio
async def test_layer1_decisions_are_persisted_and_reused(tmp_path) -> None:
    """Layer1 决策落正文；resume 后模型看到的仍是同一份预览（不二次加工、不重复落盘）。"""
    with fake_home():
        _make_thread()
        (tmp_path / "big.py").write_text(BIG, encoding="utf-8")
        model = FakeModel(
            [
                ScriptedTurn(
                    text="我读一下",
                    tool_calls=(ToolCall(id="c1", name="read", arguments={"path": "big.py"}),),
                    stop_reason="tool_use",
                    input_tokens=17_000,
                ),
                ScriptedTurn(text="<summary>已压缩</summary>"),
                ScriptedTurn(text="看完了。"),
            ]
        )
        await _collect(
            _engine(model, str(tmp_path)), TurnRequest(thread_id=THREAD, user_text="读 big.py")
        )

        view = load_thread(THREAD)
        assert view.context_replacements, "超预算结果应留下替换决策记录"
        decision = view.context_replacements[-1].records[0]
        assert "<persisted-output>" in decision.representation
        assert decision.spilled_file  # 全文在盘上的回链

        before = len(view.context_replacements)
        resumed = FakeModel([ScriptedTurn(text="继续。")])
        await _collect(
            _engine(resumed, str(tmp_path)),
            TurnRequest(thread_id=THREAD, user_text="继续", resume=True),
        )
        seen = resumed.requests[-1].messages
        assert any(
            "<persisted-output>" in result.content
            for message in seen
            for result in message.tool_results
        ), "resume 后模型看到的表示与上一轮不一致"
        assert len(load_thread(THREAD).context_replacements) == before, "不该重复追加同一批决策"


@pytest.mark.asyncio
async def test_unspilled_tool_output_is_stored_in_full(tmp_path) -> None:
    """B-86：未落盘的工具结果必须存全文——只存 preview 会让审计里找不到模型看过的字节。"""
    with fake_home():
        _make_thread()
        (tmp_path / "small.py").write_text("print(1)\n", encoding="utf-8")
        model = FakeModel([_read_call("small.py"), ScriptedTurn(text="读完了。")])
        events = await _collect(
            _engine(model, str(tmp_path)), TurnRequest(thread_id=THREAD, user_text="读 small.py")
        )
        assert isinstance(events[-1], LoopCompleted)

        view = load_thread(THREAD)
        result = next(item for item in view.items if item.kind.value == "tool_result")
        assert "print(1)" in str(result.payload.get("output", ""))
