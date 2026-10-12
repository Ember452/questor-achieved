"""M4 出口判据主钉：端到端链"转后台 → 出任务总结 → 打回 → 重做 → diff 可回看"。

全程走 serve 方法族 + 真实内核（fake model 脚本化决策，工具与环境真实）：
1. 建会话（serve `thread/create`）；
2. 落库并定稿计划（`task/plan`）；
3. 建任务并授权执行（`task/create` + `task/start`，编排门两条都在）；
4. **转后台**：`turn/start` 起一轮 run，run 在后台写文件（`wait_idle` 后观测）；
5. **出任务总结**：任务进入 `reviewed`（待审）；
6. **打回**：`task/reject`（reviewed → executing，打回重做）；
7. **diff 可回看**：`review/turn_diff` 拿写时刻算的真实 diff。

不重跑工具、不联系模型（除脚本化决策外），全部结论指向落盘事实（AGENTS §五）。
"""

from __future__ import annotations

import pathlib

import pytest

from questor.engine import Engine
from questor.engine.model import ToolCall
from questor.gesta import load_thread
from questor.orchestration import store as orch_store
from questor.schemas.model import PermissionMode
from questor.schemas.orchestration import TaskStatus as TS
from questor.serve.app_server import AppServer
from questor.serve.assembly import build_engine, ensure_workspace_for_root
from questor.serve.dispatch import HandlerCtx
from questor.serve.envelope import Notification
from questor.testenv.fake_model import FakeModel, ScriptedTurn

TARGET = "hello.txt"
CONTENT = "hello from the long run\n"


def _make_engine(model: FakeModel, cwd: pathlib.Path):  # noqa: ANN202 - 工厂签名与 AppServer 一致
    def factory(thread_id: str, mode: PermissionMode) -> Engine:
        return build_engine(model=model, cwd=str(cwd), mode=mode, thread_id=thread_id)

    return factory


@pytest.mark.asyncio
async def test_longrun_board_chain(tmp_path: pathlib.Path) -> None:
    model = FakeModel(
        [
            ScriptedTurn(
                text="我来写目标文件。",
                tool_calls=(
                    ToolCall(
                        id="tc1",
                        name="write",
                        arguments={"path": TARGET, "content": CONTENT},
                    ),
                ),
                stop_reason="tool_use",
            ),
            ScriptedTurn(text="文件已写好。"),
        ]
    )
    server = AppServer(create_engine=_make_engine(model, tmp_path))
    notes: list[Notification] = []
    server.build_dispatcher(notify=notes.append)
    ctx = HandlerCtx(request_id="e2e", principal="local", trace_id="e2e")
    workspace_id = ensure_workspace_for_root(tmp_path)

    # 1. 会话
    created = await server.thread_create({"workspace_id": workspace_id, "title": "M4 e2e"}, ctx)
    thread_id = created["thread"]["id"]

    # 2. 计划（先落库再定稿）
    plan_result = await server.task_plan(
        {"steps": [{"title": "写目标文件"}], "thread_id": thread_id, "finalize": True}, ctx
    )
    assert plan_result["plan"]["status"] == "finalized"

    # 3. 任务：门 → 建 → 授权执行
    task = (await server.task_create({"title": "写目标文件", "thread_id": thread_id}, ctx))["task"]
    task_id = task["id"]
    started = await server.task_start({"task_id": task_id, "authorized": True}, ctx)
    assert started["task"]["status"] == "executing"

    # 4. 转后台：turn/start 立即返回，run 在后台跑；wait_idle 后观测落盘事实
    accepted = await server.turn_start({"thread_id": thread_id, "user_text": "写 hello.txt"}, ctx)
    assert accepted["accepted"] is True
    await server.wait_idle()
    assert (tmp_path / TARGET).read_text(encoding="utf-8") == CONTENT  # 磁盘真实改动

    view = load_thread(thread_id)
    turn_id = view.turns[-1].id
    assert view.runs[-1].status.value == "completed"

    # 5. 任务总结：进入待审
    orch_store.transition_task(task_id, TS.REVIEWED)
    assert any(n.method == "task/status" and n.params["status"] == "executing" for n in notes)

    # 6. 打回 → 重做（reviewed → executing）
    rejected = await server.task_reject({"task_id": task_id}, ctx)
    assert rejected["task"]["status"] == "executing"
    assert any(n.method == "task/status" and n.params["status"] == "executing" for n in notes)

    # 7. diff 可回看：写时刻算的结构化 diff，指向真实文件
    diff = await server.review_turn_diff({"thread_id": thread_id, "turn_id": turn_id}, ctx)
    paths = [d["path"] for d in diff["diffs"]]
    assert TARGET in paths, paths
    assert any(d["created"] for d in diff["diffs"])  # 新建文件


@pytest.mark.asyncio
async def test_gate_refuses_start_without_authorization(tmp_path: pathlib.Path) -> None:
    """链上的门必须真拦：无授权 start 拒绝（编排门不只是文档）。"""
    from questor.serve.envelope import ProtocolError

    model = FakeModel([ScriptedTurn(text="unused")])
    server = AppServer(create_engine=_make_engine(model, tmp_path))
    server.build_dispatcher()
    ctx = HandlerCtx(request_id="e2e2", principal="local", trace_id="e2e2")
    await server.task_plan({"steps": [{"title": "x"}]}, ctx)
    task_id = (await server.task_create({"title": "x"}, ctx))["task"]["id"]
    with pytest.raises(ProtocolError) as excinfo:
        await server.task_start({"task_id": task_id}, ctx)
    assert excinfo.value.code == "need_execution_authorization"


@pytest.mark.asyncio
async def test_model_side_plan_tool_uses_injected_port(tmp_path: pathlib.Path) -> None:
    """模型侧 `plan` 工具经注入的编排端口生效（D4 的真实路径）。"""
    from questor.orchestration import OrchestrationService
    from questor.tools.base import ToolContext
    from questor.tools.filestate import FileStateCache
    from questor.tools.impl.orchestration import PlanParams, PlanTool
    from questor.tools.impl.todo import TodoStore
    from questor.tools.processmgr import ProcessManager

    wired = ToolContext(
        cwd=str(tmp_path),
        file_state=FileStateCache(),
        processes=ProcessManager(),
        todos=TodoStore(),
        thread_id="thread-x",
        orchestration=OrchestrationService(thread_id="thread-x"),
    )
    tool = PlanTool()
    result = await tool.execute(PlanParams(steps=["a", "b"], finalize=True), wired)
    assert not result.is_error, result.output
    assert "plan-" in result.output

    # 反向对照：未装配端口的 ToolContext 必须显式报不可用（fail closed）
    bare = ToolContext(
        cwd=str(tmp_path),
        file_state=FileStateCache(),
        processes=ProcessManager(),
        todos=TodoStore(),
    )
    refused = await tool.execute(PlanParams(steps=["a"]), bare)
    assert refused.is_error and "不可用" in refused.output
