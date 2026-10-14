"""契约单一来源护栏（B-119/B-121）：protocol.md §3/§4/§7 ↔ schemas/app_server/names.py 双向同源。

为什么是契约而非复述：跨语言接缝「无代码生成」（wuu 三份 TS/Go/Py 并行、会漂移）是本仓最高风险项，
唯一防线是让"文档声明面"与"代码定义面"机器双向锁死——任一处多一个/少一个/大小写或连字符漂移即红，
逼两处同批改。二者皆为契约侧产物，不依赖尚未重写的 serve handler，故本护栏 Phase 1 即绿；
"实现面 ⊆ 契约面"由旧 `test_serve_names_are_contracted`（TL-1）守，handler Phase 2a 物化后转绿。

负向验证（改本测后必须实跑一次再复原）：把 names.py 任一方法名改一个字母、或把 protocol.md 表里
一项删掉 → 本测必须红且指明缺/多的那个名；复原 → 绿。
"""

from __future__ import annotations

import re
from pathlib import Path

from questor.schemas.app_server import names

REPO = Path(__file__).resolve().parents[2]
PROTOCOL_MD = REPO / "docs" / "architecture" / "protocol.md"

# 抽取一段（"## N." 到下一 "## " 之间）里**表格行**首列的反引号 token。
_SECTION = re.compile(r"^## (\d+)\.", re.M)
_ROW = re.compile(r"^\|(.*)$")
_BACKTICK = re.compile(r"`([^`]+)`")


def _section_body(md: str, num: str) -> str:
    """返回 "## {num}." 小节正文（到下一个同级 "## " 或文件末）。"""
    parts = re.split(r"(?m)^## \d+\.", md)
    heads = re.findall(r"(?m)^## (\d+)\.", md)
    for head, body in zip(heads, parts[1:], strict=False):
        if head == num:
            return body
    raise AssertionError(f"protocol.md 缺 §{num} 小节")


def _first_col_tokens(md: str, section: str) -> set[str]:
    """取该节所有表格行第一列里的反引号 token（表头/分隔行无反引号自然被排除；
    非表格的"不做族"段落以 ** 开头、不以 | 开头，亦被排除）。"""
    out: set[str] = set()
    for line in _section_body(md, section).splitlines():
        row = _ROW.match(line.strip())
        if not row:
            continue
        first_col = row[1].split("|")[0]
        out.update(_BACKTICK.findall(first_col))
    return out


def test_method_names_match_protocol_doc() -> None:
    md = PROTOCOL_MD.read_text(encoding="utf-8")
    declared = _first_col_tokens(md, "3")
    registered = set(names.METHOD_NAMES) | set(names.REVERSE_METHOD_NAMES)
    assert declared == registered, (
        "protocol.md §3 ↔ names.py 方法表漂移：\n"
        f"  文档有而注册表无：{sorted(declared - registered)}\n"
        f"  注册表有而文档无：{sorted(registered - declared)}"
    )


def test_notification_names_match_protocol_doc() -> None:
    md = PROTOCOL_MD.read_text(encoding="utf-8")
    declared = _first_col_tokens(md, "4")
    assert declared == set(names.NOTIFICATION_NAMES), (
        "protocol.md §4 ↔ names.py 通知表漂移：\n"
        f"  文档有而注册表无：{sorted(declared - set(names.NOTIFICATION_NAMES))}\n"
        f"  注册表有而文档无：{sorted(set(names.NOTIFICATION_NAMES) - declared)}"
    )


def test_error_codes_match_protocol_doc() -> None:
    md = PROTOCOL_MD.read_text(encoding="utf-8")
    declared = _first_col_tokens(md, "7")
    assert declared == set(names.ERROR_CODES), (
        f"protocol.md §7 ↔ names.py 错误方言漂移：对称差 "
        f"{sorted(declared ^ set(names.ERROR_CODES))}"
    )


def test_initialize_methods_derives_from_single_table() -> None:
    """B-119：initialize.methods 必须由 METHOD_NAMES 派生、有序、无重复——不是另写一份字面量。"""
    methods = names.initialize_methods()
    assert methods == names.METHOD_NAMES
    assert len(methods) == len(set(methods)), "方法表含重复名"


def test_protocol_version_is_questor_and_envelope_consistent() -> None:
    """版本串单一来源（P1-1）：names.PROTOCOL_VERSION 是唯一定义，protocol.md §1 引用同值。"""
    md = PROTOCOL_MD.read_text(encoding="utf-8")
    assert names.PROTOCOL_VERSION == "questor-app-server/v0.1"
    assert names.PROTOCOL_VERSION in md, "protocol.md 未引用注册表版本串（两处会漂移）"


def test_no_legacy_method_names_leak_into_contract() -> None:
    """作废的旧自研词表（ADR-0042：thread/create、run/stop、review/turn_diff）不得回流契约面。"""
    banned = {"thread/create", "thread/show", "run/stop", "run/status", "turn/create"}
    registered = (
        set(names.METHOD_NAMES) | set(names.REVERSE_METHOD_NAMES) | set(names.NOTIFICATION_NAMES)
    )
    assert not (banned & registered), f"旧作废词表混入契约：{sorted(banned & registered)}"
