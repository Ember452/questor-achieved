"""limen 门链定序与审批/授权语义（Phase 2a 批次 2a；B-50/51/52/55/56/130/131/132）。

蓝本：wuu ``internal/tools/toolkit.go::checkPermission``（L112-146）、
``internal/tools/review.go::reviewToolCall``（L36-64）、
``internal/approvefor/review.go``、``internal/tools/authorization.go``、
``internal/tools/boundary.go``。

本文件的重心不是"结果对不对"，而是**顺序与默认分支**：
门链顺序写反（Authorizer 跑到 boundary 前、Reviewer 排在 Authorizer 后）与
"非 deny 即允许"的默认放行，都能让逐条结果测试全绿而在真实链上失效。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from questor.limen.approval import (
    ApprovalRequest,
    ReviewBlocked,
    hard_deny_reason,
    needs_review,
    sensitive_path_reason,
)
from questor.limen.authorizer import (
    AuthorizationDecision,
    AuthorizationDenied,
    AuthorizationRequest,
    enforce_authorizer,
)
from questor.limen.boundary import (
    BoundaryDenied,
    ToolMeta,
    mutates,
    read_only_boundary,
    standard_boundary,
    unconfined_boundary,
)
from questor.limen.chain import PermissionChain, PermissionContext
from questor.limen.sensitive import classify
from questor.schemas.model import PermissionMode, ToolKind


class Recorder:
    """记录每层是否被调用、以何顺序 —— 定序断言的唯一可靠手段（只看结果看不出顺序）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def hook(self, ctx: PermissionContext, info: ToolMeta, arguments: dict[str, Any]) -> None:
        self.calls.append("hook")

    def reviewer(self, request: ApprovalRequest) -> Any:
        self.calls.append("reviewer")
        return _decision("allow")

    def authorizer(self, request: AuthorizationRequest) -> AuthorizationDecision:
        self.calls.append("authorizer")
        return AuthorizationDecision(outcome="allow")


def _decision(outcome: str, reason: str = "理由") -> Any:
    from questor.limen.approval import ApprovalDecision

    return ApprovalDecision(outcome=outcome, reason=reason)


class _Reviewer:
    def __init__(self, recorder: Recorder | None, outcome: str) -> None:
        self._recorder = recorder
        self._outcome = outcome

    def review(self, request: ApprovalRequest) -> Any:
        if self._recorder is not None:
            self._recorder.calls.append("reviewer")
        if self._outcome == "boom":
            raise RuntimeError("审批通道炸了")
        return _decision(self._outcome)


class _Authorizer:
    def __init__(self, recorder: Recorder | None, outcome: str, raises: bool) -> None:
        self._recorder = recorder
        self._outcome = outcome
        self._raises = raises

    def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision:
        if self._recorder is not None:
            self._recorder.calls.append("authorizer")
        if self._raises:
            raise TimeoutError("provider 挂了")
        return AuthorizationDecision(outcome=self._outcome, reason="r")


def _chain(**kwargs: Any) -> PermissionChain:
    defaults: dict[str, Any] = {
        "boundary": standard_boundary(),
        "mode": PermissionMode.STANDARD,
        "approve_for_me": False,
    }
    defaults.update(kwargs)
    return PermissionChain(**defaults)


_WRITE = ToolMeta(name="write_file", kind="file")
_SHELL = ToolMeta(name="bash", kind="shell")


# ------------------------------------------------------------------ 定序（B-130）


def test_chain_runs_hook_then_boundary_then_reviewer_then_authorizer() -> None:
    """链的顺序必须是 hook → boundary → Reviewer → Authorizer，且各一次。"""
    recorder = Recorder()
    guard_calls: list[str] = []

    class _PathGuard:
        def check(self, info: ToolMeta, arguments: dict[str, Any]) -> None:
            recorder.calls.append("boundary")
            guard_calls.append(info.name)

    chain = _chain(
        boundary=standard_boundary(_PathGuard()),
        hook=recorder.hook,
        reviewer=_Reviewer(recorder, "allow"),
        approve_for_me=True,
        authorizer=_Authorizer(recorder, "allow", raises=False),
    )
    chain.check(PermissionContext(), _SHELL, {"command": "ls"}, call_id="c1")
    assert recorder.calls == ["hook", "boundary", "reviewer", "authorizer"], recorder.calls
    assert guard_calls == ["bash"]


