"""engine 循环单元行为：事件流、状态迁移经 gesta、B-02 收敛、B-03 熔断、B-08 恢复。"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from questor.engine import Engine
from questor.engine.constants import MAX_TOKENS_CEILING
from questor.engine.events import (
    Converging,
    LoopCompleted,
    LoopFailed,
    ToolCallCompleted,
)
from questor.engine.events import (
    RunStatus as RunStatusEvent,  # 事件类型与 schemas 的状态枚举同形不同物，别称防遮蔽
)
from questor.engine.model import ToolCall
from questor.engine.output_recovery import OutputRecoveryState
from questor.engine.output_recovery import (
    handle_output_token_limit as _handle,  # 语义测试直接驱动
)
from questor.gesta import create_thread, load_thread
from questor.schemas.model import (
    PermissionMode,
    RunStatus,
    Thread,
    Timestamp,
)
from questor.testenv.fake_home import fake_home
from questor.testenv.fake_model import FakeModel, ScriptedTurn
from questor.tools.base import ToolContext
from questor.tools.filestate import FileStateCache
from questor.tools.impl.registry_default import build_default_registry
from questor.tools.impl.todo import TodoStore
from questor.tools.processmgr import ProcessManager
from questor.tools.registry import ToolRegistry

T0: Timestamp = "2026-10-11T08:30:00Z"


def _make_thread(thread_id: str = "thread-eng01") -> None:
    create_thread(
        Thread(
            id=thread_id,
            workspace_id="ws-0001",
            title=None,
            engine_id="questor-engine",
            permission_mode=PermissionMode.STANDARD,
            pinned=False,
            archived=False,
            created_at=T0,
            updated_at=T0,
        )
    )


def _engine(
    model: FakeModel,
    tmp_path: pathlib.Path,
    *,
    mode: PermissionMode = PermissionMode.STANDARD,
    max_iterations: int = 10,
    max_seconds: float | None = None,
    registry: ToolRegistry | None = None,
) -> Engine:
    return Engine(
        model=model,
        registry=registry or build_default_registry(),
        ctx=ToolContext(
            cwd=str(tmp_path),
            file_state=FileStateCache(),
            processes=ProcessManager(),
            todos=TodoStore(),
        ),
        mode=mode,
        roots=[str(tmp_path)],
        max_iterations=max_iterations,
        max_seconds=max_seconds,
    )


async def _collect(engine: Engine, thread_id: str, user_text: str):
    from questor.engine.loop import TurnRequest

    events = []
    async for event in engine.run_turn(TurnRequest(thread_id=thread_id, user_text=user_text)):
        events.append(event)
    return events


def _event_types(events: list) -> list[str]:
    return [type(e).__name__ for e in events]


async def test_single_turn_text_only(tmp_path: pathlib.Path) -> None:
    with fake_home():
        _make_thread()
        model = FakeModel([ScriptedTurn(text="你好，完成了。", delta_splits=2)])
        events = await _collect(_engine(model, tmp_path), "thread-eng01", "打个招呼")
        types = _event_types(events)
        # running 状态先于首个迭代节拍（run 生命周期的语义顺序）
        assert types[0] == "RunStatus" and types[1] == "TurnStarted"
        assert "Usage" in types
        assert types[-1] == "LoopCompleted"
        final = events[-1]
        assert isinstance(final, LoopCompleted) and "你好" in final.final_text
        # 流式 delta 透出（切片 ≥2 片；余数并入末片是允许的）
        assert types.count("Delta") >= 2
        # 落盘：run completed + assistant message item 可回放
        view = load_thread("thread-eng01")
        assert view.runs[0].status == RunStatus.COMPLETED


async def test_tool_roundtrip_with_real_write(tmp_path: pathlib.Path) -> None:
    with fake_home():
        _make_thread()
        model = FakeModel(
            [
                ScriptedTurn(
                    text="我来写文件。",
                    tool_calls=(
                        ToolCall(
                            id="tc1",
                            name="write",
                            arguments={"path": "out.txt", "content": "工具写的"},
                        ),
                    ),
                    stop_reason="tool_use",
                ),
                ScriptedTurn(text="写好了。"),
            ]
        )
        events = await _collect(_engine(model, tmp_path), "thread-eng01", "写个文件")
        assert isinstance(events[-1], LoopCompleted)
        # 真实工具真的写了文件
        assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "工具写的"
        # 事件里有 started/completed 对；completed 携带工具输出
        assert _event_types(events).count("ToolCallStarted") == 1
        completed = [e for e in events if isinstance(e, ToolCallCompleted)][0]
        assert "wrote" in completed.output
        # 落盘可回放：items 含 tool_call 与 tool_result；事件含 item/started
        view = load_thread("thread-eng01")
        kinds = [i.kind.value for i in view.items]
        assert "tool_call" in kinds and "tool_result" in kinds
        event_types = [e.type for e in view.events]
        assert "item/started" in event_types and "item/completed" in event_types
        assert "turn/usage" in event_types and "run/status" in event_types


async def test_read_only_mode_denies_write_but_completes(tmp_path: pathlib.Path) -> None:
    with fake_home():
        _make_thread()
        model = FakeModel(
            [
                ScriptedTurn(
                    text="",
                    tool_calls=(
                        ToolCall(
                            id="tc1", name="write", arguments={"path": "x.txt", "content": "y"}
                        ),
                    ),
                    stop_reason="tool_use",
                ),
                ScriptedTurn(text="被拒了，我无法写。"),
            ]
        )
        events = await _collect(
            _engine(model, tmp_path, mode=PermissionMode.READ_ONLY),
            "thread-eng01",
            "写文件",
        )
        completed = [e for e in events if isinstance(e, ToolCallCompleted)][0]
        assert completed.is_error is True
        assert "denied:" in completed.output and "read-only" in completed.output
        assert isinstance(events[-1], LoopCompleted)  # 模型收到拒绝后正常收敛


async def test_unknown_tool_breaker_fails_run(tmp_path: pathlib.Path) -> None:
    """B-03：连续未知工具 ≥3 → LoopFailed（并行批不清零——本测试逐个调用即串行）。"""
    with fake_home():
        _make_thread()
        model = FakeModel(
            [
                ScriptedTurn(
                    text="",
                    tool_calls=(ToolCall(id=f"tc{i}", name=f"ghost{i}", arguments={}),),
                    stop_reason="tool_use",
                )
                for i in range(3)
            ]
        )
        events = await _collect(_engine(model, tmp_path), "thread-eng01", "x")
        assert isinstance(events[-1], LoopFailed)
        assert "unknown tool" in events[-1].message
        view = load_thread("thread-eng01")
        assert view.runs[0].status == RunStatus.FAILED


async def test_disabled_tool_does_not_trip_breaker(tmp_path: pathlib.Path) -> None:
    """B-17：禁用工具不算未知——连续禁用调用不熔断（模型最终收到 disabled 错误）。"""
    with fake_home():
        _make_thread()
        registry = build_default_registry()
        registry.disable("read")
        model = FakeModel(
            [
                ScriptedTurn(
                    text="",
                    tool_calls=(ToolCall(id="tc1", name="read", arguments={"path": "a.txt"}),),
                    stop_reason="tool_use",
                ),
                ScriptedTurn(text="好。"),
            ]
        )
        events = await _collect(_engine(model, tmp_path, registry=registry), "thread-eng01", "x")
        assert isinstance(events[-1], LoopCompleted)


async def test_budget_converge_keeps_readonly_tools(tmp_path: pathlib.Path) -> None:
    """B-02：收敛轮的模型请求里只保留只读工具（write/edit/run/process 不在）。"""
    with fake_home():
        _make_thread()
        model = FakeModel([ScriptedTurn(text="收尾：全部完成。")])
        events = await _collect(_engine(model, tmp_path, max_seconds=0.0), "thread-eng01", "x")
        assert any(isinstance(e, Converging) for e in events)
        assert isinstance(events[-1], LoopCompleted)
        tools = model.requests[0].tools
        names = {t["name"] for t in tools}
        assert "write" not in names and "run" not in names
        assert "read" in names and "list" in names


async def test_converging_round_still_requesting_tools_fails(tmp_path: pathlib.Path) -> None:
    with fake_home():
        _make_thread()
        model = FakeModel(
            [
                ScriptedTurn(
                    text="",
                    tool_calls=(ToolCall(id="tc1", name="read", arguments={"path": "."}),),
                    stop_reason="tool_use",
                ),
            ]
        )
        events = await _collect(_engine(model, tmp_path, max_seconds=0.0), "thread-eng01", "x")
        assert isinstance(events[-1], LoopFailed)
        assert "converged" in events[-1].message


async def test_cancellation_marks_run_cancelled(tmp_path: pathlib.Path) -> None:
    with fake_home():
        _make_thread()
        model = FakeModel([ScriptedTurn(text="慢慢来。", delta_splits=4)])
        engine = _engine(model, tmp_path)
        from questor.engine.loop import TurnRequest

        agen = engine.run_turn(TurnRequest(thread_id="thread-eng01", user_text="x"))
        async for event in agen:
            if isinstance(event, RunStatusEvent) and event.status == "running":
                break
        # athrow 把 CancelledError 注入生成器——与真实任务取消同路径（aclose 只给
        # GeneratorExit）；清理完成后 CancelledError 按纪律放行，这里接住它
        with pytest.raises(asyncio.CancelledError):
            await agen.athrow(asyncio.CancelledError)
        view = load_thread("thread-eng01")
        assert view.runs[0].status == RunStatus.CANCELLED


# ---- B-08：max_tokens 恢复（直接驱动语义件） ----


def test_output_recovery_escalates_once_then_retries(tmp_path: pathlib.Path) -> None:
    from questor.engine.conversation import Conversation
    from questor.engine.model import LLMResponse

    conv = Conversation()
    state = OutputRecoveryState()
    hit = LLMResponse(stop_reason="max_tokens")
    # B-08 的新形状：上限在内核逐请求携带，恢复层只回传"下一轮用什么值"
    first = _handle(hit, conv, 8_000, state)
    assert first.retry and first.state.max_tokens_escalated
    assert first.max_output_tokens == MAX_TOKENS_CEILING
    second = _handle(hit, conv, MAX_TOKENS_CEILING, first.state)
    assert second.retry and second.state.recoveries == 1
    assert second.max_output_tokens == MAX_TOKENS_CEILING  # 不反复拉高
    # 非 max_tokens 轮清零计数（B-08 的另一半）
    ok = _handle(LLMResponse(stop_reason="end_turn"), conv, 8_000, second.state)
    assert ok.retry is False and ok.state.recoveries == 0


def test_output_recovery_gives_up_after_budget(tmp_path) -> None:  # noqa: ARG001
    from questor.engine.conversation import Conversation
    from questor.engine.model import LLMResponse

    conv = Conversation()
    state = OutputRecoveryState(max_tokens_escalated=True, recoveries=3)
    decision = _handle(LLMResponse(stop_reason="max_tokens"), conv, MAX_TOKENS_CEILING, state)
    assert decision.retry is False  # 次数耗尽，放任模型自收敛
