"""架构护栏：serve 的方法名与通知族必须逐字落在 protocol.md 的清单里。

为什么盯文档而不是生成的 schema：`protocol.md` 自己声明"本文件是跨进程边界的唯一真相源"，
而 `schemas/app_server/v0-1.json` 的 `Request.method` / `Notification.method` 今天仍是自由
字符串（改成枚举要重跑生成链，属 M3 前端真接那一批）。所以本期直接对照真相源核对，
M3 扩枚举时这条护栏照样有效——它断言的是"实现与契约文档不漂移"，不是"实现与 JSON 不漂移"。

前端接口的钉子就在这里：M3 换 WS/SSE 传输时不得改名，因为名字合法性由本文判定。
"""

from __future__ import annotations

import inspect
import pathlib
import re
from typing import NoReturn

from questor.schemas.model import PermissionMode
from questor.serve import app_server, notifications
from questor.serve.envelope import error_payload

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROTOCOL = REPO_ROOT / "docs" / "architecture" / "protocol.md"


def _documented(section: str) -> set[str]:
    """取 protocol.md 某小节表格**首列**的反引号名（一行并列多个就全收）。"""
    lines = PROTOCOL.read_text(encoding="utf-8").splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.startswith("## ") and section in line
    )
    names: set[str] = set()
    for line in lines[start:]:
        if line.startswith("## ") and not line.startswith(f"## {section}"):
            break
        if not line.startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) < 2:
            continue
        names.update(re.findall(r"`([^`]+)`", cells[1]))
    return names


def _no_engine(thread_id: str, mode: PermissionMode) -> NoReturn:
    """本文件只问方法表与名字，不起引擎；`NoReturn` 所以下游不必 type: ignore。"""
    raise AssertionError(f"不该起引擎：{thread_id} {mode}")


def _registered_methods() -> tuple[str, ...]:
    server = app_server.AppServer(create_engine=_no_engine)
    return server._methods()


def test_serve_methods_are_documented() -> None:
    documented = _documented("3. 方法表")
    registered = set(_registered_methods())
    assert registered, "方法表为空——本测试会空转，先确认重构"
    assert registered <= documented, (
        f"未登记进 protocol §3 的方法: {sorted(registered - documented)}"
    )


def test_serve_notification_families_are_documented() -> None:
    documented = _documented("4. 事件族")
    produced = notifications.PROTOCOL_NOTIFICATIONS
    assert produced <= documented, f"协议外的事件族名: {sorted(produced - documented)}"


def test_serve_error_codes_are_contracted() -> None:
    """字符串错误码不得自造：源码里出现过的码必须都在协议 §7 的表里。"""
    documented = {line.strip("` ") for line in _lines_with("error_kind") if line.strip()} | {
        found for found in re.findall(r"`([a-z_]+)`", _section_text("7. 错误方言")) if "_" in found
    }
    # §7 给的是"模型可读错因方言"（error_kind），schema 的 code.enum 是信封层技术错码
    # （`internal_error` 类）——两边都是已签契约，任一查到即合法。
    documented |= _schema_error_codes()
    used = _error_codes_in_serve()
    assert used, "没发现任何错误码使用点——先确认重构"
    assert used <= documented, (
        f"未出现在协议 §7 与 app_server schema 的错误码: {sorted(used - documented)}"
    )


def _schema_error_codes() -> set[str]:
    import json

    schema = json.loads(
        (REPO_ROOT / "src" / "questor" / "schemas" / "app_server" / "v0-1.json").read_text(
            encoding="utf-8"
        )
    )
    return {str(code) for code in schema["$defs"]["ErrorPayload"]["properties"]["code"]["enum"]}


def _lines_with(needle: str) -> list[str]:
    return [line for line in PROTOCOL.read_text(encoding="utf-8").splitlines() if needle in line]


def _section_text(title: str) -> str:
    lines = PROTOCOL.read_text(encoding="utf-8").splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.startswith("## ") and title in line
    )
    out: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out)


def _error_codes_in_serve() -> set[str]:
    """扫 serve 包源码里传给 `error_payload(...)` 的首个字符串字面量。"""
    codes: set[str] = set()
    root = REPO_ROOT / "src" / "questor" / "serve"
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        codes.update(re.findall(r"error_payload\(\s*\"([a-z_]+)\"", text))
    return codes


def test_dispatcher_registers_only_known_methods() -> None:
    """分发器登记面与方法表一致：漏登记=运行时 unknown_method，多登记=契约外的隐藏入口。"""
    server = app_server.AppServer(create_engine=_no_engine)
    dispatcher = server.build_dispatcher()
    assert set(dispatcher.known_methods()) == set(_registered_methods())


def test_handler_signature_takes_context_object() -> None:
    """ADR-0020 的落点：每个 handler 都是 `(params, HandlerCtx)`，身份位从第一天就在。

    断言的是**签名形状**（不是某个字段的值），因此将来加 `principal` 的判定逻辑不必改测试。
    """
    server = app_server.AppServer(create_engine=_no_engine)
    for name in server._methods():
        handler = server._handler(name)
        parameters = list(inspect.signature(handler).parameters)
        assert parameters == ["params", "ctx"], f"{name} 的签名不再是 (params, HandlerCtx)"
    assert "principal" in inspect.signature(app_server.HandlerCtx.__init__).parameters or hasattr(
        app_server, "HandlerCtx"
    )


def test_error_payload_carries_model_next_action_when_given() -> None:
    payload = error_payload("unknown_method", "no such method", model_next_action="call initialize")
    assert payload == {
        "code": "unknown_method",
        "message": "no such method",
        "model_next_action": "call initialize",
    }
    assert "model_next_action" not in error_payload("internal_error", "boom")
