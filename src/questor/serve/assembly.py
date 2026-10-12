"""装配点：把 providers + tools + context + prompts 组装成一个可跑的 Engine。

为什么住在 `serve` 而不是 `cli`：矩阵上 `cli` 只可 import `serve engine providers config
schemas`（structure §5），拿不到 `tools`/`context`/`prompts`/`workspaces`。这是刻意的——
**cli 是薄壳，一切能力经 serve**（overview §14「GUI 能力必须经协议可达」的同一规则也管
命令行），否则 CLI 会变成第二条特权路径，将来桌面壳要复刻它的装配代码。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from questor.context import ReplacementState
from questor.engine import Engine
from questor.engine.events import AgentEvent
from questor.engine.loop import TurnRequest
from questor.engine.model import ModelPort
from questor.prompts import system_assembly
from questor.schemas.model import PermissionMode
from questor.tools.base import ToolContext
from questor.tools.filestate import FileStateCache
from questor.tools.impl.registry_default import build_default_registry
from questor.tools.impl.todo import TodoStore
from questor.tools.processmgr import ProcessManager

__all__ = ["build_engine", "exec_turn", "project_rules_for"]

_PROJECT_RULES_FILES = ("AGENTS.md", "CLAUDE.md", ".cursorrules")


def project_rules_for(cwd: Path, *, limit: int = 40_000) -> str:
    """读目标仓库的指令文件作为**稳定** system 块（ADR-0018）。

    只取第一个命中的文件并截断到 `limit`：多文件叠加会让"稳定前缀"的定义漂移，
    而超长指令文件本身就该被 Layer1 的预算管住（不在这里悄悄塞进上下文）。
    """
    for name in _PROJECT_RULES_FILES:
        candidate = cwd / name
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                continue
            return text[:limit]
    return ""


def build_engine(
    *,
    model: ModelPort,
    cwd: str,
    mode: PermissionMode = PermissionMode.STANDARD,
    roots: list[str] | None = None,
    project_rules: str | None = None,
    environment: str | None = None,
    replacements: ReplacementState | None = None,
) -> Engine:
    """一个线程一个 Engine：工具环境、system 装配与替换状态都在这里一次接好。"""
    workdir = Path(cwd).expanduser().resolve()
    return Engine(
        model=model,
        registry=build_default_registry(),
        ctx=ToolContext(
            cwd=str(workdir),
            file_state=FileStateCache(),
            processes=ProcessManager(),
            todos=TodoStore(),
        ),
        mode=mode,
        roots=[str(root) for root in (roots or [str(workdir)])],
        prompt=system_assembly(
            project_rules=(
                project_rules if project_rules is not None else project_rules_for(workdir)
            ),
            environment=environment or f"cwd={workdir}",
        ),
        replacements=replacements,
    )


async def exec_turn(
    engine: Engine, *, thread_id: str, user_text: str, resume: bool = False
) -> AsyncIterator[AgentEvent]:
    """跑一轮并透传事件（cli 打印、测试断言、serve 通知都消费同一股流）。"""
    async for event in engine.run_turn(
        TurnRequest(thread_id=thread_id, user_text=user_text, resume=resume)
    ):
        yield event
