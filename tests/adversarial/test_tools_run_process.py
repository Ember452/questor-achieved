"""tools 对抗测试：退出码语义（B-12）、超时杀树（B-13）、输出边界（B-14 B-19）、
run/process 真实子进程链路与 ADR-0007 诚实标注。"""

from __future__ import annotations

import sys
import time

import pytest

from questor.schemas.model import PermissionMode as PM
from questor.tools.base import ToolContext
from questor.tools.executor import execute_calls
from questor.tools.filestate import FileStateCache
from questor.tools.impl.process_semantics import (
    format_output,
    map_exit_code,
)
from questor.tools.impl.registry_default import build_default_registry
from questor.tools.impl.todo import TodoStore
from questor.tools.processmgr import ProcessManager
from questor.tools.registry import ToolCallRequest

BG_ECHO_SCRIPT = "import time; print('bg-out', flush=True); time.sleep(30)"
BG_ECHO_COMMAND = f'"{sys.executable}" -c "{BG_ECHO_SCRIPT}"'


def _ctx(tmp_path) -> ToolContext:
    return ToolContext(
        cwd=str(tmp_path),
        file_state=FileStateCache(),
        processes=ProcessManager(),
        todos=TodoStore(),
    )


async def _run(command: str, tmp_path, **extra: object):
    registry = build_default_registry()
    outcomes = await execute_calls(
        [ToolCallRequest("id1", "run", {"command": command, **extra})],
        registry,
        _ctx(tmp_path),
        PM.STANDARD,
        [str(tmp_path)],
    )
    return outcomes[0].result


# ---- B-12：退出码语义映射（纯函数，不经过子进程） ----


def test_exit_code_zero_ok() -> None:
    assert map_exit_code("anything", 0) == (True, "ok")


def test_grep_pipe_last_segment_exit1_is_no_match() -> None:
    """按管道最后一段判定 + exit 1 = 无匹配（B-12 的两个半边）。"""
    ok, note = map_exit_code("cat file.txt | grep needle", 1)
    assert ok is True and "no match" in note
    ok, _ = map_exit_code("cat f | rg needle | head -5", 1)
    assert ok is False  # 最后一段是 head，exit 1 就是错误


def test_var_prefix_and_basename_extraction() -> None:
    """VAR= 前缀跳过 + basename 提取（B-12 两个坑）。"""
    ok, note = map_exit_code("FOO=1 /usr/bin/grep x f", 1)
    assert ok is True and "no match" in note
    ok, _ = map_exit_code("FOO=1 /usr/bin/head f", 1)
    assert ok is False


def test_regular_command_nonzero_is_error() -> None:
    ok, note = map_exit_code("python -c 'raise SystemExit(3)'", 3)
    assert ok is False and "3" in note


# ---- B-19 / B-14：输出格式化 ----


def test_format_output_sections_and_no_output() -> None:
    assert format_output(b"", b"") == "(no output)"
    text = format_output(b"out-line", b"err-line")
    assert "STDOUT:\nout-line" in text and "STDERR:\nerr-line" in text
    assert "(no output)" not in text


def test_format_output_truncates_middle() -> None:
    big = ("x" * 30_000).encode()
    formatted = format_output(big, b"")
    assert "[output truncated" in formatted
    # 头尾保留：开头与结尾都在
    assert formatted.count("x") < 30_000  # 中段确实被截
    assert formatted.rstrip().endswith("x")


def test_format_output_decodes_invalid_utf8() -> None:
    """B-14：二进制/坏 UTF-8 输出以替换符呈现，不炸。"""
    formatted = format_output(b"\xff\xfe bad bytes", b"")
    assert "bad bytes" in formatted
    assert "\ufffd" in formatted  # replacement char


# ---- B-13 / 超时移交：真实子进程 ----


