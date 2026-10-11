"""list 工具：目录列举（目录优先、跳过基建目录）。"""

from __future__ import annotations

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
        if not target.is_dir():
            return ToolResult(output=f"not a directory: {params.path}", is_error=True)
        iterator = target.rglob("*") if params.recursive else target.iterdir()
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
        output = "\n".join(lines) if lines else "(empty directory)"
        return ToolResult(output=output)
