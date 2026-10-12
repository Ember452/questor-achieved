"""search 工具：正则内容搜索（相对路径行定位 + offset 分页）。

偏离留痕：overview 的"快照分页 + expected_revision"绑定工作区修订号（M3 review、
ADR-0005）；M2.2 无修订号来源，先以 offset 分页承载，修订号绑定随 M3 补
（development-plan M2.2 实际结果留痕）。

扫描循环整段沉到 :func:`_scan_matches` 同步 helper（AGENTS §五 异步纪律；护栏见
tests/architecture/test_tools_impl_no_blocking_io），async 侧一次 `to_thread`。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from pydantic import BaseModel, Field

from questor.tools.base import SKIP_DIRS, Tool, ToolContext, ToolResult, resolve_tool_path

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200
_LINE_PREVIEW = 200
_BINARY_SNIFF = 1024


class SearchParams(BaseModel):
    pattern: str = Field(min_length=1)
    """正则表达式（re 语法）。"""
    path: str = "."
    """搜索根目录（相对路径相对工作目录）。"""
    include: str = ""
    """文件名 glob（如 ``*.py``）；空为全部文件。"""
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=_DEFAULT_LIMIT, gt=0, le=_MAX_LIMIT)


class SearchTool(Tool):
    name = "search"
    description = (
        "Search file contents with a regex. Returns 'path:line:text' matches with "
        "offset pagination; use offset to page through large result sets."
    )
    kind = "file"
    mutates = False
    concurrency_safe = True
    expects_path = True
    path_param = "path"
    path_default = "."
    params_model = SearchParams

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, SearchParams)
        try:
            pattern = re.compile(params.pattern)
        except re.error as exc:
            return ToolResult(output=f"invalid regex: {exc}", is_error=True)
        root = resolve_tool_path(ctx, params.path)
        matches = await asyncio.to_thread(
            _scan_matches, root, params.include, pattern, params.offset, params.limit
        )
        if matches is None:
            return ToolResult(output=f"not a directory: {params.path}", is_error=True)

        total_known = len(matches) > params.offset + params.limit
        window = matches[params.offset : params.offset + params.limit]
        if not window:
            return ToolResult(output=f"no matches for {params.pattern!r} (offset={params.offset})")
        header = f"[{params.offset + 1}-{params.offset + len(window)}"
        header += "+ (more)" if total_known else " (end)"
        header += f" of query {params.pattern!r}]"
        return ToolResult(output=header + "\n" + "\n".join(window))


def _scan_matches(
    root: Path, include: str, pattern: re.Pattern[str], offset: int, limit: int
) -> list[str] | None:
    """同步扫描：root 不是目录时返回 None，其他情形返回匹配列表。

    够本页即停（break 条件是长度跨过 offset+limit），总数是否"还有更多"由此呈现。
    """
    if not root.is_dir():
        return None
    matches: list[str] = []
    for file in _candidate_files(root, include):
        matches.extend(_search_file(file, root, pattern))
        if len(matches) > offset + limit:
            break
    return matches


def _candidate_files(root: Path, include: str):
    iterator = root.rglob(include or "**/*")
    for file in iterator:
        if not file.is_file():
            continue
        if file.name in SKIP_DIRS or any(part in SKIP_DIRS for part in file.parts):
            continue
        yield file


def _search_file(file: Path, root: Path, pattern: re.Pattern[str]) -> list[str]:
    try:
        with file.open("rb") as handle:
            if b"\x00" in handle.read(_BINARY_SNIFF):
                return []  # 二进制文件跳过
        text = file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    relative = file.relative_to(root).as_posix()
    found: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            preview = line[:_LINE_PREVIEW]
            found.append(f"{relative}:{line_no}:{preview}")
    return found
