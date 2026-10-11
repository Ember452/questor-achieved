"""集成：单轮内核端到端（M2 出口判据"一个真实小任务完整跑通并落盘可回放"的 M2.2 形态）。

三步真实链（fake model 脚本化决策，工具与环境全部真实）：
1. write 写一个 Python 脚本；
2. run 用解释器执行它；
3. read 回读输出 → 模型给出最终回答。
断言：run 终态 completed、文件真实落盘、Item/Event 全记录、从 JSONL 重放 fold
得到完整会话（不重跑工具、不联系模型）、usage 记账。
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from questor.engine import Engine
from questor.engine.events import LoopCompleted
from questor.engine.events import RunStatus as RunStatusEvent
from questor.engine.loop import TurnRequest
from questor.engine.model import ToolCall
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

T0: Timestamp = "2026-10-11T08:30:00Z"

SCRIPT = "print(6 * 7)"


def _make_thread(thread_id: str) -> None:
    create_thread(
        Thread(
            id=thread_id,
            workspace_id="ws-0001",
            title="单轮内核端到端",
            engine_id="questor-engine",
            permission_mode=PermissionMode.STANDARD,
            pinned=False,
            archived=False,
            created_at=T0,
            updated_at=T0,
        )
    )


@pytest.mark.asyncio
async def test_single_turn_full_chain(tmp_path: pathlib.Path) -> None:
    with fake_home():
        _make_thread("thread-e2e-m22")
        model = FakeModel(
            [
                ScriptedTurn(
                    text="我来写一个计算脚本并执行。",
                    tool_calls=(
                        ToolCall(
                            id="tc1",
                            name="write",
                            arguments={"path": "calc.py", "content": SCRIPT + "\n"},
                        ),
                    ),
                    stop_reason="tool_use",
                ),
                ScriptedTurn(
                    text="脚本已写好，现在执行它。",
                    tool_calls=(
                        ToolCall(
                            id="tc2",
                            name="run",
                            arguments={"command": f'"{sys.executable}" calc.py', "timeout_s": 30},
                        ),
                    ),
                    stop_reason="tool_use",
                ),
                ScriptedTurn(text="脚本输出 42，任务完成。"),
            ]
        )
        engine = Engine(
            model=model,
            registry=build_default_registry(),
            ctx=ToolContext(
                cwd=str(tmp_path),
                file_state=FileStateCache(),
                processes=ProcessManager(),
                todos=TodoStore(),
            ),
            mode=PermissionMode.STANDARD,
            roots=[str(tmp_path)],
        )

        events = []
        async for event in engine.run_turn(
            TurnRequest(thread_id="thread-e2e-m22", user_text="写个脚本算 6*7 并执行")
        ):
            events.append(event)

        # ---- 事件面 ----
        final = events[-1]
        assert isinstance(final, LoopCompleted)
        assert "42" in final.final_text
        statuses = [e.status for e in events if isinstance(e, RunStatusEvent)]
        assert statuses == ["running", "completed"]  # 终态恰一次
        completed_calls = [e for e in events if type(e).__name__ == "ToolCallCompleted"]
        assert len(completed_calls) == 2  # write + run

        # ---- 真实世界面 ----
        assert (tmp_path / "calc.py").read_text(encoding="utf-8") == SCRIPT + "\n"

        # ---- 落盘可回放（不重跑工具、不联系模型：纯 fold） ----
        view = load_thread("thread-e2e-m22")
        assert view.runs[0].status == RunStatus.COMPLETED
        assert view.runs[0].turn_id == view.turns[0].id
        kinds = [i.kind.value for i in view.items]
        # user message + assistant×3 + tool_call×2 + tool_result×2
        assert kinds.count("message") == 4
        assert kinds.count("tool_call") == 2
        assert kinds.count("tool_result") == 2
        # 工具结果 payload 带语义退出码（run 的 B-12 语义进了审计记录）
        run_payloads = [i.payload for i in view.items if i.kind.value == "tool_result"]
        assert any(p.get("exit_code") == 0 for p in run_payloads if "exit_code" in p)
        # 事件族完整（delta 是传输态不落盘——正文以 message Item 为唯一真相）
        event_types = {e.type for e in view.events}
        assert {"item/started", "item/completed", "turn/usage", "run/status"} <= event_types
        assert "delta" not in event_types
        # seq 稠密：正文文件的可解析记录数 == last_seq（全局递增锚点无空洞）
        from questor.gesta.store import _read_records
        from questor.state.paths import thread_path

        records = _read_records(thread_path("thread-e2e-m22"))
        assert view.last_seq == len(records)

        # 模型收到的工具结果里有 run 的真实输出（对话面完整）
        model_requests = model.requests
        final_round_messages = model_requests[-1][0]
        tool_texts = " ".join(r.content for m in final_round_messages for r in m.tool_results)
        assert "42" in tool_texts
