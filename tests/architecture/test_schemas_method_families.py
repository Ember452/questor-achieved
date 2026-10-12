"""架构护栏：每个已实装方法都要在 app_server schema 里有 Params/Result 形状；
每个协议通知族都要有对应的 Notification 形状。

这是 R4 "跨进程边界只有一个真相源" 落到方法级的机械保证：
- 上游：`AppServer._methods()` 与 `PROTOCOL_NOTIFICATIONS` 是"实现面"，加/删必须同步 schema；
- 下游：`ui/src/rpc/generated/app_server-v0-1.d.ts` 由生成器展开 `$defs` 产出严格类型；
  若某项 `$defs` 缺失、或生成器把它降级为 `[k: string]: unknown`（B-92），本文件与
  `scripts/gen/types.mjs` 都会红。

负向验证（写此测试时实测）：临时把 `ThreadCreateParams` 从 `$defs` 抽掉 →
`test_methods_have_schemas` FAILED 指出未定义形状的方法；把一个 Notification 的
`method.const` 改成协议外的字符串 → `test_notification_family_const_matches_registry` FAILED。
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import NoReturn

from questor.schemas.model import PermissionMode
from questor.serve import app_server, notifications

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
APP_SERVER_SCHEMA = REPO_ROOT / "src" / "questor" / "schemas" / "app_server" / "v0-1.json"
PROTOCOL = REPO_ROOT / "docs" / "architecture" / "protocol.md"


def _schema() -> dict:
    return json.loads(APP_SERVER_SCHEMA.read_text(encoding="utf-8"))


def _method_def_base(method: str) -> str:
    """把 `thread/create` 映射为 `ThreadCreate`；`review/turn_diff` → `ReviewTurnDiff`。

    先按 `/` 拆 prefix/action，action 里再以 `_` 拆片段，逐段 capitalize。
    与 `_snake_case_method` 互逆；新加方法时两边同顺。Python 内置 capitalize
    会把 `turn_diff` 变成 `Turn_diff`，不拆内部下划线就对不上 schema 里的类名。
    """
    pieces: list[str] = []
    for segment in method.split("/"):
        pieces.extend(word for word in segment.split("_") if word)
    return "".join(word.capitalize() for word in pieces)


def _no_engine(thread_id: str, mode: PermissionMode) -> NoReturn:
    """本文件只看形状与名字，不起引擎；NoReturn 使下游不必 type: ignore。"""
    raise AssertionError(f"不该起引擎：{thread_id} {mode}")


def _registered_methods() -> tuple[str, ...]:
    server = app_server.AppServer(create_engine=_no_engine)
    return server._methods()


def test_methods_have_schemas() -> None:
    """已登记的每个方法都要在 `$defs` 里同时有 <Method>Params 与 <Method>Result。

    新增 handler 但没补形状 = 契约漂（UI 拿到 `[k: string]: unknown` 就退化为手写 DTO）。
    """
    defs = _schema()["$defs"]
    missing: list[str] = []
    for method in _registered_methods():
        base = _method_def_base(method)
        for suffix in ("Params", "Result"):
            if f"{base}{suffix}" not in defs:
                missing.append(f"{method} -> $defs.{base}{suffix}")
    assert not missing, "以下已实现方法缺 schema 形状：\n  " + "\n  ".join(missing)


def test_notifications_have_schemas() -> None:
    """每个协议通知族都要在 `$defs` 里有对应的 <Method>Notification 形状。"""
    defs = _schema()["$defs"]
    missing: list[str] = []
    for family in notifications.PROTOCOL_NOTIFICATIONS:
        base = _method_def_base(family)
        if f"{base}Notification" not in defs:
            missing.append(f"{family} -> $defs.{base}Notification")
    assert not missing, "以下协议通知族缺 schema 形状：\n  " + "\n  ".join(missing)


def test_notification_family_const_matches_registry() -> None:
    """schema 里 `<Method>Notification` 的 `method.const` 值必须出现在 PROTOCOL_NOTIFICATIONS。

    防漂双向：注册表加了新族但 schema 未跟上（test_notifications_have_schemas 咬），
    或 schema 加了新形状但代码未映射（本条咬）。
    """
    defs = _schema()["$defs"]
    declared: set[str] = set()
    for name, spec in defs.items():
        if not name.endswith("Notification"):
            continue
        const = spec.get("properties", {}).get("method", {}).get("const")
        if isinstance(const, str):
            declared.add(const)
    produced = set(notifications.PROTOCOL_NOTIFICATIONS)
    extra = declared - produced
    assert not extra, f"schema 里定义了但代码未映射的通知族名: {sorted(extra)}"


def test_schema_methods_are_documented() -> None:
    """schema `$defs.<Method>Params` 对应的 method 名要在 protocol.md §3 表里出现。

    与 `test_serve_names_are_contracted.test_serve_methods_are_documented` 同源，
    但覆盖"schema 里有形状但代码未实装"的中间态（本 plan M3a-1 首批 15 项，
    M3a-2/M3a-3 陆续实装）。
    """
    documented = _documented_method_names()
    defs = _schema()["$defs"]
    schema_methods: set[str] = set()
    for name in defs:
        if name.endswith("Params"):
            # ThreadCreateParams -> thread/create；RunStopParams -> run/stop
            base = name[: -len("Params")]
            schema_methods.add(_snake_case_method(base))
    undocumented = schema_methods - documented
    assert not undocumented, (
        f"schema 定义了但 protocol.md §3 未登记的方法名: {sorted(undocumented)}"
    )


_CAMEL_PIECE = re.compile(r"[A-Z][a-z]*")


def _snake_case_method(base: str) -> str:
    """`ReviewTurnDiff` -> `review/turn_diff`；`ThreadCreate` -> `thread/create`。

    拆规则：按驼峰分词，首段作 prefix，其余小写后以 `_` 拼接为 action；
    与 protocol 表首列同形式。
    """
    parts = _CAMEL_PIECE.findall(base)
    if not parts:
        return base.lower()
    head = parts[0].lower()
    if len(parts) == 1:
        return head
    tail = "_".join(piece.lower() for piece in parts[1:])
    return f"{head}/{tail}"


def _documented_method_names() -> set[str]:
    """取 protocol.md §3 表格首列所有反引号包围的方法名（含 `<name>/*` 展开）。"""
    lines = PROTOCOL.read_text(encoding="utf-8").splitlines()
    in_section = False
    names: set[str] = set()
    for line in lines:
        if line.startswith("## "):
            in_section = "3. 方法表" in line
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) < 2:
            continue
        for raw in re.findall(r"`([^`]+)`", cells[1]):
            names.add(raw)
            # `thread/create` / `thread/list` / ... 同一格并列
            if " / " in raw:
                for piece in raw.split(" / "):
                    names.add(piece.strip())
    # 展开 `thread/{a,b,c}` 与 `turn/{x,y}` 花括号语法
    expanded: set[str] = set()
    for name in names:
        m = re.match(r"^([a-z]+)/\{([a-z,|]+)\}$", name)
        if m:
            prefix, opts = m.group(1), m.group(2)
            for opt in re.split(r"[,|]", opts):
                expanded.add(f"{prefix}/{opt}")
    return names | expanded
