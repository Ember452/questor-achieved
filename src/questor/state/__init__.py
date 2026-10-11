"""state —— 路径单点解析、原子写、跨进程文件锁、存储编码（overview §6）。

三柱归属：三柱共同的地基——所有"过程摊开在磁盘上"的落盘纪律都从这里出。

# Reimplements wuu@wuu-main internal/statepath/statepath.go + internal/securefs/securefs.go
# + internal/storelock/store_lock.go — pitfalls: B-71 B-72 B-73
# 行为规格：docs/specs/behavior-state-wuu.md（坑条目与测试的对应关系见 pitfalls.md）
"""

from __future__ import annotations

from questor.state.atomic import mkdir_secure, write_atomic, write_excl
from questor.state.locks import LockTimeoutError, StoreLock, store_lock
from questor.state.paths import (
    config_path,
    files_dir,
    index_dir,
    questor_home,
    sessions_dir,
    thread_path,
    tool_result_path,
    validate_entity_id,
    validate_filename_component,
    workspace_dir_name,
    workspaces_dir,
)

__all__ = [
    "LockTimeoutError",
    "StoreLock",
    "config_path",
    "files_dir",
    "index_dir",
    "mkdir_secure",
    "questor_home",
    "sessions_dir",
    "store_lock",
    "thread_path",
    "tool_result_path",
    "validate_entity_id",
    "validate_filename_component",
    "workspace_dir_name",
    "workspaces_dir",
    "write_atomic",
    "write_excl",
]
