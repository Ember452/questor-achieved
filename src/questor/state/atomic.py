"""原子写与幂等写（overview §6 state 职责的第二条）。

崩溃一致性契约：``write_atomic`` 任何一步失败都不留下半写的目标文件，
且临时文件必被清理；临时文件与目标**同目录**（B-72——跨目录 rename 不原子）。

# Reimplements wuu@wuu-main internal/securefs/securefs.go#WriteFileAtomic — pitfalls: B-72
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

# 凭据与关键状态的权限位；Windows 只影响只读位，尽力而为、不作为安全保证
_FILE_MODE = 0o600
_DIR_MODE = 0o700


def mkdir_secure(directory: pathlib.Path) -> pathlib.Path:
    """创建目录（含父级），已存在不报错；POSIX 上收紧到 0700，Windows 尽力而为。"""
    directory.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        os.chmod(directory, _DIR_MODE)
    return directory


def write_atomic(path: pathlib.Path, data: bytes) -> None:
    """把 ``data`` 整体原子地写入 ``path``（替换既有内容）。

    序列：同目录临时文件 → 写入 → fsync → ``os.replace``；任一步失败则清理
    临时文件并原样抛出。Windows 上 ``os.replace`` 等价 ``MoveFileEx(REPLACE_EXISTING)``，
    目标已存在也可原子替换。mode 位在 POSIX 收紧到 0600；Windows 不假设 chmod 可靠。
    """
    parent = path.parent
    mkdir_secure(parent)
    fd, tmp_name = tempfile.mkstemp(dir=parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if sys.platform != "win32":
            os.chmod(tmp_path, _FILE_MODE)
        os.replace(tmp_path, path)
    except BaseException:
        # 崩溃一致性：临时文件必被清理，目标文件保持旧内容原封不动
        tmp_path.unlink(missing_ok=True)
        raise


def write_excl(path: pathlib.Path, data: bytes) -> bool:
    """O_EXCL 幂等写（B-24）：存在即跳过，返回是否实际写入。

    同一 id 的工具结果只落盘一次；重复调用静默跳过且**不改写**已有内容——
    这既是幂等也是 append-only 纪律在单文件上的表达。
    """
    parent = path.parent
    mkdir_secure(parent)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return True
