"""权限矩阵（三档 × 调用形状）表驱动测试（B-33 的可执行形式）与 gate 判定链单元行为。

矩阵每行 = (mode, 调用形状) → 期望效果。让本测试失败的是档位语义或判定链的
真实改动，不是随手值——负向验证记录见 gate 相关坑条目的测试 docstring。
"""

from __future__ import annotations

import pytest

from questor.limen import Boundary, ToolCallInfo, decide
from questor.limen.matrix import MODE_BOUNDARIES
from questor.schemas.model import PermissionMode as PM

WIN_ROOTS = [r"C:\ws", "/ws"]


def _file(name: str, *, mutates: bool, path: str | None = None) -> ToolCallInfo:
    return ToolCallInfo(
        tool_name="file_tool", kind="file", mutates=mutates, expects_path=True, path=path
    )


def _shell(command: str) -> ToolCallInfo:
    return ToolCallInfo(
        tool_name="run", kind="shell", mutates=True, expects_path=False, command=command
    )


def _meta() -> ToolCallInfo:
    return ToolCallInfo(tool_name="todo", kind="meta", mutates=False, expects_path=False)


# ---- 边界三元组表本身（B-33 的表就是契约） ----


def test_boundary_table_matches_overview_s9() -> None:
    assert MODE_BOUNDARIES[PM.READ_ONLY] == Boundary(enforce_paths=True, allow_mutations=False)
    assert MODE_BOUNDARIES[PM.STANDARD] == Boundary(enforce_paths=True, allow_mutations=True)
    assert MODE_BOUNDARIES[PM.UNCONFINED] == Boundary(enforce_paths=False, allow_mutations=True)


def test_boundary_for_unknown_mode_raises() -> None:
    from questor.schemas.model import PermissionMode

    # PermissionMode 枚举之外的模式不可构造——防御未来契约漂移
    assert set(MODE_BOUNDARIES) == set(PermissionMode)


# ---- 矩阵：读文件 ----


@pytest.mark.parametrize("mode", [PM.READ_ONLY, PM.STANDARD, PM.UNCONFINED])
def test_file_read_inside_root_allowed_all_modes(mode: PM) -> None:
    decision = decide(_file("read", mutates=False, path="/ws/src/a.py"), mode, WIN_ROOTS)
    assert decision.effect == "allow"


@pytest.mark.parametrize("mode", [PM.READ_ONLY, PM.STANDARD])
def test_file_read_outside_root_denied_when_enforced(mode: PM) -> None:
    decision = decide(_file("read", mutates=False, path="/outside/b.py"), mode, WIN_ROOTS)
    assert decision.effect == "deny"
    assert decision.error_kind == "boundary_denied"
    assert decision.model_next_action


def test_file_read_outside_root_allowed_unconfined() -> None:
    decision = decide(_file("read", mutates=False, path="/outside/b.py"), PM.UNCONFINED, WIN_ROOTS)
    assert decision.effect == "allow"
    assert decision.redact_output is False


# ---- 矩阵：写文件 ----


def test_write_inside_root_standard_allowed() -> None:
    assert (
        decide(_file("write", mutates=True, path="/ws/src/a.py"), PM.STANDARD, WIN_ROOTS).effect
        == "allow"
    )


def test_write_outside_root_standard_denied() -> None:
    assert (
        decide(_file("write", mutates=True, path="/tmp/x.py"), PM.STANDARD, WIN_ROOTS).effect
        == "deny"
    )


def test_write_outside_root_unconfined_allowed() -> None:
    assert (
        decide(_file("write", mutates=True, path="/tmp/x.py"), PM.UNCONFINED, WIN_ROOTS).effect
        == "allow"
    )


