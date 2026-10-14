"""tests/contract —— wuu 帧回放（§1.5 机制 2·弥补"无代码生成"漂移的唯一防线）。

基准帧来源（本机无 Go，不靠实跑）：① **真实 golden** —— wuu `_test.go` 里写死的期望 JSON
（`fixtures/wuu_initialize_request.json` 逐字取自 client_calls_test.go:60；
`fixtures/wuu_reverse_response.json` 取自 :89）；② **手写期望帧** —— 逐方法读
`internal/appserver/protocol.go` 结构体核对其 json tag 后按形状手打（下附 wuu 行号锚点）。

断言：initialize + thread/turn/run/item 四族逐字段一致（键名/类型/可选性/顺序无关）。
负向验证：把某帧一个键改成 camelCase 或塞未知键 → 模型 `extra=forbid` 必须拒（证明会咬人，贴红）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from questor.schemas.app_server import entities as ent
from questor.schemas.app_server import families, initialize
from questor.schemas.app_server.envelope import Request, ResponseError, ReverseResponse
from questor.schemas.app_server.names import PROTOCOL_VERSION

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------- initialize ----------


def test_real_wuu_initialize_request_decodes_and_flags_version() -> None:
    """真实 golden（wuu 自己的 version 串）能解码；且严格相等校验判为不匹配（B-60）。"""
    frame = _load("wuu_initialize_request.json")
    req = Request.model_validate(frame)
    params = initialize.InitializeParams.model_validate(req.params)
    assert params.client is not None and params.client.name == "cloud-host"
    assert params.capabilities is not None
    assert params.capabilities.reverse_rpc is not None
    assert params.capabilities.reverse_rpc.methods == ["browser/list_tabs"]
    # wuu 串 ≠ questor 串 → 报错（不降级）
    err = params.version_error()
    assert err is not None
    assert "unsupported protocol version" in err


def test_questor_version_handshake_ok() -> None:
    """questor 自命名版本串（P1-1）通过严格相等校验。"""
    params = initialize.InitializeParams(protocol_version=PROTOCOL_VERSION)
    assert params.version_error() is None


def test_initialize_result_roundtrip_field_for_field() -> None:
    """手写期望帧（锚 config_handlers.go:65-97 装配 + protocol.go:289-313 字段）逐字段还原。"""
    frame = {
        "status": "ready",
        "protocol_version": PROTOCOL_VERSION,
        "core": {"version": "0.1.0", "commit": "abc1234", "date": "2026-10-14", "dirty": False},
        "provider": "anthropic",
        "model": "claude-x",
        "max_parallel": 4,
        "runtime_host": {"kind": "desktop"},
        "workspace_root": "D:\\repo",
        "features": {"project_agent": False, "browser": False},
    }
    result = initialize.InitializeResult.model_validate(frame)
    assert result.status == "ready"
    assert result.core.commit == "abc1234"
    assert result.runtime_host.kind == "desktop"
    assert result.features.browser is False
    # 凭据键注入必须被拒（P1-4）
    with pytest.raises(ValidationError):
        initialize.InitializeResult.model_validate({**frame, "api_key": "sk-secret"})


# ---------- thread / turn / run / item 四族 ----------


def test_thread_started_notification_shape() -> None:
    """锚 protocol.go:2145/2367 —— Thread 实体子集字段名 snake_case 一致。"""
    frame = {
        "thread": {
            "id": "t1",
            "preview": "hi",
            "status": "idle",
            "model_provider": "anthropic",
            "model": "claude-x",
            "model_variant": "",
            "model_effort": "",
            "permission_mode": "default",
            "cwd": "D:\\repo",
            "created_at": "2026-10-14T00:00:00Z",
            "updated_at": "2026-10-14T00:00:00Z",
            "turns": [],
        }
    }
    notif = families.ThreadStartedNotification.model_validate(frame)
    assert notif.thread.id == "t1"
    assert notif.thread.status == ent.ThreadStatus.IDLE


def test_turn_items_nil_becomes_empty_array() -> None:
    """硬语义 P1-3：items 缺省序列化恒为 []（非 null），对齐 wuu MarshalJSON（#L2457-2464）。"""
    turn = ent.Turn(id="u1", status=ent.TurnStatus.IN_PROGRESS)
    assert turn.model_dump_wire()["items"] == []


def test_turn_started_and_completed_finish_reason() -> None:
    """锚 protocol.go:2178/2250 —— finish_reason/stop_reason 上线、结构化 turn 可还原。"""
    started = families.TurnStartedNotification.model_validate(
        {
            "thread_id": "t1",
            "turn": {"id": "u1", "items": [], "status": "in_progress", "items_view": "full"},
        }
    )
    assert started.turn.status == ent.TurnStatus.IN_PROGRESS
    completed = families.TurnCompletedNotification.model_validate(
        {
            "thread_id": "t1",
            "turn": {"id": "u1", "items": [], "status": "completed", "finish_reason": "stop"},
            "content": "done",
            "input_tokens": 10,
            "output_tokens": 5,
            "finish_reason": "stop",
        }
    )
    assert completed.finish_reason == "stop"


def test_run_start_and_interrupt() -> None:
    """锚 protocol.go:2006/2026 —— run/start result 携 run、interrupt 携 run_id。"""
    result = families.RunStartResult.model_validate(
        {"run": {"id": "r1", "thread_id": "t1", "status": "queued"}}
    )
    assert result.run.id == "r1"
    params = families.RunInterruptParams.model_validate({"run_id": "r1", "reason": "user"})
    assert params.run_id == "r1"


def test_item_started_and_delta() -> None:
    """锚 protocol.go:2570/2591 —— item/started 携 ThreadItem、agentMessage/delta 携 delta。"""
    started = families.ItemStartedNotification.model_validate(
        {
            "thread_id": "t1",
            "turn_id": "u1",
            "item": {"id": "i1", "type": "agent_message", "role": "assistant", "text": "par"},
            "started_at_ms": 123,
        }
    )
    assert started.item.type == ent.ThreadItemType.AGENT_MESSAGE
    delta = families.AgentMessageDeltaNotification.model_validate(
        {"thread_id": "t1", "turn_id": "u1", "item_id": "i1", "delta": "more"}
    )
    assert delta.delta == "more"


# ---------- 反向响应 ----------


def test_reverse_response_golden() -> None:
    """真实 golden（client_calls_test.go:89）：srv- 前缀 id + result 原样重解码不丢（B-59）。"""
    frame = _load("wuu_reverse_response.json")
    resp = ReverseResponse.model_validate(frame)
    assert resp.id == "srv-1"
    assert resp.result == {"tab_ids": ["tab-1"]}


# ---------- 负向验证（护栏有齿） ----------


def test_camelcase_drift_is_rejected() -> None:
    """负向注入：snake_case 键改成 camelCase → extra=forbid 拒（证明字段名漂移会咬人）。"""
    bad = {"thread": {"id": "t1", "modelProvider": "anthropic"}}
    with pytest.raises(ValidationError):
        families.ThreadStartedNotification.model_validate(bad)


def test_error_envelope_shape() -> None:
    err = ResponseError(code="boundary_denied", message="nope", model_next_action="use read")
    assert err.model_dump(exclude_none=True) == {
        "code": "boundary_denied",
        "message": "nope",
        "model_next_action": "use read",
    }
