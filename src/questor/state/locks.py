"""跨进程文件锁（overview §6 state 职责的第三条）。

契约（wuu storelock 的语义，坑 B-71）：
- 锁由**内核持有**（Windows ``LockFileEx`` 系 / POSIX ``flock``），进程死即自动释放；
  因此没有心跳、没有陈旧锁破坏逻辑——加"清理陈旧锁"反而引入竞态；
- 锁文件**永不删除**：释放后留在原地，保证所有竞争者始终锁同一 inode
  （删除-重建会让两个进程锁到不同 inode，互斥失效）；
- 非阻塞 try 循环 + 25ms 间隔，硬超时（默认 60s）报错不死等——健康事务持锁
  毫秒级，持锁超时说明持有者已 wedge；
- 释放幂等；重复释放与未 acquire 就释放都不抛错。

# Reimplements wuu@wuu-main internal/storelock/store_lock.go — pitfalls: B-71
"""

from __future__ import annotations

import errno
import os
import pathlib
import time
from contextlib import AbstractContextManager
from types import TracebackType

if os.name == "nt":
    import msvcrt

_DEFAULT_TIMEOUT_S = 60.0
_RETRY_INTERVAL_S = 0.025
_LOCK_FILE_NAME = ".store.lock"


class LockTimeoutError(RuntimeError):
    """锁在超时窗口内未被授予——持有者疑似 wedge，调用方不应继续等。"""

    def __init__(self, path: pathlib.Path, timeout: float) -> None:
        self.path = path
        self.timeout = timeout
        super().__init__(f"{path} 被其他持有者占用超过 {timeout:.1f}s")


def _try_lock(fd: int) -> bool:
    """非阻塞尝试加锁；被他人持有时返回 ``False``，其他错误原样抛出。"""
    if os.name == "nt":
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            # EACCES/EDEADLOCK = 区域已被锁（含同进程另一句柄），属竞争而非故障
            if exc.errno in (errno.EACCES, errno.EDEADLOCK):
                return False
            raise
        return True
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return False
        raise
    return True


def _unlock(fd: int) -> None:
    if os.name == "nt":
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            # 释放失败不掩盖业务异常；fd 随 close 关闭后内核锁必然消亡
            return
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


class StoreLock(AbstractContextManager["StoreLock"]):
    """store 目录上的独占跨进程锁，用法：``with store_lock(dir): ...``。"""

    def __init__(self, directory: pathlib.Path, timeout: float = _DEFAULT_TIMEOUT_S) -> None:
        self._dir = directory
        self._path = directory / _LOCK_FILE_NAME
        self._timeout = timeout
        self._fd: int | None = None

    @property
    def path(self) -> pathlib.Path:
        """锁文件路径（永不删除，仅用于诊断）。"""
        return self._path

    def acquire(self, timeout: float | None = None) -> None:
        """阻塞至持锁；超时抛 :class:`LockTimeoutError`，不修改任何既有文件。

        ``timeout`` 缺省用构造时的实例超时，可按次覆盖（engine 等高频调用方
        对热路径传更短的上限）。

        取消语义（诚实声明）：本锁是同步阻塞原语——engine 在事件循环内经
        ``asyncio.to_thread`` 调用时，协程取消**不会中断**已在重试循环里等待的
        线程；等待的上界就是这里的超时。需要更快放弃的调用方应传更短的
        per-call 超时，并把 :class:`LockTimeoutError` 上浮为用户可见错误。
        """
        effective = self._timeout if timeout is None else timeout
        if self._fd is not None:
            raise RuntimeError("StoreLock 重复 acquire")
        self._dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + effective
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                os.close(fd)
                raise LockTimeoutError(self._path, effective)
            time.sleep(_RETRY_INTERVAL_S)
        self._fd = fd

    def release(self) -> None:
        """释放锁；幂等，未持锁时调用是无操作。"""
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        _unlock(fd)
        os.close(fd)
        # B-71：锁文件刻意不删除——后来者必须继续锁同一个 inode

    def __enter__(self) -> StoreLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def store_lock(directory: pathlib.Path, timeout: float = _DEFAULT_TIMEOUT_S) -> StoreLock:
    """构造一把未持有的锁；典型用法 ``with store_lock(dir): ...``。"""
    return StoreLock(directory, timeout)
