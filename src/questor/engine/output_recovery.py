"""max_tokens 触顶恢复（B-08）：两阶段——先提输出上限，再最多 N 次分段续写。

状态机（FlowCoder output_recovery.py 语义重写）：
- stop_reason 非 max_tokens → 恢复计数清零（正常轮不影响）；
- 首次触顶：经 ModelPort.set_max_output_tokens 提到天花板，半截回复 + 续写提示
  入对话，返回 retry；
- 已提过上限且次数未满：半截回复 + 分段续写提示，返回 retry；
- 次数耗尽：不再 retry，放任循环按正常流程走（模型自己收敛）。

恢复状态每 run 重置（OutputRecoveryState 每次 run 新建，B-08 的另一半）。
"""

from __future__ import annotations

from dataclasses import dataclass

from questor.engine.constants import MAX_OUTPUT_TOKEN_RECOVERIES, MAX_TOKENS_CEILING
from questor.engine.conversation import Conversation
from questor.engine.model import LLMResponse, ModelPort

ESCALATION_PROMPT = (
    "Output token limit hit. Resume directly from where you stopped. "
    "Do not apologize and do not repeat previous content."
)
RECOVERY_PROMPT = (
    "Output token limit hit again. Continue with smaller pieces and finish the current piece first."
)


@dataclass(frozen=True)
class OutputRecoveryState:
    max_tokens_escalated: bool = False
    recoveries: int = 0


@dataclass(frozen=True)
class RecoveryDecision:
    state: OutputRecoveryState
    retry: bool
    prompt: str | None = None


def handle_output_token_limit(
    response: LLMResponse,
    conversation: Conversation,
    model: ModelPort,
    state: OutputRecoveryState,
) -> RecoveryDecision:
    """max_tokens 触顶的恢复裁决；非触顶轮清零计数并直通。"""
    if response.stop_reason != "max_tokens":
        return RecoveryDecision(state=OutputRecoveryState(), retry=False)

    if not state.max_tokens_escalated:
        model.set_max_output_tokens(MAX_TOKENS_CEILING)
        new_state = OutputRecoveryState(max_tokens_escalated=True, recoveries=0)
        prompt = ESCALATION_PROMPT
    elif state.recoveries < MAX_OUTPUT_TOKEN_RECOVERIES:
        new_state = OutputRecoveryState(max_tokens_escalated=True, recoveries=state.recoveries + 1)
        prompt = RECOVERY_PROMPT
    else:
        return RecoveryDecision(state=state, retry=False)  # 次数耗尽，不再恢复

    conversation.add_user(prompt)
    return RecoveryDecision(state=new_state, retry=True, prompt=prompt)
