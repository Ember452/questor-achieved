"""process 工具：后台进程管理（列/读/写 stdin/停；"改唤醒周期"随 M4 vigilia）。

只管理**本会话经 run 派生**的进程——停止通过持有的活对象句柄执行，
天然没有 PID 复用窗口（data-model §3.1 三元组校验的等价实现，理由见 processmgr）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from questor.tools.base import Tool, ToolContext, ToolResult
from questor.tools.impl.process_semantics import format_output
from questor.tools.processmgr import ProcessManagerError


class ProcessParams(BaseModel):
    action: Literal["list", "read", "write", "stop"]
    process_id: str | None = None
    data: str | None = None
    """write 动作写入 stdin 的内容。"""


class ProcessTool(Tool):
    name = "process"
    description = (
        "Manage background processes started by 'run': list, read accumulated "
        "output, write to stdin, or stop (kills the whole process tree). "
        "Stopping is not undoable."
    )
    kind = "process"
    mutates = True  # 默认值；实际按 action 判定（list/read 只读）
    expects_path = False
    params_model = ProcessParams

    def mutates_for(self, params: BaseModel) -> bool:
        assert isinstance(params, ProcessParams)
        return params.action in ("write", "stop")

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, ProcessParams)
        if params.action == "list":
            processes = ctx.processes.list()
            if not processes:
                return ToolResult(output="(no background processes)")
            lines = [f"{p.process_id} pid={p.popen.pid} {p.command!r}" for p in processes]
            return ToolResult(output="\n".join(lines))

        if params.process_id is None:
            return ToolResult(output=f"{params.action} requires 'process_id'", is_error=True)

        try:
            if params.action == "read":
                out, err, exited = ctx.processes.read_output(params.process_id)  # get 校验存在性
                status = "exited" if exited else "running"
                body = format_output(out, err)
                return ToolResult(
                    output=f"process {params.process_id} [{status}]\n{body}",
                    data={"process_id": params.process_id, "exited": exited},
                )
            if params.action == "write":
                if params.data is None:
                    return ToolResult(output="write requires 'data'", is_error=True)
                ctx.processes.write_stdin(params.process_id, params.data)
                return ToolResult(output=f"wrote {len(params.data)} chars to stdin")
            # stop
            ctx.processes.stop(params.process_id)
            return ToolResult(
                output=f"process {params.process_id} stopped (process tree terminated)",
                data={"process_id": params.process_id, "stopped": True},
            )
        except ProcessManagerError as exc:
            return ToolResult(output=str(exc), is_error=True)
