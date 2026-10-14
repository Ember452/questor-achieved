"""控制/配置/HITL 面帧回放（config/read · activity · process · workspace · user-question）。

手写期望帧锚 `internal/appserver/protocol.go` + activity/user_question handler 结构体的 json tag
（见 control_plane 模块头逐行锚点）。断言逐字段名/类型/可选性；含硬语义：activity 租约
`lease_token`、process 偏移 `offset_bytes`/`start_offset`。负向：camelCase 或未知键 → 模型拒。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from questor.schemas.app_server import control_plane as cp


def test_config_read_result_shape() -> None:
    """锚 protocol.go:500-520 —— provider/model/max_parallel/config_path/permissions 上线。"""
    frame = {
        "provider": "anthropic",
        "model": "claude-x",
        "max_parallel": 4,
        "config_path": "C:\\Users\\me\\.questor\\config.toml",
        "workspace_root": "D:\\repo",
        "session_dir": "D:\\repo\\.questor\\sessions",
        "permissions": {"mode": "default", "approve_for_me": False},
    }
    result = cp.ConfigReadResult.model_validate(frame)
    assert result.permissions.mode == "default"
    assert result.max_parallel == 4


def test_activity_release_carries_lease_token() -> None:
    """硬语义 —— activity/release 返 lease_token（接管竞态栅栏的一部分，§1.5 机制 4）。"""
    session = {
        "id": "a1",
        "kind": "browser",
        "thread_id": "t1",
        "workdir": "D:\\repo",
        "state": "running",
        "controller": "desktop",
        "created_at": "2026-10-14T00:00:00Z",
        "updated_at": "2026-10-14T00:00:01Z",
    }
    result = cp.ActivityReleaseResult.model_validate({"activity": session, "lease_token": "lt-9"})
    assert result.lease_token == "lt-9"
    assert result.activity.controller == "desktop"


def test_activity_started_notification_payload_is_session() -> None:
    """activity/started|updated|control_changed|stopped 载荷 = ActivitySession

    （activity_handlers.go:127）。
    """
    session = {
        "id": "a1",
        "kind": "process",
        "thread_id": "t1",
        "workdir": "D:\\repo",
        "state": "running",
        "controller": "core",
        "created_at": "2026-10-14T00:00:00Z",
        "updated_at": "2026-10-14T00:00:00Z",
    }
    parsed = cp.ActivitySession.model_validate(session)
    assert parsed.kind == "process"
    assert parsed.process_id is None  # 可选缺省


def test_process_read_offsets_and_truncation() -> None:
    """锚 protocol.go:1313-1329 —— offset_bytes 可选入、start/end/total_bytes 出。"""
    proc = {
        "id": "p1",
        "owner_kind": "turn",
        "owner_id": "u1",
        "lifecycle": "detached",
        "status": "running",
        "pid": 1234,
        "command": "python x.py",
        "cwd": "D:\\repo",
        "started_at": "2026-10-14T00:00:00Z",
        "updated_at": "2026-10-14T00:00:00Z",
    }
    params = cp.ProcessReadParams.model_validate(
        {"thread_id": "t1", "process_id": "p1", "offset_bytes": 0, "max_bytes": 4096}
    )
    assert params.offset_bytes == 0
    result = cp.ProcessReadResult.model_validate(
        {
            "process": proc,
            "output": "hello",
            "truncated": False,
            "start_offset": 0,
            "end_offset": 5,
            "total_bytes": 5,
            "timed_out": False,
        }
    )
    assert result.end_offset == 5


def test_workspace_list() -> None:
    frame = {
        "workspaces": [{"id": "w1", "name": "repo", "path": "D:\\repo"}],
        "current": "w1",
    }
    result = cp.WorkspaceListResult.model_validate(frame)
    assert result.workspaces[0].path == "D:\\repo"
    assert result.current == "w1"


def test_user_question_request_and_respond() -> None:
    """锚 user_question_handlers.go:10-34 + pluginhost.UserQuestionRequest:66。"""
    req = {
        "request_id": "q1",
        "plugin_id": "p",
        "execution_id": "e1",
        "thread_id": "t1",
        "turn_id": "u1",
        "created_at": "2026-10-14T00:00:00Z",
        "questions": [{"text": "pick one"}],
    }
    parsed = cp.UserQuestionRequest.model_validate(req)
    assert parsed.request_id == "q1"
    assert parsed.questions == [{"text": "pick one"}]
    resp = cp.UserQuestionRespondParams.model_validate(
        {"request_id": "q1", "answer": {"choice": 0}}
    )
    assert resp.answer == {"choice": 0}
    resolve = cp.UserQuestionResolveResult.model_validate({"request_id": "q1", "resolved": True})
    assert resolve.resolved is True


def test_camelcase_drift_rejected_control_plane() -> None:
    """负向注入：process/read 的 offset_bytes 写成 offsetBytes → extra=forbid 拒（漂移即咬）。"""
    with pytest.raises(ValidationError):
        cp.ProcessReadParams.model_validate(
            {"thread_id": "t1", "process_id": "p1", "offsetBytes": 0}
        )
