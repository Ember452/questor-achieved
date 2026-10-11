"""run 工具：命令执行（超时移交后台 + 退出码语义映射 + 头尾保样 + ADR-0007 诚实标注）。

执行统一走 ProcessManager 的读线程模型：spawn 即开始累积输出，前台等待只是
轮询 poll——超时时进程**已经在**后台管理器里（移交是零拷贝的语义转换），
避免 communicate+收养带来的管道竞争。
"""

from __future__ import annotations

import asyncio
import time

from pydantic import BaseModel, Field

from questor.tools.base import Tool, ToolContext, ToolResult
from questor.tools.impl.process_semantics import (
    MAX_TIMEOUT_S,
    format_output,
    map_exit_code,
)

_BACKGROUND_NOTE = (
    "moved to background; this is NOT a verification result — read it with the "
    "process tool or stop it there"
)
_POLL_INTERVAL_S = 0.05
_DRAIN_GRACE_S = 0.5  # 退出后留给读线程排空尾部的时间


class RunParams(BaseModel):
    command: str = Field(min_length=1)
    timeout_s: int = Field(default=120, gt=0, le=MAX_TIMEOUT_S)
    background: bool = False
    """直接转入后台（立即返回 process_id，不等命令完成）。"""


class RunTool(Tool):
    name = "run"
    description = (
        "Run a shell command in the workspace. Returns stdout/stderr sections and "
        "the semantic exit code. On timeout the process tree moves to the "
        "background (that is NOT a verification result). Execution is NOT "
        "OS-sandboxed on Windows: path gate + job-object tree management only "
        "(ADR-0007)."
    )
    kind = "shell"
    mutates = True
    expects_path = False
    params_model = RunParams

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, RunParams)
        process = await asyncio.to_thread(ctx.processes.spawn, params.command, cwd=ctx.cwd)

        if params.background:
            return self._background_result(process.process_id, process.popen.pid, params.command)

        deadline = time.monotonic() + params.timeout_s
        while process.popen.poll() is None:
            if time.monotonic() >= deadline:
                # 超时 ≠ 完成（overview §10）：进程已在后台管理器里，明确标注不是验证通过
                out, err = await asyncio.to_thread(ctx.processes.drain, process.process_id, 0.0)
                partial = format_output(out, err)
                return ToolResult(
                    output=(
                        f"command timed out after {params.timeout_s}s and was moved to "
                        f"background: process_id={process.process_id} pid={process.popen.pid}\n"
                        f"note: {_BACKGROUND_NOTE}\n"
                        f"--- partial output so far ---\n{partial}"
                    ),
                    is_error=True,
                    data={
                        "process_id": process.process_id,
                        "pid": process.popen.pid,
                        "timed_out": True,
                    },
                )
            await asyncio.sleep(_POLL_INTERVAL_S)

        await asyncio.sleep(_DRAIN_GRACE_S)  # 读线程排空 EOF 前的尾部
        out, err = await asyncio.to_thread(ctx.processes.drain, process.process_id, 0.0)
        exit_code = process.popen.poll()
        assert exit_code is not None
        semantic_ok, semantic_note = map_exit_code(params.command, exit_code)
        status = "ok" if semantic_ok else f"failed ({semantic_note})"
        return ToolResult(
            output=f"exit code {exit_code} ({status})\n{format_output(out, err)}",
            is_error=not semantic_ok,
            data={
                "exit_code": exit_code,
                "command": params.command,
                # ADR-0007 诚实标注：Windows standard 档无 OS 写隔离
                "sandboxed": False,
            },
        )

    def _background_result(self, process_id: str, pid: int, command: str) -> ToolResult:
        return ToolResult(
            output=(
                f"started in background: process_id={process_id} pid={pid} "
                f"command={command!r}\nnote: {_BACKGROUND_NOTE}"
            ),
            data={"process_id": process_id, "pid": pid},
        )
