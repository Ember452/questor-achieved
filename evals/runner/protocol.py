"""对照评测的被测者插拔协议（Questor evals runner 的接口层）。

被测者抽象为 FlowCoder `eval/models.py` 同构的三协议（2026-10-11 实测摘录）：

- `Solver.start() -> SolverSession`，`SolverSession.ask(prompt) -> AgentSolution`——
  Questor agent 与 FlowCoder agent 各写一个 adapter，同一任务喂两个 solver；
- `Executor.run_test(files, timeout_s) -> ExecutionOutcome`——沙箱/宿主执行统一入口；
- `Grader` 按 task.grading 类型核验产出，返回 `Verification{passed, reason, evidence}`。

失败语义对齐 FlowCoder `failure_tax.py` 的四分类（见 failure_tax.py）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class AgentSolution:
    """一次 ask 的最终产出与用量。"""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    turns: int = 0
    error: str | None = None


@runtime_checkable
class SolverSession(Protocol):
    async def ask(self, prompt: str) -> AgentSolution: ...


@runtime_checkable
class Solver(Protocol):
    """被测者工厂：k-sample 时每次 start() 新建会话，不共享可变状态。"""

    def start(self) -> SolverSession: ...


@dataclass(frozen=True)
class ExecutionOutcome:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


@runtime_checkable
class Executor(Protocol):
    async def run_test(self, files: Mapping[str, str], timeout_s: float) -> ExecutionOutcome: ...


@dataclass
class Verification:
    passed: bool
    reason: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    # evidence 条目形状：{"check": str, "expected": Any, "observed": Any}