def test_boundary_denial_skips_reviewer_and_authorizer() -> None:
    """门先拒时后面的层**不得**再跑：否则"审批覆盖了权威门的拒绝"（B-130 的实质）。"""
    recorder = Recorder()
    chain = _chain(
        boundary=read_only_boundary(),
        hook=recorder.hook,
        reviewer=_Reviewer(recorder, "allow"),
        approve_for_me=True,
        authorizer=_Authorizer(recorder, "allow", raises=False),
    )
    with pytest.raises(BoundaryDenied):
        chain.check(PermissionContext(), _SHELL, {"command": "rm -rf x"})
    assert recorder.calls == ["hook"], "boundary 之后任何一层都不该被调用"


def test_reviewer_denial_skips_authorizer() -> None:
    recorder = Recorder()
    chain = _chain(
        boundary=standard_boundary(),
        reviewer=_Reviewer(recorder, "deny"),
        approve_for_me=True,
        authorizer=_Authorizer(recorder, "allow", raises=False),
    )
    with pytest.raises(ReviewBlocked) as caught:
        chain.check(PermissionContext(), _SHELL, {"command": "cat secrets"})
    assert caught.value.error_kind == "review_denied"
    assert recorder.calls == ["reviewer"], "Authorizer 不该在审批被拒后还跑"


# --------------------------------------------------------- 幂等护盾（B-132）


def test_same_context_passes_gate_only_once() -> None:
    """同一 ctx 第二次 check 直接放行：护盾是“这一轮已过门”的事实，不因结果而变。"""
    recorder = Recorder()
    chain = _chain(
        boundary=read_only_boundary(),
        hook=recorder.hook,
        reviewer=_Reviewer(recorder, "allow"),
        approve_for_me=True,
    )
    ctx = PermissionContext()
    with pytest.raises(BoundaryDenied):
        chain.check(ctx, _WRITE, {"path": "a.py"})
    # 判定已完成（即使是拒）→ 护盾落下；嵌套调用不得再过一次门
    chain.check(ctx, _SHELL, {"command": "ls"})
    assert recorder.calls == ["hook"], "第二次 check 不该再跑 hook（即整条链短路）"


def test_fresh_context_rejudges() -> None:
    chain = _chain(boundary=read_only_boundary())
    with pytest.raises(BoundaryDenied):
        chain.check(PermissionContext(), _WRITE, {"path": "a.py"})
    with pytest.raises(BoundaryDenied):
        chain.check(PermissionContext(), _WRITE, {"path": "a.py"})


# --------------------------------------------- Authorizer fail-closed（B-131）


@pytest.mark.parametrize("outcome", ["deny", "", "ALLOW", "approved"])
def test_only_literal_allow_passes_authorizer(outcome: str) -> None:
    """只有字面 ``"allow"`` 放行（大小写变体、空串、“approved”都算拒）。"""
    request = AuthorizationRequest(
        session_id="s",
        actor_id="a",
        cwd="/ws",
        permission_mode=PermissionMode.STANDARD,
        tool=_SHELL,
        arguments="{}",
    )
    with pytest.raises(AuthorizationDenied):
        enforce_authorizer(_Authorizer(None, outcome, raises=False), request)


def test_authorizer_trims_whitespace_and_none_authorizer_passes() -> None:
    request = AuthorizationRequest(
        session_id="s",
        actor_id="a",
        cwd="/ws",
        permission_mode=PermissionMode.STANDARD,
        tool=_SHELL,
        arguments="{}",
    )
    enforce_authorizer(_Authorizer(None, "allow ", raises=False), request)
    enforce_authorizer(None, request)  # 没接策略提供方：门不加戏（母本 L132-134）


def test_authorizer_failure_is_denied_not_bypassed() -> None:
    """provider 报错 ⇒ 拒（``authorization provider unavailable``），绝不是"跳过检查"。"""
    request = AuthorizationRequest(
        session_id="s",
        actor_id="a",
        cwd="/ws",
        permission_mode=PermissionMode.STANDARD,
        tool=_SHELL,
        arguments="{}",
    )
    with pytest.raises(AuthorizationDenied) as caught:
        enforce_authorizer(_Authorizer(None, "allow", raises=True), request)
    assert "authorization provider unavailable" in str(caught.value)
    assert caught.value.error_kind == "authorization_denied"


