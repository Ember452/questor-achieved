"""max_tokens 触顶恢复（B-08）：两阶段——先提输出上限，再最多 N 次分段续写。

状态机（FlowCoder output_recovery.py 语义重写）：
- stop_reason 非 max_tokens → 恢复计数清零（正常轮不影响）；
- 首次触顶：把下一次调用的上限提到天花板（经 :attr:`RecoveryDecision.max_output_tokens`
  回传给循环，写进 `ModelRequest`——不在客户端里存可变状态，见 engine/model.py），
  半截回复 + 续写提示入对话，返回 retry；
- 已提过上限且次数未满：半截回复 + 分段续写提示，返回 retry；
- 次数耗尽：不再 retry，放任循环按正常流程走（模型自己收敛）。

恢复状态每 run 重置（`OutputRecoveryState` 每次 run 新建，B-08 的另一半）。
"""

from __future__ import annotations

from dataclasses import dataclass

from questor.engine import constants as C
from questor.engine.conversation import Conversation
from questor.engine.model import LLMResponse
from questor.prompts import render


@dataclass(frozen=True)
class OutputRecoveryState:
    max_tokens_escalated: bool = False
    recoveries: int = 0


@dataclass(frozen=True)
class RecoveryDecision:
    state: OutputRecoveryState
    retry: bool
    prompt: str | None = None
    #: 下一次调用要用的输出上限；None 表示沿用当前值不动
    max_output_tokens: int | None = None


def handle_output_token_limit(
    response: LLMResponse,
    conversation: Conversation,
    current_max_output_tokens: int,
    state: OutputRecoveryState,
) -> RecoveryDecision:
    """max_tokens 触顶的恢复裁决；非触顶轮清零计数并直通。

    ``current_max_output_tokens`` 由循环持有（预算的唯一真相在内核，不在客户端）。
    """
    if response.stop_reason != "max_tokens":
        return RecoveryDecision(state=OutputRecoveryState(), retry=False)

    if not state.max_tokens_escalated:
        new_state = OutputRecoveryState(max_tokens_escalated=True, recoveries=0)
        prompt = render("max_tokens_escalation")
        ceiling = max(current_max_output_tokens, C.MAX_TOKENS_CEILING)
    elif state.recoveries < C.MAX_OUTPUT_TOKEN_RECOVERIES:
        new_state = OutputRecoveryState(max_tokens_escalated=True, recoveries=state.recoveries + 1)
        prompt = render("max_tokens_recovery")
        ceiling = current_max_output_tokens
    else:
        return RecoveryDecision(state=state, retry=False)  # 次数耗尽，不再恢复

    conversation.add_user(prompt)
    return RecoveryDecision(state=new_state, retry=True, prompt=prompt, max_output_tokens=ceiling)
