"""护栏：tools/impl 的 async 函数不得直接调 Path/IO 阻塞方法（AGENTS §五 异步纪律）。

事件循环内禁止同步文件 IO。修法只有一种：把 IO 沉进同步 helper，async 侧
`await asyncio.to_thread(helper, ...)`。read/write/edit/search/list 五个 file 工具
都受本条管住。

负向验证（写此测试时实测）：把 read.py 里 asyncio.to_thread 剥掉、还原成
``target.read_text(...)`` → 本测试 FAILED，行号与阻塞方法名都指出；改回 to_thread → 绿。
list.py 与 search.py 的初版同样命中 `is_dir`——一并修完才转 covered。
"""

from __future__ import annotations

import ast
import pathlib

TOOLS_IMPL = pathlib.Path(__file__).resolve().parents[2] / "src" / "questor" / "tools" / "impl"

#: pathlib.Path 与内建 open 的阻塞方法。async 函数里直接调即违规。
_BLOCKING = frozenset(
    {
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
        "mkdir",
        "rglob",
        "glob",
        "iterdir",
        "walk",
        "unlink",
        "rmdir",
        "rename",
        "touch",
        "readlink",
        "open",
        "stat",
        "lstat",
        "is_dir",
        "is_file",
        "exists",
    }
)


def _is_to_thread(call: ast.Call) -> bool:
    """匹配 ``asyncio.to_thread(...)`` / ``to_thread(...)``；其参数里的调用属线程内。"""
    fn = call.func
    if isinstance(fn, ast.Attribute) and fn.attr == "to_thread":
        return True
    return isinstance(fn, ast.Name) and fn.id == "to_thread"


def _blocking_calls_in_async(node: ast.AsyncFunctionDef) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        if _is_to_thread(inner):
            # to_thread 第一个位置参数（同步函数）里的调用不递归展开——那些已经在线程里跑
            continue
        fn = inner.func
        if isinstance(fn, ast.Attribute) and fn.attr in _BLOCKING:
            hits.append((inner.lineno, fn.attr))
    return hits


def test_async_tools_do_no_blocking_io() -> None:
    violations: list[str] = []
    for py in sorted(TOOLS_IMPL.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for lineno, name in _blocking_calls_in_async(node):
                rel = py.relative_to(TOOLS_IMPL.parents[1])
                violations.append(f"{rel}:{lineno} async {node.name}() 直接 .{name}()")
    assert not violations, (
        "tools/impl 的 async 方法在事件循环里做了阻塞 IO（AGENTS §五 异步纪律），"
        "请用 asyncio.to_thread 把 IO 沉到同步 helper：\n" + "\n".join(violations)
    )
