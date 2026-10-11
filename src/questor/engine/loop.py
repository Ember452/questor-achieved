"""内置引擎循环：显式状态机（B-06），run 生命周期全经 gesta，事件双轨流出。

结构（方法各司一职，禁 1076 行巨型函数——FlowCoder core.py 的 `_run_loop` 反例）：
- :meth:`Engine.run_turn` —— 编排：建 turn/run → 迭代循环 → 终态；
- :meth:`_stream_once` —— 一次模型调用（delta 透出，聚合经 box 回传——async
  生成器不能带返回值，这是等价形式）；
- :meth:`_dispatch` —— 工具批执行 + Item/事件持久化 + 熔断计数（B-03）；
- :meth:`_budget_reason` —— 预算闸；收敛轮**保留只读工具**（B-02，Questor 对
  FlowCoder 撤光 schema 缺陷的修正）；
- ``_finish`` / ``_fail`` —— 终态两出口；取消经 CancelledError 清理（放行）。

已知边界（M2.2 留痕）：会话为 turn 作用域（跨 turn resume 随 M2.3 context）；
steered/waiting 旁态随 M3 habena；记忆观察（B-09）随 memory 模块；B-07 要求
子代理与交互路径共用本状态机——M2.2 无子代理，单一实现即满足。
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
        recovery = OutputRecoveryState()
        converging = False
        consecutive_unknown = 0
        total_turns = 0

        for iteration in range(1, self._max_iterations + 1):
            total_turns = iteration
            yield TurnStarted(turn=iteration)

            if not converging:
                reason = self._budget_reason(started)
                if reason is not None:
                    converging = True
                    yield Converging(reason=reason)
                    message = render("converge_message", reason=reason)
                    conversation.add_user(message)
                    await self._persist_message_item(writer, run.id, "user", message, injected=True)

            tools = self._tool_schemas(converging)  # B-02：收敛轮保留只读工具
            box: list[LLMResponse] = []
            async for event in self._stream_once(writer, run, conversation, tools, box):
                yield event
            response = box.pop()

            decision = handle_output_token_limit(response, conversation, self._model, recovery)
            recovery = decision.state
            if decision.retry:
                continue  # B-08：max_tokens 恢复轮（usage 已随 StreamEnd 记账）

            await self._persist_message_item(
                writer,
                run.id,
                "assistant",
                response.text,
                tool_calls=list(response.tool_calls),
            )

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

            outcomes = await execute_calls(
                [ToolCallRequest(tc.id, tc.name, dict(tc.arguments)) for tc in response.tool_calls],
                self._registry,
                self._ctx,
                self._mode,
                self._roots,
            )
            blocks: list[ToolResultBlock] = []
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
            consecutive_unknown = _advance_unknown_count(consecutive_unknown, outcomes)
            if consecutive_unknown >= C.UNKNOWN_TOOL_BREAKER:
                async for event in self._fail(
                    writer,
                    run,
                    f"too many consecutive unknown tool calls ({consecutive_unknown})",
                ):
                    yield event
                return
            conversation.add_tool_results(blocks)

        async for event in self._fail(
            writer, run, f"max iterations reached ({self._max_iterations})"
        ):
            yield event

    # ---- 一次模型调用（生成器 + box 回传聚合，等价于"yield 并返回"） ----

    async def _stream_once(
        self,
        writer: ThreadWriter,
        run: Run,
        conversation: Conversation,
        tools: list[dict[str, object]],
        box: list[LLMResponse],
    ) -> AsyncIterator[AgentEvent]:
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
            {"input_tokens": response.input_tokens, "output_tokens": response.output_tokens},
        )
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
        await self._persist_item(
            writer,
            Item(
                id=f"item-{uuid.uuid4().hex[:12]}",
                run_id=run.id,
                kind=ItemKind.TOOL_CALL,
                payload={
                    "tool_use_id": request.tool_use_id,
                    "name": request.tool_name,
                    "arguments": request.arguments,
                },
                created_at=utc_timestamp_now(),
            ),
        )
        output = outcome.result.output
        payload: dict[str, object] = {
            "tool_use_id": request.tool_use_id,
            "name": request.tool_name,
            "is_error": outcome.result.is_error,
            "elapsed_s": round(outcome.elapsed_s, 3),
            "preview": output[:2000],
        }
        if len(output) > C.TOOL_RESULT_SPILL_CHARS:
            spill = await asyncio.to_thread(_spill, writer, request.tool_use_id, output)
            payload["spilled"] = spill.file
            payload["truncated"] = spill.truncated
        yield ToolCallCompleted(
            tool_use_id=request.tool_use_id,
            name=request.tool_name,
            output=output,
            is_error=outcome.result.is_error,
            elapsed_s=outcome.elapsed_s,
        )
        await self._persist_item(
            writer,
            Item(
                id=f"item-{uuid.uuid4().hex[:12]}",
                run_id=run.id,
                kind=ItemKind.TOOL_RESULT,
                payload=payload,
                created_at=utc_timestamp_now(),
            ),
        )
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

    # ---- 预算与熔断 ----

    def _budget_reason(self, started: float) -> str | None:
        """止损（overview §10）：M2.2 只有时间维 + 迭代数（迭代数在 range 里）；
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

    async def _persist_message_item(
        self,
        writer: ThreadWriter,
        run_id: str,
        role: str,
        text: str,
        *,
        injected: bool = False,
        tool_calls: list | None = None,
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
