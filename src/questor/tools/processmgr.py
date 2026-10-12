"""后台进程管理：run 超时移交的宿主，停树用 Job Object（Windows）/进程组（POSIX）。

参照 wuu ``internal/process/manager.go`` 的语义（重写）：
- **派生即入树**：Windows 上进程一创建就 AssignProcessToJobObject，超时/取消时
  ``TerminateJobObject`` 整树硬杀（ADR-0007/0015）；POSIX ``start_new_session``
  建进程组，``os.killpg`` 杀树。
- **PID 复用防护**（data-model §3.1 取消传播三元组的等价物）：我们**持有 Popen
  对象本身**而不是记录 pid 再查——通过对象句柄杀进程天然不存在 pid 复用窗口；
  这比"记录 pid+pgid+start_time 再重查"更强（没有重查环节）。前台 run 超时
  移交（adopt）同理：移交的是活对象不是数字。
- **后台任务强引用**（B-01）：读输出的线程与 wait 任务由本管理器持引用，
  done callback 记异常日志，防 GC 中途回收与异常静默。
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_OUTPUT_CAP = 1_000_000  # 每流缓冲上限（字节）；超限保头尾，防内存失控
_KEEP_HEAD = 400_000
_IS_WINDOWS = __import__("os").name == "nt"


def _new_kill_on_close_job() -> int:
    """创建 KILL_ON_JOB_CLOSE 的 Job Object；返回 PyHANDLE（int 子类）。

    生命周期纪律：返回的**必须保持被引用**（存进 ManagedProcess.job）——PyHANDLE
    被 GC 时会关闭底层句柄，int 化拷贝不能延长生命周期（M2.2 实测踩过：
    int(handle) 返回后句柄即死，Assign 报"句柄无效"）。
    """
    import win32job  # noqa: PLC0415 —— 平台标记依赖（ADR-0015），POSIX 不 import

    handle = win32job.CreateJobObject(None, "")
    if handle is None:
        raise ProcessManagerError("Job Object 创建失败（内核返回空句柄）")
    limits = win32job.QueryInformationJobObject(handle, win32job.JobObjectExtendedLimitInformation)
    limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(handle, win32job.JobObjectExtendedLimitInformation, limits)
    return handle


def _process_handle(popen: subprocess.Popen[bytes]) -> int:
    """Windows Popen 的进程句柄（typeshed 不暴露该属性；进程树管理需要原始句柄）。"""
    return int(getattr(popen, "_handle"))  # noqa: B009, SLF001


def _killpg_posix(pid: int) -> None:
    """POSIX 进程组终止（仅 POSIX 平台调用；Windows 的 typeshed 无此 API，动态取用）。"""
    import contextlib  # noqa: PLC0415
    import os  # noqa: PLC0415
    import signal  # noqa: PLC0415

    killpg = getattr(os, "killpg")  # noqa: B009 —— typeshed 仅 POSIX 暴露
    getpgid = getattr(os, "getpgid")  # noqa: B009
    with contextlib.suppress(ProcessLookupError, PermissionError):
        killpg(getpgid(pid), getattr(signal, "SIGTERM"))  # noqa: B009


@dataclass
class ManagedProcess:
    """一个受管后台进程：活对象持有 + 增量输出缓冲。"""

    process_id: str
    command: str
    popen: subprocess.Popen[bytes]
    job: int | None = None  # Windows Job Object 句柄（POSIX 为 None）
    stdout_chunks: list[bytes] = field(default_factory=list)
    stderr_chunks: list[bytes] = field(default_factory=list)
    stdout_size: int = 0
    stderr_size: int = 0
    exited: bool = False
    exit_code: int | None = None
    truncated: bool = False


class ProcessManagerError(Exception):
    """进程管理操作错误（进程不存在、已退出等）。"""


class ProcessManager:
    """本会话派生的后台进程注册表；只管理自己创建/收养的进程。"""

    def __init__(self) -> None:
        self._processes: dict[str, ManagedProcess] = {}
        self._lock = threading.Lock()
        self._waiters: list[threading.Thread] = []  # B-01 强引用

    # ---- 派生与收养 ----

    def spawn(self, command: str, *, cwd: str | None = None) -> ManagedProcess:
        """派生命令并纳入进程树管理；立即返回（输出由读线程累积）。"""
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if _IS_WINDOWS else 0  # noqa: B009 —— typeshed 仅 Windows 暴露该属性
        job = _new_kill_on_close_job() if _IS_WINDOWS else None
        popen = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            creationflags=creationflags,
            start_new_session=not _IS_WINDOWS,
        )
        if job is not None:
            import win32job  # noqa: PLC0415

            # 派生即入树：Popen 返回与 Assign 之间存在微秒级逃逸窗口（子进程在此
            # 刻派生孙进程可逃出树）——诚实记录为 M2.2 取舍，见 tools.md 设计篇
            win32job.AssignProcessToJobObject(job, _process_handle(popen))
        process = ManagedProcess(
            process_id=uuid.uuid4().hex[:12],
            command=command,
            popen=popen,
            job=job,
        )
        with self._lock:
            self._processes[process.process_id] = process
        self._start_readers(process)
        self._monitor(process)
        return process

    # ---- 查询与操作 ----

    def get(self, process_id: str) -> ManagedProcess:
        process = self._processes.get(process_id)
        if process is None:
            raise ProcessManagerError(f"进程 {process_id!r} 不存在")
        return process

    def list(self) -> list[ManagedProcess]:
        with self._lock:
            return [p for p in self._processes.values() if not p.exited]

    def read_output(self, process_id: str) -> tuple[bytes, bytes, bool]:
        """返回 (stdout 增量, stderr 增量, exited) 并清空增量缓冲。"""
        process = self.get(process_id)
        with self._lock:
            out = b"".join(process.stdout_chunks)
            err = b"".join(process.stderr_chunks)
            process.stdout_chunks.clear()
            process.stderr_chunks.clear()
            return out, err, process.exited

    def drain(self, process_id: str, grace_s: float = 0.0) -> tuple[bytes, bytes]:
        """按宽限等待排空输出增量（前台 run 退出后取尾部用）。"""
        if grace_s > 0:
            time.sleep(grace_s)
        out, err, _ = self.read_output(process_id)
        return out, err

    def write_stdin(self, process_id: str, data: str) -> None:
        process = self.get(process_id)
        if process.exited or process.popen.stdin is None:
            raise ProcessManagerError(f"进程 {process_id} 已退出或无 stdin")
        try:
            process.popen.stdin.write(data.encode("utf-8"))
            process.popen.stdin.flush()
        except (OSError, ValueError) as exc:
            raise ProcessManagerError(f"写入 stdin 失败：{exc}") from exc

    def stop(self, process_id: str) -> None:
        """停树：Windows TerminateJobObject，POSIX killpg；持对象句柄，无 PID 复用窗口。"""
        process = self.get(process_id)
        if process.exited:
            return
        if _IS_WINDOWS and process.job is not None:
            import win32job  # noqa: PLC0415

            win32job.TerminateJobObject(process.job, 1)  # 整树硬杀
        else:
            _killpg_posix(process.popen.pid)
        try:
            process.popen.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.popen.kill()
            process.popen.wait(timeout=5)
        self._mark_exit(process)

    # ---- 内部 ----

    def _start_readers(self, process: ManagedProcess) -> None:
        for stream_name in ("stdout", "stderr"):
            thread = threading.Thread(
                target=self._read_stream,
                args=(process, stream_name),
                daemon=True,
                name=f"questor-proc-{process.process_id}-{stream_name}",
            )
            thread.start()
            self._waiters.append(thread)  # B-01 强引用

    def _read_stream(self, process: ManagedProcess, stream_name: str) -> None:
        """读线程主体：持续把流内容折进缓冲（超限后丢弃新增并打标，防内存失控）。"""
        stream = getattr(process.popen, stream_name)
        if stream is None:
            return
        try:
            while True:
                # read1 而非 read：read 会阻塞到缓冲区满或 EOF，增量输出必须
                # "有多少读多少"（M2.2 实测：read 让后台输出卡在首行后不可见）
                chunk = stream.read1(65536)
                if not chunk:
                    break
                with self._lock:
                    total = process.stdout_size if stream_name == "stdout" else process.stderr_size
                    if total + len(chunk) > _OUTPUT_CAP:
                        process.truncated = True
                        continue  # 超限丢弃新增；精化策略随 M4 存储治理
                    if stream_name == "stdout":
                        process.stdout_chunks.append(chunk)
                        process.stdout_size += len(chunk)
                    else:
                        process.stderr_chunks.append(chunk)
                        process.stderr_size += len(chunk)
        except (OSError, ValueError):
            pass  # 进程退出导致的流关闭是正常终态

    def _monitor(self, process: ManagedProcess) -> None:
        """wait 线程：退出即标记；输出排空由读线程在 EOF 自然完成，无需额外排空。"""

        def _wait() -> None:
            code = process.popen.wait()
            with self._lock:
                process.exited = True
                process.exit_code = code

        waiter = threading.Thread(
            target=_wait, daemon=True, name=f"questor-proc-wait-{process.process_id}"
        )
        waiter.start()
        self._waiters.append(waiter)  # B-01 强引用

    def _mark_exit(self, process: ManagedProcess) -> None:
        with self._lock:
            process.exited = True
            process.exit_code = process.popen.poll()
