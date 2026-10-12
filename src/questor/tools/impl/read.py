"""read 工具：读文件（行号标注 + 行范围分页）。

IO 沉进 :func:`_read_file_text` 同步 helper，async 侧走 `asyncio.to_thread`
——AGENTS §五 事件循环内禁止阻塞调用；tests/architecture/test_tools_impl_no_blocking_io
机械守卫本条。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from questor.tools.base import Tool, ToolContext, ToolResult, resolve_tool_path

_DEFAULT_LIMIT = 2000
_MAX_LIMIT = 10_000


class ReadParams(BaseModel):
    path: str
    """目标文件路径（相对路径相对工作目录解析）。"""
    offset: int = Field(default=0, ge=0)
    """起始行（0 起）。"""
    limit: int = Field(default=_DEFAULT_LIMIT, gt=0, le=_MAX_LIMIT)
    """本次读取的最大行数。"""


def _read_file_text(target: Path) -> str:
    """B-14 同族：文件内容按文本读，解码失败以替换符呈现而不是炸。"""
    return target.read_text(encoding="utf-8", errors="replace")


class ReadTool(Tool):
    name = "read"
    description = (
        "Read a text file with line numbers. Returns lines [offset, offset+limit); "
        "the output tells you if more lines remain."
    )
    kind = "file"
    mutates = False
    concurrency_safe = True
    expects_path = True
    path_param = "path"
    params_model = ReadParams

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, ReadParams)
        target = resolve_tool_path(ctx, params.path)
        try:
            text = await asyncio.to_thread(_read_file_text, target)
        except FileNotFoundError:
            return ToolResult(output=f"file not found: {params.path}", is_error=True)
        except OSError as exc:
            return ToolResult(output=f"cannot read {params.path}: {exc}", is_error=True)
        ctx.file_state.record_read(str(target))
        lines = text.splitlines()
        window = lines[params.offset : params.offset + params.limit]
        numbered = [f"{params.offset + i + 1}\t{line}" for i, line in enumerate(window)]
        remaining = len(lines) - params.offset - len(window)
        output = "\n".join(numbered) if numbered else "(empty file or offset past end)"
        if remaining > 0:
            output += f"\n... ({remaining} more lines; increase offset to continue)"
        return ToolResult(output=output)
