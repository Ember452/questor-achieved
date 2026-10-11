"""read-before-edit 门禁：写/改已存在文件前必须先读过，且读后未被外部改动。

参照 FlowCoder ``tools/file_state_cache.py`` 的两道闸（全部重写）：
1. 未读过 → 拒（"file has not been read yet"）——盲写会毁掉用户没看见的内容；
2. 读后被外部改动（mtime_ns 不匹配）→ 拒——基于陈旧内容的编辑会丢改动。

新增文件（本会话创建）不受门禁约束；文件被外部删除后放行写（重建合法）。
缓存是 run 内共享实例（``ToolContext.file_state``），read/edit/write 三件套共用。
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

_EDIT_ERROR = "file {path} has not been read yet. Read it first, then write/edit."
_STALE_ERROR = (
    "file {path} has been modified since it was read (mtime changed). Read it again, then retry."
)


@dataclass
class _Entry:
    mtime_ns: int


class FileStateCache:
    """run 内的文件读取状态（非线程安全——工具执行在同一事件循环内串行访问）。"""

    def __init__(self) -> None:
        self._read: dict[str, _Entry] = {}

    def record_read(self, path: str) -> None:
        resolved = str(pathlib.Path(path))
        self._read[resolved] = _Entry(mtime_ns=os.stat(resolved).st_mtime_ns)

    def invalidate(self, path: str) -> None:
        self._read.pop(str(pathlib.Path(path)), None)

    def ensure_editable(self, path: str) -> str | None:
        """返回拒绝原因；``None`` 表示可写。新建文件（不存在）直接放行。"""
        resolved = pathlib.Path(path)
        if not resolved.exists():
            return None  # 新建文件合法
        entry = self._read.get(str(resolved))
        if entry is None:
            return _EDIT_ERROR.format(path=path)
        if resolved.stat().st_mtime_ns != entry.mtime_ns:
            return _STALE_ERROR.format(path=path)
        return None
