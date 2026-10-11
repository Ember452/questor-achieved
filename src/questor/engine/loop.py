"""内置引擎循环：显式状态机（B-06），run 生命周期全经 gesta，事件双轨流出。

结构（方法各司一职，禁 1076 行巨型函数——FlowCoder core.py 的 `_run_loop` 反例；
护栏 tests/unit/test_engine_shape.py 机械保证单函数 ≤60 行、阈值常量只住 constants）：
- :meth:`Engine.run_turn` —— 编排：建 turn/run → 迭代循环 → 终态；
- :meth:`Engine._stream_once` —— 一次模型调用（delta 透出，聚合经 box 回传——async
  生成器不能带返回值，这是等价形式）；
- :meth:`Engine._dispatch` —— 工具批执行 + Item/事件持久化 + 熔断计数（B-03）；
- :meth:`Engine._maybe_converge` —— 预算闸；收敛轮**保留只读工具**（B-02，Questor 对
  FlowCoder 撤光 schema 缺陷的修正）；
- ``_finish`` / ``_fail`` —— 终态两出口；取消经 CancelledError 清理（放行）。

已知边界（M2.2 留痕）：会话为 turn 作用域（跨 turn resume 随 M2.3 context）；
steered/waiting 旁态随 M3 habena；记忆观察（B-09）随 memory 模块；B-07 要求
子代理与交互路径共用本状态机——M2.2 无子代理，单一实现即满足。

# Reimplements FlowCoder@flowcoder agent/core.py（语义与形状，未搬代码）— B-02 B-03 B-05 B-06
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import Any

from questor.engine import constants as C
from questor.engine.conversation import Conversation, ToolResultBlock
from questor.engine.events import (
    AgentEvent,
    Converging,
    Delta,
    LoopCompleted,
    LoopFailed,
    RunStatus,
    ToolCallCompleted,
    ToolCallStarted,
    TurnStarted,
    Usage,
)
from questor.engine.model import (
    LLMResponse,
    ModelPort,
    StreamDelta,
    StreamEnd,
    StreamToolCall,
    ToolCall,
)
from questor.engine.output_recovery import OutputRecoveryState, handle_output_token_limit
from questor.gesta.transitions import InvalidTransition
from questor.gesta.writer import ThreadWriter
from questor.prompts import render
from questor.schemas.model import (
    Item,
    ItemKind,
    Origin,
    PermissionMode,
    Run,
    utc_timestamp_now,
)
from questor.schemas.model import (
    RunStatus as RS,
)
from questor.tools.base import ToolContext
from questor.tools.executor import ToolCallOutcome, execute_calls
from questor.tools.registry import ToolCallRequest, ToolRegistry


@dataclass(frozen=True)
class TurnRequest:
    thread_id: str
    user_text: str


class Engine:
    """单轮内核：一个实例持有一组不可变协作件；run_turn 可被顺序调用。"""

    def __init__(
        self,
        *,
        model: ModelPort,
        registry: ToolRegistry,
        ctx: ToolContext,
        mode: PermissionMode,
        roots: list[str],
        engine_id: str = "questor-engine",
        max_iterations: int = C.MAX_ITERATIONS,
        max_seconds: float | None = None,
        lock_timeout: float = C.LOCK_TIMEOUT_S,
    ) -> None:
        self._model = model
        self._registry = registry
        self._ctx = ctx
        self._mode = mode
        self._roots = roots
        self._engine_id = engine_id
        self._max_iterations = max_iterations
        self._max_seconds = max_seconds
        self._lock_timeout = lock_timeout

    # ---- 编排入口 ----

    async def run_turn(self, request: TurnRequest) -> AsyncGenerator[AgentEvent, None]:
        """执行一轮 turn：用户输入 → 模型/工具循环 → 终态；事件与落盘双轨。"""
        writer = ThreadWriter(request.thread_id, lock_timeout=self._lock_timeout)
        await asyncio.to_thread(writer.open)
        turn = await asyncio.to_thread(
            writer.add_turn,
            turn_id=f"turn-{uuid.uuid4().hex[:12]}",
            origin=Origin.USER,
            created_at=utc_timestamp_now(),
        )
        run = await asyncio.to_thread(
            writer.add_run,
            Run(
                id=f"run-{uuid.uuid4().hex[:12]}",
                turn_id=turn.id,
                engine_id=self._engine_id,
                permission_mode=self._mode,
                status=RS.QUEUED,
                created_at=utc_timestamp_now(),
            ),
        )
        conversation = Conversation()
        await self._persist_message_item(writer, run.id, "user", request.user_text)
        conversation.add_user(request.user_text)

        try:
            async for event in self._loop(writer, run, conversation):
                yield event
        except asyncio.CancelledError:
            await self._cancel_cleanup(writer, run)
            raise

    # ---- 状态迁移（迁移记录 + run/status 事件同批落盘） ----

    async def _transition(self, writer: ThreadWriter, run: Run, target: RS) -> None:
        await asyncio.to_thread(writer.transition_run, run.id, target)
        await self._persist_event(writer, run, "run/status", {"status": target.value})

    # ---- 迭代循环 ----

    async def _loop(
        self,
        writer: ThreadWriter,
        run: Run,
        conversation: Conversation,
    ) -> AsyncIterator[AgentEvent]:
        await self._transition(writer, run, RS.RUNNING)
        yield RunStatus(status=RS.RUNNING.value)

        started = time.monotonic()
        recovery: list[OutputRecoveryState] = [OutputRecoveryState()]
        converging = False
        unknown: list[int] = [0]  # 熔断计数（可变容器传引用，B-03：并行批不清零）
        total_turns = 0

        for iteration in range(1, self._max_iterations + 1):
            total_turns = iteration
            yield TurnStarted(turn=iteration)

            if not converging:
                async for event in self._maybe_converge(writer, run, conversation, started):
                    yield event
                    if isinstance(event, Converging):
                        converging = True

            tools = self._tool_schemas(converging)  # B-02：收敛轮保留只读工具
            box: list[LLMResponse] = []
            async for event in self._stream_once(writer, run, conversation, tools, box, recovery):
                yield event
            response = box.pop()

            await self._persist_assistant_message(writer, run.id, response)

            if not response.tool_calls:
                async for event in self._finish(writer, run, total_turns, response.text):
                    yield event
                return

            if converging:
                # B-02 的另一半：收敛轮仍幻觉出工具调用 → 强制结束
                async for event in self._fail(
                    writer, run, "budget converged but the model requested tools"
                ):
                    yield event
                return

            blocks: list[ToolResultBlock] = []
            async for event in self._dispatch(writer, run, response, blocks, unknown):
                yield event
            if unknown[0] >= C.UNKNOWN_TOOL_BREAKER:
                async for event in self._fail(
                    writer, run, "too many consecutive unknown tool calls"
                ):
                    yield event
                return
            conversation.add_tool_results(blocks)

        async for event in self._fail(
            writer, run, f"max iterations reached ({self._max_iterations})"
        ):
            yield event

    async def _maybe_converge(
        self,
        writer: ThreadWriter,
        run: Run,
        conversation: Conversation,
        started: float,
    ) -> AsyncIterator[AgentEvent]:
        """预算闸（B-02）：触限注入收敛请求；未触限是无事件的无操作。"""
        reason = self._budget_reason(started)
        if reason is None:
            return
        yield Converging(reason=reason)
        message = render("converge_message", reason=reason)
        conversation.add_user(message)
        await self._persist_message_item(writer, run.id, "user", message, injected=True)

    async def _dispatch(
        self,
        writer: ThreadWriter,
        run: Run,
        response: LLMResponse,
        blocks: list[ToolResultBlock],
        unknown: list[int],
    ) -> AsyncIterator[AgentEvent]:
        """执行工具批并持久化（B-15/16）；熔断计数经可变容器回传（B-03：并行批不清零）。"""
        outcomes = await execute_calls(
            [ToolCallRequest(tc.id, tc.name, dict(tc.arguments)) for tc in response.tool_calls],
            self._registry,
            self._ctx,
            self._mode,
            self._roots,
        )
        for outcome in outcomes:
            async for event in self._persist_outcome(writer, run, outcome):
                yield event
            blocks.append(
                ToolResultBlock(
                    tool_use_id=outcome.request.tool_use_id,
                    content=outcome.result.output[-40_000:],
                    is_error=outcome.result.is_error,
                )
            )
        unknown[0] = _advance_unknown_count(unknown[0], outcomes)

    # ---- 一次模型调用（生成器 + box 回传聚合，等价于"yield 并返回"） ----

    async def _stream_once(
        self,
        writer: ThreadWriter,
        run: Run,
        conversation: Conversation,
        tools: list[dict[str, object]],
        box: list[LLMResponse],
        recovery: list[OutputRecoveryState],
    ) -> AsyncIterator[AgentEvent]:
        """一次模型调用（含 B-08 max_tokens 恢复循环：提上限一次 + 最多 3 次分段续写）。"""
        while True:
            system = render("system_core")
            text_parts: list[str] = []
            calls: list[ToolCall] = []
            usage = (0, 0)
            stop_reason = "end_turn"

            async for event in self._model.stream(conversation.history, system, tools):
                if isinstance(event, StreamDelta):
                    yield Delta(text=event.text)
                    text_parts.append(event.text)
                elif isinstance(event, StreamToolCall):
                    calls.append(event.call)
                elif isinstance(event, StreamEnd):
                    usage = (event.input_tokens, event.output_tokens)
                    stop_reason = event.stop_reason

            response = LLMResponse(
                text="".join(text_parts),
                tool_calls=tuple(calls),
                stop_reason=stop_reason,
                input_tokens=usage[0],
                output_tokens=usage[1],
            )
            conversation.record_usage_anchor(response.input_tokens, response.output_tokens)
            yield Usage(input_tokens=response.input_tokens, output_tokens=response.output_tokens)
            await self._persist_event(
                writer,
                run,
                "turn/usage",
                {
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                },
            )
            decision = handle_output_token_limit(response, conversation, self._model, recovery[0])
            recovery[0] = decision.state
            if not decision.retry:
                break  # 恢复轮已在上方注入续写提示，重流一次
        box.append(response)

    # ---- 工具批持久化 ----

    async def _persist_outcome(
        self, writer: ThreadWriter, run: Run, outcome: ToolCallOutcome
    ) -> AsyncIterator[AgentEvent]:
        request = outcome.request
        yield ToolCallStarted(
            tool_use_id=request.tool_use_id,
            name=request.tool_name,
            arguments=request.arguments,
        )
        await self._persist_item(writer, _tool_call_item(run, request))
        output = outcome.result.output
        spill = await self._maybe_spill(writer, request.tool_use_id, output)
        payload = _tool_result_payload(outcome, spill)
        yield ToolCallCompleted(
            tool_use_id=request.tool_use_id,
            name=request.tool_name,
            output=output,
            is_error=outcome.result.is_error,
            elapsed_s=outcome.elapsed_s,
        )
        await self._persist_item(writer, _tool_result_item(run, request, payload))
        for event_type, event_payload in (
            ("item/started", {"tool_use_id": request.tool_use_id, "name": request.tool_name}),
            (
                "item/completed",
                {
                    "tool_use_id": request.tool_use_id,
                    "name": request.tool_name,
                    "is_error": outcome.result.is_error,
                },
            ),
        ):
            await self._persist_event(writer, run, event_type, event_payload)

    async def _maybe_spill(
        self, writer: ThreadWriter, tool_use_id: str, output: str
    ) -> tuple[str | None, bool]:
        """超限结果落盘（B-24 语义）；未超限返回 (None, False)。"""
        if len(output) <= C.TOOL_RESULT_SPILL_CHARS:
            return None, False
        spill = await asyncio.to_thread(_spill, writer, tool_use_id, output)
        return spill.file, spill.truncated

    # ---- 终态与清理 ----

    async def _finish(
        self, writer: ThreadWriter, run: Run, total_turns: int, final_text: str
    ) -> AsyncIterator[AgentEvent]:
        await self._transition(writer, run, RS.COMPLETED)
        yield RunStatus(status=RS.COMPLETED.value)
        yield LoopCompleted(total_turns=total_turns, final_text=final_text)

    async def _fail(
        self, writer: ThreadWriter, run: Run, message: str
    ) -> AsyncIterator[AgentEvent]:
        await self._transition(writer, run, RS.FAILED)
        yield RunStatus(status=RS.FAILED.value)
        yield LoopFailed(message=message)

    async def _cancel_cleanup(self, writer: ThreadWriter, run: Run) -> None:
        """取消传播：停进程树 → cancelled 终态；清理失败不掩盖 CancelledError。"""
        import contextlib  # noqa: PLC0415

        for process in self._ctx.processes.list():
            with contextlib.suppress(Exception):  # 清理尽力而为
                self._ctx.processes.stop(process.process_id)
        # cancelled 迁移可能因终态已定而失败——那正是合法情形
        with contextlib.suppress(InvalidTransition):
            await self._transition(writer, run, RS.CANCELLED)

    # ---- 预算与工具集 ----

    def _budget_reason(self, started: float) -> str | None:
        """止损（overview §10）：M2.2 只有时间维（迭代数在 range 里）；
        token/成本维随 M2.3 providers 的真实用量累计接入。"""
        if self._max_seconds is not None and time.monotonic() - started > self._max_seconds:
            return f"time budget exceeded ({self._max_seconds:.0f}s)"
        return None

    def _tool_schemas(self, converging: bool) -> list[dict[str, object]]:
        """B-02：收敛轮保留只读工具（FlowCoder 撤光 schema 导致零产出强杀）。"""
        if not converging:
            return self._registry.schemas()
        readonly: list[dict[str, object]] = []
        for schema in self._registry.schemas():
            tool = self._registry.get(str(schema["name"]))
            if tool is not None and not tool.mutates:
                readonly.append(schema)
        return readonly

    # ---- 持久化助手 ----

    async def _persist_item(self, writer: ThreadWriter, item: Item) -> None:
        await asyncio.to_thread(writer.add_item, item)

    async def _persist_assistant_message(
        self, writer: ThreadWriter, run_id: str, response: LLMResponse
    ) -> None:
        """assistant 回复（含工具调用意图）作为 message Item 落盘。"""
        await self._persist_message_item(
            writer,
            run_id,
            "assistant",
            response.text,
            tool_calls=list(response.tool_calls),
        )

    async def _persist_message_item(
        self,
        writer: ThreadWriter,
        run_id: str,
        role: str,
        text: str,
        *,
        injected: bool = False,
        tool_calls: list[ToolCall] | None = None,
    ) -> None:
        payload: dict[str, object] = {"role": role, "text": text}
        if injected:
            payload["injected"] = True
        if tool_calls:
            payload["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in tool_calls
            ]
        await self._persist_item(
            writer,
            Item(
                id=f"item-{uuid.uuid4().hex[:12]}",
                run_id=run_id,
                kind=ItemKind.MESSAGE,
                payload=payload,
                created_at=utc_timestamp_now(),
            ),
        )

    async def _persist_event(
        self, writer: ThreadWriter, run: Run, event_type: str, payload: dict[str, Any]
    ) -> None:
        await asyncio.to_thread(
            writer.append_event,
            event_type=event_type,
            run_id=run.id,
            turn_id=run.turn_id,
            payload=payload,
            created_at=utc_timestamp_now(),
        )


# ---- 模块级纯函数（不经 self，便于直测） ----


def _tool_call_item(run: Run, request: ToolCallRequest) -> Item:
    return Item(
        id=f"item-{uuid.uuid4().hex[:12]}",
        run_id=run.id,
        kind=ItemKind.TOOL_CALL,
        payload={
            "tool_use_id": request.tool_use_id,
            "name": request.tool_name,
            "arguments": request.arguments,
        },
        created_at=utc_timestamp_now(),
    )


def _tool_result_payload(
    outcome: ToolCallOutcome, spill: tuple[str | None, bool]
) -> dict[str, object]:
    output = outcome.result.output
    spill_file, truncated = spill
    payload: dict[str, object] = {
        "tool_use_id": outcome.request.tool_use_id,
        "name": outcome.request.tool_name,
        "is_error": outcome.result.is_error,
        "elapsed_s": round(outcome.elapsed_s, 3),
        "preview": output[:2000],
        **outcome.result.data,  # 语义退出码 / sandboxed 标注 / 后台 pid 等进审计记录
    }
    if spill_file is not None:
        payload["spilled"] = spill_file
        payload["truncated"] = truncated
    return payload


def _tool_result_item(run: Run, request: ToolCallRequest, payload: dict[str, object]) -> Item:
    return Item(
        id=f"item-{uuid.uuid4().hex[:12]}",
        run_id=run.id,
        kind=ItemKind.TOOL_RESULT,
        payload=payload,
        created_at=utc_timestamp_now(),
    )


def _advance_unknown_count(current: int, outcomes: list[ToolCallOutcome]) -> int:
    """B-03：未知调用累加；并行批**不清零**；只有串行已知成功才清零。"""
    count = current
    for outcome in outcomes:
        if outcome.unknown:
            count += 1
        elif not outcome.parallel and not outcome.result.is_error:
            count = 0
    return count


def _spill(writer: ThreadWriter, tool_use_id: str, output: str):
    """工具结果超限落盘（B-24 语义经 gesta 的 O_EXCL 幂等写）。"""
    from questor.gesta import spill_tool_result

    return spill_tool_result(writer.thread_id, tool_use_id, output)
