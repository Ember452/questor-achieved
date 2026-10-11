"""凭据存取：keyring 优先、文件回落、SecretStr 出入（红线 ①）。

语义参照 wuu@wuu-main internal/credentialstore（OS 凭据库优先、文件存储是明示的
退路而不是平等后端）。keyring 后端的失败形态不可枚举，一律捕获 Exception 回落。
"""

from __future__ import annotations

import logging
from pathlib import Path

import keyring
from pydantic import SecretStr

from questor.state.atomic import write_atomic
from questor.state.paths import questor_home, validate_filename_component

logger = logging.getLogger(__name__)

SERVICE_NAME = "questor"
_SECRETS_DIR = "secrets"

# keyring 不可用的告警只发一次（进程生命周期内）
_fallback_warned = False


def _secrets_dir() -> Path:
    return questor_home() / _SECRETS_DIR


def _warn_fallback() -> None:
    global _fallback_warned
    if not _fallback_warned:
        _fallback_warned = True
        logger.warning(
            "OS keyring 不可用，凭据回落为 %s 下的明文文件（0600）。"
            "这不是加密存储，请尽快配置系统凭据库。",
            _SECRETS_DIR,
        )


def _validate_key(key: str) -> str:
    # 键名同时是回落文件名：统一走文件名组件校验（拒绝分隔符/冒号/点项）
    return validate_filename_component(key)


def set_secret(key: str, value: str) -> None:
    """写入凭据；keyring 失败时回落文件并告警。"""
    safe_key = _validate_key(key)
    try:
        keyring.set_password(SERVICE_NAME, safe_key, value)
    except Exception as exc:
        _warn_fallback()
        logger.debug("keyring set 失败（%s），回落文件存储", exc)
        write_atomic(_secrets_dir() / safe_key, value.encode("utf-8"))


def get_secret(key: str) -> SecretStr | None:
    """读取凭据；不存在返回 ``None``。值以 :class:`~pydantic.SecretStr` 遮蔽。"""
    safe_key = _validate_key(key)
    found: str | None = None
    try:
        found = keyring.get_password(SERVICE_NAME, safe_key)
    except Exception as exc:
        _warn_fallback()
        logger.debug("keyring get 失败（%s），回落文件存储", exc)
    if found is not None:
        return SecretStr(found)
    path = _secrets_dir() / safe_key
    if path.is_file():
        return SecretStr(path.read_text(encoding="utf-8"))
    return None


def delete_secret(key: str) -> bool:
    """删除凭据；返回是否存在过。keyring 与文件两处都清。"""
    safe_key = _validate_key(key)
    existed = False
    try:
        keyring.delete_password(SERVICE_NAME, safe_key)
        existed = True
    except Exception as exc:
        logger.debug("keyring delete 未命中（%s）", exc)
    path = _secrets_dir() / safe_key
    if path.is_file():
        path.unlink()
        existed = True
    return existed