# ------------------------------------------- 审批五态（B-56）与硬拒（B-55）


@pytest.mark.parametrize(
    ("outcome", "kind"),
    [
        ("deny", "review_denied"),
        ("unsure", "review_needs_context"),
        ("cancelled", "review_cancelled"),
        ("failed", "review_failed"),
        ("没听过的值", "review_failed"),
        ("boom", "review_failed"),
    ],
)
def test_review_outcomes_map_to_wuu_error_kinds(outcome: str, kind: str) -> None:
    """五态映射照母本 switch；**默认分支是 review_failed（拒）**，不是放行。"""
    chain = _chain(
        boundary=standard_boundary(),
        reviewer=_Reviewer(None, outcome),
        approve_for_me=True,
    )
    with pytest.raises(ReviewBlocked) as caught:
        chain.check(PermissionContext(), _SHELL, {"command": "make deploy"})
    assert caught.value.error_kind == kind
    assert caught.value.action_executed is False
    assert caught.value.model_next_action


def test_no_available_reviewer_blocks_rather_than_allows() -> None:
    """开了 approve-for-me 但没有审批通道 → 拒（母本 L48-50），不是"没人反对就过"。"""
    chain = _chain(boundary=standard_boundary(), reviewer=None, approve_for_me=True)
    with pytest.raises(ReviewBlocked) as caught:
        chain.check(PermissionContext(), _SHELL, {"command": "make deploy"})
    assert caught.value.error_kind == "review_failed"


def test_low_risk_workspace_read_skips_review() -> None:
    """工作区普通读走常规 allow/deny 路径，不进上下文审批（母本测试同场景）。"""
    assert not needs_review(
        ApprovalRequest(
            session_id="s",
            tool=ToolMeta(name="read_file", kind="file", read_only=True),
            arguments=json.dumps({"path": "/ws/a.py"}),
        )
    )


def test_shell_is_always_reviewed_even_when_classified_read_only() -> None:
    """*"Read-only classification is not proof that a shell command cannot read credentials"*。"""
    assert needs_review(
        ApprovalRequest(
            session_id="s",
            tool=ToolMeta(name="bash", kind="shell", read_only=True),
            arguments=json.dumps({"command": "cat notes.txt"}),
        )
    )
    # 原生工具名也要能触发：缺 Kind 元数据不是绕过审批的后门
    assert needs_review(
        ApprovalRequest(
            session_id="s",
            tool=ToolMeta(name="bash", kind="meta", read_only=True),
            arguments="{}",
        )
    )


@pytest.mark.parametrize("mode", [PermissionMode.READ_ONLY, PermissionMode.UNCONFINED])
def test_review_only_enabled_in_standard(mode: PermissionMode) -> None:
    assert not needs_review(
        ApprovalRequest(
            session_id="s", tool=_SHELL, permission_mode=mode, arguments='{"command":"ls"}'
        )
    )


def test_hard_denies_cannot_be_overridden() -> None:
    """硬拒三件：参数提权（两种拼法）、敏感路径写、应用自身凭据文件。"""
    escalation = ApprovalRequest(
        session_id="s", tool=_SHELL, arguments='{"command":"ls","permission_mode":"unconfined"}'
    )
    assert "permission mode" in hard_deny_reason(escalation)
    dashed = ApprovalRequest(
        session_id="s", tool=_SHELL, arguments='{"permission-mode":"unconfined"}'
    )
    assert hard_deny_reason(dashed)
    sensitive_write = ApprovalRequest(
        session_id="s", tool=_WRITE, arguments=json.dumps({"path": "/ws/.env"})
    )
    assert "sensitive path" in hard_deny_reason(sensitive_write)
    credential = ApprovalRequest(
        session_id="s",
        tool=ToolMeta(name="read_file", kind="file", read_only=True),
        arguments=json.dumps({"path": "/home/u/.questor/auth.json"}),
        referenced_paths=("/home/u/.questor/auth.json",),
    )
    assert "never accessible" in hard_deny_reason(
        credential, frozenset({"auth.json", "credentials.json"})
    )


