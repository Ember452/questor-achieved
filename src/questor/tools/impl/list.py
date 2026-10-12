"""list 工具：目录列举（目录优先、跳过基建目录）。

遍历整段沉到 :func:`_scan_entries` 同步 helper（AGENTS §五 异步纪律；护栏见
tests/architecture/test_tools_impl_no_blocking_io）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from questor.tools.base import SKIP_DIRS, Tool, ToolContext, ToolResult, resolve_tool_path

_MAX_ENTRIES = 500


class ListParams(BaseModel):
    path: str = "."
    recursive: bool = Field(default=False)
    """递归列举（深度受条目上限约束）。"""


class ListTool(Tool):
    name = "list"
    description = "List a directory. Directories first, SKIP_DIRS excluded, entries capped."
    kind = "file"
    mutates = False
    concurrency_safe = True
    expects_path = True
    path_param = "path"
    path_default = "."
    params_model = ListParams

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, ListParams)
        target = resolve_tool_path(ctx, params.path)
        lines = await asyncio.to_thread(_scan_entries, target, params.recursive)
        if lines is None:
            return ToolResult(output=f"not a directory: {params.path}", is_error=True)
        output = "\n".join(lines) if lines else "(empty directory)"
        return ToolResult(output=output)


def _scan_entries(target: Path, recursive: bool) -> list[str] | None:
    """target 不是目录时返回 None；否则返回渲染好的条目列表（受 _MAX_ENTRIES 截断）。"""
    if not target.is_dir():
        return None
    iterator = target.rglob("*") if recursive else target.iterdir()
    lines: list[str] = []
    for entry in iterator:
        if entry.name in SKIP_DIRS or any(part in SKIP_DIRS for part in entry.parts):
            continue
        relative = entry.relative_to(target)
        if entry.is_dir():
            lines.append(f"d {relative.as_posix()}/")
        else:
            lines.append(f"f {relative.as_posix()} ({entry.stat().st_size}B)")
        if len(lines) >= _MAX_ENTRIES:
            lines.append(f"... (capped at {_MAX_ENTRIES} entries)")
            break
    return lines