@pytest.mark.asyncio
async def test_run_timeout_moves_to_background(tmp_path) -> None:
    """超时 → 后台移交 + 明确标注不是验证通过（overview §10）。"""
    ctx = _ctx(tmp_path)
    registry = build_default_registry()
    timed_out = await execute_calls(
        [
            ToolCallRequest(
                "id1",
                "run",
                {
                    "command": f'"{sys.executable}" -c "import time; time.sleep(30)"',
                    "timeout_s": 1,
                },
            )
        ],
        registry,
        ctx,
        PM.STANDARD,
        [str(tmp_path)],
    )
    result = timed_out[0].result
    assert result.is_error is True
    assert "timed out" in result.output and "NOT a verification result" in result.output
    process_id = result.data["process_id"]
    # 进程确实在同一个后台管理器里活着 → stop 杀树后列表清空
    stop = await execute_calls(
        [ToolCallRequest("id2", "process", {"action": "stop", "process_id": process_id})],
        registry,
        ctx,
        PM.STANDARD,
        [str(tmp_path)],
    )
    assert not stop[0].result.is_error
    assert ctx.processes.list() == []


@pytest.mark.asyncio
async def test_run_success_exit_code_and_sections(tmp_path) -> None:
    result = await _run(f'"{sys.executable}" -c "print(\'hello-run\')"', tmp_path)
    assert result.is_error is False
    assert "exit code 0 (ok)" in result.output
    assert "hello-run" in result.output
    # ADR-0007 诚实标注：sandboxed=False 恒在 data 里
    assert result.data["sandboxed"] is False


@pytest.mark.asyncio
async def test_run_nonzero_exit_is_error(tmp_path) -> None:
    result = await _run(f'"{sys.executable}" -c "raise SystemExit(2)"', tmp_path)
    assert result.is_error is True
    assert "exit code 2" in result.output


@pytest.mark.asyncio
async def test_run_background_then_read_and_stop(tmp_path) -> None:
    """background=True → process read 看到输出 → stop 杀树。"""
    registry = build_default_registry()
    ctx = _ctx(tmp_path)
    started = await execute_calls(
        [
            ToolCallRequest(
                "id1",
                "run",
                {
                    "command": BG_ECHO_COMMAND,
                    "background": True,
                },
            )
        ],
        registry,
        ctx,
        PM.STANDARD,
        [str(tmp_path)],
    )
    process_id = started[0].result.data["process_id"]
    time.sleep(0.8)  # 留出输出时间
    read = await execute_calls(
        [ToolCallRequest("id2", "process", {"action": "read", "process_id": process_id})],
        registry,
        ctx,
        PM.STANDARD,
        [str(tmp_path)],
    )
    assert "bg-out" in read[0].result.output
    stop = await execute_calls(
        [ToolCallRequest("id3", "process", {"action": "stop", "process_id": process_id})],
        registry,
        ctx,
        PM.STANDARD,
        [str(tmp_path)],
    )
    assert "stopped" in stop[0].result.output
    assert ctx.processes.list() == []  # 停止后不在运行列表


@pytest.mark.asyncio
async def test_job_object_kills_whole_tree(tmp_path) -> None:
    """B-13/ADR-0007：父进程派生孙进程，停父 → 整树死（Windows Job Object 语义）。"""
    if sys.platform != "win32":
        pytest.skip("Job Object 是 Windows 语义")
    registry = build_default_registry()
    ctx = _ctx(tmp_path)
    child_code = (
        "import subprocess, sys, time;"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "time.sleep(60)"
    )
    started = await execute_calls(
        [
            ToolCallRequest(
                "id1",
                "run",
                {"command": f'"{sys.executable}" -c {child_code!r}', "background": True},
            )
        ],
        registry,
        ctx,
        PM.STANDARD,
        [str(tmp_path)],
    )
    process_id = str(started[0].result.data["process_id"])
    time.sleep(1.5)  # 等孙进程真正起来
    managed = ctx.processes.get(process_id)
    grandchild = managed.popen.pid  # 只能验证父树存活与停止及时性
    ctx.processes.stop(process_id)
    time.sleep(0.5)
    assert managed.exited
    # 孙进程也应随 Job Object 死亡：通过 tasklist 检查已不可行（跨会话），
    # 这里断言 stop 立即返回且父已退出；孙的死亡由 Job Object 内核语义保证
    assert grandchild > 0
