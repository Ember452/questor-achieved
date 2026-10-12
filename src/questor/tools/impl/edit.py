"""edit 工具：精确替换（匹配缺失或有歧义时文件不动并返回候选位置——overview §3）。

IO 沉到同步 helper（AGENTS §五 异步纪律；护栏见 tests/architecture/
test_tools_impl_no_blocking_io）。str.replace 不属于 Path.replace，shape 守卫不会误咬。
"""

from __future__ import annotations

import asyncio
import difflib
from pathlib import Path

from pydantic import BaseModel, Field

from questor.tools.base import Tool, ToolContext, ToolResult, resolve_tool_path

_MAX_CANDIDATES = 3


def _read_or_none(target: Path) -> str | None:
    """读文件内容（不存在时 None）。B-14 同族：解码失败以替换符呈现。"""
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None


def _write_text(target: Path, text: str) -> None:
    """写回文件（行尾 LF）。"""
    target.write_text(text, encoding="utf-8", newline="\n")


class EditParams(BaseModel):
    path: str
    old_string: str = Field(min_length=1)
    new_string: str


class EditTool(Tool):
    name = "edit"
    description = (
        "Replace exactly one occurrence of old_string with new_string in a file. "
        "When the match is missing or ambiguous the file is left untouched and "
        "candidate locations are returned."
    )
    kind = "file"
    mutates = True
    expects_path = True
    path_param = "path"
    params_model = EditParams

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, EditParams)
        target = resolve_tool_path(ctx, params.path)
        reason = ctx.file_state.ensure_editable(str(target))
        if reason is not None:
            return ToolResult(output=reason, is_error=True)
        text = await asyncio.to_thread(_read_or_none, target)
        if text is None:
            return ToolResult(output=f"file not found: {params.path}", is_error=True)

        occurrences = _occurrence_lines(text, params.old_string)
        if not occurrences:
            candidates = _nearest_lines(text, params.old_string)
            hint = ";".join(f"line {n}: {line!r}" for n, line in candidates)
            return ToolResult(
                output=(
                    f"old_string not found in {params.path}. "
                    f"Nearest similar lines: {hint or '(file is empty)'}"
                ),
                is_error=True,
            )
        if len(occurrences) > 1:
            positions = ", ".join(str(n) for n in occurrences)
            return ToolResult(
                output=(
                    f"old_string found {len(occurrences)} times in {params.path} "
                    f"(lines {positions}); it must be unique. "
                    "Include more surrounding context to disambiguate."
                ),
                is_error=True,
            )

        edited = text.replace(params.old_string, params.new_string, 1)
        await asyncio.to_thread(_write_text, target, edited)
        ctx.file_state.record_read(str(target))  # 编辑后状态同步，连续编辑无需重读
        return ToolResult(
            output=f"replaced 1 occurrence at line {occurrences[0]} in {params.path}",
            data={"path": params.path, "line": occurrences[0]},
        )


def _occurrence_lines(text: str, needle: str) -> list[int]:
    """old_string 各次出现的起始行号（1 起）。"""
    lines: list[int] = []
    offset = 0
    line_no = 1
    while True:
        index = text.find(needle, offset)
        if index < 0:
            break
        lines.append(line_no + text.count("\n", offset, index))
        offset = index + len(needle)
    return lines


def _nearest_lines(text: str, needle: str) -> list[tuple[int, str]]:
    """最相似的三行（difflib 比率），供"匹配缺失"时定位。"""
    matcher = difflib.SequenceMatcher(None, needle, "", autojunk=False)
    scored: list[tuple[float, int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        matcher.set_seq2(line)
        scored.append((matcher.ratio(), line_no, line))
    scored.sort(reverse=True)
    return [(n, line) for _, n, line in scored[:_MAX_CANDIDATES]]