def test_hard_deny_uses_targets_not_content() -> None:
    """命令文本里出现凭据文件名 ≠ 访问了凭据（母本注释：不做 free-form 子串匹配）。"""
    request = ApprovalRequest(
        session_id="s",
        tool=_SHELL,
        arguments=json.dumps({"command": "grep -r auth.json ./docs"}),
    )
    assert hard_deny_reason(request, frozenset({"auth.json"})) == ""
    assert needs_review(request), "文本提到凭据名仍该走上下文审批，但不是硬拒"


# ---------------------------------------------------- boundary 结构与方言


def test_browser_read_only_short_circuit_granularity() -> None:
    """B-50：read-only 档拦 browser 的变更调用、放观察调用（短路在查表之前）。"""
    assert mutates(ToolMeta(name="wuu_browser", kind="browser")) is True
    assert mutates(ToolMeta(name="wuu_browser", kind="browser", read_only=True)) is False
    read_only = read_only_boundary()
    read_only.check(ToolMeta(name="wuu_browser", kind="browser", read_only=True), {})
    with pytest.raises(BoundaryDenied):
        read_only.check(ToolMeta(name="wuu_browser", kind="browser"), {"action": "navigate"})


#: 两张判定表的输入集（用 ToolKind 标注，不靠 type: ignore 闭嘴）
_MUTATING: list[ToolKind] = [
    "file",
    "shell",
    "test",
    "git",
    "agent",
    "process",
    "schedule",
    "mcp",
    "browser",
    "plugin",
]
_NON_MUTATING: list[ToolKind] = ["search", "discovery", "web", "session", "skill", "unknown"]


@pytest.mark.parametrize("kind", _MUTATING)
def test_mutating_kinds_table(kind: ToolKind) -> None:
    assert mutates(ToolMeta(name="x", kind=kind)) is True


@pytest.mark.parametrize("kind", _NON_MUTATING)
def test_non_mutating_kinds_table(kind: ToolKind) -> None:
    assert mutates(ToolMeta(name="x", kind=kind)) is False


def test_denial_dialect_carries_next_action() -> None:
    """B-52：拒绝必须给模型下一步；错误串形状照母本格式串。"""
    with pytest.raises(BoundaryDenied) as caught:
        read_only_boundary().check(_WRITE, {"path": "a.py"})
    error = caught.value
    assert error.error_kind == "boundary_denied"
    assert error.model_next_action
    assert "error_kind=boundary_denied" in str(error)
    assert 'reason="' in str(error) and 'model_next_action="' in str(error)


def test_unconfined_keeps_guards_and_lifts_path_confinement() -> None:
    """B-54：逃生阀只解除路径约束；守卫链仍按注入执行（表里没有"关守卫"这一列）。"""
    ran: list[str] = []

    class _Guard:
        def check(self, info: ToolMeta, arguments: dict[str, Any]) -> None:
            ran.append(info.name)

    boundary = unconfined_boundary(_Guard())
    assert boundary.enforce is False and boundary.allow_mutations is True
    boundary.check(_WRITE, {"path": "anything"})
    assert ran == ["write_file"], "unconfined 不该跳过守卫链"


def test_guards_run_after_read_only_gate_and_short_circuit() -> None:
    """B-34：只读闸先决；命中即返回，后面的 guard 不该再跑。"""
    ran: list[str] = []

    class _Guard:
        def __init__(self, name: str) -> None:
            self.name = name

        def check(self, info: ToolMeta, arguments: dict[str, Any]) -> None:
            ran.append(self.name)

    class _DenyGuard:
        def check(self, info: ToolMeta, arguments: dict[str, Any]) -> None:
            ran.append("deny")
            raise BoundaryDenied(info.name, "nope", "do something else")

    boundary = standard_boundary(_DenyGuard(), _Guard("second"))
    with pytest.raises(BoundaryDenied):
        boundary.check(_SHELL, {})
    assert ran == ["deny"], "第二个守卫不该在已拒后继续跑"


def test_sensitive_classify_single_source_used_by_approval() -> None:
    """审批侧的敏感判定必须复用同一个实现（否则同一事实两套真相）。"""
    assert classify("/ws/.env") is not None
    assert classify("/ws/credentials.go") is None, "源码扩展名豁免（B-53）"
    reason, hit = sensitive_path_reason("/ws/.env")
    assert hit is True and reason == classify("/ws/.env")
