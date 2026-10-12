"""编排门单测（B-43：返回结构化载荷而非异常，模型可读可重试）。"""

from __future__ import annotations

from questor.orchestration.gate import evaluate


def test_create_task_without_plan_needs_plan_first() -> None:
    result = evaluate("create_task", has_plan=False)
    assert result.allowed is False
    payload = result.payload()
    assert payload["error_code"] == "need_plan_first"
    assert payload["hint"]  # 指导下一步动作，不只是"不行"


def test_create_task_with_plan_allowed() -> None:
    assert evaluate("create_task", has_plan=True).allowed is True
    assert evaluate("create_task", has_plan=True).payload() == {}


def test_start_execution_without_authorization_denied() -> None:
    result = evaluate("start_execution", has_plan=True, authorized=False)
    assert result.allowed is False
    assert result.payload()["error_code"] == "need_execution_authorization"


def test_start_execution_with_authorization_allowed() -> None:
    assert evaluate("start_execution", has_plan=True, authorized=True).allowed is True


def test_redundant_setup_denied_after_sync() -> None:
    result = evaluate("create_task_batch", has_plan=True, plan_subtasks_synced=True)
    assert result.allowed is False
    assert result.payload()["error_code"] == "plan_subtasks_already_synced"


def test_unrestricted_action_passes() -> None:
    assert evaluate("anything_else", has_plan=False, authorized=False).allowed is True
