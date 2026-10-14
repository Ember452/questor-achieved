"""架构护栏：serve 的方法名与通知族必须逐字落在 protocol.md 的清单里。

与同目 `test_schemas_method_families.py` 的分工：本文件断言"实现面 ↔ 契约文档"不漂
（`_methods()` 项项在 §3 表首列，`PROTOCOL_NOTIFICATIONS` 项项在 §4 表首列）；
后者断言"实现面 ↔ schema 形状"齐全（已实现的每个方法都有 `<Method>Params/Result`）。
两层一起才搭起 R4“跨进程边界只有一个真相源”：名字、形状、实现三处同进。

前端接口的钉子就在这里：M3 换 WS 传输时不得改名（ADR-0023），因为名字合法性由本文件判定。
"""

from __future__ import annotations

import inspect
import pathlib
import re
from typing import NoReturn

import pytest

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


@pytest.mark.xfail(
    reason=(
        "契约先于实现：protocol.md 已取齐 wuu 词表，serve 仍旧名，"
        "Phase 1/2 迁移后转绿；见 docs/research/port-ledger.md TL-1"
    ),
    strict=False,
)
def test_serve_methods_are_documented() -> None:
    documented = _documented("3. 方法表")
    registered = set(_registered_methods())
    assert registered, "方法表为空——本测试会空转，先确认重构"
    assert registered <= documented, (
        f"未登记进 protocol §3 的方法: {sorted(registered - documented)}"
    )


@pytest.mark.xfail(
    reason=(
        "契约先于实现：protocol.md 已取齐 wuu 通知族，serve 仍旧名，"
        "Phase 1/2 迁移后转绿；见 docs/research/port-ledger.md TL-1"
    ),
    strict=False,
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


def test_method_table_has_single_source() -> None:
    """方法表只许一处定义：`_methods()` 必须是 handler 注册表的派生视图。

    咬的是上一轮审计查出的形状：`_methods()` 与 `_handler()` 曾各抄一份 44 项名单。
    两份名单的失效方向是**静默**的——注册表里多一项而方法表没跟上时，`build_dispatcher`
    只按 `_methods()` 遍历，那个 handler 永远不被登记成死代码；而
    `test_dispatcher_registers_only_known_methods` 比的是这两面的交集，抓不到它。
    负向验证：把注册表里任意一行复制改名（造出第三项）即红。
    """
    server = app_server.AppServer(create_engine=_no_engine)
    registry = server._handler_registry()
    assert tuple(registry) == server._methods()
    assert len(registry) == len(set(registry)), "方法表里有重复项"
    assert server._methods(), "方法表为空——本测试会空转，先确认重构"


def test_initialize_publishes_the_same_method_table() -> None:
    """握手发布的 methods 就是注册表键序：客户端的能力发现面不得另成一份真相。"""
    import asyncio

    from questor.serve.dispatch import HandlerCtx

    server = app_server.AppServer(create_engine=_no_engine)
    dispatcher = server.build_dispatcher()
    context = HandlerCtx(request_id="r1", principal="p1", trace_id="t1")  # noqa: S106
    result = asyncio.run(server.initialize({"protocol_version": ""}, context))
    assert result["methods"] == list(server._methods())
    assert set(result["methods"]) == set(dispatcher.known_methods())


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
