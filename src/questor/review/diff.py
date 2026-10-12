"""unified diff 生成（B-66/B-93：写工具执行时刻算，随结果持久化）。

只吃 old_text / new_text，不看盘、不看 git——由 write / edit 工具在 execute 里调；
调用方负责把结果塞 `ToolResult.data["diff"]` 与 Item.payload。

fingerprint 用双哈希的前 16 位（不引第三方），供 files/read 与 selection 定位回源；
byte_size 保存原始字节数（不假设换行一致）。
"""

from __future__ import annotations

import difflib
import hashlib
import re
from typing import TypedDict


class DiffHunk(TypedDict):
    """一段变更：old/new 起点与行数 + 原文行（unified diff 中的 `+`/`-`/` ` 前缀保留）。"""

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    body: list[str]


class FileDiff(TypedDict):
    """一个文件的完整变更描述。created=True 表示原本不存在（old_text=None）。"""

    path: str
    created: bool
    hunks: list[DiffHunk]
    content_fingerprint: str
    byte_size: int
    unified: str


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def compute_diff(path: str, old_text: str | None, new_text: str) -> FileDiff:
    """old_text=None 视作新建；输出结构化 diff（hunks + unified 原文 + 指纹）。"""
    created = old_text is None
    old_lines = (old_text or "").splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    unified_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    body = new_text.encode("utf-8", errors="replace")
    return {
        "path": path,
        "created": created,
        "hunks": _parse_hunks(unified_lines),
        "content_fingerprint": hashlib.sha256(body).hexdigest()[:16],
        "byte_size": len(body),
        "unified": "\n".join(unified_lines),
    }


def _parse_hunks(unified_lines: list[str]) -> list[DiffHunk]:
    """从 unified diff 抽出 hunk 元数据；difflib 头形如 `@@ -a,b +c,d @@`。"""
    hunks: list[DiffHunk] = []
    current: DiffHunk | None = None
    for line in unified_lines:
        m = _HUNK_HEADER.match(line)
        if m:
            if current is not None:
                hunks.append(current)
            current = {
                "old_start": int(m.group(1)),
                "old_lines": int(m.group(2) or 1),
                "new_start": int(m.group(3)),
                "new_lines": int(m.group(4) or 1),
                "body": [],
            }
        elif current is not None:
            current["body"].append(line)
    if current is not None:
        hunks.append(current)
    return hunks
