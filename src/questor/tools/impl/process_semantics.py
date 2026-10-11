"""命令执行的语义件：超时上限、退出码映射（B-12）、输出格式化（B-14 B-19）。

从 run 工具抽出为纯函数——单测不经过子进程即可覆盖映射规则。
"""

from __future__ import annotations

import os
import posixpath

MAX_TIMEOUT_S = 600
_HEAD = 10_000
_TAIL = 10_000
_TRUNCATION_MARK = "\n... [output truncated: {} bytes elided] ...\n"

#: 这些命令以管道**最后一段**判定退出码语义，且 exit 1 表示"无匹配"而非错误（B-12）
_SEMANTIC_NO_MATCH = frozenset({"grep", "egrep", "fgrep", "rg", "diff", "find", "test", "["})


def _last_pipeline_segment(command: str) -> str:
    """取管道/链的最后一段命令名：跳过 VAR= 前缀、取 basename（B-12 的两个坑）。"""
    segment = command
    for separator in ("&&", "||", "|", ";"):
        if separator in segment:
            segment = segment.rsplit(separator, 1)[-1]
    segment = segment.strip()
    # VAR=value 前缀（可能连续多个）
    while True:
        head, _, rest = segment.partition(" ")
        if "=" in head and head and (head[0].isalpha() or head[0] == "_") and rest:
            segment = rest.lstrip()
        else:
            break
    first = segment.split()[0] if segment.split() else ""
    return posixpath.basename(first) if first else ""


def map_exit_code(command: str, exit_code: int) -> tuple[bool, str]:
    """退出码语义映射：返回 (是否算成功, 语义说明)。"""
    if exit_code == 0:
        return True, "ok"
    if _last_pipeline_segment(command) in _SEMANTIC_NO_MATCH and exit_code == 1:
        return True, "exit 1 = no match for this command"
    if os.name == "nt" and exit_code == 1 and command.strip().startswith("findstr"):
        return True, "exit 1 = no match for this command"
    return False, f"exit code {exit_code}"


def format_output(stdout: bytes, stderr: bytes) -> str:
    """stdout/stderr 分段标注；双空显式 "(no output)"（B-19）；超长保头尾（B-14 解码 replace）。"""
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    if not out.strip() and not err.strip():
        return "(no output)"
    sections: list[str] = []
    for label, body in (("STDOUT", out), ("STDERR", err)):
        if not body.strip():
            continue
        encoded = body.encode("utf-8")
        if len(encoded) > _HEAD + _TAIL:
            head = encoded[:_HEAD].decode("utf-8", errors="replace")
            tail = encoded[-_TAIL:].decode("utf-8", errors="replace")
            elided = len(encoded) - _HEAD - _TAIL
            body = head + _TRUNCATION_MARK.format(elided) + tail
        sections.append(f"{label}:\n{body.rstrip()}")
    return "\n\n".join(sections) if sections else "(no output)"
