"""八工具真实文件行为测试（隔离工作区；不经子进程的工具全部覆盖）。"""

from __future__ import annotations

import pathlib

import pytest

from questor.schemas.model import PermissionMode as PM
from questor.tools.base import ToolContext, resolve_tool_path
from questor.tools.executor import execute_calls
from questor.tools.filestate import FileStateCache
from questor.tools.impl.registry_default import build_default_registry
from questor.tools.impl.todo import TodoStore
from questor.tools.processmgr import ProcessManager
from questor.tools.registry import ToolCallRequest


@pytest.fixture()
def root(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path


@pytest.fixture()
def ctx(root: pathlib.Path) -> ToolContext:
    return ToolContext(
        cwd=str(root),
        file_state=FileStateCache(),
        processes=ProcessManager(),
        todos=TodoStore(),
    )


async def _call(tool_name: str, args: dict[str, object], ctx: ToolContext):
    registry = build_default_registry()
    outcomes = await execute_calls(
        [ToolCallRequest("id1", tool_name, args)],
        registry,
        ctx,
        PM.STANDARD,
        [ctx.cwd],
    )
    return outcomes[0]


async def test_read_numbered_lines_and_pagination(ctx: ToolContext, root: pathlib.Path) -> None:
    (root / "a.txt").write_text("l1\nl2\nl3\n", encoding="utf-8")
    outcome = await _call("read", {"path": "a.txt", "offset": 1, "limit": 1}, ctx)
    assert outcome.result.output.startswith("2\tl2")
    assert "1 more lines" in outcome.result.output


async def test_read_then_write_and_edit_flow(ctx: ToolContext, root: pathlib.Path) -> None:
    # 盲写已存在文件被 filestate 门禁拒绝
    (root / "b.txt").write_text("hello\n", encoding="utf-8")
    blind = await _call("write", {"path": "b.txt", "content": "x"}, ctx)
    assert blind.result.is_error and "has not been read" in blind.result.output
    # 读 → 写成功
    await _call("read", {"path": "b.txt"}, ctx)
    ok = await _call("write", {"path": "b.txt", "content": "alpha beta gamma\n"}, ctx)
    assert not ok.result.is_error
    # edit：唯一匹配成功
    edited = await _call("edit", {"path": "b.txt", "old_string": "beta", "new_string": "BETA"}, ctx)
    assert not edited.result.is_error
    assert "BETA" in (root / "b.txt").read_text(encoding="utf-8")
    # edit：歧义 → 文件不动 + 候选行号
    ambiguous = await _call("edit", {"path": "b.txt", "old_string": "a", "new_string": "z"}, ctx)
    assert ambiguous.result.is_error and "must be unique" in ambiguous.result.output
    assert "alpha" in (root / "b.txt").read_text(encoding="utf-8")  # 文件未动
    # edit：缺失 → 最近似行候选
    missing = await _call(
        "edit", {"path": "b.txt", "old_string": "不存在的内容", "new_string": "z"}, ctx
    )
    assert missing.result.is_error and "Nearest similar lines" in missing.result.output


async def test_write_creates_parents(ctx: ToolContext, root: pathlib.Path) -> None:
    outcome = await _call("write", {"path": "deep/nested/c.txt", "content": "x"}, ctx)
    assert not outcome.result.is_error
    assert (root / "deep" / "nested" / "c.txt").read_text(encoding="utf-8") == "x"


async def test_list_skips_and_marks(ctx: ToolContext, root: pathlib.Path) -> None:
    (root / "sub").mkdir()
    (root / "file.txt").write_text("x", encoding="utf-8")
    (root / "__pycache__").mkdir()
    outcome = await _call("list", {"path": "."}, ctx)
    assert "d sub/" in outcome.result.output
    assert "f file.txt" in outcome.result.output
    assert "__pycache__" not in outcome.result.output


async def test_search_pagination(ctx: ToolContext, root: pathlib.Path) -> None:
    for i in range(5):
        (root / f"n{i}.py").write_text(f"needle {i}\n", encoding="utf-8")
    page1 = await _call("search", {"pattern": "needle", "limit": 2}, ctx)
    assert page1.result.output.startswith("[1-2+ (more)")
    page3 = await _call("search", {"pattern": "needle", "offset": 4, "limit": 2}, ctx)
    assert "(end)" in page3.result.output
    bad = await _call("search", {"pattern": "("}, ctx)
    assert bad.result.is_error and "invalid regex" in bad.result.output


async def test_todo_add_update_list(ctx: ToolContext) -> None:
    added = await _call("todo", {"action": "add", "title": "第一步"}, ctx)
    assert "added" in added.result.output
    item_id = added.result.output.split("\n")[0].split()[1]
    updated = await _call("todo", {"action": "update", "id": item_id, "status": "done"}, ctx)
    assert "●" in updated.result.output
    assert "○" not in updated.result.output


async def test_search_path_outside_root_denied(ctx: ToolContext) -> None:
    """limen 集成：search 的路径参数越界即拒（executor → gate 链路）。"""
    outcome = await _call("search", {"pattern": "x", "path": "C:/Windows"}, ctx)
    assert outcome.denied is True
    assert outcome.result.is_error


async def test_todo_granularity_in_read_only_mode(ctx: ToolContext) -> None:
    """todo list 的 mutates=False 使其在 read_only 档可用；add 被拒（B-50 粒度原则）。"""
    registry = build_default_registry()
    admitted = await execute_calls(
        [ToolCallRequest("id1", "todo", {"action": "list"})],
        registry,
        ctx,
        PM.READ_ONLY,
        [ctx.cwd],
    )
    assert not admitted[0].result.is_error
    denied = await execute_calls(
        [ToolCallRequest("id2", "todo", {"action": "add", "title": "x"})],
        registry,
        ctx,
        PM.READ_ONLY,
        [ctx.cwd],
    )
    assert denied[0].denied is True


async def test_resolve_tool_path_relative(tmp_path: pathlib.Path) -> None:
    ctx_obj = ToolContext(
        cwd=str(tmp_path),
        file_state=FileStateCache(),
        processes=ProcessManager(),
        todos=TodoStore(),
    )
    assert resolve_tool_path(ctx_obj, "a/b.txt") == tmp_path / "a" / "b.txt"
