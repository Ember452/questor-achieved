"""executor —— 工具执行的**唯一授权入口**：limen.gate 的唯一消费者。

架构断言（test_permission_gate_single_entry）：除本模块外任何模块 import
limen.gate 即违规——工具实现与循环代码都摸不到门，"权限判定无绕过路径"由此机械成立。

执行序列（每个调用）：
1. 登记表查询：未知工具（B-17 计入熔断计数，由 engine 维护）与已禁用工具
   （B-17：不算未知）在这里分流；
2. 参数解析：pydantic ValidationError 转错误结果回喂模型（FlowCoder 行为 11）；
3. 构造 limen 判定输入（ToolCallInfo 由工具声明 + 参数合成）→ ``decide``；
4. deny → 错误结果携带 error_kind + reason + model_next_action 方言；
   allow + redact_output → 结果经 :func:`limen.gate.redact_output` 脱敏（B-54）；
5. 执行工具 → 异常转错误结果（行为 11）。

并行批（B-15）：``gather(..., return_exceptions=True)``——单失败降级为错误结果，
不拖垮整批；结果按原始调用顺序回填（B-16 的顺序语义）。
"""

from __future__ import annotations

import asyncio
import logging
import time

from pydantic import BaseModel, ValidationError

from questor.limen.gate import ToolCallInfo, decide, redact_output
from questor.schemas.model import PermissionMode
from questor.tools.base import Tool, ToolContext, ToolResult, resolve_tool_path
from questor.tools.registry import ToolCallRequest, ToolRegistry

logger = logging.getLogger(__name__)


class ToolCallOutcome:
    """一次调用的执行产物（engine 据此落 Item 与回喂对话）。"""

    def __init__(
        self,
        request: ToolCallRequest,
        result: ToolResult,
        *,
        denied: bool = False,
        unknown: bool = False,
        parallel: bool = False,
        elapsed_s: float = 0.0,
    ) -> None:
        self.request = request
        self.result = result
        self.denied = denied
        self.unknown = unknown
        self.parallel = parallel  # B-03：并行批的未知调用不清零熔断计数的依据
        self.elapsed_s = elapsed_s


async def execute_calls(
    requests: list[ToolCallRequest],
    registry: ToolRegistry,
    ctx: ToolContext,
    mode: PermissionMode,
    roots: list[str],
) -> list[ToolCallOutcome]:
    """执行一批（可能分多个分区的）调用；结果顺序与 requests 一致。"""
    from questor.tools.registry import partition_tool_calls

    batches = partition_tool_calls(requests, registry)
    by_id: dict[str, ToolCallOutcome] = {}
    for batch in batches:
        if batch.concurrent:
            outcomes = await asyncio.gather(
                *(_execute_one(r, registry, ctx, mode, roots) for r in batch.calls),
                return_exceptions=True,  # B-15：单失败降级，不拖垮整批
            )
            for request, outcome in zip(batch.calls, outcomes, strict=True):
                settled = _as_outcome(request, outcome)
                settled.parallel = batch.concurrent
                by_id[request.tool_use_id] = settled
        else:
            for request in batch.calls:
                by_id[request.tool_use_id] = await _execute_one(request, registry, ctx, mode, roots)
    return [by_id[r.tool_use_id] for r in requests]


def _as_outcome(
    request: ToolCallRequest, outcome: ToolCallOutcome | BaseException
) -> ToolCallOutcome:
    """并行批的单失败降级：异常转错误结果（B-15）。"""
    if isinstance(outcome, BaseException):
        logger.warning("工具 %s 并行执行异常", request.tool_name, exc_info=outcome)
        return ToolCallOutcome(
            request,
            ToolResult(output=f"tool {request.tool_name} crashed: {outcome!r}", is_error=True),
        )
    return outcome


async def _execute_one(
    request: ToolCallRequest,
    registry: ToolRegistry,
    ctx: ToolContext,
    mode: PermissionMode,
    roots: list[str],
) -> ToolCallOutcome:
    started = time.perf_counter()
    tool = registry.get(request.tool_name)

    if tool is None:
        # B-17：未知工具——executor 报告 unknown 事实，熔断计数由 engine 维护
        return ToolCallOutcome(
            request,
            ToolResult(output=f"unknown tool: {request.tool_name!r}", is_error=True),
            unknown=True,
            elapsed_s=time.perf_counter() - started,
        )
    if not registry.is_enabled(request.tool_name):
        # B-17：禁用 ≠ 未知——工具存在但被明确停用
        return ToolCallOutcome(
            request,
            ToolResult(
                output=f"tool {request.tool_name!r} is disabled in this session",
                is_error=True,
            ),
            elapsed_s=time.perf_counter() - started,
        )

    try:
        params = tool.params_model.model_validate(request.arguments)
    except ValidationError as exc:
        return ToolCallOutcome(
            request,
            ToolResult(
                output=f"invalid arguments for {request.tool_name}: {exc}",
                is_error=True,
            ),
            elapsed_s=time.perf_counter() - started,
        )

    call_info = _build_call_info(tool, params, ctx)
    decision = await asyncio.to_thread(decide, call_info, mode, roots)
    if decision.effect == "deny":
        assert decision.error_kind is not None
        return ToolCallOutcome(
            request,
            ToolResult(
                output=(
                    f"denied: {decision.reason} "
                    f"(error_kind={decision.error_kind}, "
                    f"model_next_action={decision.model_next_action!r})"
                ),
                is_error=True,
            ),
            denied=True,
            elapsed_s=time.perf_counter() - started,
        )

    try:
        result = await tool.execute(params, ctx)
    except Exception as exc:  # noqa: BLE001 —— 工具异常转错误结果回喂，不炸批次（行为 11）
        logger.warning("工具 %s 执行异常", tool.name, exc_info=exc)
        result = ToolResult(output=f"tool {tool.name} raised: {exc!r}", is_error=True)
    if decision.redact_output:
        result = ToolResult(
            output=redact_output(decision, result.output),
            is_error=result.is_error,
            data={**result.data, "redacted": True},
        )
    return ToolCallOutcome(request, result, elapsed_s=time.perf_counter() - started)


def _build_call_info(tool: Tool, params: BaseModel, ctx: ToolContext) -> ToolCallInfo:
    """从工具声明 + 已解析参数合成判定输入（工具自己不 import limen）。

    路径参数带缺省值的工具（search/list）在此填缺省——门之前填，B-31 只拦
    "真的没给路径"的调用。相对路径在此解析为绝对路径，让门的可达性推导
    看到规范输入。
    """
    raw_path = tool.declared_path(params)
    if raw_path is not None and tool.expects_path:
        raw_path = str(resolve_tool_path(ctx, raw_path))
    command = getattr(params, "command", None) if tool.kind == "shell" else None
    return ToolCallInfo(
        tool_name=tool.name,
        kind=tool.kind,
        mutates=tool.mutates_for(params),
        expects_path=tool.expects_path,
        path=raw_path,
        command=str(command) if command is not None else None,
    )