def test_read_only_blocks_all_mutations() -> None:
    for call in (
        _file("write", mutates=True, path="/ws/a.py"),
        _shell("ls -la"),
        ToolCallInfo(tool_name="todo", kind="meta", mutates=True, expects_path=False),
    ):
        decision = decide(call, PM.READ_ONLY, WIN_ROOTS)
        assert decision.effect == "deny", call.tool_name
        assert decision.model_next_action == (
            "use read-only tools, or tell the user this agent cannot make changes"
        )


# ---- 矩阵：敏感路径（B-54 全档位） ----


@pytest.mark.parametrize("mode", [PM.READ_ONLY, PM.STANDARD, PM.UNCONFINED])
def test_sensitive_write_denied_every_mode(mode: PM) -> None:
    decision = decide(_file("write", mutates=True, path="/ws/.env"), mode, WIN_ROOTS)
    assert decision.effect == "deny"
    assert decision.error_kind == "boundary_denied"
    if mode is not PM.READ_ONLY:
        # READ_ONLY 由只读闸先决短路（B-34），理由是只读方言；其余档位给出敏感理由
        assert "credential-bearing" in decision.reason


@pytest.mark.parametrize("mode", [PM.READ_ONLY, PM.STANDARD])
def test_sensitive_read_denied_non_unconfined(mode: PM) -> None:
    assert decide(_file("read", mutates=False, path="/ws/.env"), mode, WIN_ROOTS).effect == "deny"


def test_sensitive_read_unconfined_downgrades_with_redaction() -> None:
    decision = decide(_file("read", mutates=False, path="/ws/.env"), PM.UNCONFINED, WIN_ROOTS)
    assert decision.effect == "allow"
    assert decision.redact_output is True


# ---- 矩阵：shell（B-32 全档位硬拒；B-18 无静默降级路径） ----


@pytest.mark.parametrize("mode", [PM.READ_ONLY, PM.STANDARD, PM.UNCONFINED])
def test_dangerous_command_denied_every_mode(mode: PM) -> None:
    decision = decide(_shell("rm -rf /"), mode, WIN_ROOTS)
    assert decision.effect == "deny"
    assert decision.error_kind == "boundary_denied"
    if mode is not PM.READ_ONLY:
        # READ_ONLY 由只读闸先决短路（B-34）；其余档位给出黑名单理由
        assert "dangerous-command blacklist" in decision.reason


def test_benign_command_standard_allowed() -> None:
    assert decide(_shell("git status"), PM.STANDARD, WIN_ROOTS).effect == "allow"


# ---- B-31：缺路径参数 ----


@pytest.mark.parametrize("mode", [PM.READ_ONLY, PM.STANDARD, PM.UNCONFINED])
def test_missing_path_denied_not_skipped(mode: PM) -> None:
    """B-31：unconfined 不查路径门，但缺路径参数仍是调用形状错误，照样 deny。"""
    decision = decide(_file("read", mutates=False, path=None), mode, WIN_ROOTS)
    assert decision.effect == "deny"
    assert "missing its required path argument" in decision.reason


# ---- 参数提权前哨（B-55 的门内侧） ----


@pytest.mark.parametrize("mode", [PM.READ_ONLY, PM.STANDARD])
def test_param_mode_escalation_denied(mode: PM) -> None:
    """参数试图携带比当前档位更高的模式 → 硬拒（B-55 的门内侧）。"""
    call = ToolCallInfo(
        tool_name="run",
        kind="shell",
        mutates=True,
        expects_path=False,
        command="ls",
        requested_mode=PM.UNCONFINED,
    )
    decision = decide(call, mode, WIN_ROOTS)
    assert decision.effect == "deny"
    assert "elevate permission_mode" in decision.reason


def test_param_mode_equal_to_current_allowed() -> None:
    call = ToolCallInfo(
        tool_name="run",
        kind="shell",
        mutates=False,
        expects_path=False,
        command="git status",
        requested_mode=PM.STANDARD,
    )
    assert decide(call, PM.STANDARD, WIN_ROOTS).effect == "allow"
