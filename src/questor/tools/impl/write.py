"""write 工具：写文件（自动建父目录；已存在文件必须先读过——filestate 门禁）。"""

from __future__ import annotations

from pydantic import BaseModel

from questor.tools.base import Tool, ToolContext, ToolResult, resolve_tool_path


class WriteParams(BaseModel):
    path: str
    content: str


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
        target.parent.mkdir(parents=True, exist_ok=True)
        # 行尾统一 LF（.gitattributes 同款约定）；写出后记录读取状态供后续编辑
        target.write_text(params.content, encoding="utf-8", newline="\n")
        ctx.file_state.record_read(str(target))
        return ToolResult(
            output=f"wrote {len(params.content)} chars to {params.path}",
            data={"path": params.path, "bytes": len(params.content.encode("utf-8"))},
        )
