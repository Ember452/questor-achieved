"""write 工具：写文件（自动建父目录；已存在文件必须先读过——filestate 门禁）。

IO 沉进 :func:`_write_file_text`（AGENTS §五 异步纪律；护栏见 tests/architecture/
test_tools_impl_no_blocking_io）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from questor.tools.base import Tool, ToolContext, ToolResult, resolve_tool_path


class WriteParams(BaseModel):
    path: str
    content: str


def _write_file_text(target: Path, content: str) -> None:
    """行尾统一 LF（.gitattributes 同款约定）。父目录自动创建。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


class WriteTool(Tool):
    name = "write"
    description = (
        "Write content to a file (creates parent directories). Overwriting an "
        "existing file requires reading it first in this session."
    )
    kind = "file"
    mutates = True
    expects_path = True
    path_param = "path"
    params_model = WriteParams

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, WriteParams)
        target = resolve_tool_path(ctx, params.path)
        reason = ctx.file_state.ensure_editable(str(target))
        if reason is not None:
            return ToolResult(output=reason, is_error=True)
        await asyncio.to_thread(_write_file_text, target, params.content)
        ctx.file_state.record_read(str(target))  # 写出后记录读取状态供后续编辑
        return ToolResult(
            output=f"wrote {len(params.content)} chars to {params.path}",
            data={"path": params.path, "bytes": len(params.content.encode("utf-8"))},
        )
