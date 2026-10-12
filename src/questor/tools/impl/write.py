"""write 工具：写文件（自动建父目录；已存在文件必须先读过——filestate 门禁）。

IO 沉进 `_read_or_none` / `_write_file_text` 同步 helper（AGENTS §五 异步纪律；护栏见
tests/architecture/test_tools_impl_no_blocking_io）。写完成后：

1. 用 `review.compute_diff(old_text, new_text)` 生成结构化 diff（B-66/B-93）；
2. 若 `ctx.workspace_id` 存在，调 `workspaces.bump_revision` 递增修订号（B-92）；
3. 把 `diff` 与 `revision` 塞 `ToolResult.data`，engine 会随 Item.payload 落正文。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from questor.review import compute_diff
from questor.tools.base import Tool, ToolContext, ToolResult, resolve_tool_path
from questor.workspaces import bump_revision


class WriteParams(BaseModel):
    path: str
    content: str


def _read_or_none(target: Path) -> str | None:
    """读回旧内容；不存在返回 None（供 diff 判 created）。"""
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None


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
        old_text = await asyncio.to_thread(_read_or_none, target)
        await asyncio.to_thread(_write_file_text, target, params.content)
        ctx.file_state.record_read(str(target))  # 写出后记录读取状态供后续编辑
        diff = compute_diff(params.path, old_text, params.content)
        data: dict[str, object] = {
            "path": params.path,
            "bytes": len(params.content.encode("utf-8")),
            "diff": dict(diff),
        }
        if ctx.workspace_id is not None:
            data["revision"] = await asyncio.to_thread(bump_revision, ctx.workspace_id)
        return ToolResult(output=f"wrote {len(params.content)} chars to {params.path}", data=data)
