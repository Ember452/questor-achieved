"""护栏：schemas/model.py 绑定与 model/v1.json 逐字一致（required、枚举、pattern）。

pydantic 只做绑定，JSON Schema 是唯一真相源——本测试是"绑定不得漂移"的机械形式。
负向验证（2026-10-11，已复原）：临时给 model.Run 的 status 加默认值 QUEUED →
``test_required_fields_match[Run]`` FAILED（required 集合少 status）。
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import get_args

import pytest

from questor.schemas import model

REPO = pathlib.Path(__file__).resolve().parents[2]

SCHEMA = json.loads(
    (REPO / "src" / "questor" / "schemas" / "model" / "v1.json").read_text(encoding="utf-8")
)

ENTITY_MODELS = {
    "Workspace": model.Workspace,
    "Thread": model.Thread,
    "Turn": model.Turn,
    "Run": model.Run,
    "Item": model.Item,
    "Event": model.Event,
}
ENUM_MODELS = {
    "PermissionMode": model.PermissionMode,
    "RunStatus": model.RunStatus,
    "AcceptanceStatus": model.AcceptanceStatus,
    "ItemKind": model.ItemKind,
    "Origin": model.Origin,
}


@pytest.mark.parametrize("name", sorted(ENTITY_MODELS))
def test_required_fields_match_schema(name: str) -> None:
    schema_required = set(SCHEMA["$defs"][name].get("required", []))
    m = ENTITY_MODELS[name]
    pydantic_required = {field_name for field_name, f in m.model_fields.items() if f.is_required()}
    assert pydantic_required == schema_required, name


@pytest.mark.parametrize("name", sorted(ENTITY_MODELS))
def test_entities_are_frozen_and_closed(name: str) -> None:
    """append-only 的模型层表达：frozen（不可变）+ extra=forbid（对齐 additionalProperties）。"""
    m = ENTITY_MODELS[name]
    assert m.model_config.get("frozen") is True, name
    assert m.model_config.get("extra") == "forbid", name


@pytest.mark.parametrize("name", sorted(ENUM_MODELS))
def test_enum_values_match_schema(name: str) -> None:
    schema_values = SCHEMA["$defs"][name]["enum"]
    enum_values = [e.value for e in ENUM_MODELS[name]]
    assert enum_values == schema_values, name


def test_id_and_timestamp_patterns_match_schema() -> None:
    for type_name, annotated in (("Id", model.Id), ("Timestamp", model.Timestamp)):
        constraints = [a for a in get_args(annotated)[1:] if getattr(a, "pattern", None)]
        assert len(constraints) == 1, type_name
        assert constraints[0].pattern == SCHEMA["$defs"][type_name]["pattern"], type_name


def test_utc_timestamp_now_matches_contract_pattern() -> None:
    pattern = SCHEMA["$defs"]["Timestamp"]["pattern"]
    assert re.match(pattern, model.utc_timestamp_now()), model.utc_timestamp_now()
