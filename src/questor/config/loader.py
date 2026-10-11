"""配置分层加载：用户 base + 项目共享层 + 项目本地层，strip 用户专属安全字段。

- 合并语义：表（dict）递归深合并，标量与列表整体覆盖；**绝不 mutate 输入**；
- strip 语义（B-57/B-75）：``USER_ONLY_FIELDS`` 中的键在两个项目层里以
  **大小写不敏感的全拼写**删除（``API_Key`` 删、``my_api_key`` 不删），任意深度；
  每处 strip 发一条一次性去重警告（wuu settings_layer 同款）；
- 坏 TOML 抛 :class:`ConfigError`（带文件路径），不静默跳过——配置错误必须可见。
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from questor.state.paths import config_path

logger = logging.getLogger(__name__)

# 用户专属安全字段：项目层（共享与本地）出现即 strip 并警告（B-57）。
# permission_mode 依据 data-model §2 只能来自用户配置，仓库配置不可设定。
USER_ONLY_FIELDS = frozenset({"api_key", "auth_token", "permission_mode"})

_PROJECT_DIR = ".questor"
_SHARED_LAYER = "config.toml"
_LOCAL_LAYER = "config.local.toml"

# 一次性去重警告的登记表：(层文件绝对路径小写, 字段路径) —— 同一处只警告一次
_warned: set[tuple[str, str]] = set()


class ConfigError(Exception):
    """配置不可用（TOML 解析失败等）——修复前不得用于执行（overview §10）。"""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"配置文件不可解析：{path}（{reason}）")


class ConfigSnapshot(BaseModel):
    """分层合并后的配置快照（frozen；``data`` 为用户 TOML 的合并结果）。"""

    model_config = ConfigDict(frozen=True)

    data: dict[str, Any]
    layers_applied: tuple[str, ...]
    stripped: tuple[str, ...]


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(path, str(exc)) from exc


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """深合并：dict 递归，其余整体覆盖；返回新 dict，不改写任何输入。"""
    merged: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _strip_user_fields(
    overlay: dict[str, Any], layer_path: Path, prefix: str = ""
) -> tuple[dict[str, Any], list[str]]:
    """递归删除 USER_ONLY_FIELDS（大小写不敏感全拼写），返回新 dict 与被删路径。"""
    stripped: list[str] = []
    result: dict[str, Any] = {}
    for key, value in overlay.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(key, str) and key.lower() in USER_ONLY_FIELDS:
            stripped.append(path)
            message = f"项目配置层 {layer_path} 的 {path} 是用户专属字段，已忽略"
            mark = (str(layer_path).lower(), path)
            if mark not in _warned:
                _warned.add(mark)
                logger.warning(message)
            continue
        if isinstance(value, dict):
            child, child_stripped = _strip_user_fields(value, layer_path, prefix=path)
            stripped.extend(child_stripped)
            result[key] = child
        else:
            result[key] = value
    return result, stripped


def load_config(project_root: Path | None = None) -> ConfigSnapshot:
    """加载并合并配置层：用户 base → 项目共享 → 项目本地（后者覆盖前者）。

    ``project_root`` 为 ``None`` 时只读用户层。任何一层缺失即跳过（配置稀疏合法）；
    解析失败抛 :class:`ConfigError`。返回的快照不可变。
    """
    layers: list[tuple[str, Path]] = [("user", config_path())]
    if project_root is not None:
        project_dir = project_root / _PROJECT_DIR
        layers.append(("project-shared", project_dir / _SHARED_LAYER))
        layers.append(("project-local", project_dir / _LOCAL_LAYER))

    data: dict[str, Any] = {}
    applied: list[str] = []
    stripped_all: list[str] = []
    for name, path in layers:
        raw = _read_toml(path)
        if not raw:
            continue
        applied.append(name)
        if name == "user":
            data = _deep_merge(data, raw)
        else:
            clean, stripped = _strip_user_fields(raw, path)
            stripped_all.extend(f"{name}:{s}" for s in stripped)
            data = _deep_merge(data, clean)
    return ConfigSnapshot(data=data, layers_applied=tuple(applied), stripped=tuple(stripped_all))
