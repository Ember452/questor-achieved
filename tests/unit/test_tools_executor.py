"""executor 与登记表单元行为：授权序列、禁用≠未知（B-17）、并行批分区（B-16 B-15）。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from questor.schemas.model import PermissionMode as PM
from questor.tools.base import Tool, ToolContext, ToolResult
from questor.tools.executor import execute_calls
from questor.tools.filestate import FileStateCache
from questor.tools.impl.todo import TodoStore
from questor.tools.processmgr import ProcessManager
from questor.tools.registry import ToolCallRequest, ToolRegistry, partition_tool_calls

ROOTS = ["/ws"]


def _ctx(tmp_path) -> ToolContext:
    return ToolContext(
        cwd=str(tmp_path),
        file_state=FileStateCache(),
        processes=ProcessManager(),
        todos=TodoStore(),
    )


class _EchoParams(BaseModel):
    text: str = ""


class _EchoTool(Tool):
    name = "echo"
    description = "test double"
    kind = "meta"
    mutates = False
    concurrency_safe = True
    params_model = _EchoParams

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(params, _EchoParams)
        return ToolResult(output=f"echo:{params.text}")


class _BoomTool(_EchoTool):
    name = "boom"

    async def execute(self, params: BaseModel, ctx: ToolContext) -> ToolResult:
        raise RuntimeError("boom")


class _DenyTool(_EchoTool):
    name = "denywrite"
    kind = "file"
    mutates = True
    concurrency_safe = False  # 非安全工具：分区打断的测试桩
    expects_path = True
    path_param = "path"


def _registry_with(*tools: Tool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


@pytest.mark.asyncio
async def test_echo_roundtrip(tmp_path) -> None:
    registry = _registry_with(_EchoTool())
    outcomes = await execute_calls(
        [ToolCallRequest("id1", "echo", {"text": "hi"})],
        registry,
        _ctx(tmp_path),
        PM.STANDARD,
        ROOTS,
    )
    assert outcomes[0].result.output == "echo:hi"
    assert not outcomes[0].result.is_error


@pytest.mark.asyncio
async def test_unknown_tool_flagged_not_disabled(tmp_path) -> None:
    """B-17：未知工具的 outcome.unknown=True（engine 据此计熔断）；与禁用是两回事。"""
    outcomes = await execute_calls(
        [ToolCallRequest("id1", "nope", {})],
        _registry_with(_EchoTool()),
        _ctx(tmp_path),
        PM.STANDARD,
        ROOTS,
    )
    assert outcomes[0].unknown is True
    assert outcomes[0].result.is_error


@pytest.mark.asyncio
async def test_disabled_tool_is_not_unknown(tmp_path) -> None:
    """B-17 另一半：禁用的工具不算未知——已知但明确停用，不得计入熔断计数。"""
    registry = _registry_with(_EchoTool())
    registry.disable("echo")
    outcomes = await execute_calls(
        [ToolCallRequest("id1", "echo", {})],
        registry,
        _ctx(tmp_path),
        PM.STANDARD,
        ROOTS,
    )
    assert outcomes[0].unknown is False
    assert "disabled" in outcomes[0].result.output


@pytest.mark.asyncio
async def test_invalid_arguments_become_error_result(tmp_path) -> None:
    """pydantic 校验失败转错误结果回喂（FlowCoder 行为 11），不抛出。"""
    outcomes = await execute_calls(
        [ToolCallRequest("id1", "echo", {"text": 123})],
        _registry_with(_EchoTool()),
        _ctx(tmp_path),
        PM.STANDARD,
        ROOTS,
    )
    assert outcomes[0].result.is_error
    assert "invalid arguments" in outcomes[0].result.output


@pytest.mark.asyncio
async def test_tool_exception_becomes_error_result(tmp_path) -> None:
    """工具异常转错误结果（行为 11），executor 不炸。"""
    outcomes = await execute_calls(
        [ToolCallRequest("id1", "boom", {})],
        _registry_with(_BoomTool()),
        _ctx(tmp_path),
        PM.STANDARD,
        ROOTS,
    )
    assert outcomes[0].result.is_error
    assert "boom" in outcomes[0].result.output


@pytest.mark.asyncio
async def test_denied_by_gate(tmp_path) -> None:
    """deny 结果携带完整方言（error_kind + model_next_action）。"""
    outcomes = await execute_calls(
        [ToolCallRequest("id1", "denywrite", {"path": "/outside/x.txt"})],
        _registry_with(_DenyTool()),
        _ctx(tmp_path),
        PM.STANDARD,
        ROOTS,
    )
    outcome = outcomes[0]
    assert outcome.denied is True
    assert outcome.result.is_error
    assert "denied:" in outcome.result.output
    assert "model_next_action" in outcome.result.output


@pytest.mark.asyncio
async def test_parallel_batch_survives_single_failure(tmp_path) -> None:
    """B-15：并行批单失败降级为错误结果，其余照常返回。"""
    boom, echo = _BoomTool(), _EchoTool()
    registry = _registry_with(boom, echo)
    outcomes = await execute_calls(
        [
            ToolCallRequest("id1", "echo", {"text": "a"}),
            ToolCallRequest("id2", "boom", {}),
            ToolCallRequest("id3", "echo", {"text": "b"}),
        ],
        registry,
        _ctx(tmp_path),
        PM.STANDARD,
        ROOTS,
    )
    assert [o.request.tool_use_id for o in outcomes] == ["id1", "id2", "id3"]
    assert outcomes[0].result.output == "echo:a"
    assert outcomes[1].result.is_error
    assert outcomes[2].result.output == "echo:b"


def test_partition_consecutive_safe_merge() -> None:
    """B-16：连续安全工具合并并行批；非安全工具打断；单元素安全批退化为串行。"""
    registry = _registry_with(_EchoTool(), _DenyTool())  # echo safe / denywrite unsafe
    calls = [
        ToolCallRequest("a", "echo", {}),
        ToolCallRequest("b", "echo", {}),
        ToolCallRequest("c", "denywrite", {"path": "/ws/x"}),
        ToolCallRequest("d", "echo", {}),
    ]
    batches = partition_tool_calls(calls, registry)
    shapes = [(b.concurrent, len(b.calls)) for b in batches]
    # echo×2 连续安全 → 并行批；denywrite 打断；单个 echo 退化为串行（B-16）
    assert shapes == [(True, 2), (False, 1), (False, 1)]


def test_partition_respects_registry_order() -> None:
    registry = _registry_with(_EchoTool())
    calls = [ToolCallRequest(f"i{i}", "echo", {}) for i in range(4)]
    batches = partition_tool_calls(calls, registry)
    assert len(batches) == 1
    assert batches[0].concurrent is True
    assert [c.tool_use_id for c in batches[0].calls] == ["i0", "i1", "i2", "i3"]
